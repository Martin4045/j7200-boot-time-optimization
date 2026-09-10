#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location("profile", Path(__file__).with_name("spl-profile.py"))
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class ProfileTest(unittest.TestCase):
    def test_conventional(self):
        m = profile.decode(struct.pack(">12I", 0x53504C31, 0x3FF, *range(100, 1100, 100)))
        self.assertEqual(profile.intervals(m)["A72_SPL_C_STAGE_US"], 400)
        self.assertEqual(profile.intervals(m)["R5_IMAGE_LOADER_US"], 100)

    def test_semi_absent_is_not_zero_duration(self):
        m = profile.decode(struct.pack(">12I", 0x53504C31, 0x20F, *range(100, 1100, 100)))
        self.assertIsNone(profile.intervals(m)["A72_SPL_C_STAGE_US"])
        self.assertEqual(profile.intervals(m)["ARM64_REQUEST_TO_NEXT_C_ENTRY_US"], 600)

    def test_bad_header(self):
        for data in (b"", bytes(48)):
            with self.assertRaises(ValueError):
                profile.decode(data)

    def test_negative_interval(self):
        m = profile.decode(struct.pack(">12I", 0x53504C31, 0x3FF, *range(100, 1100, 100)))
        m["R5_LOAD_DONE_US"] = 1
        with self.assertRaises(ValueError):
            profile.intervals(m)


if __name__ == "__main__":
    unittest.main()
