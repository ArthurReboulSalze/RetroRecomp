"""CPS-1 native code: MC68000 and Z80 instruction AOT for one board folder.

The 68000 program ROM is swept statically (every even offset that decodes
legally) and observed work-RAM code adds guarded variants; the Z80 sound ROM
is translated at every byte position, banks included. Generated bodies use
the qualified Mega Drive/Neo Geo semantics, imported read-only; every
instruction stays guarded by its live code words at run time. Generated code
is a build product of the user's own ROMs and is never distributed.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re

from .paths import ROOT, ASSETS
from .core import run
from .library import atomic_json
from .m68000 import adapt_semantics, operation_bodies, mnemonic_names, instruction_literal
from .megadrive_codegen import write_changed
from .neogeo_codegen import canonical_instruction, structural_key, structural_body, shared_registers, decoder_tool
from .megadrive_z80 import opcode_key

PREFIX = 'rr_cps1'
CHUNKS = 16
RAM_BYTES = 0x10000
Z80_FIXED, Z80_BANKS = 0x8000, (0x10000, 0x18000)


def program_size(game: dict) -> int:
    """Bytes of maincpu actually loaded (the region is padded to 4 MiB)."""
    from .cps1_board import LAYOUTS
    end, layout = 0, LAYOUTS['load']
    for region in game['regions']:
        if region['tag'] != 'maincpu':
            continue
        for load in region['loads']:
            if load['op'] in LAYOUTS:
                layout = LAYOUTS[load['op']]
            elif load['op'] not in ('continue', 'reload'):
                continue
            group, skip, _ = layout
            count = (load['bytes'] + group - 1) // group
            end = max(end, load['offset'] + (count - 1) * (group + skip) + group)
    return min((end + 1) & ~1, 0x400000)


def ram_variants(records) -> list[tuple[int, bytes]]:
    """Bounded observed work-RAM code: (offset, up to eight words)."""
    unique = set()
    for record in records or ():
        offset, words = record.get('offset'), record.get('words')
        if type(offset) is not int or not 0 <= offset < RAM_BYTES or offset & 1:
            continue
        if not isinstance(words, str) or len(words) % 4 or not re.fullmatch(r'[0-9a-fA-F]{4,32}', words):
            continue
        data = bytes.fromhex(words)
        if offset + len(data) <= RAM_BYTES:
            unique.add((offset, data))
        if len(unique) > 4096:
            raise ValueError('CPS-1 RAM code observation bound exceeded.')
    return sorted(unique)


def _semantics(project: Path):
    engine = ROOT / '.deps/segagenesisrecomp'
    if not (engine / 'external/m68k-recomp-core/common/m68k_decoder.h').is_file():
        from .console16 import dependencies16
        engine, *_ = dependencies16('md', print)
    from .console16 import REPOSITORIES
    if run(['git', '-C', engine, 'rev-parse', 'HEAD']).strip() != REPOSITORIES['md'][1]:
        raise ValueError('MC68000 translation dependency differs from its qualified pin.')
    source = adapt_semantics((engine / 'runner/m68k_interp.c').read_text(encoding='utf-8'), hook_prefix=PREFIX)
    helper = source[source.index('static uint32_t szmask('):source.index('static uint8_t *s_exec_cov')]
    helper = helper[:helper.rfind('/* =====')]
    timing = source[source.index('static int interp_popcount16('):source.index('static void interp_account_cycles(')]
    timing = timing[:timing.rfind('/* The emit_cycle_accounting')]
    write_changed(project / 'cps1_step_semantics.h',
        '/* Qualified MC68000 helpers; see embedded GenesisRecomp notices. */\n'
        '#pragma once\n#include "m68kcpu.h"\n#include "cps1_native.h"\n#include <stddef.h>\n'
        f'#define s_illegal_ea {PREFIX}_illegal_ea\n'
        'static int interp_ea_read_cost(int ea,M68KSize sz);\n'
        'static int game_instruction_hook_site(uint32_t pc) {(void)pc;return 0;}\n'
        'static int genesis_game_instruction_hook(uint32_t pc) {(void)pc;return 0;}\n'
        'static void discover(uint32_t pc) {(void)pc;}\n' + shared_registers(helper + '\n' + timing))
    prefetch = (ASSETS / 'native/md_prefetch.inc').read_text(encoding='utf-8')
    arithmetic = prefetch[prefetch.index('unsigned rr_md_multiply_clocks('):prefetch.index('void rr_md_arithmetic_phase(')]
    write_changed(project / 'cps1_arithmetic.c', '#include "cps1_native.h"\n' + arithmetic.replace('rr_md_', PREFIX + '_') +
        f'\nvoid {PREFIX}_arithmetic_phase(unsigned base,unsigned ea,int multiply) {{\n'
        f' (void)multiply;{PREFIX}_arithmetic_cycles=base+ea;\n}}\n')
    for name, path in (('m68k_decoder.h', 'external/m68k-recomp-core/common/m68k_decoder.h'),
                       ('rom_parser.h', 'recompiler/src/rom_parser.h')):
        write_changed(project / name, (engine / path).read_text(encoding='utf-8'))
    return engine, source


def generate_m68k(project: Path, program: bytes, ram_records=()) -> dict:
    engine, source = _semantics(project)
    names = mnemonic_names(engine)
    bodies = operation_bodies(source)
    # CPS-1 boards leave the 68000 RESET output unconnected (MAME wires no
    # reset callback): like Musashi, the instruction only takes its clocks.
    bodies['MN_RESET'] = ('if (!(g_cpu.SR & SR_S))\n'
                          f'            return {PREFIX}_instruction_exception(next_pc, 8, ins->addr, 34);\n'
                          f'        {PREFIX}_arithmetic_cycles = CYC_RESET + CYC_INSTRUCTION[ins->words[0]];\n'
                          '        return M68KI_OK;')
    decoder = decoder_tool(engine)
    work = project / 'decode'
    work.mkdir(exist_ok=True)
    image = work / 'program.bin'
    image.write_bytes(program)
    # Reset and exception vectors are code roots; the sweep covers the rest.
    entries = sorted({int.from_bytes(program[n:n + 4], 'big') for n in range(4, 0x100, 4)
                      if int.from_bytes(program[n:n + 4], 'big') < len(program)} | {0})
    (work / 'program-pcs.txt').write_text(''.join(f'{pc:06x}\n' for pc in entries if not pc & 1), encoding='ascii')
    run([decoder, image, '0', work / 'program-pcs.txt', work / 'program.json', f'{len(program):x}'],
        log=project / 'decode.log')
    decoded = json.loads((work / 'program.json').read_text(encoding='utf-8'))
    instructions = [dict(ins, region=1, offset=ins['addr']) for ins in decoded
                    if names[ins['mnemonic']] in bodies]
    translated_rom = len(instructions)
    ram_keys = set()
    for offset, data in ram_variants(ram_records):
        base = 0xff0000 + offset
        (work / 'ram.bin').write_bytes(data)
        (work / 'ram-pcs.txt').write_text(f'{base:06x}\n', encoding='ascii')
        run([decoder, work / 'ram.bin', f'{base:x}', work / 'ram-pcs.txt', work / 'ram.json'], log=project / 'decode.log')
        ins = next((i for i in json.loads((work / 'ram.json').read_text(encoding='utf-8')) if i['addr'] == base), None)
        if not ins or names[ins['mnemonic']] not in bodies:
            continue
        key = (offset, tuple(ins['words'][:ins['word_count']]))
        if key not in ram_keys:
            ram_keys.add(key)
            instructions.append(dict(ins, region=3, offset=offset))
    instructions.sort(key=lambda ins: (ins['region'], ins['offset'], tuple(ins['words'])))
    chunks = [[] for _ in range(CHUNKS)]
    declarations, table, descriptors, forms, positions, records = [], [], {}, {}, [], []
    for ins in instructions:
        name = names[ins['mnemonic']]
        literal = instruction_literal(canonical_instruction(ins, name), name)
        key = (literal, ins['offset'] if ins['region'] == 3 else None)
        if key not in descriptors:
            form = structural_key(ins)
            if form not in forms:
                symbol = f'{PREFIX}_form_{len(forms)}'
                forms[form] = symbol
                body = structural_body(ins, name, bodies[name]).replace('rr_ng_', PREFIX + '_')
                chunks[(ins['words'][0] >> 1) % CHUNKS].append(
                    f'M68kiStatus {symbol}(const M68KInstr *compiled,uint32_t *next_pc) {{\n{body}}}\n')
                declarations.append(f'extern M68kiStatus {symbol}(const M68KInstr*,uint32_t*);\n')
            descriptors[key] = len(table) + 1
            records.append(ins)
            table.append('{' + literal + f',{forms[form]}' + '}')
        positions.append(descriptors[key])
    steps = project / 'steps'
    steps.mkdir(exist_ok=True)
    for index, chunk in enumerate(chunks):
        write_changed(steps / f'cps1_step_part{index:02d}.c',
                      '#include "cps1_step_semantics.h"\n' + shared_registers('\n'.join(chunk)))
    words = len(program) // 2
    rom_map = {ins['offset'] >> 1: positions[i] for i, ins in enumerate(instructions) if ins['region'] == 1}
    ram_heads, ram_next = {}, [0] * len(records)
    for index in range(len(records) - 1, -1, -1):
        if records[index]['region'] == 3:
            ram_next[index] = ram_heads.get(records[index]['offset'] >> 1, 0)
            ram_heads[records[index]['offset'] >> 1] = index + 1
    write_changed(steps / 'cps1_step_index.c',
        '#include "cps1_native.h"\n#include <stddef.h>\n' + ''.join(declarations) +
        'static const RrCps1NativeStep entries[]={\n' + ',\n'.join(table) + '\n};\n' +
        f'static const uint32_t rom_map[{words}]={{' + ','.join(str(rom_map.get(i, 0)) for i in range(words)) + '};\n' +
        'static const uint32_t ram_map[32768]={' + ','.join(str(ram_heads.get(i, 0)) for i in range(32768)) + '};\n' +
        'static const uint32_t ram_next[]={' + (','.join(map(str, ram_next)) or '0') + '};\n' +
        f'''const RrCps1NativeStep *{PREFIX}_native_lookup(uint32_t region,uint32_t offset) {{
    if(region!=RR_CPS1_CODE_ROM || (offset&1u) || offset>={words * 2}u)return NULL;
    unsigned index=rom_map[offset>>1];return index?&entries[index-1]:NULL;
}}
const RrCps1NativeStep *{PREFIX}_ram_native_lookup(uint32_t pc,uint32_t offset,unsigned available) {{
    if(offset>=65536u || (offset&1u))return NULL;
    for(unsigned index=ram_map[offset>>1];index;index=ram_next[index-1]) {{
        const RrCps1NativeStep *op=&entries[index-1];
        if(op->instruction.byte_length>available)continue;
        int match=1;
        for(unsigned n=0;n<(unsigned)op->instruction.word_count;++n) {{
            uint16_t actual;
            if(!{PREFIX}_code_word(pc+n*2u,&actual) || actual!=op->instruction.words[n]) {{match=0;break;}}
        }}
        if(match)return op;
    }}
    return NULL;
}}
''')
    return {'program_bytes': len(program), 'program_sha256': hashlib.sha256(program).hexdigest(),
            'decoded': len(decoded), 'translated_rom_positions': translated_rom,
            'guarded_ram_variants': len(ram_keys), 'unique_descriptors': len(table),
            'structural_bodies': len(forms), 'semantics_sha256': hashlib.sha256(source.encode()).hexdigest()}


def generate_z80(project: Path, z80_source: str, audio: bytes, ram_records=()) -> dict:
    """Every byte position of the fixed ROM and both banks, plus RAM variants."""
    from .neogeo_z80 import Emitter
    emitter = Emitter(z80_source)
    window = audio + audio[:3]
    mapping, keys = [None] * len(audio), set()
    for start, end in ((0, Z80_FIXED), Z80_BANKS):
        for offset in range(start, min(end, len(audio))):
            key = opcode_key(window[offset:offset + 4])
            mapping[offset] = key
            if key is not None:
                keys.add(key)
    ram = set()
    for item in ram_records or ():
        pc, raw = item.get('address'), item.get('bytes')
        if type(pc) is int and 0xd000 <= pc < 0xd800 and isinstance(raw, str) and re.fullmatch('[0-9a-fA-F]{8}', raw):
            key = opcode_key(bytes.fromhex(raw))
            if key is not None:
                ram.add((pc, key))
                keys.add(key)
    ordered = sorted(keys)
    indices = {key: index + 1 for index, key in enumerate(ordered)}
    functions, entries = [], []
    for index, (mask, raw) in enumerate(ordered):
        code = emitter.emit(raw)
        if 'exec_opcode' in code:
            raise ValueError('Runtime Z80 opcode dispatch leaked into AOT.')
        functions.append(f'static unsigned {PREFIX}_z80_op_{index}(z80 *z) {{unsigned cyc=0;\n{code}\nreturn cyc;}}\n')
        entries.append('{' + str(mask) + ',{' + ','.join(map(str, raw)) + f'}},{PREFIX}_z80_op_{index}' + '}')
    generated = ('/* Generated static Z80 bodies from the pinned core; notices embedded. */\n' + ''.join(functions) +
                 f'static const RrCps1Z80Step {PREFIX}_z80_entries[]={{\n' + ',\n'.join(entries) + '\n};\n' +
                 f'static const uint16_t {PREFIX}_z80_map[{len(audio)}]={{' +
                 ','.join(str(indices.get(key, 0)) for key in mapping) + '};\n' +
                 f'''static const RrCps1Z80Step *{PREFIX}_z80_native_lookup(uint32_t offset) {{
    unsigned index=offset<{len(audio)}u?{PREFIX}_z80_map[offset]:0;
    return index?&{PREFIX}_z80_entries[index-1]:NULL;
}}
static const RrCps1Z80Step *{PREFIX}_z80_ram_lookup(uint16_t pc) {{
''')
    for pc, key in sorted(ram):
        generated += f'''    if(pc=={pc}) {{
        const RrCps1Z80Step *op=&{PREFIX}_z80_entries[{indices[key] - 1}];int match=1;
        for(unsigned n=0;n<4;++n)if(op->mask&(1u<<n)) {{
            uint8_t actual;if(!{PREFIX}_z80_code_byte((uint16_t)(pc+n),&actual) || actual!=op->bytes[n])match=0;
        }}
        if(match)return op;
    }}
'''
    generated += '    return NULL;\n}\n'
    write_changed(project / 'cps1_z80_steps.inc', generated)
    return {'audio_bytes': len(audio), 'audio_sha256': hashlib.sha256(audio).hexdigest(),
            'structural_bodies': len(ordered), 'guarded_ram_variants': len(ram),
            'translated_positions': sum(key is not None for key in mapping)}


def generate(project: Path, board: Path, game: dict, z80_source: str, observations: dict | None = None) -> dict:
    observations = observations or {}
    program = (board / 'maincpu.bin').read_bytes()[:program_size(game)]
    audio = (board / 'audiocpu.bin').read_bytes()
    result = {'schema': 1, 'set': game['set'],
              'm68000': generate_m68k(project, program, observations.get('m68k_ram', ())),
              'z80': generate_z80(project, z80_source, audio, observations.get('z80_ram', ())),
              'knowledge_promoted': False}
    atomic_json(project / 'native-analysis.json', result)
    return result
