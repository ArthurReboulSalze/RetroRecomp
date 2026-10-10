"""Compare emitted bank-boundary instructions against the internal SM83 CPU."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smsrecomp.core import run
from smsrecomp.gameboy import _dependencies
from smsrecomp.gameboy_boundary import boundary_instruction, instruction_length
from smsrecomp.gameboy_build import safe_body_entries
from smsrecomp.gameboy_runtime import adapt_generated_project
from smsrecomp.paths import ASSETS


def main():
    project = ROOT / '.build/gb-boundary-selftest'
    project.mkdir(parents=True, exist_ok=True)
    rom = bytearray(32768)
    rom[0x100:0x103] = bytes.fromhex('c3 00 01')
    (project / 'fixture.gb').write_bytes(rom)
    engine, compiler, sdl, cmake, generator = _dependencies(print)
    log = project / 'build.log'
    run([compiler, project / 'fixture.gb', '-o', project, '--runtime-dir', engine / 'runtime',
         '--output-prefix', 'game', '--no-comments'], log=log, timeout=600)
    adapt_generated_project(project, 'boundary-fixture', '0' * 64, 'Authored bank fixture')
    (project / 'game_resources.rc').write_text('1 RCDATA { 0 }\n', encoding='utf-8')
    source = []
    cases = []
    for opcode in range(256):
        for address in (0x3FFE, 0x3FFF, 0x7FFE, 0x7FFF):
            code = boundary_instruction(opcode, address)
            if code and (address & 0x3FFF) + instruction_length(opcode) > 0x4000:
                name = f'fixture_{opcode:02x}_{address:04x}'
                source.append(f'static void {name}(GBContext* ctx) {{\n{code}\n}}')
                cases.append(f'{{0x{opcode:02x}, 0x{address:04x}, {name}}}')
    source.append('typedef struct { unsigned opcode, address; void (*step)(GBContext*); } Fixture;')
    source.append('static const Fixture fixtures[] = {\n' + ',\n'.join(cases) + '\n};')
    # Authored sparse entry map, including every unmatched 16-bit PC. This
    # exercises the balanced C selector with real /O2 compilation.
    entries = [(3 + 29 * index, index + 1) for index in range(1024)]
    entry_body = ('static void body_authored_entries(GBContext* ctx) {\n'
                  '    gbrt_note_generated_direct_transition(ctx);\n'
                  '    switch (ctx->pc) {\n' + ''.join(
                      f'        case 0x{pc:04x}: goto loc_{pc:04x};\n' for pc, _ in entries) +
                  '        default: break;\n    }\n' + ''.join(
                      f'loc_{pc:04x}:\n    ctx->de = {value}; return;\n' for pc, value in entries) + '}\n')
    transformed, count = safe_body_entries(entry_body)
    assert count == 1
    source.append(transformed)
    (project / 'runtime/include/gb_boundary_generated.inc').write_text('\n'.join(source), encoding='utf-8')
    with (project / 'CMakeLists.txt').open('a', encoding='utf-8') as out:
        out.write(f'\nadd_executable(retro_gb_boundary_checks "{(ASSETS / "native/gb_boundary_checks.c").as_posix()}")\ntarget_link_libraries(retro_gb_boundary_checks PRIVATE gbrt)\n')
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, '-A', 'x64',
         f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'], log=log, timeout=600)
    run([cmake, '--build', project / 'build', '--config', 'Release', '--target',
         'retro_gb_boundary_checks', '--parallel', '4'], log=log, timeout=600)
    output = run([project / 'build/Release/retro_gb_boundary_checks.exe'], timeout=180)
    (project / 'checks.log').write_text(output, encoding='utf-8')
    result = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
    (project / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result)


if __name__ == '__main__':
    main()
