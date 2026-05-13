from pathlib import Path

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    ok: bool


class ScanRequest(BaseModel):
    source_dir: Path
    music_dir: Path


class ScanResponse(BaseModel):
    mp4_count: int
    image_count: int
    music_count: int


class MergeOptions(BaseModel):
    source_dir: Path
    output_file: Path
    music_dir: Path
    photo_duration: float = Field(default=7.0, gt=0)
    original_volume: float = Field(default=0.2, ge=0)
    music_volume: float = Field(default=0.85, ge=0)


class DryRunResponse(BaseModel):
    command: list[str]
    command_text: str
    messages: list[str]
    summary: ScanResponse


class JobCreateResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    logs: list[str]
    error: str | None = None
