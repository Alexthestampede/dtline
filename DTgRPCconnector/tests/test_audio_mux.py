#!/usr/bin/env python3
"""Regression tests for video audio muxing (no server required).

Covers the two failure modes found while shipping LTX/H3 video support:

1. ``-shortest`` with ``-c:v copy`` truncates the video tail because the AAC
   encoder lags. Measured on a 73-frame clip: 73 frames in, 70 out.
2. Raw ``-f f32le`` pipes break on odd byte counts / incomplete stereo frames
   and on NaN/Inf samples.

Run directly:
    python tests/test_audio_mux.py
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from drawthings_client import DrawThingsClient  # noqa: E402

FRAMES = 73
FPS = 24
RATE = 32000


def _ffprobe(path: Path) -> dict:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-count_frames",
            "-show_entries", "stream=codec_type,nb_read_frames,sample_rate",
            "-of", "default=noprint_wrappers=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    info, current = {}, None
    for line in out.splitlines():
        if line.startswith("codec_type="):
            current = line.split("=", 1)[1]
            info[current] = {}
        elif "=" in line and current:
            k, v = line.split("=", 1)
            info[current][k] = v
    return info


class AudioMuxTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.client = DrawThingsClient("127.0.0.1:1", insecure=True)

    def _frames_only_video(self) -> Path:
        import imageio

        path = self.dir / "frames.mp4"
        writer = imageio.get_writer(str(path), fps=FPS, codec="libx264")
        for i in range(FRAMES):
            writer.append_data(np.full((96, 128, 3), i * 3 % 255, dtype=np.uint8))
        writer.close()
        return path

    def test_mux_keeps_every_video_frame(self):
        """The AAC tail must not truncate the video (the -shortest bug)."""
        video = self._frames_only_video()
        audio = (
            0.2 * np.sin(np.arange(RATE * 3 * 2) / 10)
        ).astype(np.float32).tobytes()

        DrawThingsClient.mux_audio_into_video(
            str(video), audio, audio_sample_rate=RATE, video_duration=FRAMES / FPS
        )

        info = _ffprobe(video)
        self.assertEqual(int(info["video"]["nb_read_frames"]), FRAMES)
        self.assertEqual(int(info["audio"]["sample_rate"]), RATE)

    def test_mux_survives_nan_and_odd_sample_count(self):
        """NaN/Inf and an odd float count must not break the mux."""
        video = self._frames_only_video()
        clean = (0.2 * np.sin(np.arange(RATE * 3 * 2) / 10)).astype(np.float32)
        clean[::97] = np.nan
        clean[::193] = np.inf
        odd = clean[:-1]  # odd number of float32 samples

        DrawThingsClient.mux_audio_into_video(
            str(video),
            odd.tobytes(),
            audio_sample_rate=RATE,
            video_duration=FRAMES / FPS,
        )

        info = _ffprobe(video)
        self.assertEqual(int(info["video"]["nb_read_frames"]), FRAMES)

    def test_silent_audio_skips_mux_but_keeps_video(self):
        video = self._frames_only_video()
        silence = np.zeros(RATE * 3 * 2, dtype=np.float32).tobytes()

        DrawThingsClient.mux_audio_into_video(
            str(video), silence, audio_sample_rate=RATE, video_duration=FRAMES / FPS
        )

        info = _ffprobe(video)
        self.assertEqual(int(info["video"]["nb_read_frames"]), FRAMES)
        self.assertNotIn("audio", info)


if __name__ == "__main__":
    unittest.main(verbosity=2)
