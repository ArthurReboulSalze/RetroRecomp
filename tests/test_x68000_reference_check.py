"""Check campaign acceptance using authored synthetic traces and reports."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools import x68000_reference_check as check


def report(frames=2):
    return {"mode": "interpreted-reference", "native_cpu": False,
            "cpu_mhz": 10, "ram_mib": 2, "core_error": False,
            "fixed_rtc_epoch": 946684800, "frames": frames,
            "video_frames": 1, "nonblack_frames": 1, "audio_samples": 10,
            "width": 256, "height": 256, "fps": 55.46, "sample_rate": 44100,
            "nonzero_samples": 8, "final_video_fnv64": "1" * 16,
            "pcm_fnv64": "2" * 16, "ram_fnv64": "3" * 16, "cpu": [0] * 18}


def trace():
    return ("\t".join(check.TRACE_COLUMNS) + "\n" + "\n".join(
        "\t".join([str(frame), "1" * 16, "2" * 16, "3" * 16,
                   "5", "256", "256"] + ["00000000"] * 18)
        for frame in range(2)) + "\n")


class X68000ReferenceCheckTests(unittest.TestCase):
    def test_cases_are_bounded_and_replay_inputs_match(self):
        cases = check.cases()
        self.assertEqual([case.frames for case in cases], [1200, 1800, 4000, 4000])
        self.assertEqual(cases[2].events, cases[3].events)
        self.assertEqual(cases[1].events,
                         ((1000, 1008, "key", 13, 1), (1200, 1208, "key", 32, 1)))
        for case in cases:
            self.assertLessEqual(case.frames, 36000)
            for begin, end, kind, identifier, value in case.events:
                self.assertTrue(0 <= begin < end <= case.frames)
                self.assertIn(kind, ("key", "joy"))
                self.assertEqual(value, 1)
                if kind == "joy":
                    self.assertNotIn(identifier, (2, 12, 13, 14, 15))

    def test_exact_replay_comparison_catches_every_state_column(self):
        with TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "a.tsv", Path(tmp) / "b.tsv"
            first.write_text(trace(), encoding="ascii")
            second.write_text(trace(), encoding="ascii")
            self.assertTrue(check.compare_traces(first, second)["identical"])
            self.assertEqual(check.validate_trace(first, 2)["audio_samples"], 10)
            for index in range(1, len(check.TRACE_COLUMNS)):
                rows = trace().splitlines()
                fields = rows[2].split("\t")
                fields[index] = "1" if index in (4, 5, 6) else "f" * len(fields[index])
                rows[2] = "\t".join(fields)
                second.write_text("\n".join(rows) + "\n", encoding="ascii")
                difference = check.compare_traces(first, second)
                self.assertFalse(difference["identical"], check.TRACE_COLUMNS[index])
                self.assertEqual(difference["first_different_frame"], 1)

    def test_truncated_malformed_and_nonsequential_traces_fail(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.tsv"
            invalid = ("", trace().replace("video", "wrong", 1),
                       "\n".join(trace().splitlines()[:-1]) + "\n",
                       trace().replace("\n1\t", "\n2\t"),
                       trace().replace("1" * 16, "z" * 16, 1))
            for content in invalid:
                path.write_text(content, encoding="ascii")
                with self.assertRaises(ValueError):
                    check.validate_trace(path, 2)

    def test_report_requires_completed_configured_cpu_and_audible_gameplay(self):
        check.validate_report(report(), 2, audible=True)
        for key, value in (("native_cpu", True), ("frames", 1), ("ram_mib", 4),
                           ("cpu_mhz", 16), ("core_error", True), ("nonzero_samples", 0),
                           ("video_frames", 0), ("audio_samples", 0),
                           ("cpu", [0]), ("fps", float("nan"))):
            changed = report()
            changed[key] = value
            with self.assertRaises(ValueError, msg=key):
                check.validate_report(changed, 2, audible=True)
        silent = report()
        silent["nonzero_samples"] = 0
        check.validate_report(silent, 2, audible=False)


if __name__ == "__main__":
    unittest.main()
