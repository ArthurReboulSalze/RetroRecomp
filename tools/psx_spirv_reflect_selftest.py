"""Does our SPIR-V reflector answer as SPIRV-Cross does, on every prebuilt shader of the pinned Beetle PSX?

    python tools/psx_spirv_reflect_selftest.py [--work DIR]

A developer's check, never part of a game. Beetle's Vulkan renderer asks `rhi_spirv_reflect()` for the resource layout of each of
its prebuilt shaders. Upstream implements it with SPIRV-Cross (Apache-2.0), which a GPL-2.0-only game cannot hold; the game
compiles `native/psx_machine/psx_spirv_reflect.c` instead (ours, written from the SPIR-V specification). This tool builds a small
program from the pinned checkout under `.deps/beetle-psx`: upstream's `rhi/rhi_spirv_reflect.cpp` with SPIRV-Cross on one side
(the oracle), our file on the other, and every `rhi/shaders_vulkan/prebuilt/*.inc` as data. It compares the two answers byte for
byte and writes `psx-spirv-reflect.json` under the work folder (default `.build/psx-spirv-reflect-selftest`): the shaders, how many
agree, and the first differing field of each one that does not. Exit code 0 when every shader agrees.

SPIRV-Cross is compiled here only as the oracle; nothing of it is copied into the repository or linked into a game.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MAIN = r'''#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <stddef.h>
extern "C" {
#include "rhi_spirv_reflect.h"
#include <libretro.h>
void upstream_reflect(const uint32_t *data, size_t word_count, RhiSpirvResourceLayout *out);
void ours_reflect(const uint32_t *data, size_t word_count, RhiSpirvResourceLayout *out);
static void quiet(enum retro_log_level level, const char *format, ...) { (void)level; (void)format; }
retro_log_printf_t libretro_log = quiet;
}
%(arrays)s
struct Shader { const char *name; const uint32_t *words; size_t count; };
static const Shader shaders[] = {
%(table)s};
#define FIELD(f) if (memcmp(&a.f, &b.f, sizeof a.f)) return #f;
static const char *first_difference(const RhiSpirvResourceLayout &a, const RhiSpirvResourceLayout &b) {
    FIELD(input_mask) FIELD(output_mask) FIELD(push_constant_size) FIELD(spec_constant_mask)
    for (int s = 0; s < RHI_SPIRV_NUM_DESCRIPTOR_SETS; ++s) {
        FIELD(sets[s].sampled_image_mask) FIELD(sets[s].storage_image_mask) FIELD(sets[s].uniform_buffer_mask)
        FIELD(sets[s].storage_buffer_mask) FIELD(sets[s].sampled_buffer_mask) FIELD(sets[s].input_attachment_mask)
        FIELD(sets[s].sampler_mask) FIELD(sets[s].separate_image_mask) FIELD(sets[s].fp_mask)
        FIELD(sets[s].immutable_sampler_mask) FIELD(sets[s].immutable_samplers)
    }
    return NULL;
}
int main(void) {
    int different = 0;
    printf("{\"shaders\": [\n");
    for (size_t i = 0; i < sizeof shaders / sizeof shaders[0]; ++i) {
        RhiSpirvResourceLayout a, b;
        upstream_reflect(shaders[i].words, shaders[i].count, &a);
        ours_reflect(shaders[i].words, shaders[i].count, &b);
        const char *field = first_difference(a, b);
        unsigned used = 0;
        for (int s = 0; s < RHI_SPIRV_NUM_DESCRIPTOR_SETS; ++s)
            used |= a.sets[s].sampled_image_mask | a.sets[s].storage_image_mask | a.sets[s].uniform_buffer_mask | a.sets[s].storage_buffer_mask
                  | a.sets[s].sampled_buffer_mask | a.sets[s].input_attachment_mask | a.sets[s].sampler_mask | a.sets[s].separate_image_mask;
        different += field != NULL;
        printf("  {\"name\": \"%%s\", \"words\": %%u, \"equal\": %%s, \"first_difference\": %%s%%s%%s, \"inputs\": %%u, \"outputs\": %%u, "
               "\"push_constant_bytes\": %%u, \"spec_constants\": %%u, \"bindings\": %%u}%%s\n",
               shaders[i].name, (unsigned)shaders[i].count, field ? "false" : "true", field ? "\"" : "", field ? field : "null",
               field ? "\"" : "", a.input_mask, a.output_mask, a.push_constant_size, a.spec_constant_mask, used,
               i + 1 < sizeof shaders / sizeof shaders[0] ? "," : "");
    }
    printf("], \"different\": %%d}\n", different);
    return different != 0;
}
'''


def ready() -> str | None:
    """Why the check cannot run here (no compiler, no pinned Beetle checkout), or None. It never clones: a check, not a setup."""
    try:
        from retrorecomp.core import toolchain
        toolchain()
    except Exception as error:      # no compiler in this installation
        return f'no C toolchain: {error}'
    if not (ROOT / '.deps' / 'beetle-psx' / 'rhi' / 'rhi_spirv_reflect.cpp').is_file():
        return 'the pinned Beetle PSX checkout is not there (.deps/beetle-psx)'
    return None


def cmake_project(beetle: Path) -> str:
    cross = sorted(p.as_posix() for p in (beetle / 'parallel-psx' / 'SPIRV-Cross').glob('*.cpp'))
    return '\n'.join([
        'cmake_minimum_required(VERSION 3.20)',
        'project(RetroPsxSpirvReflect LANGUAGES C CXX)',
        'set(CMAKE_C_STANDARD 99)',
        'set(CMAKE_CXX_STANDARD 11)',
        'add_library(oracle STATIC "' + (beetle / 'rhi' / 'rhi_spirv_reflect.cpp').as_posix() + '" ' + ' '.join(f'"{p}"' for p in cross) + ')',
        'target_compile_definitions(oracle PRIVATE rhi_spirv_reflect=upstream_reflect HAVE_LIBRETRO)',
        f'target_include_directories(oracle PRIVATE "{(beetle / "rhi").as_posix()}" "{(beetle / "parallel-psx" / "SPIRV-Cross").as_posix()}" '
        f'"{(beetle / "libretro-common" / "include").as_posix()}")',
        'add_library(ours STATIC "' + (ROOT / 'native' / 'psx_machine' / 'psx_spirv_reflect.c').as_posix() + '")',
        'target_compile_definitions(ours PRIVATE rhi_spirv_reflect=ours_reflect)',
        f'target_include_directories(ours PRIVATE "{(beetle / "rhi").as_posix()}")',
        'if(NOT MSVC)',
        '  target_compile_options(oracle PRIVATE -w)',
        '  target_compile_options(ours PRIVATE -Wall -Wextra -Werror)',
        'endif()',
        'add_executable(psx_spirv_reflect main.cpp)',
        f'target_include_directories(psx_spirv_reflect PRIVATE "{(beetle / "rhi").as_posix()}" "{(beetle / "libretro-common" / "include").as_posix()}")',
        'target_link_libraries(psx_spirv_reflect PRIVATE oracle ours)',
        '',
    ])


def main_source(beetle: Path) -> tuple[str, int]:
    prebuilt = sorted((beetle / 'rhi' / 'shaders_vulkan' / 'prebuilt').glob('*.inc'))
    arrays = ''.join(f'static const uint32_t shader_{i}[] =\n#include "{p.as_posix()}"\n;\n' for i, p in enumerate(prebuilt))
    table = ''.join(f'    {{"{p.name[:-4]}", shader_{i}, sizeof shader_{i} / sizeof shader_{i}[0]}},\n' for i, p in enumerate(prebuilt))
    return MAIN % {'arrays': arrays, 'table': table}, len(prebuilt)


def run_check(work: Path) -> dict:
    import subprocess
    from retrorecomp import psx_beetle
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_jobs, cmake_target_args, build_executable
    cmake, generator = toolchain()
    beetle = psx_beetle.source(print)
    project, binary, log = work / 'project', work / 'project' / 'build', work / 'build.log'
    project.mkdir(parents=True, exist_ok=True)
    log.write_text('', encoding='utf-8')
    source, count = main_source(beetle)
    (project / 'CMakeLists.txt').write_text(cmake_project(beetle), encoding='utf-8', newline='\n')
    (project / 'main.cpp').write_text(source, encoding='utf-8', newline='\n')
    run([cmake, '-S', project, '-B', binary, '-G', generator, *cmake_target_args()], log=log, timeout=900)
    run([cmake, '--build', binary, '--target', 'psx_spirv_reflect', '--parallel', build_jobs()], log=log, timeout=3600)
    done = subprocess.run([str(build_executable(binary, 'psx_spirv_reflect'))], capture_output=True, text=True, timeout=300,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    result = json.loads(done.stdout)
    result.update(revision=psx_beetle.BEETLE_REV, prebuilt=count, equal=sum(s['equal'] for s in result['shaders']), exit=done.returncode)
    (work / 'psx-spirv-reflect.json').write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8', newline='\n')
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--work', type=Path, default=ROOT / '.build' / 'psx-spirv-reflect-selftest')
    arguments = parser.parse_args()
    result = run_check(arguments.work)
    for shader in result['shaders']:
        if not shader['equal']:
            print(f"DIFFERENT {shader['name']}: {shader['first_difference']}")
    print(f"{result['equal']} of {result['prebuilt']} prebuilt shaders: the same layout as SPIRV-Cross "
          f"({sum(1 for s in result['shaders'] if s['bindings'])} with descriptor bindings, "
          f"{sum(1 for s in result['shaders'] if s['push_constant_bytes'])} with push constants, "
          f"{sum(1 for s in result['shaders'] if s['spec_constants'])} with specialization constants)")
    return 0 if result['equal'] == result['prebuilt'] and result['prebuilt'] else 1


if __name__ == '__main__':
    sys.exit(main())
