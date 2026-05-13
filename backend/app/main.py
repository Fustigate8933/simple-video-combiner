import subprocess

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.app.jobs import JobBusyError, JobNotFoundError, job_manager
from backend.app.models import (
    DryRunResponse,
    HealthResponse,
    JobCreateResponse,
    JobStatusResponse,
    MergeOptions,
    ScanRequest,
    ScanResponse,
)
from backend.app.services import build_dry_run, scan_paths


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True)


@app.post("/scan", response_model=ScanResponse)
def scan(request: ScanRequest) -> ScanResponse:
    try:
        return scan_paths(request.source_dir, request.music_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/dry-run", response_model=DryRunResponse)
def dry_run(options: MergeOptions) -> DryRunResponse:
    try:
        return build_dry_run(options)
    except (ValueError, subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/jobs", response_model=JobCreateResponse)
def create_job(options: MergeOptions) -> JobCreateResponse:
    try:
        job = job_manager.start(options)
    except JobBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JobCreateResponse(job_id=job.job_id)


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> JobStatusResponse:
    try:
        return job_manager.response(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@app.get("/jobs/{job_id}/events")
def job_events(job_id: str) -> StreamingResponse:
    try:
        job_manager.get(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    return StreamingResponse(
        job_manager.sse_lines(job_id),
        media_type="text/event-stream",
    )


@app.post("/jobs/{job_id}/cancel", response_model=JobStatusResponse)
def cancel_job(job_id: str) -> JobStatusResponse:
    try:
        job_manager.cancel(job_id)
        return job_manager.response(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
