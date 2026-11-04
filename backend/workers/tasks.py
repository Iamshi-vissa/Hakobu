"""RQ task: execute one conversion job end to end."""

from __future__ import annotations

import logging
import resource
import shutil
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

from app.config import get_settings
from app.errors import ErrorCode
from app.formats import FORMATS
from app.models import FileRecord, JobRecord, JobStatus
from app.naming import stem_of
from app.storage import get_storage
from app.store import get_file_sync, get_job_sync, save_job_sync
from app.zipstream import write_zip
from engines.base import ConversionError, CorruptInputError, ProgressFn
from engines.pdf import merge_to_pdf
from registry import UnsupportedConversion, get_registry

log = logging.getLogger(__name__)

PROGRESS_INTERVAL = 0.25  # seconds between progress publications


class ProgressReporter:
    """Maps per-step progress onto the whole job and throttles Redis writes."""

    def __init__(self, job: JobRecord, steps: int) -> None:
        self.job, self.steps, self._last = job, max(steps, 1), 0.0

    def step(self, index: int) -> ProgressFn:
        def report(fraction: float) -> None:
            self.update((index + min(max(fraction, 0.0), 1.0)) / self.steps)

        return report

    def update(self, overall: float, force: bool = False) -> None:
        now = time.monotonic()
        percent = round(overall * 100, 1)
        if force or (now - self._last >= PROGRESS_INTERVAL and percent > self.job.progress):
            self.job.progress, self._last = percent, now
            save_job_sync(self.job)


def _limit_job_memory() -> None:
    """Cap the RQ work horse (forked per job) so in-process engines can't exhaust the host."""
    settings = get_settings()
    if settings.sync_jobs:
        return  # running inside the API process (tests/dev): don't cap the server itself
    limit = settings.subprocess_memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_DATA, (limit, limit))


def run_conversion(job_id: str) -> None:
    _limit_job_memory()
    job = get_job_sync(job_id)
    if job is None:
        return  # expired before a worker picked it up
    job.status, job.progress = JobStatus.RUNNING, 0.0
    save_job_sync(job)
    try:
        records = [get_file_sync(fid) for fid in job.file_ids]
        if any(r is None for r in records):
            raise ConversionError("The uploaded file has expired; please upload it again.")
        _run(job, [r for r in records if r is not None])
        job.status, job.progress = JobStatus.DONE, 100.0
    except CorruptInputError as exc:
        _fail(job, ErrorCode.CORRUPTED, str(exc))
    except (ConversionError, UnsupportedConversion) as exc:
        _fail(job, ErrorCode.FAILED, str(exc))
    except Exception:
        log.exception("job %s crashed", job_id)
        _fail(job, ErrorCode.FAILED, "Something went wrong while converting this file.")
    finally:
        save_job_sync(job)


def mark_failed(rq_job, connection, exc_type, exc_value, tb) -> None:
    """RQ on_failure callback (e.g. the work horse was killed by a timeout or OOM)."""
    job = get_job_sync(rq_job.id)
    if job is not None and not job.finished:
        _fail(job, ErrorCode.FAILED, "The conversion took too long or ran out of memory.")
        save_job_sync(job)


def _fail(job: JobRecord, code: ErrorCode, message: str) -> None:
    job.status, job.error_code, job.error = JobStatus.FAILED, code, message


def _run(job: JobRecord, records: list[FileRecord]) -> None:
    storage = get_storage()
    first = records[0]
    merging = len(records) > 1
    stem = "merged" if merging else stem_of(first.name)
    ext = FORMATS[job.target].extension

    steps = () if merging else get_registry().plan(first.format, job.target, job.options)
    if not merging and not steps:  # same format, nothing to do: hand back the original
        job.output_key, job.output_name = first.key, f"{stem}.{ext}"
        job.output_size, job.output_count = first.size, 1
        return

    reporter = ProgressReporter(job, len(steps) or 1)
    with tempfile.TemporaryDirectory(prefix="hakobu-") as tmp:
        workdir = Path(tmp)
        if merging:
            outputs = _merge(records, workdir / f"{stem}.pdf", reporter)
        else:
            with storage.local_path(first.key) as current:
                for index, step in enumerate(steps):
                    out_dir = workdir / f"step{index}"
                    out_dir.mkdir()
                    target_ext = FORMATS[step.dst].extension
                    outputs = step.engine.convert(
                        current, out_dir / f"{stem}.{target_ext}", job.options, progress=reporter.step(index)
                    )
                    reporter.update((index + 1) / len(steps))
                    current = outputs[0]
        _store_outputs(job, outputs, stem)


def _merge(records: list[FileRecord], out: Path, reporter: ProgressReporter) -> list[Path]:
    storage = get_storage()
    with ExitStack() as stack:
        paths = [stack.enter_context(storage.local_path(r.key)) for r in records]
        merge_to_pdf(paths, out, progress=reporter.step(0))
    return [out]


def _store_outputs(job: JobRecord, outputs: list[Path], stem: str) -> None:
    storage = get_storage()
    if not outputs or not all(p.exists() for p in outputs):
        raise ConversionError("The converter produced no output.")
    if len(outputs) == 1:
        produced, name = outputs[0], outputs[0].name
    else:
        name = f"{stem}.zip"
        produced = outputs[0].parent / f".bundle-{job.id}.zip"
        write_zip(((p.name, p) for p in outputs), produced)
    key = f"outputs/{job.id}/{name}"
    with storage.write_path(key) as dst:
        shutil.move(produced, dst)
    job.output_key, job.output_name = key, name
    job.output_size, job.output_count = storage.size(key), len(outputs)
