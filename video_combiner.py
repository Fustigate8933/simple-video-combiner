#!/usr/bin/env python3
"""Merge camera MP4 files and mix in background music with ffmpeg."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence, TextIO


DEFAULT_MUSIC_DIR = Path(
    "/mnt/ianch-Secondary/Downloads/Compressed/"
    "Frieren Beyond Journey's End Original Soundtrack [MP3]"
)
VIDEO_EXTENSIONS = {".mp4"}
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}


@dataclass(frozen=True)
class MediaItem:
    path: Path
    kind: str


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
    working_dir: Path | None = None


def set_mtime(path: Path, timestamp: float) -> None:
    """Set access and modification time; used by tests and harmless for callers."""
    os.utime(path, (timestamp, timestamp))


def find_videos(input_dir: Path) -> list[Path]:
    """Return top-level MP4 files in chronological camera order."""
    if not input_dir.is_dir():
        raise ValueError(f"Input directory does not exist: {input_dir}")

    videos = [path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() == ".mp4"]
    return sorted(videos, key=lambda path: (path.stat().st_mtime, path.name.lower()))


def find_media(input_dir: Path) -> list[MediaItem]:
    """Return top-level videos and photos in chronological camera order."""
    if not input_dir.is_dir():
        raise ValueError(f"Input directory does not exist: {input_dir}")

    media: list[MediaItem] = []
    for path in input_dir.iterdir():
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in VIDEO_EXTENSIONS:
            media.append(MediaItem(path, "video"))
        elif suffix in PHOTO_EXTENSIONS:
            media.append(MediaItem(path, "photo"))

    return sorted(media, key=lambda item: (item.path.stat().st_mtime, item.path.name.lower()))


def find_music(music_dir: Path) -> list[Path]:
    """Return MP3 tracks from music_dir and its immediate subdirectories."""
    if not music_dir.is_dir():
        raise ValueError(f"Music directory does not exist: {music_dir}")

    tracks: list[Path] = []
    for path in music_dir.iterdir():
        if path.is_file() and path.suffix.lower() == ".mp3":
            tracks.append(path)
        elif path.is_dir():
            tracks.extend(
                child
                for child in path.iterdir()
                if child.is_file() and child.suffix.lower() == ".mp3"
            )

    return sorted(
        tracks,
        key=lambda path: tuple(part.lower() for part in path.relative_to(music_dir).parts),
    )


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
            media_items=[
                MediaItem(Path(item.path.name), item.kind)
                for item in media_items
            ],
            audio_flags=media_audio_flags,
            durations=media_durations,
            music_list=music_list,
            output=output,
            original_volume=original_volume,
            music_volume=music_volume,
        )
        command = externalize_filter_complex(command, temp_dir / "render-filter.txt")
        working_dir = input_dir
    else:
        messages.append("Writing concat lists")
        write_concat_list(videos, video_list)
        messages.append("Copying video stream without re-encoding")
        command = build_ffmpeg_command(
            video_list=video_list,
            videos=[Path(video.name) for video in videos],
            audio_flags=audio_flags,
            durations=video_durations,
            music_list=music_list,
            output=output,
            original_volume=original_volume,
            music_volume=music_volume,
        )
        command = externalize_filter_complex(command, temp_dir / "audio-filter.txt")
        working_dir = input_dir

    return PreparedMerge(
        command=command,
        messages=messages,
        summary=ScanSummary(
            mp4_count=len(videos),
            image_count=len(photos),
            music_count=len(tracks),
        ),
        working_dir=working_dir,
    )


def quote_for_concat_file(path: Path) -> str:
    """Quote a path for ffmpeg concat demuxer list files."""
    normalized = path.resolve().as_posix()
    return "'" + normalized.replace("'", "'\\''") + "'"


def write_concat_list(paths: Iterable[Path], output: Path) -> None:
    lines = [f"file {quote_for_concat_file(path)}\n" for path in paths]
    output.write_text("".join(lines), encoding="utf-8")


def run_checked(command: Sequence[str], **kwargs) -> subprocess.CompletedProcess[str]:
    try:
        kwargs.setdefault("check", True)
        return subprocess.run(command, **kwargs)
    except FileNotFoundError as exc:
        tool = command[0]
        raise ValueError(
            f"{tool} not found. Install ffmpeg and ensure ffmpeg and ffprobe are on PATH."
        ) from exc


def has_audio_stream(video: Path) -> bool:
    result = run_checked(
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
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def get_duration(video: Path) -> float:
    result = run_checked(
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

    if videos and all(audio_flags):
        return [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(video_list),
            "-stream_loop",
            "-1",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(music_list),
            "-filter_complex",
            (
                f"[0:a:0]volume={original_volume},"
                "aformat=sample_rates=48000:channel_layouts=stereo,"
                "asetpts=PTS-STARTPTS[original];"
                f"[1:a:0]volume={music_volume}[music];"
                "[original][music]amix=inputs=2:duration=first:dropout_transition=2[a]"
            ),
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


def externalize_filter_complex(command: list[str], script_path: Path) -> list[str]:
    if "-filter_complex" not in command:
        return command

    next_command = list(command)
    index = next_command.index("-filter_complex")
    filter_complex = next_command[index + 1]
    script_path.write_text(filter_complex, encoding="utf-8")
    next_command[index:index + 2] = ["-filter_complex_script", str(script_path)]
    return next_command


def build_rendered_ffmpeg_command(
    *,
    media_items: Sequence[MediaItem],
    audio_flags: Sequence[bool],
    durations: Sequence[float],
    music_list: Path,
    output: Path,
    original_volume: float,
    music_volume: float,
) -> list[str]:
    if not (len(media_items) == len(audio_flags) == len(durations)):
        raise ValueError("media_items, audio_flags, and durations must have the same length")

    command = ["ffmpeg", "-y"]
    for item, duration in zip(media_items, durations):
        if item.kind == "photo":
            command.extend(["-loop", "1", "-t", f"{duration:g}", "-i", str(item.path)])
        else:
            command.extend(["-i", str(item.path)])
    command.extend(["-stream_loop", "-1", "-f", "concat", "-safe", "0", "-i", str(music_list)])

    filter_parts: list[str] = []
    concat_inputs: list[str] = []
    for index, (item, has_audio, duration) in enumerate(zip(media_items, audio_flags, durations)):
        filter_parts.append(
            (
                f"[{index}:v:0]scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
                "setsar=1,fps=30,format=yuv420p,"
                f"trim=duration={duration:g},setpts=PTS-STARTPTS[v{index}]"
                if item.kind == "photo"
                else
                f"[{index}:v:0]scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
                f"setsar=1,fps=30,format=yuv420p,setpts=PTS-STARTPTS[v{index}]"
            )
        )

        if has_audio:
            filter_parts.append(
                f"[{index}:a:0]volume={original_volume},"
                "aformat=sample_rates=48000:channel_layouts=stereo,"
                f"asetpts=PTS-STARTPTS[a{index}]"
            )
        else:
            filter_parts.append(
                "anullsrc=channel_layout=stereo:"
                f"sample_rate=48000:d={duration:g}[a{index}]"
            )
        concat_inputs.extend([f"[v{index}]", f"[a{index}]"])

    music_index = len(media_items)
    filter_parts.extend(
        [
            "".join(concat_inputs) + f"concat=n={len(media_items)}:v=1:a=1:unsafe=1[v][original]",
            f"[{music_index}:a:0]volume={music_volume}[music]",
            "[original][music]amix=inputs=2:duration=first:dropout_transition=2[a]",
        ]
    )

    command.extend(
        [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
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
    photo_duration: float = 7.0,
    dry_run: bool = False,
    quiet: bool = False,
    log: TextIO = sys.stdout,
) -> list[str]:
    def log_message(message: str) -> None:
        if not quiet:
            print(message, file=log)

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

        output.parent.mkdir(parents=True, exist_ok=True)
        log_message("Running ffmpeg")
        run_checked(prepared.command, cwd=prepared.working_dir)
        log_message(f"Output: {output}")
        return prepared.command


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
        help=f"Soundtrack root scanned for MP3 files one directory deep (default: {DEFAULT_MUSIC_DIR})",
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
        "--photo-duration",
        type=float,
        default=7.0,
        help="Seconds each photo should appear in the output (default: 7)",
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
            photo_duration=args.photo_duration,
            dry_run=args.dry_run,
            quiet=args.quiet,
        )
    except (subprocess.CalledProcessError, ValueError) as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
