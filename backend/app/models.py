"""Pydantic models for API payloads and the records kept in Redis."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.formats import FORMATS, Category
from engines.base import ConversionOptions


class HealthResponse(BaseModel):
    status: str
    redis: bool
    tools: dict[str, bool]


class FormatInfo(BaseModel):
    id: str
    label: str
    category: Category
    extension: str

    @classmethod
    def of(cls, fmt: str) -> FormatInfo:
        f = FORMATS[fmt]
        return cls(id=f.id, label=f.label, category=f.category, extension=f.extension)


class TargetInfo(BaseModel):
    format: str
    label: str
    category: Category
    steps: int = Field(description="Number of conversion steps (1 = direct)")


class FormatsResponse(BaseModel):
    formats: list[FormatInfo]
    conversions: dict[str, list[TargetInfo]]
    max_upload_mb: int


class FileRecord(BaseModel):
    id: str
    name: str
    format: str
    mime: str
    size: int
    sha256: str
    key: str


class UploadResponse(BaseModel):
    file_id: str
    name: str
    format: FormatInfo
    mime: str
    size: int
    targets: list[TargetInfo]


class UploadProgress(BaseModel):
    """Returned (HTTP 202) for each chunk of a multi-chunk upload except the last."""

    upload_id: str
    received: int


class ConvertRequest(BaseModel):
    file_id: str
    target_format: str
    options: ConversionOptions = Field(default_factory=ConversionOptions)


class MergeRequest(BaseModel):
    """Combine several PDFs and/or images into one PDF, in the given order."""

    file_ids: list[str] = Field(min_length=2, max_length=100)


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class JobRecord(BaseModel):
    id: str
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    error_code: str | None = None
    error: str | None = None
    file_ids: list[str]
    target: str
    options: ConversionOptions = Field(default_factory=ConversionOptions)
    cache_key: str | None = None
    output_key: str | None = None
    output_name: str | None = None
    output_size: int | None = None
    output_count: int = 0

    @property
    def finished(self) -> bool:
        return self.status in (JobStatus.DONE, JobStatus.FAILED)


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: float
    error_code: str | None = None
    error: str | None = None
    output_name: str | None = None
    output_size: int | None = None
    output_count: int = 0

    @classmethod
    def of(cls, job: JobRecord) -> JobResponse:
        return cls(
            job_id=job.id,
            status=job.status,
            progress=round(job.progress, 1),
            error_code=job.error_code,
            error=job.error,
            output_name=job.output_name,
            output_size=job.output_size,
            output_count=job.output_count,
        )
