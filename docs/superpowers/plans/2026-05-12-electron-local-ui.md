# Electron Local UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Electron app with a Vue 3 + Tailwind UI and FastAPI backend for configuring, scanning, running, and monitoring the existing video combiner.

**Architecture:** Keep ffmpeg command construction in Python and expose it through a FastAPI API. Electron owns native dialogs and launches the backend; Vue renders the approved compact Kiwi control-panel UI and communicates with FastAPI over localhost.

**Tech Stack:** Python 3.10+, FastAPI, Uvicorn, pytest, Node/Vite, Vue 3, Tailwind CSS, Electron, TypeScript.

---

## File Structure

- `video_combiner.py`: keep CLI compatibility; add reusable scan/prepare helpers for the backend.
- `test_video_combiner.py`: extend existing unit tests for scan/prepare behavior and UTF-8 paths.
- `backend/requirements.txt`: Python backend runtime/test dependencies.
- `backend/app/__init__.py`: package marker.
- `backend/app/models.py`: Pydantic request/response models shared by API routes.
- `backend/app/services.py`: dependency checks, scan conversion, dry-run preparation.
- `backend/app/jobs.py`: one-at-a-time merge job manager, log buffering, cancellation, SSE events.
- `backend/app/main.py`: FastAPI route definitions.
- `backend/tests/test_api.py`: API and job-manager tests.
- `package.json`: Electron/Vite scripts and JavaScript dependencies.
- `index.html`, `vite.config.ts`, `tsconfig.json`, `tailwind.config.js`, `postcss.config.js`: frontend build configuration.
- `electron/main.cjs`: Electron main process, backend launcher, IPC dialog handlers.
- `electron/preload.cjs`: safe renderer bridge for file/directory dialogs.
- `src/main.ts`: Vue app bootstrap.
- `src/App.vue`: app shell and state orchestration.
- `src/components/*.vue`: focused UI components for path fields, options, stats, progress, logs, and buttons.
- `src/lib/api.ts`: typed FastAPI client and SSE helper.
- `src/styles.css`: Tailwind imports and Kiwi theme tokens.
- `README.md`: add desktop app development instructions and v1 prerequisites.

---

### Task 1: Extract Reusable Python Scan And Prepare Helpers

**Files:**
- Modify: `video_combiner.py`
- Modify: `test_video_combiner.py`

- [ ] **Step 1: Write failing tests for scan summary and prepared commands**

Add these tests to `test_video_combiner.py` after `test_finds_mp3_music_from_root_and_one_subdirectory_level`:

```python
    def test_scans_inputs_with_media_and_music_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "media"
            music = root / "music"
            media.mkdir()
            music.mkdir()

            (media / "clip.mp4").write_text("x")
            (media / "photo.jpg").write_text("x")
            (media / "notes.txt").write_text("x")
            (music / "01.mp3").write_text("x")

            summary = video_combiner.scan_inputs(media, music)

            self.assertEqual(summary.mp4_count, 1)
            self.assertEqual(summary.image_count, 1)
            self.assertEqual(summary.music_count, 1)

    def test_prepares_merge_command_without_running_ffmpeg(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "media"
            music = root / "music"
            media.mkdir()
            music.mkdir()
            video = media / "clip.mp4"
            track = music / "01.mp3"
            video.write_text("x")
            track.write_text("x")

            with (
                patch("video_combiner.has_audio_stream", return_value=False),
                patch("video_combiner.get_duration", return_value=5.0),
            ):
                prepared = video_combiner.prepare_merge(
                    input_dir=media,
                    output=root / "out.mp4",
                    music_dir=music,
                    temp_dir=root / "tmp",
                    original_volume=0.2,
                    music_volume=0.85,
                    photo_duration=7.0,
                )

            self.assertIn("Found 1 MP4 files", prepared.messages)
            self.assertIn("Found 1 soundtrack tracks", prepared.messages)
            self.assertIn("-filter_complex", prepared.command)
            self.assertEqual(prepared.summary.mp4_count, 1)
            self.assertEqual(prepared.summary.image_count, 0)
            self.assertEqual(prepared.summary.music_count, 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m unittest test_video_combiner.VideoCombinerTests.test_scans_inputs_with_media_and_music_counts test_video_combiner.VideoCombinerTests.test_prepares_merge_command_without_running_ffmpeg
```

Expected: FAIL with missing `scan_inputs` and `prepare_merge`.

- [ ] **Step 3: Add reusable dataclasses and helpers**

In `video_combiner.py`, add these dataclasses after `MediaItem`:

```python
@dataclass(frozen=True)
class ScanSummary:
    mp4_count: int
    image_count: int
    music_count: int


@dataclass(frozen=True)
class PreparedMerge:
    command: list[str]
    messages: list[str]
    summary: ScanSummary
```

Add these functions after `find_music`:

```python
def scan_inputs(input_dir: Path, music_dir: Path) -> ScanSummary:
    media_items = find_media(input_dir)
    tracks = find_music(music_dir)
    return ScanSummary(
        mp4_count=sum(1 for item in media_items if item.kind == "video"),
        image_count=sum(1 for item in media_items if item.kind == "photo"),
        music_count=len(tracks),
    )


def prepare_merge(
    *,
    input_dir: Path,
    output: Path,
    music_dir: Path,
    temp_dir: Path,
    original_volume: float,
    music_volume: float,
    photo_duration: float,
) -> PreparedMerge:
    messages: list[str] = []
    media_items = find_media(input_dir)
    videos = [item.path for item in media_items if item.kind == "video"]
    photos = [item.path for item in media_items if item.kind == "photo"]
    if not media_items:
        raise ValueError(f"No MP4, JPG, JPEG, or PNG files found in {input_dir}")

    messages.append(f"Found {len(videos)} MP4 files")
    if photos:
        messages.append(f"Found {len(photos)} photo files")

    audio_flags = [has_audio_stream(video) for video in videos]
    audio_count = sum(audio_flags)
    video_durations = [get_duration(video) for video in videos]
    if videos and audio_count == len(videos):
        messages.append("Original audio detected; mixing it under the soundtrack")
    elif audio_count:
        messages.append(
            f"{audio_count} of {len(videos)} videos have audio; "
            "inserting silence for clips without audio"
        )
    else:
        messages.append("No original audio detected; inserting silence under the soundtrack")

    media_audio_flags: list[bool] = []
    media_durations: list[float] = []
    video_index = 0
    for item in media_items:
        if item.kind == "video":
            media_audio_flags.append(audio_flags[video_index])
            media_durations.append(video_durations[video_index])
            video_index += 1
        else:
            media_audio_flags.append(False)
            media_durations.append(photo_duration)

    tracks = find_music(music_dir)
    if not tracks:
        raise ValueError(f"No MP3 files found in {music_dir} or its immediate subdirectories")
    messages.append(f"Found {len(tracks)} soundtrack tracks")

    temp_dir.mkdir(parents=True, exist_ok=True)
    music_list = temp_dir / "music.txt"
    video_list = temp_dir / "videos.txt"
    write_concat_list(tracks, music_list)
    if photos:
        messages.append("Rendering timeline because photos are present")
        command = build_rendered_ffmpeg_command(
            media_items=media_items,
            audio_flags=media_audio_flags,
            durations=media_durations,
            music_list=music_list,
            output=output,
            original_volume=original_volume,
            music_volume=music_volume,
        )
    else:
        messages.append("Writing concat lists")
        write_concat_list(videos, video_list)
        messages.append("Copying video stream without re-encoding")
        command = build_ffmpeg_command(
            video_list=video_list,
            videos=videos,
            audio_flags=audio_flags,
            durations=video_durations,
            music_list=music_list,
            output=output,
            original_volume=original_volume,
            music_volume=music_volume,
        )

    return PreparedMerge(
        command=command,
        messages=messages,
        summary=ScanSummary(
            mp4_count=len(videos),
            image_count=len(photos),
            music_count=len(tracks),
        ),
    )
```

- [ ] **Step 4: Refactor `merge_videos` to use `prepare_merge`**

Replace the body of `merge_videos` after `log_message` with:

```python
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="video-combiner-") as tmp:
        prepared = prepare_merge(
            input_dir=input_dir,
            output=output,
            music_dir=music_dir,
            temp_dir=Path(tmp),
            original_volume=original_volume,
            music_volume=music_volume,
            photo_duration=photo_duration,
        )
        for message in prepared.messages:
            log_message(message)
        if dry_run:
            print(shlex.join(prepared.command), file=log)
            return prepared.command

        log_message("Running ffmpeg")
        subprocess.run(prepared.command, check=True)
        log_message(f"Output: {output}")
        return prepared.command
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
python -m unittest test_video_combiner.VideoCombinerTests.test_scans_inputs_with_media_and_music_counts test_video_combiner.VideoCombinerTests.test_prepares_merge_command_without_running_ffmpeg test_video_combiner.VideoCombinerTests.test_merge_logs_progress_messages
```

Expected: OK.

- [ ] **Step 6: Run all Python tests**

Run:

```bash
python -m unittest
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add video_combiner.py test_video_combiner.py
git commit -m "refactor: expose merge preparation helpers"
```

---

### Task 2: Build FastAPI Scan And Dry-Run API

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/models.py`
- Create: `backend/app/services.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/test_api.py`

- [ ] **Step 1: Add backend dependencies**

Create `backend/requirements.txt`:

```text
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
pytest==8.3.4
httpx==0.28.1
```

- [ ] **Step 2: Create package marker**

Create `backend/app/__init__.py`:

```python
"""FastAPI backend for Kiwi Merge."""
```

- [ ] **Step 3: Write failing API tests**

Create `backend/tests/test_api.py`:

```python
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_health_reports_ready():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_scan_returns_media_counts(tmp_path: Path):
    source = tmp_path / "source"
    music = tmp_path / "music"
    source.mkdir()
    music.mkdir()
    (source / "clip.mp4").write_text("x")
    (source / "image.png").write_text("x")
    (music / "track.mp3").write_text("x")

    response = client.post(
        "/scan",
        json={"source_dir": str(source), "music_dir": str(music)},
    )

    assert response.status_code == 200
    assert response.json() == {"mp4_count": 1, "image_count": 1, "music_count": 1}


def test_dry_run_returns_command_and_summary(tmp_path: Path):
    source = tmp_path / "source"
    music = tmp_path / "music"
    source.mkdir()
    music.mkdir()
    (source / "clip.mp4").write_text("x")
    (music / "track.mp3").write_text("x")

    with (
        patch("video_combiner.has_audio_stream", return_value=False),
        patch("video_combiner.get_duration", return_value=3.0),
    ):
        response = client.post(
            "/dry-run",
            json={
                "source_dir": str(source),
                "output_file": str(tmp_path / "out.mp4"),
                "music_dir": str(music),
                "photo_duration": 7.0,
                "original_volume": 0.2,
                "music_volume": 0.85,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {"mp4_count": 1, "image_count": 0, "music_count": 1}
    assert body["command"][0] == "ffmpeg"
    assert "ffmpeg " in body["command_text"]
```

- [ ] **Step 4: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_api.py -q
```

Expected: FAIL because backend modules are missing.

- [ ] **Step 5: Add Pydantic models**

Create `backend/app/models.py`:

```python
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
```

- [ ] **Step 6: Add service functions**

Create `backend/app/services.py`:

```python
import shlex
import tempfile
from pathlib import Path

import video_combiner
from backend.app.models import DryRunResponse, MergeOptions, ScanResponse


def to_scan_response(summary: video_combiner.ScanSummary) -> ScanResponse:
    return ScanResponse(
        mp4_count=summary.mp4_count,
        image_count=summary.image_count,
        music_count=summary.music_count,
    )


def scan_paths(source_dir: Path, music_dir: Path) -> ScanResponse:
    return to_scan_response(video_combiner.scan_inputs(source_dir, music_dir))


def build_dry_run(options: MergeOptions) -> DryRunResponse:
    with tempfile.TemporaryDirectory(prefix="kiwi-merge-dry-run-") as tmp:
        prepared = video_combiner.prepare_merge(
            input_dir=options.source_dir,
            output=options.output_file,
            music_dir=options.music_dir,
            temp_dir=Path(tmp),
            original_volume=options.original_volume,
            music_volume=options.music_volume,
            photo_duration=options.photo_duration,
        )
    return DryRunResponse(
        command=prepared.command,
        command_text=shlex.join(prepared.command),
        messages=prepared.messages,
        summary=to_scan_response(prepared.summary),
    )
```

- [ ] **Step 7: Add FastAPI routes**

Create `backend/app/main.py`:

```python
from fastapi import FastAPI, HTTPException

from backend.app.models import HealthResponse, MergeOptions, ScanRequest, ScanResponse
from backend.app.services import build_dry_run, scan_paths


app = FastAPI(title="Kiwi Merge Backend")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True)


@app.post("/scan", response_model=ScanResponse)
def scan(request: ScanRequest) -> ScanResponse:
    try:
        return scan_paths(request.source_dir, request.music_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/dry-run")
def dry_run(options: MergeOptions):
    try:
        return build_dry_run(options)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [ ] **Step 8: Run backend tests**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_api.py -q
```

Expected: 3 passed.

- [ ] **Step 9: Commit**

```bash
git add backend
git commit -m "feat: add fastapi scan and dry-run api"
```

---

### Task 3: Add Backend Job Manager With Logs, Status, SSE, And Cancellation

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/app/jobs.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Write failing job API tests**

Append to `backend/tests/test_api.py`:

```python
def test_job_lifecycle_succeeds_with_fake_runner(tmp_path: Path):
    source = tmp_path / "source"
    music = tmp_path / "music"
    source.mkdir()
    music.mkdir()
    (source / "clip.mp4").write_text("x")
    (music / "track.mp3").write_text("x")

    with (
        patch("video_combiner.has_audio_stream", return_value=False),
        patch("video_combiner.get_duration", return_value=3.0),
        patch("backend.app.jobs.run_command", return_value=0),
    ):
        response = client.post(
            "/jobs",
            json={
                "source_dir": str(source),
                "output_file": str(tmp_path / "out.mp4"),
                "music_dir": str(music),
                "photo_duration": 7.0,
                "original_volume": 0.2,
                "music_volume": 0.85,
            },
        )

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    status = client.get(f"/jobs/{job_id}").json()
    assert status["status"] == "succeeded"
    assert any("Running ffmpeg" in line for line in status["logs"])


def test_starting_second_job_while_running_returns_conflict(tmp_path: Path):
    from backend.app.jobs import job_manager

    job_manager.active_job_id = "busy"

    response = client.post(
        "/jobs",
        json={
            "source_dir": str(tmp_path),
            "output_file": str(tmp_path / "out.mp4"),
            "music_dir": str(tmp_path),
            "photo_duration": 7.0,
            "original_volume": 0.2,
            "music_volume": 0.85,
        },
    )

    job_manager.active_job_id = None
    assert response.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_api.py -q
```

Expected: FAIL because `/jobs` routes and `backend.app.jobs` do not exist.

- [ ] **Step 3: Add job response models**

Append to `backend/app/models.py`:

```python
class JobCreateResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    logs: list[str]
    error: str | None = None
```

- [ ] **Step 4: Add job manager**

Create `backend/app/jobs.py`:

```python
import json
import subprocess
import tempfile
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Deque

import video_combiner
from backend.app.models import JobStatusResponse, MergeOptions


def run_command(command: list[str], logs: Deque[str], stop_event: threading.Event) -> int:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert process.stdout is not None
    for line in process.stdout:
        logs.append(line.rstrip())
        if stop_event.is_set():
            process.terminate()
            return 130
    return process.wait()


@dataclass
class MergeJob:
    job_id: str
    options: MergeOptions
    status: str = "queued"
    logs: Deque[str] = field(default_factory=lambda: deque(maxlen=500))
    error: str | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)


class JobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, MergeJob] = {}
        self.active_job_id: str | None = None
        self.lock = threading.Lock()

    def start(self, options: MergeOptions) -> MergeJob:
        with self.lock:
            if self.active_job_id is not None:
                raise RuntimeError("A merge job is already running")
            job = MergeJob(job_id=uuid.uuid4().hex, options=options)
            self.jobs[job.job_id] = job
            self.active_job_id = job.job_id
        thread = threading.Thread(target=self._run, args=(job,), daemon=True)
        thread.start()
        thread.join(timeout=2.0)
        return job

    def _run(self, job: MergeJob) -> None:
        job.status = "running"
        try:
            with tempfile.TemporaryDirectory(prefix="kiwi-merge-job-") as tmp:
                prepared = video_combiner.prepare_merge(
                    input_dir=job.options.source_dir,
                    output=job.options.output_file,
                    music_dir=job.options.music_dir,
                    temp_dir=Path(tmp),
                    original_volume=job.options.original_volume,
                    music_volume=job.options.music_volume,
                    photo_duration=job.options.photo_duration,
                )
                job.logs.extend(prepared.messages)
                job.logs.append("Running ffmpeg")
                code = run_command(prepared.command, job.logs, job.stop_event)
                if job.stop_event.is_set():
                    job.status = "cancelled"
                elif code == 0:
                    job.logs.append(f"Output: {job.options.output_file}")
                    job.status = "succeeded"
                else:
                    job.error = f"ffmpeg exited with status {code}"
                    job.status = "failed"
        except Exception as exc:
            job.error = str(exc)
            job.status = "failed"
        finally:
            with self.lock:
                if self.active_job_id == job.job_id:
                    self.active_job_id = None

    def get(self, job_id: str) -> MergeJob | None:
        return self.jobs.get(job_id)

    def cancel(self, job_id: str) -> MergeJob | None:
        job = self.get(job_id)
        if job is not None:
            job.stop_event.set()
        return job

    def response(self, job: MergeJob) -> JobStatusResponse:
        return JobStatusResponse(
            job_id=job.job_id,
            status=job.status,
            logs=list(job.logs),
            error=job.error,
        )

    def sse_lines(self, job_id: str):
        last_count = 0
        while True:
            job = self.get(job_id)
            if job is None:
                yield "event: error\ndata: {\"message\":\"Unknown job\"}\n\n"
                return
            logs = list(job.logs)
            for line in logs[last_count:]:
                yield f"event: log\ndata: {json.dumps({'line': line})}\n\n"
            last_count = len(logs)
            yield f"event: status\ndata: {self.response(job).model_dump_json()}\n\n"
            if job.status in {"succeeded", "failed", "cancelled"}:
                return


job_manager = JobManager()
```

- [ ] **Step 5: Add job routes**

Modify `backend/app/main.py` imports:

```python
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.jobs import job_manager
from backend.app.models import (
    HealthResponse,
    JobCreateResponse,
    JobStatusResponse,
    MergeOptions,
    ScanRequest,
    ScanResponse,
)
from backend.app.services import build_dry_run, scan_paths
```

Append these routes:

```python
@app.post("/jobs", response_model=JobCreateResponse)
def create_job(options: MergeOptions) -> JobCreateResponse:
    try:
        job = job_manager.start(options)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JobCreateResponse(job_id=job.job_id)


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> JobStatusResponse:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    return job_manager.response(job)


@app.get("/jobs/{job_id}/events")
def job_events(job_id: str) -> StreamingResponse:
    return StreamingResponse(job_manager.sse_lines(job_id), media_type="text/event-stream")


@app.post("/jobs/{job_id}/cancel", response_model=JobStatusResponse)
def cancel_job(job_id: str) -> JobStatusResponse:
    job = job_manager.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    return job_manager.response(job)
```

- [ ] **Step 6: Run backend tests**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_api.py -q
```

Expected: all backend tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat: add merge job api"
```

---

### Task 4: Scaffold Electron, Vite, Vue, Tailwind, And IPC Dialogs

**Files:**
- Create: `package.json`
- Create: `index.html`
- Create: `vite.config.ts`
- Create: `tsconfig.json`
- Create: `tailwind.config.js`
- Create: `postcss.config.js`
- Create: `electron/main.cjs`
- Create: `electron/preload.cjs`
- Create: `src/main.ts`
- Create: `src/styles.css`
- Create: `src/vite-env.d.ts`

- [ ] **Step 1: Create package scripts and dependencies**

Create `package.json`:

```json
{
  "name": "kiwi-merge",
  "version": "0.1.0",
  "private": true,
  "main": "electron/main.cjs",
  "scripts": {
    "dev": "vite --host 127.0.0.1",
    "electron": "electron .",
    "app:dev": "concurrently -k \"npm run dev\" \"wait-on http://127.0.0.1:5173 && npm run electron\"",
    "build": "vue-tsc --noEmit && vite build",
    "test": "vitest run"
  },
  "dependencies": {
    "@vitejs/plugin-vue": "5.2.1",
    "concurrently": "9.1.2",
    "electron": "33.3.1",
    "vite": "6.0.7",
    "vue": "3.5.13",
    "wait-on": "8.0.1"
  },
  "devDependencies": {
    "@types/node": "22.10.5",
    "autoprefixer": "10.4.20",
    "postcss": "8.4.49",
    "tailwindcss": "3.4.17",
    "typescript": "5.7.2",
    "vitest": "2.1.8",
    "vue-tsc": "2.2.0"
  }
}
```

- [ ] **Step 2: Add Vite and TypeScript config**

Create `index.html`:

```html
<div id="app"></div>
<script type="module" src="/src/main.ts"></script>
```

Create `vite.config.ts`:

```ts
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
  },
})
```

Create `tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "jsx": "preserve",
    "sourceMap": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "types": ["node"]
  },
  "include": ["src/**/*.ts", "src/**/*.vue", "vite.config.ts"]
}
```

- [ ] **Step 3: Add Tailwind config and styles**

Create `tailwind.config.js`:

```js
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{vue,ts}'],
  theme: {
    extend: {
      colors: {
        kiwi: {
          50: '#f8fbf1',
          100: '#edf6db',
          200: '#d9ebb3',
          400: '#9bc447',
          600: '#6f961f',
          800: '#405a17'
        }
      },
      boxShadow: {
        kiwi: '0 16px 40px rgba(111, 150, 31, 0.14)'
      }
    }
  },
  plugins: []
}
```

Create `postcss.config.js`:

```js
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {}
  }
}
```

Create `src/styles.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  color: #23301e;
  background: #f8fbf1;
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-width: 320px;
  min-height: 100vh;
  background: #f8fbf1;
}

button,
input {
  font: inherit;
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
  }
}
```

- [ ] **Step 4: Add Electron main and preload**

Create `electron/main.cjs`:

```js
const { app, BrowserWindow, dialog, ipcMain } = require('electron')
const { spawn } = require('node:child_process')
const path = require('node:path')

let backendProcess = null

function startBackend() {
  const backendPath = path.join(__dirname, '..', 'backend', 'app', 'main.py')
  backendProcess = spawn('python', ['-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', '8765'], {
    cwd: path.join(__dirname, '..'),
    stdio: 'inherit'
  })
}

async function createWindow() {
  const win = new BrowserWindow({
    width: 1120,
    height: 760,
    minWidth: 760,
    minHeight: 560,
    backgroundColor: '#f8fbf1',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs')
    }
  })

  await win.loadURL('http://127.0.0.1:5173')
}

ipcMain.handle('dialog:directory', async () => {
  const result = await dialog.showOpenDialog({ properties: ['openDirectory'] })
  return result.canceled ? null : result.filePaths[0]
})

ipcMain.handle('dialog:save-file', async () => {
  const result = await dialog.showSaveDialog({
    filters: [{ name: 'MP4 Video', extensions: ['mp4'] }]
  })
  return result.canceled ? null : result.filePath
})

app.whenReady().then(() => {
  startBackend()
  createWindow()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  if (backendProcess) backendProcess.kill()
})
```

Create `electron/preload.cjs`:

```js
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('kiwi', {
  pickDirectory: () => ipcRenderer.invoke('dialog:directory'),
  pickOutputFile: () => ipcRenderer.invoke('dialog:save-file')
})
```

- [ ] **Step 5: Add Vue bootstrap and global types**

Create `src/main.ts`:

```ts
import { createApp } from 'vue'
import App from './App.vue'
import './styles.css'

createApp(App).mount('#app')
```

Create `src/vite-env.d.ts`:

```ts
/// <reference types="vite/client" />

declare global {
  interface Window {
    kiwi?: {
      pickDirectory: () => Promise<string | null>
      pickOutputFile: () => Promise<string | null>
    }
  }
}

export {}
```

- [ ] **Step 6: Add temporary App component**

Create `src/App.vue`:

```vue
<template>
  <main class="min-h-screen bg-kiwi-50 p-6 text-[#23301e]">
    <h1 class="text-2xl font-bold">Kiwi Merge</h1>
    <p class="mt-2 text-sm text-[#66735e]">Electron shell is running.</p>
  </main>
</template>
```

- [ ] **Step 7: Install dependencies**

Run:

```bash
npm install
```

Expected: `node_modules` and `package-lock.json` are created.

- [ ] **Step 8: Verify build**

Run:

```bash
npm run build
```

Expected: TypeScript and Vite build pass.

- [ ] **Step 9: Commit**

```bash
git add package.json package-lock.json index.html vite.config.ts tsconfig.json tailwind.config.js postcss.config.js electron src
git commit -m "feat: scaffold electron vue app"
```

---

### Task 5: Implement Vue API Client And UI Components

**Files:**
- Create: `src/lib/api.ts`
- Create: `src/components/PathField.vue`
- Create: `src/components/OptionPanel.vue`
- Create: `src/components/StatsPanel.vue`
- Create: `src/components/ProgressPanel.vue`
- Create: `src/components/LogPanel.vue`
- Modify: `src/App.vue`

- [ ] **Step 1: Add typed API client**

Create `src/lib/api.ts`:

```ts
const API_BASE = 'http://127.0.0.1:8765'

export interface ScanSummary {
  mp4_count: number
  image_count: number
  music_count: number
}

export interface MergeOptions {
  source_dir: string
  output_file: string
  music_dir: string
  photo_duration: number
  original_volume: number
  music_volume: number
}

export interface DryRunResponse {
  command: string[]
  command_text: string
  messages: string[]
  summary: ScanSummary
}

export interface JobCreateResponse {
  job_id: string
}

export interface JobStatusResponse {
  job_id: string
  status: string
  logs: string[]
  error: string | null
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(body.detail ?? response.statusText)
  }
  return response.json() as Promise<T>
}

export function scan(sourceDir: string, musicDir: string): Promise<ScanSummary> {
  return request('/scan', {
    method: 'POST',
    body: JSON.stringify({ source_dir: sourceDir, music_dir: musicDir })
  })
}

export function dryRun(options: MergeOptions): Promise<DryRunResponse> {
  return request('/dry-run', {
    method: 'POST',
    body: JSON.stringify(options)
  })
}

export function startJob(options: MergeOptions): Promise<JobCreateResponse> {
  return request('/jobs', {
    method: 'POST',
    body: JSON.stringify(options)
  })
}

export function getJob(jobId: string): Promise<JobStatusResponse> {
  return request(`/jobs/${jobId}`)
}

export function cancelJob(jobId: string): Promise<JobStatusResponse> {
  return request(`/jobs/${jobId}/cancel`, { method: 'POST' })
}

export function subscribeJob(jobId: string, onStatus: (status: JobStatusResponse) => void, onLog: (line: string) => void): EventSource {
  const source = new EventSource(`${API_BASE}/jobs/${jobId}/events`)
  source.addEventListener('status', (event) => onStatus(JSON.parse((event as MessageEvent).data)))
  source.addEventListener('log', (event) => onLog(JSON.parse((event as MessageEvent).data).line))
  return source
}
```

- [ ] **Step 2: Add path field component**

Create `src/components/PathField.vue`:

```vue
<script setup lang="ts">
defineProps<{
  label: string
  modelValue: string
  buttonLabel: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  browse: []
}>()
</script>

<template>
  <label class="grid gap-1.5 text-xs font-medium text-[#65715e]">
    {{ label }}
    <div class="flex min-h-11 gap-2">
      <input
        class="min-w-0 flex-1 rounded-lg border border-[#dce8cf] bg-[#fbfdf7] px-3 text-sm text-[#2f3c28] outline-none transition focus:border-kiwi-400 focus:ring-2 focus:ring-kiwi-100"
        :value="modelValue"
        @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      />
      <button
        class="rounded-lg bg-kiwi-200 px-3 text-sm font-bold text-kiwi-800 transition hover:bg-kiwi-400 hover:text-white active:scale-[0.98]"
        type="button"
        @click="emit('browse')"
      >
        {{ buttonLabel }}
      </button>
    </div>
  </label>
</template>
```

- [ ] **Step 3: Add option panel**

Create `src/components/OptionPanel.vue`:

```vue
<script setup lang="ts">
defineProps<{
  photoDuration: number
  originalVolume: number
  musicVolume: number
}>()

const emit = defineEmits<{
  'update:photoDuration': [value: number]
  'update:originalVolume': [value: number]
  'update:musicVolume': [value: number]
}>()
</script>

<template>
  <section class="rounded-xl border border-[#e3ecd8] bg-white p-4 shadow-sm">
    <h2 class="mb-3 text-sm font-bold text-[#3d4b35]">Options</h2>
    <div class="grid gap-3 sm:grid-cols-3">
      <label class="grid gap-1 text-xs text-[#65715e]">
        Photo duration
        <input class="rounded-lg border border-[#dce8cf] bg-[#fbfdf7] px-3 py-2 text-sm text-[#2f3c28]" type="number" min="1" :value="photoDuration" @input="emit('update:photoDuration', Number(($event.target as HTMLInputElement).value))" />
      </label>
      <label class="grid gap-1 text-xs text-[#65715e]">
        Original volume
        <input class="rounded-lg border border-[#dce8cf] bg-[#fbfdf7] px-3 py-2 text-sm text-[#2f3c28]" type="number" min="0" step="0.05" :value="originalVolume" @input="emit('update:originalVolume', Number(($event.target as HTMLInputElement).value))" />
      </label>
      <label class="grid gap-1 text-xs text-[#65715e]">
        Music volume
        <input class="rounded-lg border border-[#dce8cf] bg-[#fbfdf7] px-3 py-2 text-sm text-[#2f3c28]" type="number" min="0" step="0.05" :value="musicVolume" @input="emit('update:musicVolume', Number(($event.target as HTMLInputElement).value))" />
      </label>
    </div>
  </section>
</template>
```

- [ ] **Step 4: Add stat, progress, and log components**

Create `src/components/StatsPanel.vue`:

```vue
<script setup lang="ts">
import type { ScanSummary } from '../lib/api'

defineProps<{ summary: ScanSummary | null }>()
</script>

<template>
  <section class="grid grid-cols-3 gap-3">
    <div v-for="[label, value] in [['MP4s', summary?.mp4_count ?? 0], ['Images', summary?.image_count ?? 0], ['Tracks', summary?.music_count ?? 0]]" :key="label" class="rounded-xl border border-[#e3ecd8] bg-white p-4 shadow-sm">
      <div class="text-3xl font-extrabold text-kiwi-600">{{ value }}</div>
      <div class="text-xs text-[#677260]">{{ label }}</div>
    </div>
  </section>
</template>
```

Create `src/components/ProgressPanel.vue`:

```vue
<script setup lang="ts">
defineProps<{ status: string }>()
</script>

<template>
  <section class="rounded-xl border border-[#e3ecd8] bg-white p-4 shadow-sm">
    <div class="mb-3 flex items-center justify-between">
      <h2 class="text-sm font-bold text-[#3d4b35]">Progress</h2>
      <span class="text-xs text-[#66735e]">{{ status }}</span>
    </div>
    <div class="h-2.5 overflow-hidden rounded-full bg-[#edf4e3]">
      <div class="h-full rounded-full bg-kiwi-400 transition-all duration-300" :class="status === 'running' ? 'w-2/3 animate-pulse' : status === 'succeeded' ? 'w-full' : 'w-0'"></div>
    </div>
  </section>
</template>
```

Create `src/components/LogPanel.vue`:

```vue
<script setup lang="ts">
defineProps<{ logs: string[] }>()
</script>

<template>
  <section class="min-h-56 overflow-hidden rounded-xl bg-[#1f2a19] p-4 font-mono text-xs leading-6 text-[#dfead4]">
    <div v-if="logs.length === 0" class="text-[#87947d]">Logs will appear here.</div>
    <div v-for="(line, index) in logs" :key="`${index}-${line}`" class="break-words">{{ line }}</div>
  </section>
</template>
```

- [ ] **Step 5: Replace `src/App.vue` with app shell**

Use this full `src/App.vue`:

```vue
<script setup lang="ts">
import { computed, ref } from 'vue'
import LogPanel from './components/LogPanel.vue'
import OptionPanel from './components/OptionPanel.vue'
import PathField from './components/PathField.vue'
import ProgressPanel from './components/ProgressPanel.vue'
import StatsPanel from './components/StatsPanel.vue'
import { cancelJob, dryRun, scan, startJob, subscribeJob, type JobStatusResponse, type MergeOptions, type ScanSummary } from './lib/api'

const sourceDir = ref('')
const outputFile = ref('')
const musicDir = ref('')
const photoDuration = ref(7)
const originalVolume = ref(0.2)
const musicVolume = ref(0.85)
const summary = ref<ScanSummary | null>(null)
const logs = ref<string[]>([])
const status = ref('ready')
const error = ref('')
const activeJobId = ref<string | null>(null)
let events: EventSource | null = null

const canRun = computed(() => sourceDir.value && outputFile.value && musicDir.value && status.value !== 'running')

function options(): MergeOptions {
  return {
    source_dir: sourceDir.value,
    output_file: outputFile.value,
    music_dir: musicDir.value,
    photo_duration: photoDuration.value,
    original_volume: originalVolume.value,
    music_volume: musicVolume.value
  }
}

async function pickSource() {
  sourceDir.value = (await window.kiwi?.pickDirectory()) ?? sourceDir.value
}

async function pickMusic() {
  musicDir.value = (await window.kiwi?.pickDirectory()) ?? musicDir.value
}

async function pickOutput() {
  outputFile.value = (await window.kiwi?.pickOutputFile()) ?? outputFile.value
}

async function rescan() {
  error.value = ''
  status.value = 'scanning'
  try {
    summary.value = await scan(sourceDir.value, musicDir.value)
    status.value = 'ready'
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
    status.value = 'failed'
  }
}

async function runDryRun() {
  error.value = ''
  try {
    const result = await dryRun(options())
    summary.value = result.summary
    logs.value = [...result.messages, result.command_text]
    status.value = 'ready'
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
    status.value = 'failed'
  }
}

function applyJob(update: JobStatusResponse) {
  status.value = update.status
  logs.value = update.logs
  if (update.error) error.value = update.error
}

async function runMerge() {
  error.value = ''
  logs.value = []
  status.value = 'running'
  const response = await startJob(options())
  activeJobId.value = response.job_id
  events?.close()
  events = subscribeJob(response.job_id, applyJob, (line) => logs.value.push(line))
}

async function cancelActiveJob() {
  if (!activeJobId.value) return
  applyJob(await cancelJob(activeJobId.value))
}
</script>

<template>
  <main class="min-h-screen bg-kiwi-50 p-4 text-[#23301e] sm:p-6">
    <div class="mx-auto max-w-6xl overflow-hidden rounded-[18px] border border-[#dfead4] bg-[#f8fbf4] shadow-kiwi">
      <header class="flex items-center justify-between border-b border-[#dfead4] bg-[#fbfdf7] px-5 py-4">
        <div>
          <h1 class="text-xl font-extrabold">Kiwi Merge</h1>
          <p class="mt-0.5 text-xs text-[#66735e]">Local video combiner</p>
        </div>
        <div class="flex items-center gap-2 text-xs text-[#55614e]">
          <span class="h-2.5 w-2.5 rounded-full bg-kiwi-400 ring-4 ring-kiwi-100"></span>
          {{ status }}
        </div>
      </header>

      <div class="grid gap-5 p-5 lg:grid-cols-[1.05fr_.95fr]">
        <section class="grid gap-4">
          <div class="rounded-xl border border-[#e3ecd8] bg-white p-4 shadow-sm">
            <h2 class="mb-3 text-sm font-bold text-[#3d4b35]">Paths</h2>
            <div class="grid gap-3">
              <PathField v-model="sourceDir" label="Source directory" button-label="Browse" @browse="pickSource" />
              <PathField v-model="outputFile" label="Output file" button-label="Save as" @browse="pickOutput" />
              <PathField v-model="musicDir" label="Music directory" button-label="Browse" @browse="pickMusic" />
            </div>
          </div>

          <OptionPanel v-model:photo-duration="photoDuration" v-model:original-volume="originalVolume" v-model:music-volume="musicVolume" />

          <div v-if="error" class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</div>

          <div class="flex flex-wrap gap-2">
            <button class="min-h-11 rounded-lg bg-kiwi-600 px-5 font-extrabold text-white transition hover:bg-kiwi-800 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50" :disabled="!canRun" @click="runMerge">Start merge</button>
            <button class="min-h-11 rounded-lg border border-[#d4e4c4] bg-white px-4 font-bold text-[#425039] transition hover:border-kiwi-400" :disabled="!canRun" @click="runDryRun">Dry run</button>
            <button class="min-h-11 rounded-lg border border-[#d4e4c4] bg-white px-4 font-bold text-[#425039] transition hover:border-kiwi-400" @click="rescan">Rescan</button>
            <button v-if="status === 'running'" class="min-h-11 rounded-lg border border-red-200 bg-white px-4 font-bold text-red-700 transition hover:bg-red-50" @click="cancelActiveJob">Cancel</button>
          </div>
        </section>

        <section class="grid content-start gap-4">
          <StatsPanel :summary="summary" />
          <ProgressPanel :status="status" />
          <LogPanel :logs="logs" />
        </section>
      </div>
    </div>
  </main>
</template>
```

- [ ] **Step 6: Build frontend**

Run:

```bash
npm run build
```

Expected: build passes.

- [ ] **Step 7: Commit**

```bash
git add src
git commit -m "feat: build kiwi merge ui"
```

---

### Task 6: Wire Backend Startup Robustness And Documentation

**Files:**
- Modify: `electron/main.cjs`
- Modify: `README.md`

- [ ] **Step 1: Improve Electron backend readiness**

Modify `electron/main.cjs` by adding this helper before `createWindow`:

```js
async function waitForBackend() {
  const started = Date.now()
  while (Date.now() - started < 15000) {
    try {
      const response = await fetch('http://127.0.0.1:8765/health')
      if (response.ok) return
    } catch {
      await new Promise(resolve => setTimeout(resolve, 300))
    }
  }
  throw new Error('Backend did not start within 15 seconds')
}
```

Change `app.whenReady().then(() => { ... })` to:

```js
app.whenReady().then(async () => {
  startBackend()
  await waitForBackend()
  await createWindow()
})
```

- [ ] **Step 2: Write README desktop app instructions**

Append to `README.md`:

```markdown
## Desktop App Development

The Electron app is a local UI around the Python combiner. Version 1 expects
Python 3.10+ and `ffmpeg`/`ffprobe` on `PATH`; they are not bundled yet.

Install Python backend dependencies:

```bash
python -m pip install -r backend/requirements.txt
```

Install frontend dependencies:

```bash
npm install
```

Run the desktop app in development:

```bash
npm run app:dev
```

The Electron main process starts the FastAPI backend on `127.0.0.1:8765`.
The Vue renderer runs through Vite on `127.0.0.1:5173`.
```
```

- [ ] **Step 3: Run backend and frontend verification**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_api.py -q
python -m unittest
npm run build
```

Expected: all commands pass.

- [ ] **Step 4: Start the app for manual verification**

Run:

```bash
npm run app:dev
```

Expected: Electron window opens, backend starts, UI renders. Leave the dev server running and give the user the local app status.

- [ ] **Step 5: Commit**

```bash
git add electron/main.cjs README.md
git commit -m "docs: document desktop app development"
```

---

## Self-Review

Spec coverage:

- Source/output/music configuration: Task 5.
- Progress and logs: Tasks 3 and 5.
- MP4/image/music counts: Tasks 1, 2, and 5.
- Clean minimal kiwi UI: Tasks 4 and 5.
- Responsive and subtle feedback: Task 5.
- Vue 3 + Tailwind + FastAPI + Electron: Tasks 2, 4, 5, and 6.
- No bundled Python/ffmpeg in v1: Task 6 README and Electron launcher.

Placeholder scan:

- No placeholder markers or unspecified implementation steps are intentionally left in this plan.

Type consistency:

- API request field names use backend snake_case: `source_dir`, `output_file`, `music_dir`, `photo_duration`, `original_volume`, `music_volume`.
- Frontend interfaces mirror backend response shapes.
- Job statuses use `ready`, `scanning`, `running`, `succeeded`, `failed`, and `cancelled` in UI, with backend returning job status values after start.
