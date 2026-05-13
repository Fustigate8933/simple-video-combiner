# Video Combiner

Simple command-line video editor for merging camera MP4 files and photos in
chronological order and overlaying background music.

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

The program reads MP4 videos plus JPG, JPEG, and PNG photos from the input
directory. It orders all media together by modification time, then filename.
Photos appear for 7 seconds by default.

The program reads MP3 tracks directly inside the music directory and inside its
immediate subdirectories. It loops that soundtrack playlist for the full
merged-video length, lowers the original video audio to 20%, and mixes the
background music at 85%. Photos and MP4s with no audio contribute silence to
the original-audio timeline, while the background music still spans the whole
merged video.

Video is stream-copied by default with `-c:v copy`, so the source video frames
are not re-encoded and do not lose quality. Only the final mixed audio track is
encoded. The output is not written with `+faststart`, because on very large
files that option adds a long final metadata-moving pass.

If photos are present, the output timeline must be rendered so still images can
become video frames. In that case the program encodes video with `libx264`.

Useful options:

```bash
python video_combiner.py /path/to/videos \
  --output final.mp4 \
  --photo-duration 7 \
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

If photos are present, the video-copy line is replaced by:

```text
Found 3 photo files
Rendering timeline because photos are present
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

If `npm install` fails because of a broken local npm cache or shell resolution,
this environment worked with:

```bash
npm_config_script_shell=/usr/bin/sh npm install --cache /tmp/kiwi-merge-npm-cache
```

Run the desktop app in development:

```bash
npm run app:dev
```

The Electron main process starts the FastAPI backend on `127.0.0.1:8765`.
The Vue renderer runs through Vite on `127.0.0.1:5173`.
