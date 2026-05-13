import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.main import app, cancel_job, create_job, dry_run, get_job, health, scan
from backend.app.models import MergeOptions, ScanRequest
from backend.app.services import cleanup_stale_dry_run_dirs


def test_routes_are_registered():
    route_map = {
        route.path: route.methods
        for route in app.routes
        if hasattr(route, "methods")
    }

    assert "/health" in route_map
    assert "GET" in route_map["/health"]
    assert "/scan" in route_map
    assert "POST" in route_map["/scan"]
    assert "/dry-run" in route_map
    assert "POST" in route_map["/dry-run"]
    assert "/jobs" in route_map
    assert "POST" in route_map["/jobs"]
    assert "/jobs/{job_id}" in route_map
    assert "GET" in route_map["/jobs/{job_id}"]
    assert "/jobs/{job_id}/events" in route_map
    assert "GET" in route_map["/jobs/{job_id}/events"]
    assert "/jobs/{job_id}/cancel" in route_map
    assert "POST" in route_map["/jobs/{job_id}/cancel"]


def test_health_reports_ready():
    response = health()

    assert response.model_dump() == {"ok": True}


def test_app_enables_cors_for_local_ui_requests():
    cors_middleware = next(
        (
            middleware
            for middleware in app.user_middleware
            if middleware.cls is CORSMiddleware
        ),
        None,
    )

    assert cors_middleware is not None


def test_scan_returns_media_counts(tmp_path: Path):
    source_dir = tmp_path / "source"
    music_dir = tmp_path / "music"
    source_dir.mkdir()
    music_dir.mkdir()

    (source_dir / "clip.mp4").write_bytes(b"")
    (source_dir / "photo.jpg").write_bytes(b"")
    (music_dir / "track.mp3").write_bytes(b"")

    response = scan(ScanRequest(source_dir=source_dir, music_dir=music_dir))

    assert response.model_dump() == {
        "mp4_count": 1,
        "image_count": 1,
        "music_count": 1,
    }


def test_scan_invalid_directory_returns_http_400(tmp_path: Path):
    with pytest.raises(HTTPException) as exc_info:
        scan(
            ScanRequest(
                source_dir=tmp_path / "missing-source",
                music_dir=tmp_path / "missing-music",
            )
        )

    assert exc_info.value.status_code == 400


def test_dry_run_returns_command_and_summary(tmp_path: Path):
    source_dir = tmp_path / "source"
    music_dir = tmp_path / "music"
    output_file = tmp_path / "nested" / "dir" / "out.mp4"
    source_dir.mkdir()
    music_dir.mkdir()

    (source_dir / "clip.mp4").write_bytes(b"")
    (music_dir / "track.mp3").write_bytes(b"")

    with (
        patch("video_combiner.has_audio_stream", return_value=True),
        patch("video_combiner.get_duration", return_value=3.5),
    ):
        response = dry_run(
            MergeOptions(
                source_dir=source_dir,
                output_file=output_file,
                music_dir=music_dir,
                photo_duration=7.0,
                original_volume=0.2,
                music_volume=0.85,
            )
        )

    payload = response.model_dump()
    assert payload["command"][0] == "ffmpeg"
    assert payload["command_text"]
    assert payload["messages"]
    assert payload["summary"] == {
        "mp4_count": 1,
        "image_count": 0,
        "music_count": 1,
    }
    assert Path(payload["command"][7]).exists()
    assert output_file.parent.exists()
    assert Path(payload["command"][-1]) == output_file


def test_dry_run_probe_failure_returns_http_400(tmp_path: Path):
    source_dir = tmp_path / "source"
    music_dir = tmp_path / "music"
    source_dir.mkdir()
    music_dir.mkdir()
    (source_dir / "clip.mp4").write_bytes(b"")
    (music_dir / "track.mp3").write_bytes(b"")

    options = MergeOptions(
        source_dir=source_dir,
        output_file=tmp_path / "out.mp4",
        music_dir=music_dir,
    )

    with patch(
        "video_combiner.prepare_merge",
        side_effect=subprocess.CalledProcessError(1, ["ffprobe"], stderr="bad media"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            dry_run(options)

    assert exc_info.value.status_code == 400


def test_dry_run_missing_tool_returns_http_400(tmp_path: Path):
    source_dir = tmp_path / "source"
    music_dir = tmp_path / "music"
    source_dir.mkdir()
    music_dir.mkdir()
    (source_dir / "clip.mp4").write_bytes(b"")
    (music_dir / "track.mp3").write_bytes(b"")

    options = MergeOptions(
        source_dir=source_dir,
        output_file=tmp_path / "out.mp4",
        music_dir=music_dir,
    )

    with patch("video_combiner.prepare_merge", side_effect=FileNotFoundError("ffprobe")):
        with pytest.raises(HTTPException) as exc_info:
            dry_run(options)

    assert exc_info.value.status_code == 400


def test_merge_options_defaults_apply(tmp_path: Path):
    options = MergeOptions(
        source_dir=tmp_path / "source",
        output_file=tmp_path / "out.mp4",
        music_dir=tmp_path / "music",
    )

    assert options.photo_duration == 7.0
    assert options.original_volume == 0.2
    assert options.music_volume == 0.85


def test_cleanup_stale_dry_run_dirs_removes_old_temp_dirs(tmp_path: Path):
    stale_dir = Path(tempfile.mkdtemp(prefix="kiwi-merge-api-", dir=tmp_path))
    fresh_dir = Path(tempfile.mkdtemp(prefix="kiwi-merge-api-", dir=tmp_path))

    old_timestamp = 1
    fresh_timestamp = fresh_dir.stat().st_mtime

    with patch("backend.app.services.tempfile.gettempdir", return_value=str(tmp_path)):
        import os

        os.utime(stale_dir, (old_timestamp, old_timestamp))
        os.utime(fresh_dir, (fresh_timestamp, fresh_timestamp))
        cleanup_stale_dry_run_dirs(max_age_seconds=3600)

    assert not stale_dir.exists()
    assert fresh_dir.exists()


def test_job_lifecycle_succeeds_with_fake_runner(tmp_path: Path):
    source_dir = tmp_path / "source"
    music_dir = tmp_path / "music"
    output_file = tmp_path / "out.mp4"
    source_dir.mkdir()
    music_dir.mkdir()
    (source_dir / "clip.mp4").write_bytes(b"")
    (music_dir / "track.mp3").write_bytes(b"")

    def fake_run_command(command: list[str], logs: list[str], stop_event, working_dir=None) -> None:
        logs.append(f"Running {' '.join(command[:1])}")

    with (
        patch("video_combiner.has_audio_stream", return_value=True),
        patch("video_combiner.get_duration", return_value=3.5),
        patch("backend.app.jobs.run_command", side_effect=fake_run_command),
    ):
        create_response = create_job(
            MergeOptions(
                source_dir=source_dir,
                output_file=output_file,
                music_dir=music_dir,
                photo_duration=7.0,
                original_volume=0.2,
                music_volume=0.85,
            )
        )
    job_id = create_response.job_id

    status_response = get_job(job_id)

    assert status_response.status == "succeeded"
    assert "Running ffmpeg" in status_response.logs


def test_create_job_returns_http_409_when_manager_is_busy(tmp_path: Path):
    source_dir = tmp_path / "source"
    music_dir = tmp_path / "music"
    output_file = tmp_path / "out.mp4"
    source_dir.mkdir()
    music_dir.mkdir()
    (source_dir / "clip.mp4").write_bytes(b"")
    (music_dir / "track.mp3").write_bytes(b"")

    from backend.app.jobs import job_manager

    original_active_job_id = job_manager.active_job_id
    job_manager.active_job_id = "busy-job"
    try:
        with pytest.raises(HTTPException) as exc_info:
            create_job(
                MergeOptions(
                    source_dir=source_dir,
                    output_file=output_file,
                    music_dir=music_dir,
                )
            )
    finally:
        job_manager.active_job_id = original_active_job_id

    assert exc_info.value.status_code == 409


def test_cancel_job_eventually_reaches_cancelled_state(tmp_path: Path):
    source_dir = tmp_path / "source"
    music_dir = tmp_path / "music"
    output_file = tmp_path / "out.mp4"
    source_dir.mkdir()
    music_dir.mkdir()
    (source_dir / "clip.mp4").write_bytes(b"")
    (music_dir / "track.mp3").write_bytes(b"")

    from backend.app.jobs import JobCancelledError, job_manager

    def fake_run_command(command: list[str], logs: list[str], stop_event, working_dir=None) -> None:
        while not stop_event.is_set():
            time.sleep(0.01)
        raise JobCancelledError("Job cancelled")

    with (
        patch("video_combiner.has_audio_stream", return_value=True),
        patch("video_combiner.get_duration", return_value=3.5),
        patch("backend.app.jobs.run_command", side_effect=fake_run_command),
    ):
        create_response = create_job(
            MergeOptions(
                source_dir=source_dir,
                output_file=output_file,
                music_dir=music_dir,
            )
        )
        cancel_response = cancel_job(create_response.job_id)

        deadline = time.time() + 1
        while time.time() < deadline:
            status_response = get_job(create_response.job_id)
            if status_response.status == "cancelled":
                break
            time.sleep(0.01)
        else:
            raise AssertionError("job did not reach cancelled state")

    assert cancel_response.status in {"running", "cancelled"}
    assert status_response.status == "cancelled"
    assert job_manager.active_job_id is None


def test_unknown_job_routes_return_http_404():
    with pytest.raises(HTTPException) as get_exc:
        get_job("missing-job")

    with pytest.raises(HTTPException) as cancel_exc:
        cancel_job("missing-job")

    assert get_exc.value.status_code == 404
    assert cancel_exc.value.status_code == 404


def test_worker_exception_marks_job_failed(tmp_path: Path):
    source_dir = tmp_path / "source"
    music_dir = tmp_path / "music"
    output_file = tmp_path / "out.mp4"
    source_dir.mkdir()
    music_dir.mkdir()
    (source_dir / "clip.mp4").write_bytes(b"")
    (music_dir / "track.mp3").write_bytes(b"")

    with patch("video_combiner.prepare_merge", side_effect=PermissionError("no access")):
        create_response = create_job(
            MergeOptions(
                source_dir=source_dir,
                output_file=output_file,
                music_dir=music_dir,
            )
        )

    deadline = time.time() + 1
    while time.time() < deadline:
        status_response = get_job(create_response.job_id)
        if status_response.status == "failed":
            break
        time.sleep(0.01)
    else:
        raise AssertionError("job did not reach failed state")

    assert "no access" in (status_response.error or "")
