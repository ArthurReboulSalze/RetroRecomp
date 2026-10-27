"""Release check for Capcom CPS-1 conversions at the Standard level (developer tool).

Thin wrapper around the console-independent ``tools/release_check.py``: it
converts the given CPS-1 romsets with the converter about to be published,
through the same ``batch`` command line as a player, and checks the receipts:

    python tools/cps1_release_check.py CONVERTER ROM.zip [ROM.zip ...]
        [--work DIR] [--level standard] [--max-fallback 0]

Same command line, same exit codes and the same report gates as before; the
result goes to DIR/release-check.json. See ``release_check.py`` for the other
consoles and for --require-packed / --require-states.
"""
from __future__ import annotations

from pathlib import Path
import sys

try:
    from . import release_check as shared
except ImportError:  # Run directly: python tools/cps1_release_check.py ...
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import release_check as shared


def report_problems(report: dict, level: str, max_fallback: int) -> list[str]:
    """What a CPS-1 conversion report lacks for the release check."""
    return shared.check_report(report, 'cps1', level, max_fallback)['problems']


def batch_problems(record: dict, requested: int) -> list[str]:
    """What the CPS-1 batch record itself proves, before the reports are read."""
    return shared.batch_problems(record, requested, 'cps1')


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    return shared.main([*argv, '--console', 'cps1'])


if __name__ == '__main__':
    sys.exit(main())
