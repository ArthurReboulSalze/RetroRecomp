"""Stage 0 baseline: photograph values later refactors must not change.

The photograph is ROM-free by construction: the cartridge items below carry
constant fake identities and one tiny fixture file the script writes and
deletes; no ROM is ever read. Run from the repository root:

    python -B tools/std_baseline.py OUT.json

Add --with-snapshot to include the compilation-knowledge.json.gz section
(slow: decompresses the whole file). The same command twice must produce a
byte-identical canonical JSON document (sorted keys, indent 1, UTF-8, LF).
"""
import argparse
import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from retrorecomp import compilation_inputs, freshness  # noqa: E402

SYSTEMS = ('sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'x68', 'cps1')

# One tiny fixed fixture stands in for cartridge paths that request_parts
# hashes (never a ROM: constant non-ROM bytes, deleted when the script ends).
FIXTURE_NAME = 'std-baseline-fixture.sms'
FIXTURE_BYTES = b'retro-recomp std-baseline fixture (not a ROM)\n'

ITEMS = (
    ('baseline-item-1', 'aa' * 32, 'Baseline One'),
    ('baseline-item-2', 'bb' * 32, 'Baseline Two'),
    ('baseline-item-3', 'cc' * 32, 'Baseline Three'),
)

# Three option sets per console: defaults, one non-standard scan level and
# console-specific options (ng_bios/x68_ipl deliberately point at the fixture
# so the calls stay ROM-free and fail deterministically). Every set disables
# the cover lookup: the artwork import needs Pillow, and this photograph must
# stay standard-library-only; the ng/x68 calls that require real BIOS/disk
# data raise and are recorded as exceptions instead.
DEFAULT_OPTIONS = {'use_cover': False}
SCAN_OPTIONS = {'use_cover': False, 'scan_level': 'thorough'}
CONSOLE_OPTIONS = {
    'sms': {'use_cover': False, 'frames': 18000},
    'gg': {'use_cover': False, 'frames': 9000},
    'gb': {'use_cover': False, 'passes': 2},
    'nes': {'use_cover': False, 'nes_advanced_scan': True},
    'md': {'use_cover': False, 'md_advanced_scan': True},
    'snes': {'use_cover': False, 'md_advanced_scan': True},
    'ng': {'use_cover': False, 'ng_bios': 'fixture'},
    'x68': {'use_cover': False, 'x68_ipl': 'fixture'},
    'cps1': {'use_cover': False, 'passes': 3},
}


@dataclass
class _FakeItem:
    """Just the attributes freshness.request_parts reads; nothing else."""
    system: str
    path: Path
    title: str
    sha256: str
    cover: Path | None = None


def _sha256_text(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode('utf-8')).hexdigest()


def _console_options(fixture: Path) -> dict:
    """Resolve the 'fixture' sentinel to the temporary file's real path."""
    return {system: {key: str(fixture) if value == 'fixture' else value
                     for key, value in options.items()}
            for system, options in CONSOLE_OPTIONS.items()}


def _firmware_stand_ins():
    """Neo Geo needs a validated BIOS set and X68000 a disk with its IPL ROM,
    which a ROM-free photograph cannot hold: only those identification steps
    return fixed values, the rest of the request signature is computed for real."""
    from contextlib import ExitStack
    from types import SimpleNamespace
    from unittest.mock import patch
    stack = ExitStack()
    stack.enter_context(patch('retrorecomp.neogeo.validate_bios', return_value='baseline-neo-geo-bios'))
    stack.enter_context(patch('retrorecomp.x68000.machine',
                              return_value=(None, SimpleNamespace(sha256='baseline-x68000-machine'))))
    return stack


def _request_section(fixture: Path) -> dict:
    with _firmware_stand_ins():
        return _requests(fixture)


def _requests(fixture: Path) -> dict:
    console_options = _console_options(fixture)
    section = {}
    for system in SYSTEMS:
        console = {}
        for name, sha, title in ITEMS:
            calls = {}
            for label, options in (('defaults', DEFAULT_OPTIONS),
                                   ('scan_thorough', SCAN_OPTIONS),
                                   ('console', console_options[system])):
                try:
                    item = _FakeItem(system, fixture, title, sha)
                    parts = freshness.request_parts(item, options)
                    calls[label] = {'parts': parts, 'sha256': _sha256_text(parts)}
                except Exception as error:  # the photograph records the failure
                    calls[label] = {'error': f'{type(error).__name__}: {error}'}
            console[name] = calls
        section[system] = console
    return section


def _manifest_name(path: str) -> str:
    """The name a stamp manifest uses for one tracked file: 'retrorecomp.x' for a converter module, else its path."""
    if path.startswith('retrorecomp/') and path.endswith('.py'):
        name = path[:-3].replace('/', '.')
        return name[:-len('.__init__')] if name.endswith('.__init__') else name
    return path


def _owners_section() -> dict:
    """Which consoles' stamps each tracked file enters: read from the one manifest (`stamp_inputs.INPUTS`).
    A file no console owns is not an input of any stamp (its owners are empty and it has no role)."""
    tracked = subprocess.run(['git', 'ls-files', '-z'], cwd=REPO_ROOT, check=True,
                             capture_output=True).stdout.decode('utf-8').split('\0')
    owners = {}
    for system in SYSTEMS:
        for name in compilation_inputs.manifest_names(system):
            owners.setdefault(name, []).append(system)
    section = {}
    for path in sorted(name for name in tracked if name):
        name = _manifest_name(path)
        listed = sorted(owners.get(name, ()))
        section[path] = {'owners': listed, 'role': compilation_inputs.role(name) if listed else None}
    return section


def _snapshot_section() -> dict:
    raw = gzip.decompress((REPO_ROOT / 'assets' / 'compilation-knowledge.json.gz').read_bytes())
    document = json.loads(raw.decode('utf-8'))
    consoles = document.get('consoles', {}) if isinstance(document, dict) else {}
    records = {system: len(consoles.get(system) or {}) for system in SYSTEMS}
    return {'records': records, 'sha256': hashlib.sha256(raw).hexdigest()}


def build_baseline(with_snapshot: bool = False) -> dict:
    with tempfile.TemporaryDirectory(prefix='std-baseline-') as folder:
        fixture = Path(folder) / FIXTURE_NAME
        fixture.write_bytes(FIXTURE_BYTES)
        document = {'schema': 1, 'consoles': {}, 'owners': _owners_section(),
                    'snapshot_sha256': None}
        request_section = _request_section(fixture)
        for system in SYSTEMS:
            document['consoles'][system] = {
                'role_stamps': compilation_inputs.role_stamps(system),
                'engine_stamp': compilation_inputs.engine_stamp(system),
                'request_parts': request_section[system],
            }
        if with_snapshot:
            document['snapshot_sha256'] = _snapshot_section()
    return document


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.partition('\n')[0])
    parser.add_argument('output', type=Path, help='canonical JSON file to write')
    parser.add_argument('--with-snapshot', action='store_true',
                        help='also photograph assets/compilation-knowledge.json.gz (slow)')
    arguments = parser.parse_args(argv)
    document = build_baseline(with_snapshot=arguments.with_snapshot)
    text = json.dumps(document, sort_keys=True, indent=1, ensure_ascii=True) + '\n'
    with arguments.output.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
