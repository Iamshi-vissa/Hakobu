import type {
  ApiErrorBody,
  ConversionOptions,
  ErrorCode,
  FormatsResponse,
  JobResponse,
  UploadResponse,
} from "@/lib/types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

/** Files up to this size go in one request; larger ones are uploaded in chunks of this size. */
export const CHUNK_SIZE = 8 * 1024 * 1024;
const MAX_CHUNK_RETRIES = 3;

export class ApiError extends Error {
  constructor(
    readonly code: ErrorCode,
    message: string,
    readonly status = 0,
    readonly received?: number,
  ) {
    super(message);
  }
}

function toApiError(status: number, body: unknown): ApiError {
  const err = (body as Partial<ApiErrorBody> | null)?.error;
  if (err?.code) return new ApiError(err.code, err.message, status, err.received);
  return new ApiError("failed", `Request failed (${status}).`, status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError("network", "Can't reach Hakobu's server. Check your connection and try again.");
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw toApiError(response.status, body);
  return body as T;
}

function postJson<T>(path: string, payload: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export const fetchFormats = (): Promise<FormatsResponse> => request<FormatsResponse>("/api/formats");

export const startConversion = (fileId: string, target: string, options: ConversionOptions) =>
  postJson<JobResponse>("/api/convert", { file_id: fileId, target_format: target, options });

export const startMerge = (fileIds: string[]) => postJson<JobResponse>("/api/merge", { file_ids: fileIds });

export const getJob = (jobId: string) => request<JobResponse>(`/api/jobs/${encodeURIComponent(jobId)}`);

export const downloadUrl = (jobId: string) => `${API_URL}/api/download/${encodeURIComponent(jobId)}`;

export const batchDownloadUrl = (jobIds: string[]) =>
  `${API_URL}/api/download/batch?${jobIds.map((id) => `job_ids=${encodeURIComponent(id)}`).join("&")}`;

// ---------- Uploads ----------

interface ChunkResult {
  status: number;
  body: unknown;
}

function sendChunk(
  blob: Blob,
  headers: Record<string, string>,
  onProgress: (loaded: number) => void,
  signal?: AbortSignal,
): Promise<ChunkResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/api/upload`);
    for (const [name, value] of Object.entries(headers)) xhr.setRequestHeader(name, value);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.responseType = "json";
    xhr.upload.onprogress = (event) => onProgress(event.loaded);
    xhr.onload = () => resolve({ status: xhr.status, body: xhr.response });
    xhr.onerror = () => reject(new ApiError("network", "Upload interrupted."));
    xhr.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"));
    signal?.addEventListener("abort", () => xhr.abort(), { once: true });
    xhr.send(blob);
  });
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Upload a file, in sequential chunks when it's larger than {@link CHUNK_SIZE}.
 * Interrupted chunks are retried with backoff and resumed from the server's offset.
 */
export async function uploadFile(
  file: File,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<UploadResponse> {
  const total = file.size;
  const chunked = total > CHUNK_SIZE;
  const baseHeaders = { "X-File-Name": encodeURIComponent(file.name) };
  let offset = 0;
  let uploadId: string | undefined;
  let retries = 0;

  for (;;) {
    const end = chunked ? Math.min(offset + CHUNK_SIZE, total) : total;
    const headers: Record<string, string> = { ...baseHeaders };
    if (chunked) headers["Content-Range"] = `bytes ${offset}-${end - 1}/${total}`;
    if (uploadId) headers["X-Upload-Id"] = uploadId;

    let result: ChunkResult;
    try {
      result = await sendChunk(file.slice(offset, end), headers, (loaded) => onProgress((offset + loaded) / total), signal);
    } catch (error) {
      if (error instanceof ApiError && error.code === "network" && retries < MAX_CHUNK_RETRIES) {
        retries += 1;
        await wait(500 * 2 ** retries);
        continue;
      }
      throw error;
    }

    if (result.status === 200) {
      onProgress(1);
      return result.body as UploadResponse;
    }
    if (result.status === 202) {
      const progress = result.body as { upload_id: string; received: number };
      uploadId = progress.upload_id;
      offset = progress.received;
      retries = 0;
      continue;
    }
    const error = toApiError(result.status, result.body);
    if (error.code === "upload_conflict" && uploadId && error.received !== undefined && retries < MAX_CHUNK_RETRIES) {
      retries += 1;
      offset = error.received; // resume from what the server actually has
      continue;
    }
    throw error;
  }
}

// ---------- Job progress ----------

const TERMINAL = new Set(["done", "failed"]);
const POLL_INTERVAL = 1000;

/** Follow a job via Server-Sent Events, falling back to polling. Returns an unsubscribe function. */
export function watchJob(jobId: string, onUpdate: (job: JobResponse) => void): () => void {
  let closed = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const source = new EventSource(`${API_URL}/api/jobs/${encodeURIComponent(jobId)}/events`);

  const deliver = (job: JobResponse) => {
    if (closed) return;
    onUpdate(job);
    if (TERMINAL.has(job.status)) stop();
  };

  const poll = async () => {
    if (closed) return;
    try {
      deliver(await getJob(jobId));
    } catch {
      /* transient — keep polling */
    }
    if (!closed) timer = setTimeout(poll, POLL_INTERVAL);
  };

  source.onmessage = (event: MessageEvent<string>) => deliver(JSON.parse(event.data) as JobResponse);
  source.onerror = () => {
    // The server closes the stream after the final event; otherwise fall back to polling.
    source.close();
    if (!closed) void poll();
  };

  function stop() {
    closed = true;
    source.close();
    clearTimeout(timer);
  }
  return stop;
}
