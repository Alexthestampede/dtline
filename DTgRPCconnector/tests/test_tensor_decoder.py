#!/usr/bin/env python3
"""Regression tests for the CCV tensor decoder (no server required).

Run directly:
    python tests/test_tensor_decoder.py
"""

import struct
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tensor_decoder import decode_tensor, tensor_to_pil  # noqa: E402

HEADER_SIZE = 68
CCV_TENSOR_CPU_MEMORY = 0x1
CCV_TENSOR_FORMAT_NHWC = 0x02
CCV_16F = 0x20000


def make_tensor(channels, height=4, width=4, pixel=None):
    """Build an uncompressed float16 CCV tensor with every pixel set to ``pixel``.

    ``pixel`` is in the wire channel order: RGB for 3 channels, ARGB for 4.
    """
    header = bytearray(HEADER_SIZE)
    struct.pack_into("<I", header, 0, 0)  # uncompressed
    struct.pack_into("<I", header, 4, CCV_TENSOR_CPU_MEMORY)
    struct.pack_into("<I", header, 8, CCV_TENSOR_FORMAT_NHWC)
    struct.pack_into("<I", header, 12, CCV_16F)
    struct.pack_into("<I", header, 20, 1)  # batch
    struct.pack_into("<I", header, 24, height)
    struct.pack_into("<I", header, 28, width)
    struct.pack_into("<I", header, 32, channels)

    values = np.zeros((height, width, channels), dtype=np.float16)
    if pixel is not None:
        for index, value in enumerate(pixel):
            values[:, :, index] = value
    return bytes(header) + values.tobytes()


class TensorDecodeTests(unittest.TestCase):
    def test_three_channel_tensor_is_rgb(self):
        tensor = make_tensor(3, pixel=(1.0, -1.0, -1.0))  # red
        image = tensor_to_pil(tensor)
        self.assertEqual(image.mode, "RGB")
        self.assertEqual(image.getpixel((0, 0)), (255, 0, 0))

    def test_four_channel_argb_is_normalized_to_rgba(self):
        # ARGB: opaque red (alpha first).
        tensor = make_tensor(4, pixel=(1.0, 1.0, -1.0, -1.0))
        image = tensor_to_pil(tensor)
        self.assertEqual(image.mode, "RGBA")
        self.assertEqual(image.getpixel((0, 0)), (255, 0, 0, 255))

        array, width, height, channels = decode_tensor(tensor)
        self.assertEqual((width, height, channels), (4, 4, 4))
        self.assertEqual(tuple(array[0, 0]), (255, 0, 0, 255))

    def test_four_channel_alpha_is_preserved(self):
        # ARGB: fully transparent blue.
        tensor = make_tensor(4, pixel=(-1.0, -1.0, -1.0, 1.0))
        image = tensor_to_pil(tensor)
        self.assertEqual(image.mode, "RGBA")
        self.assertEqual(image.getpixel((0, 0)), (0, 0, 255, 0))

    def test_decode_tensor_returns_uint8(self):
        tensor = make_tensor(3, pixel=(0.0, 0.0, 0.0))
        array, _width, _height, _channels = decode_tensor(tensor)
        self.assertEqual(array.dtype, np.uint8)
        self.assertEqual(tuple(array[0, 0]), (127, 127, 127))


if __name__ == "__main__":
    unittest.main()
