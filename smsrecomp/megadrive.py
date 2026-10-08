"""Qualified Mega Drive cartridges and ROM-verified discovery inputs.

No game-specific RAM guesses are shared between titles. Probe observations
belong to the converter, never to a launched game's working directory.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil

from .core import ConversionError, run
from .library import atomic_json, entry_lock, library_root

PROFILES = {
    '46160baa06362c711c9f1a5017cb7371026444936c8af5e93a78996cf32ff2a6':
        {'id': 'sonic', 'title': 'Sonic the Hedgehog', 'prefix': 'sonic', 'sonic': True},
    '85c1cbf2eb0a40d1c33dbe05576676381995c4fdab70726e7ea0aa50016eafa7':
        {'id': 'columns', 'title': 'Columns', 'prefix': 'game', 'sonic': False},
    'e9f5340ecf8151253eb6fcda136c4d4d8940e373340ce2eeb2bf24f9f6c1004d':
        {'id': 'golden-axe', 'title': 'Golden Axe', 'prefix': 'game', 'sonic': False},
    '2d535ff7eda650a64a9093ba6fabf8d5ac87801b898a76b591db41a1c8e47c4f':
        {'id': 'castle-of-illusion', 'title': 'Castle of Illusion', 'prefix': 'game', 'sonic': False},
    '7f6f00dbe774cee92cb91d0f1d26e898a199e5a5a8b77bf199a1b7f8a0d44b7b':
        {'id': 'menacer', 'title': 'Menacer 6-Game Cartridge', 'prefix': 'game', 'sonic': False},
    'cd2fbb02b42cb0f4e26b4aa5fa1c79ba798c48233ae4e02e19012b08c6848071':
        {'id': 't2-arcade', 'title': 'T2 - The Arcade Game', 'prefix': 'game', 'sonic': False},
}


def profile_for(rom):
    profile = PROFILES.get(rom.sha256)
    if profile is None:
        raise ConversionError('Mega Drive integration is experimental. This cartridge was '
            'identified, but will not be compiled with another game\'s profile. '
            'Qualified titles: ' + ', '.join(p['title'] for p in PROFILES.values()) + '.')
    return profile


def vectors(rom) -> dict:
    data = rom.data
    values = {name: int.from_bytes(data[p:p + 4], 'big') & 0xffffff
              for name, p in (('ssp', 0), ('entry', 4), ('hblank', 0x70), ('vblank', 0x78))}
    if not 0xff0000 <= values['ssp'] <= 0xffffff or values['ssp'] & 1:
        raise ConversionError('Mega Drive reset stack is outside writable RAM.')
    if not 0x200 <= values['entry'] < len(data) or values['entry'] & 1:
        raise ConversionError('Mega Drive reset/interrupt vectors are not valid ROM entries.')
    # Menacer installs its V-int handler in RAM and has a low-ROM RTE stub.
    # Validate the bus address, rather than requiring every IRQ to be in ROM.
    for name in ('hblank', 'vblank'):
        pc = values[name]
        if pc & 1 or not (8 <= pc < len(data) or 0xff0000 <= pc <= 0xfffffe):
            raise ConversionError('Mega Drive interrupt vector is outside mapped ROM/RAM.')
    candidates = {int.from_bytes(data[p:p + 4], 'big') & 0xffffff for p in range(4, 0x100, 4)}
    values['roots'] = sorted(value for value in candidates if 8 <= value < len(data) and not value & 1)
    return values


def _entry_signature(rom, address):
    if isinstance(address, int) and 0x200 <= address <= len(rom.data) - 8 and not address & 1:
        return rom.data[address:address + 8].hex()
    return None


def memory_file(rom) -> Path:
    return library_root('md') / rom.sha256 / 'native-entries.json'


def read_entries(rom) -> set[int]:
    try:
        record = json.loads(memory_file(rom).read_text(encoding='utf-8'))
        if record.get('schema') not in (1, 2) or record.get('rom_sha256') != rom.sha256:
            return set()
        return {item['address'] for item in record.get('entries', [])
                if _entry_signature(rom, item.get('address')) == item.get('bytes')
                and item.get('bytes') is not None}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return set()


def valid_ram_variant(item):
    if not isinstance(item, dict):
        return False
    address, raw = item.get('address'), item.get('bytes')
    return (isinstance(address, int) and 0xff0000 <= address <= 0xfffff0 and not address & 1
            and isinstance(raw, str) and 4 <= len(raw) <= 32 and len(raw) % 4 == 0
            and re.fullmatch('[0-9a-fA-F]+', raw) is not None)


def read_ram_variants(rom) -> list[dict]:
    try:
        record = json.loads(memory_file(rom).read_text(encoding='utf-8'))
        if record.get('schema') != 2 or record.get('rom_sha256') != rom.sha256:
            return []
        return [item for item in record.get('ram_variants', []) if valid_ram_variant(item)][:2048]
    except (OSError, ValueError, TypeError, AttributeError):
        return []


def learn_entries(rom, checks) -> int:
    additions = {address for check in checks for address in check.get('rom_entries', [])
                 if _entry_signature(rom, address) is not None}
    variants = {(item['address'], item['bytes'].lower()) for check in checks
                for item in check.get('ram_variants', []) if valid_ram_variant(item)}
    if not additions and not variants:
        return 0
    path = memory_file(rom)
    with entry_lock(path.parent):
        previous = read_entries(rom)
        merged = previous | additions
        old_ram = {(item['address'], item['bytes']) for item in read_ram_variants(rom)}
        merged_ram = set(sorted(old_ram | variants)[:2048])
        if merged != previous or merged_ram != old_ram:
            atomic_json(path, {'schema': 2, 'rom_sha256': rom.sha256, 'title': profile_for(rom)['title'],
                'entries': [{'address': address, 'bytes': _entry_signature(rom, address)}
                            for address in sorted(merged)],
                'ram_variants': [{'address': address, 'bytes': raw} for address, raw in sorted(merged_ram)]})
    return len(merged - previous) + len(merged_ram - old_ram)


def write_profile(project: Path, engine: Path, rom, entries: set[int]) -> str:
    profile = profile_for(rom)
    if profile['sonic']:
        for source in (engine / 'sonicthehedgehog').iterdir():
            if source.is_file() and source.suffix in ('.toml', '.csv'):
                shutil.copy2(source, project / source.name)
        return profile['prefix']
    v = vectors(rom)
    # Observed interior PCs are instruction starts, not C-function entries.
    roots = v['roots']
    config = ('[game]\noutput_prefix="game"\njump_table_autodiscovery=true\n\n'
              '[ram_layout]\ngame_mode=0\nvint_runcount=0\nvint_routine=0\n'
              'plc_pending=0\nplayer_object=0\nlevel_modes=[]\n'
              f'initial_ssp={v["ssp"]:#x}\nvbla_stack={v["ssp"]:#x}\nintr_stack={v["ssp"]:#x}\n\n'
              '[functions]\nextra=[' + ','.join(hex(address) for address in roots) + ']\n')
    (project / 'game.toml').write_text(config, encoding='utf-8')
    return profile['prefix']


def generate(compiler: Path, project: Path, rom_file: Path, *, instruction_map=False) -> None:
    """Reject unsupported translation. Retry only false mid-instruction roots.

    The emitter proves these speculative entries overlap an existing decoded
    instruction's extension words. Excluding a root preserves that parent
    stream; this does not permit unsupported opcode bodies or skip live code.
    """
    import tomllib
    if instruction_map:
        # The old function emitter supplies discovery/cycle-address metadata
        # only. Its C bodies are not linked into the instruction-AOT executable.
        # Speculative function aliases therefore must not reject a different
        # translator. Live instructions still go through byte-checked native
        # bodies, fallback accounting, and the mandatory reference gate.
        log = project / 'discovery.log'
        run([compiler, rom_file.name, '--game', 'game.toml', '--output-dir', project / 'generated'],
            cwd=project, log=log, timeout=600)
        atomic_json(project / 'discovery-audit.json', {'schema': 2,
            'mode': 'instruction_aot', 'function_bodies_linked': False,
            'discovery_diagnostics': re.findall(r'^\s+([A-Z_]+)\s+@ \$([0-9A-Fa-f]+)',
                                               log.read_text(encoding='utf-8', errors='replace'), re.M)})
        return
    config = project / 'game.toml'
    initial = config.read_text(encoding='utf-8')
    protected = set(tomllib.loads(initial).get('functions', {}).get('extra', []))
    rejected = set()
    for attempt in range(3):
        log = project / f'generate-{attempt + 1}.log'
        try:
            run([compiler, rom_file.name, '--game', 'game.toml', '--output-dir', project / 'generated',
                 '--fail-on-unsupported'], cwd=project, log=log, timeout=600)
            atomic_json(project / 'discovery-audit.json', {'schema': 1,
                'rejected_speculative_entries': sorted(rejected), 'strict_translation': True})
            return
        except ConversionError:
            text = log.read_text(encoding='utf-8', errors='replace')
            count = re.search(r'--fail-on-unsupported: (\d+) unsupported', text)
            addresses = {int(value, 16) for value in re.findall(
                r'MISALIGNED_FUNC_ENTRY\s+@ \$([0-9A-Fa-f]+)', text)}
            if (not count or int(count[1]) != len(addresses) or not addresses - rejected
                    or addresses & protected or attempt == 2):
                raise
            rejected |= addresses
            # The generated generic profile has no other blacklist. Rewrite
            # this field instead of creating duplicate TOML keys on retries.
            config.write_text(initial + 'blacklist=[' +
                ','.join(hex(value) for value in sorted(rejected)) + ']\n', encoding='utf-8')


def write_spec(project: Path, rom, title: str) -> None:
    profile = profile_for(rom)
    v = vectors(rom)
    (project / 'retro_md_game.h').write_text(
        '/* Generated from the qualified cartridge, never from another game. */\n'
        f'#define RR_MD_TITLE {json.dumps(title, ensure_ascii=True)}\n'
        f'#define RR_MD_KEY "{profile["id"]}"\n'
        f'#define RR_MD_ROM_BYTES {len(rom.data)}u\n'
        f'#define RR_MD_CRC32 0x{rom.crc32:08x}u\n'
        f'#define RR_MD_ENTRY 0x{v["entry"]:06x}u\n'
        f'#define RR_MD_VBLANK 0x{v["vblank"]:06x}u\n'
        f'#define RR_MD_HBLANK 0x{v["hblank"]:06x}u\n'
        f'#define RR_MD_SONIC {int(profile["sonic"])}\n', encoding='utf-8')
    with (project / 'retro_md_game.h').open('a', encoding='utf-8') as output:
        output.write('#define RR_MD_STEP_AOT 1\n')


def analysis_identity(project: Path, engine_revision: str, rom) -> dict:
    # Include both the exact ROM and all profile/discovery inputs. A library
    # addition or compiler-adapter edit invalidates the native source cache.
    config_hash = hashlib.sha256((project / 'game.toml').read_bytes()).hexdigest()
    from . import megadrive_codegen
    return {'rom': rom.sha256, 'engine': engine_revision, 'config': config_hash,
            'adapter': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'codegen': hashlib.sha256(Path(megadrive_codegen.__file__).read_bytes()).hexdigest(),
            'entries': sorted(read_entries(rom)), 'ram_variants': read_ram_variants(rom), 'schema': 4}
