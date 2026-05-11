#!/usr/bin/env python3
"""Merge camera MP4 files and mix in background music with ffmpeg."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Sequence, TextIO


DEFAULT_MUSIC_DIR = Path(
    "/mnt/ianch-Secondary/Downloads/Compressed/"
    "Frieren Beyond Journey's End Original Soundtrack [MP3]"
)


def set_mtime(path: Path, timestamp: float) -> None:
    """Set access and modification time; used by tests and harmless for callers."""
    os.utime(path, (timestamp, timestamp))


def find_videos(input_dir: Path) -> list[Path]:
    """Return top-level MP4 files in chronological camera order."""
    if not input_dir.is_dir():
        raise ValueError(f"Input directory does not exist: {input_dir}")

    videos = [path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() == ".mp4"]
    return sorted(videos, key=lambda path: (path.stat().st_mtime, path.name.lower()))


def find_music(music_dir: Path) -> list[Path]:
    """Return MP3 tracks from Disc 1 and Disc 2, sorted by disc then filename."""
    if not music_dir.is_dir():
        raise ValueError(f"Music directory does not exist: {music_dir}")

    tracks: list[Path] = []
    for disc_name in ("Disc 1", "Disc 2"):
        disc = music_dir / disc_name
        if disc.is_dir():
            tracks.extend(
                path
                for path in disc.iterdir()
                if path.is_file() and path.suffix.lower() == ".mp3"
            )

    return sorted(tracks, key=lambda path: (path.parent.name.lower(), path.name.lower()))


def quote_for_concat_file(path: Path) -> str:
    """Quote a path for ffmpeg concat demuxer list files."""
    return "'" + str(path.resolve()).replace("'", "'\\''") + "'"


def write_concat_list(paths: Iterable[Path], output: Path) -> None:
    lines = [f"file {quote_for_concat_file(path)}\n" for path in paths]
    output.write_text("".join(lines))


def has_audio_stream(video: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def get_duration(video: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def build_ffmpeg_command(
    *,
    video_list: Path,
    videos: Sequence[Path],
    audio_flags: Sequence[bool],
    durations: Sequence[float],
    music_list: Path,
    output: Path,
    original_volume: float,
    music_volume: float,
) -> list[str]:
    if not (len(videos) == len(audio_flags) == len(durations)):
        raise ValueError("videos, audio_flags, and durations must have the same length")

    command = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(video_list)]
    for video in videos:
        command.extend(["-i", str(video)])
    command.extend(["-stream_loop", "-1", "-f", "concat", "-safe", "0", "-i", str(music_list)])

    filter_parts: list[str] = []
    concat_inputs: list[str] = []
    for index, (has_audio, duration) in enumerate(zip(audio_flags, durations)):
        if has_audio:
            input_index = index + 1
            filter_parts.append(
                f"[{input_index}:a:0]volume={original_volume},"
                "aformat=sample_rates=48000:channel_layouts=stereo,"
                f"asetpts=PTS-STARTPTS[a{index}]"
            )
        else:
            filter_parts.append(
                "anullsrc=channel_layout=stereo:"
                f"sample_rate=48000:d={duration:g}[a{index}]"
            )
        concat_inputs.append(f"[a{index}]")

    music_index = len(videos) + 1
    filter_parts.extend(
        [
            "".join(concat_inputs)
            + f"concat=n={len(videos)}:v=0:a=1[original]",
            f"[{music_index}:a:0]volume={music_volume}[music]",
            "[original][music]amix=inputs=2:duration=first:dropout_transition=2[a]",
        ]
    )
    filter_complex = ";".join(filter_parts)

    command.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "0:v:0",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(output),
        ]
    )
    return command


def merge_videos(
    *,
    input_dir: Path,
    output: Path,
    music_dir: Path,
    original_volume: float = 0.2,
    music_volume: float = 0.85,
    dry_run: bool = False,
    quiet: bool = False,
    log: TextIO = sys.stdout,
) -> list[str]:
    def log_message(message: str) -> None:
        if not quiet:
            print(message, file=log)

    videos = find_videos(input_dir)
    if not videos:
        raise ValueError(f"No MP4 files found in {input_dir}")
    log_message(f"Found {len(videos)} MP4 files")
    audio_flags = [has_audio_stream(video) for video in videos]
    audio_count = sum(audio_flags)
    durations = [get_duration(video) for video in videos]
    if audio_count == len(videos):
        log_message("Original audio detected; mixing it under the soundtrack")
    elif audio_count:
        log_message(
            f"{audio_count} of {len(videos)} videos have audio; "
            "inserting silence for clips without audio"
        )
    else:
        log_message("No original audio detected; inserting silence under the soundtrack")

    tracks = find_music(music_dir)
    if not tracks:
        raise ValueError(f"No MP3 files found in Disc 1 or Disc 2 under {music_dir}")
    log_message(f"Found {len(tracks)} soundtrack tracks")

    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="video-combiner-") as tmp:
        tmpdir = Path(tmp)
        music_list = tmpdir / "music.txt"
        video_list = tmpdir / "videos.txt"
        log_message("Writing concat lists")
        write_concat_list(videos, video_list)
        write_concat_list(tracks, music_list)
        log_message("Copying video stream without re-encoding")

        command = build_ffmpeg_command(
            video_list=video_list,
            videos=videos,
            audio_flags=audio_flags,
            durations=durations,
            music_list=music_list,
            output=output,
            original_volume=original_volume,
            music_volume=music_volume,
        )
        if dry_run:
            print(shlex.join(command), file=log)
            return command

        log_message("Running ffmpeg")
        subprocess.run(command, check=True)
        log_message(f"Output: {output}")
        return command


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge chronological MP4 videos and overlay Frieren soundtrack music."
    )
    parser.add_argument("input_dir", type=Path, help="Directory containing MP4 files")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("merged_video.mp4"),
        help="Output MP4 path (default: merged_video.mp4)",
    )
    parser.add_argument(
        "--music-dir",
        type=Path,
        default=DEFAULT_MUSIC_DIR,
        help=f"Soundtrack root containing Disc 1 and Disc 2 (default: {DEFAULT_MUSIC_DIR})",
    )
    parser.add_argument(
        "--original-volume",
        type=float,
        default=0.2,
        help="Original video audio volume multiplier (default: 0.2)",
    )
    parser.add_argument(
        "--music-volume",
        type=float,
        default=0.85,
        help="Background music volume multiplier (default: 0.85)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the ffmpeg command without creating the output",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress wrapper progress logs. ffmpeg will still print its own output.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        merge_videos(
            input_dir=args.input_dir,
            output=args.output,
            music_dir=args.music_dir,
            original_volume=args.original_volume,
            music_volume=args.music_volume,
            dry_run=args.dry_run,
            quiet=args.quiet,
        )
    except (subprocess.CalledProcessError, ValueError) as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
