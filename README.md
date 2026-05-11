# Video Combiner

Simple command-line video editor for merging camera MP4 files in chronological
order and overlaying background music.

## Requirements

- Python 3.10+
- `ffmpeg` available on `PATH`

## Usage

```bash
python video_combiner.py /path/to/video-directory -o merged_video.mp4
```

By default, background music is loaded from:

```text
/mnt/ianch-Secondary/Downloads/Compressed/Frieren Beyond Journey's End Original Soundtrack [MP3]/
```

The program reads MP3 tracks from `Disc 1` and `Disc 2`, loops that soundtrack
playlist for the full merged-video length, lowers the original video audio to
20%, and mixes the background music at 85%. If an input MP4 has no audio stream,
that clip contributes silence to the original-audio timeline, while the
background music still spans the whole merged video.

Video is stream-copied by default with `-c:v copy`, so the source video frames
are not re-encoded and do not lose quality. Only the final mixed audio track is
encoded. The output is not written with `+faststart`, because on very large
files that option adds a long final metadata-moving pass.

Useful options:

```bash
python video_combiner.py /path/to/videos \
  --output final.mp4 \
  --original-volume 0.2 \
  --music-volume 0.85
```

During a normal run, the wrapper prints high-level progress:

```text
Found 12 MP4 files
Found 68 soundtrack tracks
Writing concat lists
Copying video stream without re-encoding
Running ffmpeg
Output: final.mp4
```

`ffmpeg` also prints its own encoding progress while it runs. To suppress only
the wrapper progress lines:

```bash
python video_combiner.py /path/to/videos --quiet
```

Preview the generated `ffmpeg` command without producing a video:

```bash
python video_combiner.py /path/to/videos --dry-run
```
