"""Validate instruction AOT with authored ROM/stack/flags/RAM fixtures.

No commercial cartridge, SDL window or visual validation is involved.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smsrecomp.core import run, toolchain
from smsrecomp.megadrive_codegen import generate_steps, adapt_interpreter, adapt_cpu_snapshot, decode


def discovery_checks(engine, project):
    payload = bytearray([0xff] * 4096)
    payload[0x100:0x104] = b'SEGA'
    payload[:8] = bytes.fromhex('0000000000000200')
    program = {0x200: '4eb900000300', 0x206: '6608', 0x208: '600e',
               0x20a: '7002', 0x210: '7001', 0x212: '4e75', 0x218: '4ed0',
               0x21a: '7003', 0x300: '61000010', 0x304: '4e75',
               0x312: '4e71', 0x314: '60fc', 0xffe: '4eb9'}
    for pc, raw in program.items():
        code = bytes.fromhex(raw); payload[pc:pc + len(code)] = code
    rom = project / 'discovery-fixture.bin'
    rom.write_bytes(payload)
    roots = {0x200, 0x201, 0xffe, 0x1000}
    basic = decode(engine, project, rom, roots, follow_flow=False)
    followed = decode(engine, project, rom, roots)
    assert {ins['addr'] for ins in basic} == {0x200}, 'Invalid root or truncated opcode accepted'
    expected = {0x200, 0x206, 0x208, 0x210, 0x212, 0x218, 0x300, 0x304, 0x312, 0x314}
    assert len(followed) == len(expected) and {ins['addr'] for ins in followed} == expected, \
        'Static control flow must follow both branches/calls, terminate loops, and stop at returns/indirect jumps'
    tail = decode(engine, project, rom, set(),
        [{'address': 0xfffff4, 'bytes': '4ef900000800'},
         {'address': 0xfffffa, 'bytes': '4ef900000800'},
         {'address': 0xfffffe, 'bytes': '4e71'},
         {'address': 0xfffffc, 'bytes': '4ef900000800'},
         {'address': 0xfffffe, 'bytes': '4e710000'}])
    assert {ins['addr'] for ins in tail} == {0xfffff4, 0xfffffa, 0xfffffe} and len(tail) == 3, \
        'Accept instructions ending at the RAM boundary; reject byte windows crossing the bus end'
    return len(expected)


def main():
    project = ROOT / '.build/megadrive-native-selftest'
    project.mkdir(parents=True, exist_ok=True)
    engine = ROOT / '.deps/segagenesisrecomp'
    discovered = discovery_checks(engine, project)
    payload = bytearray(4096)
    payload[0x100:0x104] = b'SEGA'
    payload[:8] = bytes.fromhex('00ffc00000000200')
    operations = [
        '70ff', '7000', '7001', '1001', '3001', '2001', '207c00ff1000',
        '41f900ff1000', '41fa0008', '487900ff1000', '4a80', '4280', '4880', '48c0', '4840', 'c141',
        'd081', '9081', 'd0c1', '90c1', 'b081', 'b0c1', 'b108', 'c081', '8081', 'b380',
        '5280', '5380', '068000000001', '048000000001', '0c8000000001',
        '028000000001', '008000000001', '0a8000000001', '60fc', '67fc', '61fc', '51c8fffc',
        '4ef900000800', '4eb900000800', '4eba0008', '4e75', '4e77', '4e73',
        'e348', 'e248', 'e140', 'e040', 'e358', 'e258', 'e350', 'e250', 'e3d0',
        '08000001', '08400001', '08800001', '08c00001', '4480', '4080', '4680', '4ad0',
        'c0c1', 'c1c1', '80c1', '81c1', '48e700ff', '4cdf00ff', '4e56fff0', '4e5e',
        '57c0', '46fc2300', '40c0', '44fc001f', '4e60', 'd101', '9101', 'c101', '8101', '4800',
        '003c0001', '007c0001', '023c001f', '027c2700', '0a3c0001', '0a7c0001',
        '101f', '1027', '1ec0', '1f00', '521f', '0c180001', '303b0008', '4e71',
        '027cdfff', '46fc0315', '0a7c2000']
    pcs = set()
    positions = {}
    for index, raw in enumerate(operations):
        pc = 0x200 + index * 16; pcs.add(pc); positions.setdefault(raw, pc)
        code = bytes.fromhex(raw); payload[pc:pc + len(code)] = code
    payload[0x800:0x802] = bytes.fromhex('4e75'); pcs.add(0x800)
    for vector in range(16):
        pc = 0x900 + vector * 16
        payload[pc:pc + 2] = (0x4e40 + vector).to_bytes(2, 'big'); pcs.add(pc)
        payload[0x80 + vector * 4:0x84 + vector * 4] = positions['4e73'].to_bytes(4, 'big')
    payload[0xb00:0xb04] = bytes.fromhex('4e722500'); pcs.add(0xb00)
    payload[0xb10:0xb14] = bytes.fromhex('4e720700'); pcs.add(0xb10)
    # Keep peripheral-transfer fixtures away from the exception/return code.
    for index, raw in enumerate(('0108fff0', '0148fff0', '0188fff0', '01c8fff0')):
        pc = 0xc00 + index * 16
        payload[pc:pc + 4] = bytes.fromhex(raw); pcs.add(pc)
    (project / 'cartridge.bin').write_bytes(payload)
    rom = SimpleNamespace(data=payload, sha256=hashlib.sha256(payload).hexdigest())
    stats = generate_steps(engine, project, rom, pcs,
        [{'address': 0xff8000, 'bytes': '7001'}, {'address': 0xff8000, 'bytes': '70ff'},
         {'address': 0xff8040, 'bytes': '4eba0008'}, {'address': 0xff8060, 'bytes': '4eb900000800'},
         {'address': 0xff8080, 'bytes': '4e40'},
         {'address': 0xfffff4, 'bytes': '4ef900000800'},
         {'address': 0xfffffa, 'bytes': '4ef900000800'},
         {'address': 0xfffffe, 'bytes': '4e71'}],
        follow_flow=False)
    if stats['rejected_or_unimplemented']:
        raise RuntimeError(f'Authored fixture was not translated: {stats}')
    header = ('static const unsigned char fixture_rom[] = {' + ','.join(map(str, payload)) + '};\n' +
              'static const unsigned fixture_pcs[] = {' + ','.join(map(str, sorted(pcs))) + '};\n')
    for label, raw in [('JSR', '4eb900000800'), ('RTE', '4e73'), ('A7_POST', '101f'), ('A7_PRE', '1027'),
                       ('SR_AND', '027cdfff'), ('SR_MOVE', '46fc0315'), ('SR_EOR', '0a7c2000'),
                       ('USP_MOVE', '4e60')]:
        header += f'#define TEST_{label} {positions[raw]}u\n'
    header += '#define TEST_TRAP 0x900u\n'
    header += '#define TEST_STOP 0xb00u\n#define TEST_STOP_USER 0xb10u\n'
    header += '#define TEST_MOVEP 0xc00u\n'
    (project / 'fixture_data.h').write_text(header, encoding='ascii')
    shutil.copy2(ROOT / 'native/md_native_steps.h', project / 'md_native_steps.h')
    (project / 'retro_md_game.h').write_text('#define RR_MD_STEP_AOT 1\n', encoding='ascii')
    source = (engine / 'runner/m68k_interp.c').read_text(encoding='utf-8')
    source = source.replace('static void cov_mark(uint32_t pc) {',
        'extern void rr16_note_interpreted(void);\nstatic void cov_mark(uint32_t pc) {\n rr16_note_interpreted();', 1)
    (project / 'reference.c').write_text(adapt_interpreter(source), encoding='utf-8')
    snapshot = adapt_cpu_snapshot((engine / 'runner/rb_state.c').read_text(encoding='utf-8'))
    snapshot = snapshot[snapshot.index('static size_t sec_cpu_save('):snapshot.index('static size_t sec_ram_save(')]
    (project / 'md_cpu_snapshot_fixture.h').write_text(snapshot, encoding='utf-8')
    prefix = engine.as_posix()
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroMdNativeChecks C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
file(GLOB STEPS "steps/*.c")
add_executable(checks "{ROOT.as_posix()}/native/md_native_checks.c" reference.c ${{STEPS}}
  "{prefix}/recompiler/src/m68k_decoder.c" "{prefix}/recompiler/src/rom_parser.c")
target_include_directories(checks PRIVATE . "{prefix}/runner" "{prefix}/runner/include" "{prefix}/recompiler/src")
target_compile_options(checks PRIVATE /utf-8 /wd4996)
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, '-A', 'x64'], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'], log=project / 'build.log')
    output = run([project / 'build/Release/checks.exe'])
    result = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
    result['static_flow_instructions'] = discovered
    (project / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
