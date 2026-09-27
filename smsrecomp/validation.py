"""Evidence required before a banked candidate replaces a delivered game."""
import csv
from pathlib import Path


def vdp_states(path: Path) -> list:
    # The legacy trace appends RAM hashes and SP under a shorter header.
    # Compare VDP and RAM on every frame; CPU registers are compared separately.
    with path.open(newline='', encoding='utf-8') as source:
        rows = list(csv.reader(source))[1:]
    if any(len(row) < 9 for row in rows):
        raise ValueError('Incomplete VDP trace')
    return [row[:9] for row in rows]


def compare_execution(native: dict, reference: dict, native_dir: Path, reference_dir: Path) -> dict:
    checks = {
        'completed': bool(native.get('passed') and reference.get('passed')),
        'same_frame_budget': native.get('completed_frames') == reference.get('completed_frames') == native.get('requested_frames'),
        'final_cpu': bool(native.get('final_cpu')) and native.get('final_cpu') == reference.get('final_cpu'),
    }
    missing = []
    for key, filename in (('final_image', 'frame.png'), ('final_ram', 'frame.png.ram'), ('vdp_trace', 'vdp.csv')):
        a, b = native_dir / filename, reference_dir / filename
        try:
            if key == 'vdp_trace':
                left, right = vdp_states(a), vdp_states(b)
                checks[key] = bool(left) and left == right and len(left) == native.get('requested_frames')
            else:
                checks[key] = a.read_bytes() == b.read_bytes()
        except (OSError, ValueError, IndexError, csv.Error) as error:
            checks[key] = False
            missing.append(f'{filename}: {error}')
    return {'passed': all(checks.values()), 'checks': checks, 'missing_or_invalid_evidence': missing}
