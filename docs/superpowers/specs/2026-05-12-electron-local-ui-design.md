# Electron Local UI Design

## Goal

Turn the existing CLI video combiner into a local desktop app that can be distributed across Windows, macOS, and Linux. Version 1 will not bundle Python or ffmpeg; users must have Python 3.10+ and `ffmpeg`/`ffprobe` available on `PATH`. The architecture should still leave a clean path to bundling a Python executable and ffmpeg binaries later.

## Users And Context

The app is for people combining camera videos and photos into one output file with background music. They should not need to remember CLI flags or inspect terminal output. The interface should feel calm, minimal, and practical, with light kiwi-green accents used for state, primary actions, and subtle visual warmth.

## Product Scope

The app will support:

- Selecting a source directory.
- Selecting an output MP4 file path.
- Selecting a music directory.
- Configuring photo duration, original audio volume, and music volume.
- Scanning the selected folders and showing detected MP4, image, and music-track counts.
- Starting a merge job.
- Viewing live progress and logs.
- Running a dry run to inspect the generated ffmpeg command.
- Cancelling an active job when possible.

Version 1 will not include bundled runtimes, project presets, drag-and-drop timelines, media previews, batch queues, or advanced ffmpeg profile editing.

## Architecture

Use an Electron desktop shell with a Vue 3 + Tailwind CSS renderer and a FastAPI backend.

Electron main process responsibilities:

- Own native app lifecycle.
- Open native file and directory picker dialogs.
- Start the FastAPI backend as a local subprocess during development and v1 distribution.
- Wait for backend `/health` before loading the UI.
- Stop the backend when the app exits.
- Later, switch from launching `python backend/main.py` to launching a bundled backend executable without changing the Vue UI.

Vue renderer responsibilities:

- Render the compact Kiwi control-panel UI.
- Store the current form state.
- Call backend endpoints for scanning, dry runs, jobs, status, logs, and cancellation.
- Use Electron IPC only for native dialogs and app-level concerns.

FastAPI backend responsibilities:

- Provide a small HTTP API around the existing `video_combiner.py` functions.
- Reuse `find_media`, `find_music`, command building, and merge behavior instead of duplicating ffmpeg logic.
- Manage one active merge job at a time for v1.
- Capture wrapper logs and ffmpeg output into a job log buffer.
- Expose job status and Server-Sent Events for live UI updates.

## API Design

`GET /health`

- Returns backend readiness and basic dependency status if cheap to determine.

`POST /scan`

- Input: `source_dir`, `music_dir`.
- Returns: `mp4_count`, `image_count`, `music_count`, and any validation errors.
- Uses the same media and music detection rules as the CLI.

`POST /dry-run`

- Input: all merge options.
- Returns the generated ffmpeg command as a string/list plus the same scan summary.
- Does not create output.

`POST /jobs`

- Input: all merge options.
- Starts a merge job if no job is running.
- Returns `job_id`.

`GET /jobs/{job_id}`

- Returns current status: `queued`, `running`, `succeeded`, `failed`, or `cancelled`, plus recent logs and coarse progress state.

`GET /jobs/{job_id}/events`

- Streams log and status updates over SSE.

`POST /jobs/{job_id}/cancel`

- Requests cancellation. The backend should terminate the active ffmpeg process where possible and mark the job cancelled.

## UI Design

Use the approved compact control-panel layout from the visual companion.

Desktop layout:

- Header with app name, short status text, and readiness indicator.
- Left column for path selectors and merge options.
- Right column for detected counts, progress, and logs.
- Primary `Start merge` button, secondary `Dry run` and `Rescan` buttons.

Responsive layout:

- Collapse to a single column on narrow windows.
- Keep controls at stable sizes and prevent path text from overflowing.
- Keep touch/click targets at least 44px high where practical.

Visual direction:

- Light neutral surfaces tinted slightly green.
- Kiwi-green accents for primary actions, progress, and success states.
- Restrained borders, small-radius cards, and clear hierarchy.
- Avoid heavy decoration, dark dashboard styling, and overuse of green.

Motion and feedback:

- Subtle 150-250ms transitions for hover, focus, disabled, and loading states.
- Progress bar should update smoothly.
- Buttons should visibly respond to click and loading states.
- Respect `prefers-reduced-motion`.

## Error Handling

The UI should show clear, actionable errors for:

- Missing source directory.
- Missing music directory.
- No supported media found.
- No MP3 files found.
- ffmpeg or ffprobe missing from `PATH`.
- Backend failed to start.
- Merge failed or was cancelled.

Backend errors should return structured JSON with a short user-facing message and optional technical detail for logs.

## Progress And Logs

The existing script already emits high-level progress messages. The backend will capture those messages and ffmpeg output. For v1, progress may be coarse:

- `scanning`
- `preparing`
- `running ffmpeg`
- `succeeded`
- `failed`
- `cancelled`

If ffmpeg progress parsing is straightforward during implementation, the app can show approximate percentage. Otherwise it will show an indeterminate running state plus live logs.

## Testing

Backend tests:

- Scan counts for MP4, JPG/JPEG/PNG, and MP3 files.
- Validation errors for missing directories and empty directories.
- Dry-run command generation through the API.
- Job state transitions for success and failure using mocked merge execution.
- UTF-8 paths in API payloads and concat-list generation.

Frontend tests:

- Form validation and disabled states.
- Scan summary rendering.
- Job status and log rendering.
- Error message rendering.

Integration/manual verification:

- Start the dev Electron app.
- Pick source, output, and music paths.
- Confirm counts render.
- Run dry run.
- Run a merge with mocked or small real media when available.

## Distribution Plan

Version 1 distribution assumes local prerequisites:

- Python 3.10+ installed.
- Backend dependencies installed.
- ffmpeg and ffprobe installed and available on `PATH`.

Later bundling path:

- Package the FastAPI backend as a platform-specific executable with PyInstaller.
- Bundle platform-specific ffmpeg and ffprobe binaries.
- Update Electron backend launch and environment configuration.
- Add per-platform build, signing, and notarization steps.
