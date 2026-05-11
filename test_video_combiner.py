import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import video_combiner


class VideoCombinerTests(unittest.TestCase):
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

    def test_finds_mp3_music_from_disc_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            disc1 = root / "Disc 1"
            disc2 = root / "Disc 2"
            misc = root / "Other"
            disc1.mkdir()
            disc2.mkdir()
            misc.mkdir()

            track_b = disc1 / "02.mp3"
            track_a = disc1 / "01.mp3"
            track_c = disc2 / "01.mp3"
            ignored = misc / "01.mp3"

            for path in (track_b, track_a, track_c, ignored):
                path.write_text("x")

            self.assertEqual(
                video_combiner.find_music(root),
                [track_a, track_b, track_c],
            )

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
