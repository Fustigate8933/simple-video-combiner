import shlex
import shutil
import tempfile
import time
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
    summary = video_combiner.scan_inputs(source_dir, music_dir)
    return to_scan_response(summary)


def cleanup_stale_dry_run_dirs(*, max_age_seconds: int = 3600) -> None:
    temp_root = Path(tempfile.gettempdir())
    cutoff = time.time() - max_age_seconds
    for path in temp_root.glob("kiwi-merge-api-*"):
        try:
            if path.is_dir() and path.stat().st_mtime < cutoff:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            continue


def build_dry_run(options: MergeOptions) -> DryRunResponse:
    cleanup_stale_dry_run_dirs()
    # Keep the concat lists on disk so the returned command remains executable.
    temp_dir = Path(tempfile.mkdtemp(prefix="kiwi-merge-api-"))
    options.output_file.parent.mkdir(parents=True, exist_ok=True)
    prepared = video_combiner.prepare_merge(
        input_dir=options.source_dir,
        output=options.output_file,
        music_dir=options.music_dir,
        temp_dir=temp_dir,
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
