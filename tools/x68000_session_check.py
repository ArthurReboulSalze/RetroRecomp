"""Fail-closed verification of authored X68000 session device checks."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

NAMES = (
    'queued_pcm_and_fractional_clock_resume',
    'queued_pcm_wrap_and_pointer_rebuild',
    'adpcm_pending_decode_exact_pcm_resume',
    'keyboard_pending_make_break_order',
    'mouse_pending_motion_buttons_capture',
    'scc_partial_mouse_packet_resume',
    'joystick_cyberstick_handshake_resume',
    'active_external_dma_exact_resume',
    'mfp_fractional_prescaler_irq_resume',
    'pending_irq_callback_process_rebuild',
    'video_clear_scan_progress_resume',
)
EXPECTED = (1 << len(NAMES)) - 1


def check_diagnostics(record: dict) -> dict:
    if not isinstance(record, dict) or record.get('schema') != 1:
        raise ValueError('Invalid session diagnostic schema.')
    if record.get('kind') != 'authored-state-continuation' or record.get('destructive_after_capture') is not True:
        raise ValueError('Session checks must run after normal capture and reports.')
    cases = record.get('cases')
    if not isinstance(cases, list) or len(cases) != len(NAMES):
        raise ValueError('Missing session continuation checks.')
    if tuple(case.get('name') for case in cases if isinstance(case, dict)) != NAMES:
        raise ValueError('Session continuation identities differ.')
    if any(case.get('passed') is not True for case in cases):
        raise ValueError('A session continuation fixture failed.')
    if record.get('mask') != EXPECTED or record.get('expected_mask') != EXPECTED or record.get('passed') is not True:
        raise ValueError('Session continuation mask differs.')
    size = record.get('state_bytes')
    if type(size) is not int or size < 1024 or size > 64 * 1024 * 1024:
        raise ValueError('Session core state size is outside bounds.')
    return {'passed': True, 'checks': len(NAMES), 'state_bytes': size,
            'scope': 'authored device state continuation, not full hardware fidelity'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('diagnostic', type=Path)
    args = parser.parse_args()
    print(json.dumps(check_diagnostics(json.loads(args.diagnostic.read_text(encoding='utf-8'))), indent=2))


if __name__ == '__main__':
    main()
