# Hakobu (運ぶ)

**Carry your files anywhere.** Hakobu is a universal file converter: drop in any file, and it
detects what the file *really* is from its bytes (not its name), shows only the formats it can
become, converts it with live progress, and hands back a download — one file at a time or a
whole batch as a ZIP.

![Hakobu converting a batch of files](docs/screenshot.png)

- **~50 formats, 800+ conversion paths**: images, documents, spreadsheets & data, presentations,
  audio, video, e-books and archives. Missing direct paths are bridged automatically
  (e.g. PPTX → PDF → PNG).
- **Fast by default**: stream copy when only the container changes, a warm LibreOffice pool,
  hardware H.264 when available, result caching, and a worker pool sized to your CPUs.
- **Forest green & beige**: a calm palette in light and dark mode, every text pair WCAG AA.
- **Built to be safe**: content-based validation, sandboxed conversions with timeouts and memory
  caps, no `shell=True`, macros disabled, archive-bomb and zip-slip guards, and every file deleted
  after an hour.

---

## Quick start

```bash
docker compose up --build
```

Then open <http://localhost:3000>. The API listens on <http://localhost:8000> (OpenAPI docs at
`/docs`).

`docker compose up` starts four services:

| Service    | What it runs                                                                  |
|------------|-------------------------------------------------------------------------------|
| `redis`    | Job queue, job/file records and progress pub/sub (in-memory only)             |
| `api`      | FastAPI (async) — uploads, job dispatch, SSE progress, streamed downloads     |
| `worker`   | RQ worker pool (one worker per CPU) + warm LibreOffice instances (unoserver)  |
| `frontend` | Next.js production server                                                     |

The API and worker share a `data` volume for uploads and outputs.

### Local development (without Docker)

You need Python 3.11+, Node 22+, Redis, and the conversion tools on your `PATH` (FFmpeg,
LibreOffice, Pandoc, Calibre, Ghostscript and libvips). Missing tools simply disable the engines
that need them — `GET /api/health` lists what was found.

```bash
# backend
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
redis-server --daemonize yes
python -m workers.run &                      # worker pool
uvicorn app.main:app --reload --port 8000    # API
```

```bash
# frontend (in another terminal)
cd frontend
npm install
npm run dev                                  # http://localhost:3000
```

Set `HAKOBU_SYNC_JOBS=1` to run conversions inside the API process with no worker at all
(handy for quick experiments; this is what the tests use).

---

## Supported conversions

Direct conversions are done by one engine. Multi-step chains are found automatically with a BFS
over the format graph, which is built once at startup.

| Category | Format | Direct targets | Via a chain | Engine(s) |
|---|---|---|---|---|
| Image | PNG, JPEG, WebP, GIF, BMP, TIFF | each other, AVIF, HEIC, ICO, PDF | — | pyvips (Pillow fallback), PyMuPDF |
| Image | HEIC/HEIF, AVIF, ICO, SVG | PNG, JPEG, WebP, GIF, AVIF, HEIC, TIFF, BMP, ICO | PDF | pyvips/Pillow, pillow-heif, cairosvg |
| Image | GIF (animated) | + MP4, MOV, WebM, MKV | AVI | FFmpeg |
| Document | DOCX, DOC, ODT, RTF, TXT, HTML | PDF, DOCX, DOC, ODT, RTF, TXT (+ MD, HTML, EPUB from DOCX/ODT/HTML) | PNG/JPG/WebP pages, MOBI, AZW3 | LibreOffice, Pandoc |
| Document | Markdown | DOCX, HTML, ODT, RTF, TXT, EPUB | PDF, DOC, MOBI, AZW3, page images | Pandoc (→ LibreOffice) |
| Document | PDF | DOCX, TXT, PNG/JPG/WebP (one per page), EPUB, MOBI, AZW3 | MD, HTML, ODT, RTF, DOC | pdf2docx, PyMuPDF, Calibre |
| PDF tools | PDF (+ images) | merge, split, compress | — | PyMuPDF, Ghostscript |
| Spreadsheet | XLSX, XLS, ODS, CSV | each other, PDF, TSV, JSON, XML, YAML | page images | LibreOffice Calc, data engine |
| Data | CSV, TSV, JSON, XML, YAML | each other, XLSX | ODS, XLS, PDF | data engine (streaming) |
| Presentation | PPTX, PPT, ODP | each other, PDF | PNG/JPG/WebP (one per slide) | LibreOffice Impress |
| Audio | MP3, WAV, AAC, M4A, OGG, FLAC, Opus | each other | — | FFmpeg |
| Video | MP4, MOV, MKV, WebM, AVI | each other, GIF, any audio format (extraction) | a still frame as an image or PDF | FFmpeg |
| E-book | EPUB, MOBI, AZW3 | each other, PDF, DOCX, TXT, RTF | MD, HTML, ODT, DOC, page images | Calibre |
| Archive | ZIP, TAR, TAR.GZ, 7z | each other | — | zipfile, tarfile, py7zr |

The live, exact matrix is served by `GET /api/formats`.

**Options** (all optional, validated server-side): `width`/`height` (resize, keeping the aspect
ratio), `quality` (1–100), `strip_metadata`, `dpi` (PDF rendering), `bitrate` (e.g. `192k`),
`sample_rate`, `trim_start`/`trim_end` (seconds), `pdf_compress`, `pdf_split`.

**Notes**
- A same-format request returns the original file untouched, unless options ask for real work
  (resizing a PNG, compressing a PDF, trimming audio…).
- Multi-output conversions (PDF/slides → images, PDF split) download as a ZIP.
- Workbook → CSV/JSON/… uses the first sheet.
- Chains are kept sensible: layout reconstruction (PDF → DOCX/e-book) only runs on real PDFs, and
  audio is never "extracted" from a GIF that was turned into a video.

---

## API

| Method & path | Purpose |
|---|---|
| `POST /api/upload` | Streamed (optionally chunked, resumable) upload → `file_id`, detected format, size, allowed targets |
| `POST /api/convert` | `{file_id, target_format, options}` → `job_id` |
| `POST /api/merge` | `{file_ids: [...]}` (PDFs and/or images) → one-PDF `job_id` |
| `GET /api/jobs/{job_id}` | Status, progress %, error |
| `GET /api/jobs/{job_id}/events` | Server-Sent Events stream of live progress |
| `GET /api/download/{job_id}` | Streamed file (a ZIP for multi-output jobs) |
| `GET /api/download/batch?job_ids=…&job_ids=…` | All listed outputs as one streamed ZIP |
| `GET /api/formats` | Full conversion matrix (`ETag`, `Cache-Control`, gzip) |
| `GET /api/health` | Redis status and which conversion tools are installed |

Every error has the same shape and a machine-readable code the UI maps to a specific state:

```json
{ "error": { "code": "too_large", "message": "Files can be at most 200 MB.", "limit_mb": 200 } }
```

Codes: `unsupported_format`, `unsupported_conversion`, `too_large`, `corrupted`, `failed`,
`not_found`, `not_ready`, `upload_conflict`, `rate_limited`, `invalid_request`.

### Upload protocol

The body is the raw bytes (no multipart parsing, nothing buffered in memory).

- `X-File-Name`: the URL-encoded original filename (required).
- Small files: send everything in one request.
- Large files: send sequential chunks with `Content-Range: bytes <start>-<end>/<total>`. The first
  chunk returns `202 {"upload_id", "received"}`; send `X-Upload-Id` on the following chunks. If a
  chunk doesn't start where the server's copy ends, you get `409` with `received`, so the client
  can resume from that offset. The last chunk returns the normal upload response.

```bash
curl -X POST localhost:8000/api/upload -H "X-File-Name: report.docx" --data-binary @report.docx
curl -X POST localhost:8000/api/convert -H "Content-Type: application/json" \
     -d '{"file_id": "<id>", "target_format": "pdf"}'
curl -N localhost:8000/api/jobs/<job_id>/events
curl -OJ localhost:8000/api/download/<job_id>
```

---

## Architecture

```
browser ──XHR chunks──▶ api (FastAPI) ──detect (first 64 KB)──▶ storage (uploads/)
   ▲                      │  └─ registry: (src → dst) shortest chain, built once
   │ SSE progress         ▼
   └──── redis pub/sub ◀── worker pool (RQ, 1 per CPU) ──▶ engines ──▶ storage (outputs/)
                                     └─ warm LibreOffice (unoserver × N)
```

```
backend/
  app/            FastAPI app: api/ routers, config, detection, storage, store (Redis), models
  engines/        one module per engine + base.py (interface, options, guarded subprocess)
  registry.py     format graph, BFS chains, target ordering
  workers/        RQ task (run.py starts the pool + unoserver; tasks.py runs a job)
  tests/          pytest: one file per engine, plus detection, registry, storage and end-to-end API
frontend/
  app/            Next.js App Router (layout, page, global styles)
  components/
    reactbits/    React Bits components, installed with the CLI
    ui/           shadcn/ui primitives (select, dialog, toast, button)
    app/          Hakobu's own components
  lib/            API client, converter state (useConverter), theme, hooks, types
```

Jobs live in Redis as JSON records that expire after the file TTL. Workers publish every
(throttled) progress change on a per-job channel, and the SSE endpoint subscribes *before*
reading the snapshot, so no update can slip in between.

---

## Adding an engine

1. Create `backend/engines/myengine.py` and implement the common interface:

```python
import shutil
from pathlib import Path

from engines.base import ConversionOptions, Engine, Pair, ProgressFn, formats_of, pairs, run_subprocess


class MyEngine(Engine):
    name = "my-tool"

    def supported_pairs(self) -> frozenset[Pair]:
        return pairs(("foo",), ("bar", "baz"))  # every (src, dst) this engine does directly

    def available(self) -> bool:                # optional: skip when the tool is missing
        return shutil.which("my-tool") is not None

    def convert(self, input_path: Path, output_path: Path, options: ConversionOptions,
                progress: ProgressFn | None = None) -> list[Path]:
        src, dst = formats_of(input_path, output_path)   # from the canonical extensions
        run_subprocess(["my-tool", input_path, "-o", output_path])  # timeout + memory cap built in
        return [output_path]
```

2. If the formats are new, add them to `app/formats.py` and teach `app/detection.py` their
   signature.
3. Register an instance in `engines/__init__.py`. List order is priority order when two engines
   offer the same pair.
4. Add `tests/test_engine_myengine.py`. The `samples` fixture builds real input files, and
   `convert()` / `detected()` check that the output really is the target format.

Optional hooks: `terminal_pairs` (multi-output steps, which may only end a chain),
`entry_only_pairs` (steps that only make sense on the original upload) and `transforms` (formats
the engine can re-process in place, such as resize or compress).

---

## Configuration

Backend settings are environment variables (also read from `backend/.env`):

| Variable | Default | Meaning |
|---|---|---|
| `HAKOBU_DATA_DIR` | `/tmp/hakobu` (`/data` in Docker) | Where uploads and outputs are stored |
| `HAKOBU_MAX_UPLOAD_MB` | `200` | Maximum size per file |
| `HAKOBU_FILE_TTL_SECONDS` | `3600` | Files, jobs and cache entries are deleted after this |
| `HAKOBU_CLEANUP_INTERVAL_SECONDS` | `300` | How often the cleanup sweeper runs |
| `HAKOBU_REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `HAKOBU_QUEUE_NAME` | `conversions` | RQ queue name |
| `HAKOBU_WORKER_CONCURRENCY` | CPU count | Workers in the pool |
| `HAKOBU_JOB_TIMEOUT_SECONDS` | `900` | Hard limit per job |
| `HAKOBU_SUBPROCESS_TIMEOUT_SECONDS` | `600` | Limit per external tool call |
| `HAKOBU_SUBPROCESS_MEMORY_MB` | `4096` | Memory cap (`RLIMIT_DATA`) for tools and work horses |
| `HAKOBU_UNOSERVER_INSTANCES` | `0` locally, `2` in Compose | Warm LibreOffice instances (`0` = one-shot `soffice`) |
| `HAKOBU_UNOSERVER_BASE_PORT` | `2003` | First unoserver port |
| `HAKOBU_FFMPEG_HWACCEL` | `auto` | `auto` probes NVENC/QSV/VAAPI once; `off` forces libx264 |
| `HAKOBU_MAX_ARCHIVE_EXPANDED_MB` | `2048` | Archive-bomb guard (total expanded size) |
| `HAKOBU_MAX_ARCHIVE_ENTRIES` | `10000` | Archive-bomb guard (entry count) |
| `HAKOBU_RATE_LIMIT_PER_MINUTE` | `120` | Uploads + conversions per IP per minute (`0` disables) |
| `HAKOBU_CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed browser origins (JSON list) |
| `HAKOBU_SYNC_JOBS` | `false` | Run jobs inside the API process (no worker) |

Frontend: `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). It is baked in at build time
and passed as a build arg in `docker-compose.yml`.

**GPU encoding**: to let the worker use NVENC, expose the GPU to the `worker` service (for example
`deploy.resources.reservations.devices` with the NVIDIA runtime, or `/dev/dri` for VAAPI).
Detection is automatic.

---

## React Bits components

Each component was installed individually with the CLI (TypeScript + Tailwind variant) into
`frontend/components/reactbits/`, for example:

```bash
npx shadcn@latest add https://reactbits.dev/r/BlurText-TS-TW
```

| Component | Used for | Loading |
|---|---|---|
| **Aurora** | Hero background | Lazy (`next/dynamic`, `ssr: false`), mounted after idle, desktop only, never with reduced motion; pauses itself off-screen |
| **BlurText** | Headline "Hakobu — carry your files" | Lazy; the server renders a static `<h1>` first |
| **ShinyText** | The "anywhere" accent | Lazy |
| **SpotlightCard** | Drag-and-drop upload zone | Eager (no dependencies, above the fold) |
| **ClickSpark** | Feedback on the "Choose files" button | Eager (tiny canvas) |
| **AnimatedList** | File queue (≤ 50 files; virtualised beyond that) | Lazy, with the rest of the queue UI |
| **Stepper** | Upload → Choose format → Convert → Download | Lazy |
| **CountUp** | "N files converted, X MB saved" | Lazy |

`AnimatedList` has one small local addition, an `interactiveItems` prop. File cards contain their
own buttons and selects, so the list renders `list`/`listitem` semantics instead of a selectable
`listbox`/`option`. The vendored sources are otherwise unchanged and excluded from ESLint.

shadcn/ui is used only for primitives React Bits doesn't cover: **Select** (grouped target
formats), **Dialog** (advanced options), **Sonner** toasts and **Button**.

---

## Performance

Measured on the production build:

- **Initial JS: ~166 KB gzipped** (target < 200 KB). The file queue, Radix primitives, toasts and
  every animated component are separate lazy chunks.
- **Lighthouse: Performance 99 (mobile) / 100 (desktop)**, Accessibility 100, Best Practices 100,
  SEO 100.

Backend:
- Uploads and downloads stream in 1 MB chunks, and archives are converted entry by entry. Batch
  ZIPs are generated on the fly, without temp files.
- Detection reads only the first 64 KB. OLE2 files (DOC/XLS/PPT) also read their 2 KB directory
  sector.
- CPU work runs in an RQ worker pool (one per core), never on the request thread. LibreOffice
  stays warm through `unoserver` and is recycled every 250 conversions.
- No unnecessary work:
  - same-format requests return the original,
  - container-only video changes use `-c copy`,
  - results are cached by `sha256(file) + target + options`,
  - the format graph and `/api/formats` payload (with its gzip version and ETag) are built once.
- Every subprocess has a timeout and a memory cap, as does each forked work horse. Temp
  directories are always removed in `finally`.

Frontend: React Bits loaded via `next/dynamic` with `ssr: false`, at most one animated background,
memoised file cards, list virtualisation above 50 files, uploads in chunks (3 files in parallel),
and the format matrix fetched once with SWR (plus HTTP caching/ETag).

---

## Security & limits

- The real type comes from the content (magic bytes plus python-magic). Executables and unknown
  types are rejected, whatever their extension.
- The size limit is enforced while streaming. Requests are rate-limited per IP.
- External tools are never run through a shell, always get argument lists, and run in their own
  process group with a timeout and a memory limit.
- LibreOffice profiles are created with macro execution disabled. Ghostscript runs with
  `-dSAFER`.
- Pandoc runs a filter that strips non-embedded images and raw passthrough, so a document can't
  pull in local files or URLs. Text writers also use `--sandbox`.
- XML is parsed without entity expansion, DTDs or network access, and YAML only with `safe_load`.
- Archive entries are sanitised (no absolute paths or `..`), links and devices are skipped, and the
  expanded size and entry count are capped.
- Filenames are sanitised, and IDs are validated before they touch storage keys.
- All files expire after one hour. Redis records expire with them, and a sweeper deletes what's on
  disk. File contents are never logged.

---

## Tests

```bash
cd backend
pytest              # 217 tests, ~25 s with every tool installed
ruff check .
```

```bash
cd frontend
npx tsc --noEmit && npm run lint && npm run build
```

The suite covers each engine against real generated files, detection of every format, registry
invariants (shortest chains, no terminal or entry-only steps mid-chain), storage and cleanup, and
end-to-end HTTP flows:
- upload → convert → download, including SSE progress,
- chunked and resumed uploads,
- the result cache, batch ZIP and merge,
- error states and rate limiting.

Tests needing a missing external tool are skipped, not failed.
