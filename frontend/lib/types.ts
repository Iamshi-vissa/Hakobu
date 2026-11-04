/** Types mirroring the backend's Pydantic models (backend/app/models.py). */

export type Category =
  | "image"
  | "document"
  | "spreadsheet"
  | "presentation"
  | "audio"
  | "video"
  | "ebook"
  | "archive";

export interface FormatInfo {
  id: string;
  label: string;
  category: Category;
  extension: string;
}

export interface TargetInfo {
  format: string;
  label: string;
  category: Category;
  /** 1 = direct conversion, >1 = multi-step chain. */
  steps: number;
}

export interface FormatsResponse {
  formats: FormatInfo[];
  conversions: Record<string, TargetInfo[]>;
  max_upload_mb: number;
}

export interface UploadResponse {
  file_id: string;
  name: string;
  format: FormatInfo;
  mime: string;
  size: number;
  targets: TargetInfo[];
}

export type JobStatus = "queued" | "running" | "done" | "failed";

export interface JobResponse {
  job_id: string;
  status: JobStatus;
  progress: number;
  error_code: string | null;
  error: string | null;
  output_name: string | null;
  output_size: number | null;
  output_count: number;
}

export interface ConversionOptions {
  width?: number;
  height?: number;
  quality?: number;
  strip_metadata?: boolean;
  dpi?: number;
  bitrate?: string;
  sample_rate?: number;
  trim_start?: number;
  trim_end?: number;
  pdf_compress?: boolean;
  pdf_split?: boolean;
}

export type ErrorCode =
  | "unsupported_format"
  | "unsupported_conversion"
  | "too_large"
  | "corrupted"
  | "failed"
  | "not_found"
  | "not_ready"
  | "upload_conflict"
  | "rate_limited"
  | "invalid_request"
  | "network";

export interface ApiErrorBody {
  error: { code: ErrorCode; message: string; received?: number; retry_after?: number };
}
