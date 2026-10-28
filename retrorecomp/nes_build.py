"""Exact-input NES generation with stable, content-checked C build paths.

Cache generated sources only. Native/reference qualification always runs again.
RAM guards do not affect ROM body emission; they are applied to the selected
umbrella before materialising it at its stable compilation path.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import re
import tempfile

from .conversion_common import preserve_unchanged, write_if_changed
from .core import ConversionError, run
from .library import atomic_json, file_sha256
from .nes_ram import trace_text, write_guards

SCHEMA = 1
SOURCE_NAME = re.compile(r'game_cyc(?:_[A-Za-z0-9_]+)?\.c\Z')


digest = file_sha256


def _sources(directory: Path) -> dict[str, str]:
    return {p.name: digest(p) for p in sorted(directory.glob('*.c'))
            if SOURCE_NAME.fullmatch(p.name)}


def _quote(value: str) -> str:
    equals = '='
    while ']' + equals + ']' in value:
        equals += '='
    return '[' + equals + '[' + value + ']' + equals + ']'


def prepare_native(project: Path, compiler: Path, rom, rom_sites: set[str],
                   ram_sites: set[tuple[int, int]]) -> dict:
    cycle = project / 'cycle'
    raw = cycle / 'raw'
    active = cycle / 'native'
    rom_seed = cycle / 'rom-seeds.trace'
    # The compiler consumes ROM entries only. Guard comments belong to the
    # converter and must not select another directory of identical ROM bodies.
    write_if_changed(rom_seed, trace_text(rom_sites, set()).encode('ascii'))
    identity = {'schema': SCHEMA, 'rom': rom.sha256, 'compiler': digest(compiler),
                'rom_seeds': digest(rom_seed), 'config': '[game]\n',
                'arguments': ['--cycle-accurate', '--output-prefix', 'game']}
    receipt_path = raw / 'generation.json'
    try:
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        inventory = _sources(raw / 'generated')
        reuse = (receipt['identity'] == identity and inventory
                 and 'game_cyc.c' in inventory and 'game_cyc_live.c' in inventory
                 and receipt['sources'] == inventory
                 and receipt['log'] == digest(raw / 'codegen.log'))
    except (OSError, ValueError, KeyError, TypeError):
        reuse = False
    if not reuse:
        # A failed emitter cannot replace the last usable source set. The
        # temporary directory contains our generated files only, never inputs.
        cycle.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='emit-', dir=cycle) as temporary:
            work = Path(temporary)
            config = work / 'game.toml'
            config.write_text('[game]\n', encoding='utf-8')
            output = run([compiler, project / 'rom.nes', '--game', config,
                          '--cycle-accurate', '--output-prefix', 'game',
                          '--cycle-seed-file', rom_seed], cwd=work, timeout=600,
                         log=project / 'build.log')
            emitted = _sources(work / 'generated')
            if not {'game_cyc.c', 'game_cyc_live.c'} <= emitted.keys() or not any(n.startswith('game_cyc_dense_') for n in emitted):
                raise ConversionError('NES compiler produced no complete native source set.')
            for name in emitted:
                write_if_changed(raw / 'generated' / name, (work / 'generated' / name).read_bytes())
            # Old groups are not selected and do not grow the cache indefinitely.
            for stale in (raw / 'generated').glob('*.c'):
                if SOURCE_NAME.fullmatch(stale.name) and stale.name not in emitted:
                    stale.unlink()
            write_if_changed(raw / 'codegen.log', output.encode('utf-8'))
            atomic_json(receipt_path, {'identity': identity, 'sources': emitted,
                                      'log': digest(raw / 'codegen.log')})
    names = sorted(_sources(raw / 'generated'))
    # Adapt the umbrella separately: the immutable raw receipt stays valid
    # when an observed RAM entry is added or removed.
    with tempfile.TemporaryDirectory(prefix='guards-', dir=cycle) as temporary:
        umbrella = Path(temporary) / 'game_cyc.c'
        umbrella.write_bytes((raw / 'generated/game_cyc.c').read_bytes())
        guards = write_guards(umbrella, ram_sites, rom)
        changed = []
        for name in names:
            data = (umbrella if name == 'game_cyc.c' else raw / 'generated' / name).read_bytes()
            if write_if_changed(active / 'generated' / name, data):
                changed.append(name)
    for stale in (active / 'generated').glob('*.c'):
        if SOURCE_NAME.fullmatch(stale.name) and stale.name not in names:
            stale.unlink()
    write_if_changed(active / 'codegen.log', (raw / 'codegen.log').read_bytes())
    sources = [active / 'generated' / name for name in names]
    manifest = ''
    for variable, values in [('CYC_PROJECT_SOURCES', sources),
                             ('CYC_PROJECT_DEPENDS', [project / 'rom.nes', compiler, rom_seed]),
                             ('CYC_PROJECT_ROM', [project / 'rom.nes']),
                             ('CYC_PROJECT_ROM_SHA256', [rom.sha256])]:
        manifest += 'set(' + variable + '\n' + ''.join(
            '  ' + _quote(p.as_posix() if isinstance(p, Path) else p) + '\n' for p in values) + ')\n'
    write_if_changed(cycle / 'sources.cmake', manifest.encode('utf-8'))
    return {'raw_generation_reused': bool(reuse), 'source_files': len(names),
            'unchanged_sources': len(names) - len(changed), 'changed_sources': changed,
            'compiled_ram_guards': guards, 'qualification_reused': False}


@contextmanager
def preserve_inputs(project: Path):
    """Avoid recompiling identical host resources rewritten by their adapters."""
    def inputs():
        if project.is_dir():
            yield from (path for path in project.iterdir()
                        if path.is_file() and (path.suffix in {'.c', '.h', '.inc', '.rc', '.md', '.ico', '.bin', '.nes'}
                                               or path.name == 'CMakeLists.txt'))
    with preserve_unchanged(inputs):
        yield


def stage_native(project: Path, source: Path) -> Path:
    """Stable include paths across separate one-file converter launches."""
    target = project / 'native'
    for path in source.iterdir():
        if path.is_file() and path.suffix in {'.c', '.h', '.inc'}:
            write_if_changed(target / path.name, path.read_bytes())
    return target


def object_stamps(build: Path) -> dict[str, int]:
    # Visual Studio keeps objects per configuration, Ninja under CMakeFiles.
    folder = build / 'game.dir/Release'
    if not folder.is_dir():
        folder = build / 'CMakeFiles/game.dir'
    return {p.relative_to(folder).as_posix(): p.stat().st_mtime_ns
            for pattern in ('*.obj', '*.o') for p in folder.rglob(pattern)} if folder.is_dir() else {}
