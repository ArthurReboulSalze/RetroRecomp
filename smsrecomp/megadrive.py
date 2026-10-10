"""Mega Drive cartridge-derived profiles and ROM-verified discovery inputs.

No game-specific RAM guesses are shared between titles. Probe observations
belong to the converter, never to a launched game's working directory.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil

from .core import ConversionError, run, module_fingerprint
from .cartridge16 import megadrive_regions
from .library import atomic_json, entry_lock, library_root
from .knowledge import record_for, ram_variants as shared_ram_variants

PROFILES = {
    '46160baa06362c711c9f1a5017cb7371026444936c8af5e93a78996cf32ff2a6':
        {'id': 'sonic', 'title': 'Sonic the Hedgehog', 'prefix': 'sonic', 'sonic': True},
    '85c1cbf2eb0a40d1c33dbe05576676381995c4fdab70726e7ea0aa50016eafa7':
        {'id': 'columns', 'title': 'Columns', 'prefix': 'game', 'sonic': False,
         'legacy_region_mask': 1},
    'e9f5340ecf8151253eb6fcda136c4d4d8940e373340ce2eeb2bf24f9f6c1004d':
        {'id': 'golden-axe', 'title': 'Golden Axe', 'prefix': 'game', 'sonic': False,
         'legacy_region_mask': 1},
    '2d535ff7eda650a64a9093ba6fabf8d5ac87801b898a76b591db41a1c8e47c4f':
        {'id': 'castle-of-illusion', 'title': 'Castle of Illusion', 'prefix': 'game', 'sonic': False,
         'legacy_region_mask': 4},
    # Empty region field; exact image matched to the Libretro/No-Intro Japan
    # record (CRC 8A5ED856, SHA1 0BD83099EDD3938A0F127ED399CB01046E36AC32).
    # https://github.com/libretro/libretro-database/blob/master/metadat/no-intro/Sega%20-%20Mega%20Drive%20-%20Genesis.dat
    'bd412e0c8861db976e3ed7ded7389080e54fc29895e4325295297786fdac519e':
        {'id': 'alex-kidd-japan', 'title': 'Alex Kidd - Tenkuu Majou', 'prefix': 'game', 'sonic': False,
         'legacy_region_mask': 1},
    '7f6f00dbe774cee92cb91d0f1d26e898a199e5a5a8b77bf199a1b7f8a0d44b7b':
        {'id': 'menacer', 'title': 'Menacer 6-Game Cartridge', 'prefix': 'game', 'sonic': False},
    'cd2fbb02b42cb0f4e26b4aa5fa1c79ba798c48233ae4e02e19012b08c6848071':
        {'id': 't2-arcade', 'title': 'T2 - The Arcade Game', 'prefix': 'game', 'sonic': False},
    '121b5e2a0fc03816dc5d42e3069ef41120efc9a7d3728363c91449e762e7b7cc':
        {'id': 'aladdin-japan', 'title': 'Aladdin', 'prefix': 'game', 'sonic': False},
    '4a314edbfee92282850fe95c4c764921916efd9d3c2277fdec2581279b1369b1':
        {'id': 'streets-of-rage-2', 'title': 'Streets of Rage 2', 'prefix': 'game', 'sonic': False},
    'd2163f1cc7a200075e1129f038a245c421688e2d62afca9934fedeffdf833cf5':
        {'id': 'revenge-of-shinobi', 'title': 'The Revenge of Shinobi', 'prefix': 'game', 'sonic': False},
    '549b1731062c24195ae7fa8ca84ad34ae5bfa2972c9eb2535df880d06880ea86':
        {'id': 'gunstar-heroes-japan', 'title': 'Gunstar Heroes', 'prefix': 'game', 'sonic': False},
    '48b280520c4f1b36d43a252d4a137443a714f78832e17b729811ac0d28eefef7':
        {'id': 'ecco', 'title': 'Ecco the Dolphin', 'prefix': 'game', 'sonic': False},
    'deae2e33345244707c62dbc8ed1b087899463e67e217843a4b6c8b4d9c8b47c4':
        {'id': 'desert-strike', 'title': 'Desert Strike - Return to the Gulf', 'prefix': 'game', 'sonic': False},
    'eb19bda4982366a2fd43d65ab8a7f9709d83a8cc902c14a682c088c16359c263':
        {'id': 'beyond-oasis', 'title': 'Beyond Oasis', 'prefix': 'game', 'sonic': False},
    'ec6cee3af3cc7cc6113d1443d5b5c27f18c2506d5ef61a453a42d6655c5e07c4':
        {'id': 'comix-zone-japan', 'title': 'Comix Zone', 'prefix': 'game', 'sonic': False},
    'f8feee8e3f2768bec97419c3b278a87827e248fa4d5ae35a1af46a14366c6856':
        {'id': 'contra-hard-corps', 'title': 'Contra - Hard Corps', 'prefix': 'game', 'sonic': False},
    '697af64f489935f9d2ca5f1b89b2467c042a0113edfbe913e354f4765ce221e0':
        {'id': 'dynamite-headdy', 'title': 'Dynamite Headdy', 'prefix': 'game', 'sonic': False},
    '040b833996c84e1ac30711287f38c0264c4370cd45fa4d30138e6e972c4d50bc':
        {'id': 'rocket-knight-japan', 'title': 'Rocket Knight Adventures', 'prefix': 'game', 'sonic': False},
    'ae07a6fd26590571d4bfc73b678e1aa38cb1a1466cf93f3af3714a45cad4bf60':
        {'id': 'street-fighter-2-japan', 'title': "Street Fighter II' Plus - Champion Edition", 'prefix': 'game', 'sonic': False},
    '1950560594416d2bba700c05c6ce21591647c59863fa4afe2d10f871f290679d':
        {'id': 'thunder-force-4-japan', 'title': 'Thunder Force IV', 'prefix': 'game', 'sonic': False},
    '65ea2386f5f4eda45335d8298ab30bc19d38b9bd5483ffa592818b645c14c163':
        {'id': 'toejam-and-earl', 'title': 'ToeJam & Earl', 'prefix': 'game', 'sonic': False},
    '8d167aa613cbc17377314c920642a9d7bc8d4204eead3cfbc84dbc23c86a6e09':
        {'id': 'vectorman', 'title': 'Vectorman', 'prefix': 'game', 'sonic': False},
    '6b2ac36f624f914ad26e32baa87d1253aea9dcfc13d2a5842ecdd2bd4a7a43b9':
        {'id': 'wonder-boy-monster-world', 'title': 'Wonder Boy in Monster World', 'prefix': 'game', 'sonic': False},
    '193bc4064ce0daf27ea9e908ed246d87ec576cc294833badebb590b6ad8e8f6b':
        {'id': 'sonic-2', 'title': 'Sonic the Hedgehog 2', 'prefix': 'game', 'sonic': False},
    'c452d3306a1f2f040f6b04ce876c6cd14cb1c5d072ff41ba791bbd3797fe9113':
        {'id': 'earthworm-jim-pal', 'title': 'Earthworm Jim', 'prefix': 'game', 'sonic': False,
         'standards': ('pal',)},
    'e8d4514ebcb91e09ffa636268660e7b3e24317e95179c3a9572f58c40866b747':
        {'id': 'mortal-kombat-2', 'title': 'Mortal Kombat II', 'prefix': 'game', 'sonic': False,
         'six_buttons': True},
    'c7a609019b1f052bcee6204a3a09ea77a5150a748de90b51382fedf4df207848':
        {'id': 'road-rash-2', 'title': 'Road Rash II', 'prefix': 'game', 'sonic': False},
    '3802900c87d0c62cfd0f75f9922f16713f30c7616843af6c946995451040234c':
        {'id': 'shining-force-2-pal', 'title': 'Shining Force II', 'prefix': 'game', 'sonic': False,
         'standards': ('pal',)},
}


def profile_for(rom):
    limitations = []
    # EEPROM is not ordinary SRAM. Keep conversion available (including games
    # already tested), but never imply their original cartridge saves work.
    # https://www.plutiedev.com/rom-header
    if rom.data[0x1b0:0x1b2] == b'RA' and rom.data[0x1b3] == 0x40:
        limitations.append('EEPROM cartridge saves are not implemented; use F8/F9 quick states.')
    profile = PROFILES.get(rom.sha256)
    if profile is not None:
        return dict(profile, source='catalogue', limitations=limitations)
    # A catalogue entry is an optional exact-ROM override, not permission to
    # compile. Generic discovery reads this cartridge's vectors and bytes.
    return {'id': 'rom-' + rom.sha256, 'title': rom.title, 'prefix': 'game',
            'sonic': False, 'six_buttons': b'6' in rom.data[0x190:0x1a0],
            'source': 'cartridge', 'limitations': limitations}


def validate_cartridge(rom):
    """Reject known hardware gaps before allocating/building native tables."""
    if len(rom.data) > 0x400000:
        raise ConversionError('Mega Drive cartridges above 4 MiB require a bank mapper '
                              'that this runtime does not support yet.')
    system = rom.data[0x100:0x110].decode('ascii', errors='replace').strip('\0 ').upper()
    if any(marker in system for marker in ('32X', 'PICO', 'TERA', 'SSF', 'MEGAWIFI')):
        raise ConversionError(f'The cartridge declares {system} hardware; '
                              'the Mega Drive runtime does not support this extension yet.')


def region_mask(rom):
    """Keep exact qualified legacy headers separate from general detection.

    Columns, Golden Axe and the verified Japanese Alex Kidd image have empty
    headers; Castle of Illusion uses the older US code. Only complete SHA-256 identities supply
    this exception; another image or a filename cannot inherit it.
    """
    return megadrive_regions(rom.data) or PROFILES.get(rom.sha256, {}).get('legacy_region_mask', 0)


def video_standard(rom, override=None):
    """Use the declared cartridge regions, independently of test history."""
    regions = region_mask(rom)
    if not regions:
        raise ConversionError('This Mega Drive cartridge has an unrecognized region header; timing cannot be qualified yet.')
    standard = override or ('ntsc' if regions & 5 else 'pal')
    if standard not in ('ntsc', 'pal'):
        raise ConversionError('Unknown Mega Drive video timing.')
    if not regions & (5 if standard == 'ntsc' else 10):
        raise ConversionError(f'This Mega Drive cartridge declares {"PAL" if standard == "ntsc" else "NTSC"} timing; '
                              f'it cannot be forced to {standard.upper()}.')
    return standard


def vectors(rom) -> dict:
    data = rom.data
    values = {name: int.from_bytes(data[p:p + 4], 'big') & 0xffffff
              for name, p in (('ssp', 0), ('entry', 4), ('hblank', 0x70), ('vblank', 0x78))}
    # A7 is 32-bit; only bus accesses discard its upper byte. An empty stack
    # at zero is valid: predecrement pushes wrap to $FFFFFC in work RAM.
    values['ssp'] = int.from_bytes(data[:4], 'big')
    stack_bus = values['ssp'] & 0xffffff
    if (stack_bus != 0 and not 0xff0000 <= stack_bus <= 0xffffff) or stack_bus & 1:
        raise ConversionError('Mega Drive reset stack is outside writable RAM.')
    if not 0x200 <= values['entry'] < len(data) or values['entry'] & 1:
        raise ConversionError('Mega Drive reset/interrupt vectors are not valid ROM entries.')
    # Menacer installs its V-int handler in RAM and has a low-ROM RTE stub.
    # Validate the bus address, rather than requiring every IRQ to be in ROM.
    for name in ('hblank', 'vblank'):
        pc = values[name]
        # Disabled H-int vectors are often unpopulated (zero or all ones).
        # Do not seed them as native code. If the game enables that interrupt,
        # keep its actual vector and let the normal execution checks report it.
        if name == 'hblank' and pc in (0, 0xffffff):
            continue
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
    from .console16 import REPOSITORIES
    shared = {address for (address,) in record_for('md', rom, REPOSITORIES['md'][1]).get('rom_entries', [])
              if _entry_signature(rom, address) is not None}
    try:
        record = json.loads(memory_file(rom).read_text(encoding='utf-8'))
        if record.get('schema') not in (1, 2) or record.get('rom_sha256') != rom.sha256:
            return shared
        return shared | {item['address'] for item in record.get('entries', [])
                if _entry_signature(rom, item.get('address')) == item.get('bytes')
                and item.get('bytes') is not None}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return shared


def valid_ram_variant(item):
    if not isinstance(item, dict):
        return False
    address, raw = item.get('address'), item.get('bytes')
    return (isinstance(address, int) and 0xff0000 <= address <= 0xfffffe and not address & 1
            and isinstance(raw, str) and 4 <= len(raw) <= 32 and len(raw) % 4 == 0
            and address + len(raw) // 2 <= 0x1000000
            and re.fullmatch('[0-9a-fA-F]+', raw) is not None)


def read_ram_variants(rom) -> list[dict]:
    from .console16 import REPOSITORIES
    shared = shared_ram_variants('md', rom, REPOSITORIES['md'][1])
    try:
        record = json.loads(memory_file(rom).read_text(encoding='utf-8'))
        if record.get('schema') != 2 or record.get('rom_sha256') != rom.sha256:
            record = {}
    except (OSError, ValueError, TypeError, AttributeError):
        record = {}
    items = [item for item in record.get('ram_variants', []) + shared if valid_ram_variant(item)]
    return [{'address': addr, 'bytes': raw} for addr, raw in
            sorted({(item['address'], item['bytes'].lower()) for item in items})[:2048]]


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


def write_spec(project: Path, rom, title: str, standard='ntsc') -> None:
    profile = profile_for(rom)
    v = vectors(rom)
    (project / 'retro_md_game.h').write_text(
        '/* Generated from this exact cartridge, never from another game. */\n'
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
        # The video-standard and domestic/overseas bits are separate hardware
        # choices. Region checks remain untouched in the cartridge.
        output.write(f'#define RR_MD_PAL {int(standard == "pal")}\n')
        output.write(f'#define RR_MD_SIX_BUTTONS {int(profile.get("six_buttons", "street-fighter" in profile["id"]))}\n')
        output.write(f'#define RR_MD_OVERSEAS {int(bool(region_mask(rom) & (8 if standard == "pal" else 4)))}\n')


def analysis_identity(project: Path, engine_revision: str, rom) -> dict:
    # Include both the exact ROM and all profile/discovery inputs. A library
    # addition or compiler-adapter edit invalidates the native source cache.
    config_hash = hashlib.sha256((project / 'game.toml').read_bytes()).hexdigest()
    from . import megadrive_codegen
    return {'rom': rom.sha256, 'engine': engine_revision, 'config': config_hash,
            'adapter': module_fingerprint(__name__),
            'codegen': module_fingerprint(megadrive_codegen.__name__),
            'entries': sorted(read_entries(rom)), 'ram_variants': read_ram_variants(rom), 'schema': 4}
