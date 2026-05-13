import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import video_combiner


class VideoCombinerTests(unittest.TestCase):
    def test_finds_media_files_by_mtime_then_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video1 = root / "DJI_0001.MP4"
            photo = root / "DJI_0002.JPG"
            video2 = root / "DJI_0003.mp4"
            ignored = root / "DJI_0004.txt"

            for path in (video2, photo, video1, ignored):
                path.write_text("x")

            video_combiner.set_mtime(video1, 100)
            video_combiner.set_mtime(photo, 200)
            video_combiner.set_mtime(video2, 300)

            media = video_combiner.find_media(root)
            self.assertEqual([item.path for item in media], [video1, photo, video2])
            self.assertEqual([item.kind for item in media], ["video", "photo", "video"])

    def test_finds_mp4_files_by_mtime_then_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "CAM_0001.mp4"
            second_a = root / "CAM_0002.mp4"
            second_b = root / "CAM_0003.mp4"
            ignored = root / "notes.txt"

            for path in (second_b, second_a, first, ignored):
                path.write_text("x")

            video_combiner.set_mtime(first, 100)
            video_combiner.set_mtime(second_b, 200)
            video_combiner.set_mtime(second_a, 200)

            self.assertEqual(
                video_combiner.find_videos(root),
                [first, second_a, second_b],
            )

    def test_finds_mp3_music_from_root_and_one_subdirectory_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            album = root / "Album"
            other = root / "Other"
            deep = album / "Deep"
            album.mkdir()
            other.mkdir()
            deep.mkdir()

            root_track = root / "00.mp3"
            album_track_b = album / "02.mp3"
            album_track_a = album / "01.mp3"
            other_track = other / "01.mp3"
            deep_ignored = deep / "01.mp3"

            for path in (album_track_b, album_track_a, other_track, root_track, deep_ignored):
                path.write_text("x")

            self.assertEqual(
                video_combiner.find_music(root),
                [root_track, album_track_a, album_track_b, other_track],
            )

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

    def test_writes_ffmpeg_concat_list_with_escaped_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "list.txt"
            video_combiner.write_concat_list(
                [Path("/tmp/plain.mp4"), Path("/tmp/it's fine.mp4")],
                output,
            )

            self.assertEqual(
                output.read_text(),
                "file '/tmp/plain.mp4'\nfile '/tmp/it'\\''s fine.mp4'\n",
            )

    def test_writes_ffmpeg_concat_list_as_utf8(self):
        output = Path("/tmp/清單.txt")
        video = Path("/tmp/影片一.mp4")

        with patch.object(Path, "write_text", autospec=True) as write_text:
            video_combiner.write_concat_list([video], output)

        write_text.assert_called_once_with(
            output,
            f"file '{video.resolve()}'\n",
            encoding="utf-8",
        )

    def test_gets_video_duration_with_ffprobe(self):
        with patch("subprocess.run") as run:
            run.return_value.stdout = "12.345000\n"

            self.assertEqual(video_combiner.get_duration(Path("/tmp/video.mp4")), 12.345)

        self.assertIn("-show_entries", run.call_args.args[0])
        self.assertIn("format=duration", run.call_args.args[0])

    def test_builds_ffmpeg_command_with_silence_for_video_without_audio(self):
        cmd = video_combiner.build_ffmpeg_command(
            video_list=Path("/tmp/videos.txt"),
            videos=[Path("/tmp/clip1.mp4"), Path("/tmp/clip2.mp4")],
            audio_flags=[False, True],
            durations=[4.5, 6.0],
            music_list=Path("/tmp/music.txt"),
            output=Path("/tmp/out.mp4"),
            original_volume=0.2,
            music_volume=0.85,
        )

        filter_complex = cmd[cmd.index("-filter_complex") + 1]
        self.assertEqual(
            cmd,
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                "/tmp/videos.txt",
                "-i",
                "/tmp/clip1.mp4",
                "-i",
                "/tmp/clip2.mp4",
                "-stream_loop",
                "-1",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                "/tmp/music.txt",
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
                "/tmp/out.mp4",
            ],
        )
        self.assertIn(
            "anullsrc=channel_layout=stereo:sample_rate=48000:d=4.5[a0]",
            filter_complex,
        )
        self.assertIn(
            "[2:a:0]volume=0.2,aformat=sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS[a1]",
            filter_complex,
        )
        self.assertIn("[a0][a1]concat=n=2:v=0:a=1[original]", filter_complex)
        self.assertIn("[3:a:0]volume=0.85[music]", filter_complex)
        self.assertIn("[original][music]amix=inputs=2:duration=first:dropout_transition=2[a]", filter_complex)

    def test_builds_rendered_command_for_interleaved_photo_timeline(self):
        items = [
            video_combiner.MediaItem(Path("/tmp/video1.mp4"), "video"),
            video_combiner.MediaItem(Path("/tmp/photo1.jpg"), "photo"),
            video_combiner.MediaItem(Path("/tmp/video2.mp4"), "video"),
        ]

        cmd = video_combiner.build_rendered_ffmpeg_command(
            media_items=items,
            audio_flags=[True, False, False],
            durations=[3.0, 7.0, 4.0],
            music_list=Path("/tmp/music.txt"),
            output=Path("/tmp/out.mp4"),
            original_volume=0.2,
            music_volume=0.85,
        )

        filter_complex = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("-loop", cmd)
        self.assertIn("/tmp/photo1.jpg", cmd)
        self.assertIn("[1:v:0]scale=1920:1080:force_original_aspect_ratio=decrease", filter_complex)
        self.assertIn("pad=1920:1080:(ow-iw)/2:(oh-ih)/2", filter_complex)
        self.assertIn("trim=duration=7", filter_complex)
        self.assertIn("anullsrc=channel_layout=stereo:sample_rate=48000:d=7[a1]", filter_complex)
        self.assertIn(
            "[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1:unsafe=1[v][original]",
            filter_complex,
        )
        self.assertEqual(cmd[cmd.index("-map") + 1], "[v]")
        self.assertEqual(cmd[cmd.index("-c:v") + 1], "libx264")

    def test_detects_audio_stream_with_ffprobe(self):
        with patch("subprocess.run") as run:
            run.return_value.stdout = "0\n"

            self.assertTrue(video_combiner.has_audio_stream(Path("/tmp/video.mp4")))

        self.assertIn("-select_streams", run.call_args.args[0])
        self.assertIn("a", run.call_args.args[0])

    def test_detects_missing_audio_stream_with_ffprobe(self):
        with patch("subprocess.run") as run:
            run.return_value.stdout = ""

            self.assertFalse(video_combiner.has_audio_stream(Path("/tmp/video.mp4")))

    def test_merge_logs_progress_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            videos = root / "videos"
            music = root / "music"
            videos.mkdir()
            (music / "Disc 1").mkdir(parents=True)
            (music / "Disc 2").mkdir()

            (videos / "CAM_0001.mp4").write_text("x")
            (videos / "CAM_0002.mp4").write_text("x")
            (music / "Disc 1" / "01.mp3").write_text("x")
            (music / "Disc 2" / "01.mp3").write_text("x")

            log = StringIO()
            with (
                patch("video_combiner.has_audio_stream", return_value=True),
                patch("video_combiner.get_duration", return_value=10.0),
                patch("subprocess.run") as run,
            ):
                video_combiner.merge_videos(
                    input_dir=videos,
                    output=root / "out.mp4",
                    music_dir=music,
                    log=log,
                )

            self.assertEqual(run.call_count, 1)
            self.assertIn("Found 2 MP4 files", log.getvalue())
            self.assertIn("Copying video stream without re-encoding", log.getvalue())
            self.assertIn("Found 2 soundtrack tracks", log.getvalue())
            self.assertIn("Writing concat lists", log.getvalue())
            self.assertIn("Running ffmpeg", log.getvalue())
            self.assertIn(f"Output: {root / 'out.mp4'}", log.getvalue())

    def test_merge_does_not_create_output_parent_when_inputs_are_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "missing-parent" / "out.mp4"

            with self.assertRaises(ValueError):
                video_combiner.merge_videos(
                    input_dir=root / "missing-videos",
                    output=output,
                    music_dir=root / "missing-music",
                )

            self.assertFalse(output.parent.exists())

    def test_merge_uses_rendered_timeline_when_photos_are_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "media"
            music = root / "music"
            media.mkdir()
            (music / "Disc 1").mkdir(parents=True)

            video = media / "CAM_0001.mp4"
            photo = media / "CAM_0002.jpg"
            video.write_text("x")
            photo.write_text("x")
            (music / "Disc 1" / "01.mp3").write_text("x")
            video_combiner.set_mtime(video, 100)
            video_combiner.set_mtime(photo, 200)

            log = StringIO()
            with (
                patch("video_combiner.has_audio_stream", return_value=True),
                patch("video_combiner.get_duration", return_value=3.0),
                patch("subprocess.run") as run,
            ):
                video_combiner.merge_videos(
                    input_dir=media,
                    output=root / "out.mp4",
                    music_dir=music,
                    photo_duration=7.0,
                    log=log,
                )

            command = run.call_args.args[0]
            self.assertIn("-loop", command)
            self.assertEqual(command[command.index("-c:v") + 1], "libx264")
            self.assertIn("Found 1 photo files", log.getvalue())
            self.assertIn("Rendering timeline because photos are present", log.getvalue())

    def test_merge_inserts_silence_when_any_video_lacks_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            videos = root / "videos"
            music = root / "music"
            videos.mkdir()
            (music / "Disc 1").mkdir(parents=True)

            (videos / "CAM_0001.mp4").write_text("x")
            (videos / "CAM_0002.mp4").write_text("x")
            (music / "Disc 1" / "01.mp3").write_text("x")

            log = StringIO()
            with (
                patch("video_combiner.has_audio_stream", side_effect=[False, True]),
                patch("video_combiner.get_duration", side_effect=[4.5, 6.0]),
                patch("subprocess.run") as run,
            ):
                video_combiner.merge_videos(
                    input_dir=videos,
                    output=root / "out.mp4",
                    music_dir=music,
                    log=log,
                )

            command = run.call_args.args[0]
            filter_complex = command[command.index("-filter_complex") + 1]
            self.assertIn("anullsrc=channel_layout=stereo:sample_rate=48000:d=4.5[a0]", filter_complex)
            self.assertIn(
                "[2:a:0]volume=0.2,aformat=sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS[a1]",
                filter_complex,
            )
            self.assertIn("1 of 2 videos have audio; inserting silence for clips without audio", log.getvalue())

    def test_quiet_merge_suppresses_wrapper_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            videos = root / "videos"
            music = root / "music"
            videos.mkdir()
            (music / "Disc 1").mkdir(parents=True)

            (videos / "CAM_0001.mp4").write_text("x")
            (music / "Disc 1" / "01.mp3").write_text("x")

            log = StringIO()
            with (
                patch("video_combiner.has_audio_stream", return_value=False),
                patch("video_combiner.get_duration", return_value=10.0),
                patch("subprocess.run"),
            ):
                video_combiner.merge_videos(
                    input_dir=videos,
                    output=root / "out.mp4",
                    music_dir=music,
                    log=log,
                    quiet=True,
                )

            self.assertEqual(log.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
