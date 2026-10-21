"""Bounded, private X68000 reference boot/replay checks for stages 1 and 2.

Runs a supplied reference executable in four fresh bundles: authored fixture,
game title, gameplay, identical gameplay replay. CPU/RAM/video/PCM traces are
compared exactly. Captures require human inspection; no OCR or general hardware,
gameplay, AOT coverage, real-time performance, or physical-latency claim is made.
No private game, OS or firmware content is copied outside the requested fresh
work directory below this checkout's .build. No source media is modified.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.x68000_reference import prepare_bundle

TRACE_COLUMNS = (
    "frame", "video", "pcm", "ram", "samples", "width", "height", "PC", "SR",
    "D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7",
    "A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7",
)
HEX64 = re.compile(r"[0-9a-f]{16}\Z")
HEX32 = re.compile(r"[0-9a-f]{8}\Z")
HARDWARE_COLUMNS = ("guest_frames", "cpu_cycles", "peripheral_ticks", "lines",
                    "audio_pairs", "audio_errors", "max_audio_batch", "frame_budget")


@dataclass(frozen=True)
class Case:
    name: str
    fixture: bool
    frames: int
    events: tuple[tuple[int, int, str, int, int], ...] = ()


def cases() -> tuple[Case, ...]:
    gameplay = []
    for frame in range(2000, 3501, 200):
        gameplay.extend(((frame, frame + 8, "key", 13, 1),
                         (frame + 30, frame + 38, "key", 32, 1),
                         (frame + 60, frame + 68, "joy", 0, 1),
                         (frame + 90, frame + 98, "joy", 8, 1)))
    gameplay.extend(((2200, 2500, "joy", 0, 1),
                     (2200, 2300, "joy", 7, 1),
                     (2300, 2400, "joy", 5, 1),
                     (2400, 2500, "joy", 6, 1)))
    replay = tuple(sorted(gameplay))
    return (Case("fixture", True, 1200),
            Case("title", False, 1800,
                 ((1000, 1008, "key", 13, 1), (1200, 1208, "key", 32, 1))),
            Case("gameplay-a", False, 4000, replay),
            Case("gameplay-b", False, 4000, replay))


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True)
        stream.write("\n")


def validate_trace(path: Path, expected_frames: int) -> dict:
    """Validate every column/row before accepting an exact replay comparison."""
    digest_sets = {name: set() for name in ("video", "pcm", "ram", "PC")}
    samples = 0
    with path.open("r", encoding="ascii", newline="") as stream:
        header = stream.readline().rstrip("\r\n").split("\t")
        if header not in (list(TRACE_COLUMNS), list(TRACE_COLUMNS + HARDWARE_COLUMNS)):
            raise ValueError("Unexpected reference trace header.")
        count = 0
        for count, line in enumerate(stream, 1):
            values = line.rstrip("\r\n").split("\t")
            if len(values) != len(header):
                raise ValueError(f"Incomplete trace row {count}.")
            if values[0] != str(count - 1):
                raise ValueError(f"Nonsequential trace frame {count}.")
            if not all(HEX64.fullmatch(value) for value in values[1:4]):
                raise ValueError(f"Invalid trace hash at frame {count - 1}.")
            if not all(value.isdecimal() and value.isascii() for value in values[4:7]):
                raise ValueError(f"Invalid trace geometry/sample count at frame {count - 1}.")
            if not (0 < int(values[5]) <= 2048 and 0 < int(values[6]) <= 1536):
                # The first core frame can precede video initialization.
                if (count != 1 or values[5:7] != ["0", "0"]):
                    raise ValueError(f"Invalid trace dimensions at frame {count - 1}.")
            if not all(HEX32.fullmatch(value) for value in values[7:len(TRACE_COLUMNS)]):
                raise ValueError(f"Invalid CPU register at frame {count - 1}.")
            if not all(value.isascii() and value.isdecimal() for value in values[len(TRACE_COLUMNS):]):
                raise ValueError(f"Invalid hardware counter at frame {count - 1}.")
            samples += int(values[4])
            for name, index in (("video", 1), ("pcm", 2), ("ram", 3), ("PC", 7)):
                digest_sets[name].add(values[index])
        if count != expected_frames:
            raise ValueError(f"Trace has {count} frames; expected {expected_frames}.")
    return {"rows": count, "sha256": digest(path), "audio_samples": samples,
            "distinct_values": {name: len(values) for name, values in digest_sets.items()}}


def compare_traces(first: Path, second: Path) -> dict:
    """All bytes must agree; report first differing frame without masking fields."""
    a = first.read_bytes().splitlines()
    b = second.read_bytes().splitlines()
    if a == b:
        return {"identical": True, "rows_compared": max(0, len(a) - 1),
                "first_sha256": digest(first), "second_sha256": digest(second)}
    first_difference = next((index for index, (x, y) in enumerate(zip(a, b))
                             if x != y), min(len(a), len(b)))
    return {"identical": False, "first_different_line": first_difference + 1,
            "first_different_frame": first_difference - 1 if first_difference else None,
            "first_lines": len(a), "second_lines": len(b),
            "first_sha256": digest(first), "second_sha256": digest(second)}


def validate_report(report: dict, expected_frames: int, *, audible=False) -> None:
    if (report.get("mode") != "interpreted-reference"
            or report.get("native_cpu") is not False or report.get("cpu_mhz") != 10
            or report.get("ram_mib") != 2 or report.get("core_error") is not False
            or report.get("fixed_rtc_epoch") != 946684800
            or report.get("frames") != expected_frames):
        raise ValueError("Reference mode, machine configuration or completion differs.")
    for name in ("video_frames", "nonblack_frames", "audio_samples", "width", "height"):
        if type(report.get(name)) is not int or report[name] <= 0:
            raise ValueError(f"Reference counter is missing or zero: {name}")
    if (not isinstance(report.get("fps"), (float, int))
            or not math.isfinite(report["fps"]) or not 20 <= report["fps"] <= 120
            or report.get("sample_rate") != 44100):
        raise ValueError("Unexpected reference audio/video timing.")
    if audible and (type(report.get("nonzero_samples")) is not int
                    or report["nonzero_samples"] <= 0):
        raise ValueError("Gameplay produced no nonzero PCM samples.")
    if not all(isinstance(report.get(name), str) and HEX64.fullmatch(report[name])
               for name in ("final_video_fnv64", "pcm_fnv64", "ram_fnv64")):
        raise ValueError("Reference final-state hashes are missing or invalid.")
    cpu = report.get("cpu")
    if (not isinstance(cpu, list) or len(cpu) != 18
            or not all(type(value) is int and 0 <= value <= 0xFFFFFFFF for value in cpu)):
        raise ValueError("Reference final CPU state is invalid.")


def _validate_capture(path: Path, report: dict) -> None:
    content = path.read_bytes()
    header = re.match(rb"P6\n([0-9]+) ([0-9]+)\n255\n", content)
    if not header:
        raise ValueError("Missing or invalid private PPM capture.")
    width, height = map(int, header.groups())
    if ((width, height) != (report["width"], report["height"])
            or len(content) != header.end() + width * height * 3):
        raise ValueError("Private PPM capture dimensions or size differ.")


def run_campaign(*, executable: Path, disk: Path, fixture_disk: Path,
                 ipl: Path, cgrom: Path, work: Path, timeout: int = 300) -> dict:
    if timeout <= 0 or timeout > 1800:
        raise ValueError("Per-case timeout must be from 1 to 1800 seconds.")
    work = work.absolute()
    if any(part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction())
           for part in (work, *work.parents)):
        raise ValueError("Campaign work directory must not contain symbolic links or junctions.")
    work = work.resolve()
    if not work.is_relative_to((ROOT / ".build").resolve()):
        raise ValueError("Private reference campaigns must stay inside project .build.")
    if work.exists():
        raise FileExistsError("Campaign work directory already exists; use a fresh folder.")
    sources = {name: path.resolve(strict=True) for name, path in (
        ("disk", disk), ("fixture_disk", fixture_disk), ("ipl", ipl), ("cgrom", cgrom))}
    if any(path.is_relative_to(work) for path in sources.values()):
        raise ValueError("Original sources cannot be inside the campaign work directory.")
    before = {name: {"path": str(path), "size": path.stat().st_size,
                     "sha256": digest(path)} for name, path in sources.items()}
    work.mkdir(parents=True, exist_ok=False)
    result = {"schema": "retrorecomp.x68000.reference-check.v1", "passed": False,
              "machine": {"cpu": "MC68000", "cpu_mhz": 10, "ram_mib": 2},
              "mode": "interpreted-reference", "native_cpu": False,
              "sources_before": before, "cases": [],
              "visual_review": "Private captures require human inspection; no OCR asserted.",
              "limits": "Replay agreement is not hardware/gameplay fidelity or physical latency."}
    try:
        for case in cases():
            case_dir = work / case.name
            staged = prepare_bundle(case_dir,
                [sources["fixture_disk"] if case.fixture else sources["disk"]],
                sources["ipl"], sources["cgrom"], executable,
                title="X68000 reference check", ram_mib=2)
            events_path = case_dir / "input-events.tsv"
            with events_path.open("x", encoding="ascii", newline="\n") as stream:
                stream.write("# begin end kind id value; exclusive end frame\n")
                for event in case.events:
                    stream.write(" ".join(map(str, event)) + "\n")
            report_path = case_dir / "report.json"
            trace_path = case_dir / "trace.tsv"
            capture_path = case_dir / "capture.ppm"
            args = [str(staged), "--headless", "--frames", str(case.frames),
                    "--ram-mb", "2", "--report", str(report_path),
                    "--capture", str(capture_path), "--trace", str(trace_path),
                    "--input-events", str(events_path)]
            record = {"name": case.name, "frames": case.frames,
                      "input_sha256": digest(events_path), "passed": False}
            result["cases"].append(record)
            print(f"X68000 reference check: {case.name}, {case.frames} frames", flush=True)
            with (case_dir / "stdout.log").open("xb") as stdout, (
                    case_dir / "stderr.log").open("xb") as stderr:
                process = subprocess.run(args, cwd=case_dir, stdout=stdout, stderr=stderr,
                    timeout=timeout, check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            record["exit_code"] = process.returncode
            if process.returncode:
                raise ValueError(f"Reference case {case.name} exited with {process.returncode}; inspect stderr.log.")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            validate_report(report, case.frames, audible=case.name.startswith("gameplay"))
            trace = validate_trace(trace_path, case.frames)
            if trace["audio_samples"] != report["audio_samples"]:
                raise ValueError("Trace and report audio sample totals differ.")
            _validate_capture(capture_path, report)
            record.update(passed=True, report=report, trace=trace,
                          capture_sha256=digest(capture_path), report_sha256=digest(report_path),
                          source_manifest_sha256=digest(case_dir / "datas/source-manifest.json"))
        replay = compare_traces(work / "gameplay-a/trace.tsv", work / "gameplay-b/trace.tsv")
        result["replay"] = replay
        if not replay["identical"]:
            raise ValueError("Fresh gameplay replay differs; no mismatch was masked.")
        result["passed"] = True
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        after = {name: {"size": path.stat().st_size, "sha256": digest(path)}
                 for name, path in sources.items()}
        result["sources_after"] = after
        result["sources_preserved"] = all(
            before[name]["sha256"] == value["sha256"]
            and before[name]["size"] == value["size"] for name, value in after.items())
        if not result["sources_preserved"]:
            result["passed"] = False
            result["error"] = "Source media or firmware changed during the campaign."
        _write_json(work / "report.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("executable", "disk", "fixture-disk", "ipl", "cgrom", "work"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=300,
                        help="Maximum seconds for each bounded case (default 300).")
    args = parser.parse_args()
    result = run_campaign(**vars(args))
    print(json.dumps(result, indent=2, ensure_ascii=True))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
