"""ROM-scoped RAM instruction observations owned by the SNES converter."""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import re
from .library import atomic_json, entry_lock, library_root
from .knowledge import ram_variants as shared_ram_variants,record_for

RAM_VARIANT_LIMIT = 16384
PROFILES = {
    # Super Mario World has no entry since 1.4.1: like any cartridge without one,
    # it gets the generic analysis (no Rust, no foreign function list).
    '7a8ffaf8bb549b400ec2f0bda9f3c0dbf5852c38618cdb21cd783c368383e2c7':
        {'id': 'super-scope-6', 'title': 'Super Scope 6', 'legacy_functions': False},
    '66871d66be19ad2c34c927d6b14cd8eb6fc3181965b6e517cb361f7316009cfb':
        {'id': 'zelda-alttp', 'title': 'The Legend of Zelda - A Link to the Past',
         'legacy_functions': False},
    '12b77c4bc9c1832cee8881244659065ee1d84c70c3d29e6eaf92e6798cc2ca72':
        {'id': 'super-metroid', 'title': 'Super Metroid', 'legacy_functions': False},
    '628147468c3539283197f58f03b94df49758a332831857481ea9cc31645f0527':
        {'id': 'donkey-kong-country', 'title': 'Donkey Kong Country',
         'legacy_functions': False, 'mapping': 'hirom'},
    '0ef6f4cce5a2273fa49fe1ce724e0048a8e39c91da6b00dbb693fe1ba909177d':
        {'id': 'super-castlevania-iv', 'title': 'Super Castlevania IV', 'legacy_functions': False},
    'bf16c3c867c58e2ab061c70de9295b6930d63f29f81cc986f5ecae03e0ad18d2':
        {'id': 'f-zero', 'title': 'F-Zero', 'legacy_functions': False},
    'b8f70a6e7fb93819f79693578887e2c11e196bdf1ac6ddc7cb924b1ad0be2d32':
        {'id': 'mega-man-x', 'title': 'Mega Man X', 'legacy_functions': False},
    '06d1c2b06b716052c5596aaa0c2e5632a027fee1a9a28439e509f813c30829a9':
        {'id': 'chrono-trigger', 'title': 'Chrono Trigger', 'legacy_functions': False,
         'mapping': 'hirom'},
    '4efab3f49cbe91ec77b6cba747ddfedfdc0b080c755a8b6ba51234f0676c000f':
        {'id': 'super-bomberman', 'title': 'Super Bomberman', 'legacy_functions': False,
         'mapping': 'hirom'},
    'a9e3e57d591e995e8e0dd228b619b6aed42205eaf55316fa8ff33f236b3a32b3':
        {'id': 'super-mario-all-stars', 'title': 'Super Mario All-Stars', 'legacy_functions': False},
    '979572fe92501a409207399817911d04438f4078bc6832cbc851e98eb2f1c2d2':
        {'id': 'popn-twinbee-pal', 'title': "Pop'n TwinBee", 'legacy_functions': False,
         'standard': 'pal', 'video_scope': 'standard_ppu'},
}


def profile_for(rom):
    from .core import ConversionError
    profile = PROFILES.get(rom.sha256)
    if profile is None:
        profile = {'id': 'rom-' + rom.sha256, 'title': rom.title,
                   'legacy_functions': False, 'mapping': rom.mapping,
                   'standard': rom.standard, 'source': 'cartridge'}
        if rom.standard == 'pal':
            profile['video_scope'] = 'standard_ppu'
        return profile
    mapping = profile.get('mapping', 'lorom')
    standard = profile.get('standard', 'ntsc')
    if rom.mapping != mapping or rom.standard != standard:
        raise ConversionError(f'This qualified SNES profile requires its {standard.upper()} {mapping} cartridge.')
    return dict(profile, source='catalogue')


def project_path(root: Path, rom, profile) -> Path:
    """Keep MSVC tracking paths short without merging different exact ROMs."""
    if profile.get('source') != 'cartridge':
        return root / '.build' / ('snes-' + profile['id'])
    for length in (16,32,64):
        path=root / '.build' / ('snes-rom-' + rom.sha256[:length])
        cartridge=path / 'cartridge.sfc'
        identity=path / 'generation-identity.json'
        try:
            occupied=json.loads(identity.read_text(encoding='utf-8')).get('rom')
        except (OSError,ValueError,AttributeError):
            occupied=None
        if occupied:
            if occupied == rom.sha256:return path
        elif cartridge.exists():
            if hashlib.sha256(cartridge.read_bytes()).hexdigest()==rom.sha256:return path
        else:return path
    from .core import ConversionError
    raise ConversionError('SNES build directory conflicts with this exact ROM identity.')


def validate_cartridge(rom):
    """Validate supported maps and explicitly identified enhancement circuits."""
    from .core import ConversionError
    from .cartridge16 import snes_header
    header = snes_header(rom.data)
    if not header:
        raise ConversionError('SNES cartridge header could not be validated.')
    offset, mapping = header
    mode, chip = rom.data[offset + 21], rom.data[offset + 22]
    from .snes_chips import identify
    identify(rom.data)
    if mapping not in ('lorom', 'hirom') or len(rom.data) > 0x400000:
        raise ConversionError(f'SNES {mapping} cartridges above 4 MiB or extended mappings '
                              'are not supported by the native runtime yet.')
    # Mode $32 is the ExLoROM byte of the S-DD1 boards (chip type $43/$45, refused by `identify` above). On a
    # LoROM header with no chip (type 0, 1 or 2: nothing, RAM, RAM and battery) it is a mastering quirk of an ordinary
    # LoROM cartridge, which the pinned loader maps as LoROM (Duel: Test Drive II, 1 MiB).
    ordinary_exlorom = mode == 0x32 and mapping == 'lorom' and chip in (0, 1, 2)
    if mode not in (0x20, 0x21, 0x30, 0x31) and not ordinary_exlorom and not (mode>>4 not in (2,3) and chip in (0,1,2)):
        raise ConversionError(f'This SNES cartridge uses an unsupported enhancement chip or mapping '
                              f'(map ${mode:02X}, cartridge type ${chip:02X}). '
                              'The native runtime currently supports ordinary LoROM/HiROM cartridges, '
                              'with or without RAM/battery.')
    from .snes_cart import layout
    layout(rom)  # Validate the bounded RAM allocation before invoking the loader.


def support_stage(rom):
    """Only validated ordinary/DSP-1/CX4/Super FX board signatures pass this gate.

    Super FX boards are qualified like DSP-1/CX4 (docs/SNES_SUPERFX.md, "Release
    qualification"); their GSU stays a counted interpreted device.
    """
    validate_cartridge(rom)
    return 'supported'


def video_standard(rom, override=None):
    from .core import ConversionError
    standard = rom.standard
    if override and override != standard:
        raise ConversionError(f'This SNES cartridge requires {standard.upper()} timing.')
    return standard


def validate_activity(profile, checks):
    """Require complete raster geometry and active picture/sound on long PAL runs.

    Legacy narrow-profile gates remain explicit. Standard PPU reports retain
    every selected row and dot; short boot probes may precede picture/sound.
    """
    if profile.get('video_scope') not in ('progressive_224', 'standard_ppu'):
        return
    from .core import ConversionError
    for check in checks:
        for mode in ('overscan_seen', 'interlace_seen', 'hires_seen') if profile.get('video_scope')=='progressive_224' else ():
            if check.get(mode) is None or check[mode]:
                raise ConversionError('This SNES profile requires a progressive 256 x 224 display. '
                    'The tested raster uses an unsupported or unverified video mode; previous export preserved.')
        if profile.get('video_scope')=='standard_ppu':
            if (check.get('visible_width') not in (256,512) or check.get('active_raster_height') not in (224,239) or
                    check.get('output_row_density') not in (1,2) or
                    check.get('visible_height') != check.get('active_raster_height',0)*check.get('output_row_density',0) or
                    check.get('captured_rows') != check.get('active_raster_height')):
                raise ConversionError('SNES validation is missing complete display geometry; previous export preserved.')
        if check.get('frames', 0) >= 3600 and (not check.get('visible_frames') or not check.get('pcm_nonzero')):
            raise ConversionError('SNES validation found no active picture or audible samples in a long test. '
                'The cartridge remains unqualified; previous export preserved.')


LIVENESS_MIN_FRAMES = 1200
LIVENESS_FIELDS = ('last_picture_change_frame', 'last_device_frame', 'last_audible_frame')


def validate_device_liveness(checks):
    """Refuse a device cartridge whose picture, device and sound all stopped.

    Only cartridges with a counted interpreted device (Super FX, CX4) are
    checked: the Star Fox 2 Japanese prototype sat on a controller notice from
    frame ~60 (picture frozen, GSU counter frozen at 770,961, silent) and still
    passed, because the activity test only asked for a non-zero device count.
    A scenario fails when, for its last max(600, frames/4) frames, the picture
    did not change AND the device executed nothing AND no sample was audible.
    A static screen that keeps its music, or a silent one whose device or
    picture still moves, is never refused. Ordinary cartridges are not checked.
    """
    from .core import ConversionError
    for check in checks:
        if check.get('cartridge_chip') in (None, 'none') or check.get('coprocessor_mode') != 'interpreted':
            continue
        frames = check.get('frames', 0)
        if frames < LIVENESS_MIN_FRAMES:
            continue
        if any(not isinstance(check.get(field), int) or isinstance(check.get(field), bool) for field in LIVENESS_FIELDS):
            raise ConversionError('SNES validation is missing the picture, device and sound activity evidence; '
                                  'previous export preserved.')
        alive = max(check[field] for field in LIVENESS_FIELDS)
        if frames - alive >= max(600, frames // 4):
            raise ConversionError(
                f"The {check['cartridge_chip'].upper()} cartridge stopped doing anything in the "
                f"{check.get('scenario', 'test')} run: no picture change, no device instruction and no sound "
                f"after frame {alive} of {frames}. The game is stuck (for instance on a notice), so the "
                'cartridge remains unqualified; previous export preserved.')


def write_profile(project: Path, rom, title: str) -> None:
    """Identity for a per-instruction program; no foreign game's function tree."""
    profile = profile_for(rom)
    from .snes_cart import layout
    memory = layout(rom)
    (project / 'retro_snes_game.h').write_text(
        f'#define RR_SN_TITLE {json.dumps(title, ensure_ascii=True)}\n'
        f'#define RR_SN_ROM_BYTES {len(rom.data)}u\n'
        f'#define RR_SN_SMW {int(profile["legacy_functions"])}\n'
        f'#define RR_SN_HIROM {int(rom.mapping=="hirom")}\n'
        f'#define RR_SN_PAL {int(video_standard(rom) == "pal")}\n', encoding='ascii')
    with (project / 'retro_snes_game.h').open('a', encoding='ascii') as file:
        file.write(f'#define RR_SN_RAM_BYTES {memory["bytes"]}u\n'
                   f'#define RR_SN_BATTERY {int(memory["battery"])}\n')
    if profile['legacy_functions']:
        return
    generated = project / 'generated'
    generated.mkdir(exist_ok=True)
    digest = ','.join(str(byte) for byte in bytes.fromhex(rom.sha256))
    # The operation map is generated separately for every ROM byte. The old
    # function-level dispatcher is unused, with its bridge disabled on both
    # paths. Empty metadata here never replaces any guest instruction body.
    (generated / 'instruction_program.c').write_text(f'''/* Original program identity. Guest operations are in snes_native_ops.inc. */
#include "cpu_state.h"
#include "program_module.h"
const DispatchEntry g_dispatch_table[] = {{{{0xffffffffu, {{NULL,NULL,NULL,NULL}}, 0}}}};
const unsigned g_dispatch_table_count = 0;
const RamRoutineGuard g_ram_routine_guards[] = {{{{0xffffffffu, 0, 0}}}};
const unsigned g_ram_routine_guard_count = 0;
static SnesProgramModule rr_program = {{
    .id = "main", .symbol_prefix = "", .dispatch = g_dispatch_table,
    .dispatch_count = 0, .guards = g_ram_routine_guards, .guard_count = 0,
    .rom_size = {len(rom.data)}u, .rom_sha256 = {{{digest}}},
    .program_digest = "{rom.sha256}", .build_digest = "rr-instruction-map-v1"
}};
SNES_PROGRAM_MODULE_CONSTRUCTOR(rr_register_instruction_program) {{
    snes_program_module_register(&rr_program);
}}
''', encoding='ascii')


def wram_offset(address: int) -> int | None:
    if not isinstance(address, int) or not 0 <= address <= 0xffffff:
        return None
    bank, offset = address >> 16, address & 0xffff
    if bank in (0x7e, 0x7f):
        return address & 0x1ffff
    if bank & 0x7f < 0x40 and offset < 0x2000:
        return offset
    return None


def valid_ram_variant(item, rom=None, *, memory=None) -> bool:
    if not isinstance(item, dict):
        return False
    address, raw = item.get('address'), item.get('bytes')
    return (isinstance(address, int) and isinstance(raw, str)
            and re.fullmatch('[0-9a-fA-F]{8}', raw) is not None
            and valid_ram_address(address,rom,memory=memory))


def valid_ram_address(address,rom=None,*,memory=None) -> bool:
    """Keep the existing four-byte ordinary RAM window, excluding MMIO."""
    if type(address) is not int or not 0<=address<=0xffffff:return False
    addresses=[(address&0xff0000)|((address+n)&0xffff) for n in range(4)]
    if all(wram_offset(a) is not None for a in addresses):return True
    from .snes_cart import layout,ram_offset
    if memory is None and rom is not None:memory=layout(rom)
    return memory is not None and all(wram_offset(a) is not None or ram_offset(memory,a) is not None for a in addresses)


def memory_file(rom) -> Path:
    return library_root('snes') / rom.sha256 / 'native-ram.json'


def knowledge_engine(rom) -> str:
    """The CPU/runtime revision recorded by SNES conversion reports."""
    from .console16 import REPOSITORIES
    return REPOSITORIES['snes'][1]


def bundled_record(rom) -> dict:
    """The qualified bank's record for this exact ROM, without imported hints."""
    from .knowledge import bundled_record as bundled
    return bundled('snes', rom, knowledge_engine(rom))


def read_ram_variants(rom, *, imported: bool = True) -> list[dict]:
    """Without `imported`: this player's library and gameplay rows and the bundled
    snapshot only. Other players' hints guide a conversion but are remembered
    (and shared again) only once a conversion observes them."""
    shared = (shared_ram_variants('snes', rom, knowledge_engine(rom)) if imported else
              [{'address': address, 'bytes': rom.data[offset:offset+length].hex()}
               for address, offset, length in bundled_record(rom).get('ram_refs', [])])
    from .feedback import variants
    shared += variants('snes', rom.sha256, 8, rom if imported else None)
    try:
        record = json.loads(memory_file(rom).read_text(encoding='utf-8'))
        if record.get('schema') != 1 or record.get('rom_sha256') != rom.sha256:
            record = {}
    except (OSError, ValueError, TypeError, AttributeError):
        record = {}
    items = [item for item in record.get('ram_variants', []) + shared if valid_ram_variant(item, rom)]
    return [{'address': addr, 'bytes': raw} for addr, raw in
            sorted({(item['address'], item['bytes'].lower()) for item in items})[:RAM_VARIANT_LIMIT]]


def read_ram_opcodes(rom, *, imported: bool = True) -> list[tuple[int,int]]:
    """Observed PC/opcode guards; operands remain live, never shared dumps."""
    sites={(item['address'],int(item['bytes'][:2],16)) for item in read_ram_variants(rom, imported=imported)}
    record = record_for('snes',rom,knowledge_engine(rom)) if imported else bundled_record(rom)
    for pc,offset in record.get('ram_opcode_refs',[]):
        if valid_ram_address(pc,rom) and 0<=offset<len(rom.data):sites.add((pc,rom.data[offset]))
    return sorted(sites)[:RAM_VARIANT_LIMIT]


def learn_ram_variants(rom, checks) -> int:
    additions = {(item['address'], item['bytes'].lower()) for check in checks
                 for item in check.get('ram_variants', []) if valid_ram_variant(item, rom)}
    if not additions:
        return 0
    path = memory_file(rom)
    with entry_lock(path.parent):
        # Imported hints enter the library only when this conversion observed
        # them; what counts as new (another pass) still includes them.
        known = {(item['address'], item['bytes'].lower()) for item in read_ram_variants(rom)}
        previous = {(item['address'], item['bytes'].lower()) for item in read_ram_variants(rom, imported=False)}
        merged = set(sorted(previous | additions)[:RAM_VARIANT_LIMIT])
        if previous != merged:
            atomic_json(path, {'schema': 1, 'rom_sha256': rom.sha256, 'ram_variants':
                [{'address': address, 'bytes': raw} for address, raw in sorted(merged)]})
    return len(merged - previous - known)
