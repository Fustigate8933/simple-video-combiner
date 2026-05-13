from __future__ import annotations

import shlex
import subprocess
import tempfile
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import video_combiner

from backend.app.models import JobStatusResponse, MergeOptions


class JobBusyError(RuntimeError):
    pass


class JobNotFoundError(KeyError):
    pass


class JobCancelledError(RuntimeError):
    pass


def run_command(
    command: list[str],
    logs: list[str],
    stop_event: threading.Event,
    working_dir: Path | None = None,
) -> None:
    logs.append(f"Running {shlex.join(command)}")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(working_dir) if working_dir else None,
    )
    assert process.stdout is not None

    line_buffer: deque[str] = deque()

    def read_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            line = line.strip()
            if line:
                line_buffer.append(line)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()

    try:
        while process.poll() is None:
            while line_buffer:
                logs.append(line_buffer.popleft())
            if stop_event.is_set():
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise JobCancelledError("Job cancelled")
            time.sleep(0.05)

        while line_buffer:
            logs.append(line_buffer.popleft())
        return_code = process.wait()
    finally:
        reader.join(timeout=1)
        if process.stdout is not None:
            process.stdout.close()
        if process.poll() is None:
            process.kill()
            process.wait()

    if stop_event.is_set():
        raise JobCancelledError("Job cancelled")
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, command)


@dataclass
class MergeJob:
    job_id: str
    options: MergeOptions
    status: str = "pending"
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    updated_at: float = field(default_factory=time.time)
    temp_dir: Path | None = None


class JobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, MergeJob] = {}
        self.active_job_id: str | None = None
        self.lock = threading.Lock()

    def start(self, options: MergeOptions) -> MergeJob:
        with self.lock:
            if self.active_job_id is not None:
                raise JobBusyError("A merge job is already active")
            job = MergeJob(job_id=uuid.uuid4().hex, options=options)
            self.jobs[job.job_id] = job
            self.active_job_id = job.job_id

        worker = threading.Thread(target=self._run, args=(job.job_id,), daemon=True)
        worker.start()
        worker.join(0.05)
        return job

    def _run(self, job_id: str) -> None:
        job = self.jobs[job_id]
        try:
            job.status = "running"
            job.updated_at = time.time()
            job.options.output_file.parent.mkdir(parents=True, exist_ok=True)
            job.temp_dir = Path(tempfile.mkdtemp(prefix="kiwi-merge-api-"))
            prepared = video_combiner.prepare_merge(
                input_dir=job.options.source_dir,
                output=job.options.output_file,
                music_dir=job.options.music_dir,
                temp_dir=job.temp_dir,
                original_volume=job.options.original_volume,
                music_volume=job.options.music_volume,
                photo_duration=job.options.photo_duration,
            )
            job.logs.extend(prepared.messages)
            run_command(prepared.command, job.logs, job.stop_event, prepared.working_dir)
            if job.stop_event.is_set():
                job.status = "cancelled"
                job.error = "Job cancelled"
            else:
                job.status = "succeeded"
        except JobCancelledError as exc:
            job.status = "cancelled"
            job.error = str(exc)
            job.logs.append(str(exc))
        except (ValueError, FileNotFoundError, subprocess.CalledProcessError) as exc:
            job.status = "failed"
            job.error = str(exc)
            job.logs.append(str(exc))
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.logs.append(str(exc))
        finally:
            job.updated_at = time.time()
            with self.lock:
                if self.active_job_id == job_id:
                    self.active_job_id = None

    def get(self, job_id: str) -> MergeJob:
        try:
            return self.jobs[job_id]
        except KeyError as exc:
            raise JobNotFoundError(job_id) from exc

    def cancel(self, job_id: str) -> MergeJob:
        job = self.get(job_id)
        if job.status in {"succeeded", "failed", "cancelled"}:
            return job
        job.stop_event.set()
        job.updated_at = time.time()
        return job

    def response(self, job_id: str) -> JobStatusResponse:
        job = self.get(job_id)
        return JobStatusResponse(
            job_id=job.job_id,
            status=job.status,
            logs=list(job.logs),
            error=job.error,
        )

    def sse_lines(self, job_id: str):
        last_index = 0
        last_status: str | None = None

        while True:
            current = self.get(job_id)
            for line in current.logs[last_index:]:
                yield f"event: log\ndata: {line}\n\n"
            last_index = len(current.logs)

            if current.status != last_status:
                yield f"event: status\ndata: {current.status}\n\n"
                last_status = current.status

            if current.status in {"succeeded", "failed", "cancelled"}:
                return

            time.sleep(0.1)


job_manager = JobManager()
