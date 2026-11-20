"""Mupen64Plus-Next at its pin, adapted for Retro-Recomp at build time (MIT script; the files it copies and changes keep their own
licences: licenses/mupen64plus-next.md).

The Nintendo 64 machine is the libretro core "Mupen64Plus-Next" (libretro/mupen64plus-libretro-nx): the Mupen64Plus core
(GPL-2.0-or-later), its HLE and cxd4 RSP plugins (GPL-2.0-or-later, CC0), ParaLLEl-RSP (MIT, with GNU Lightning, LGPL-3.0-or-later)
and ParaLLEl-RDP (MIT, Vulkan). The converter clones it at the pinned revision into the workspace's `.deps` and copies only the
parts the game compiles into a build folder. Left out on purpose (Fable review and lead decisions of 7 November 2026,
.build/n64-gate/CONDITIONS-20261107.md):

* `mupen64plus-video-angrylion` (old MAME licence, no commercial use): never copied, so never in an export or its sources.
* The GLideN64 renderer (GPL-2.0-only: it cannot share a GPL-3 exe with the Apache-2.0 Vulkan headers and LGPL-3 Lightning): only
  its two OS-abstraction files (Mupen64Plus, GPL-2.0-or-later) are copied.
* Eleven files with no licence notice under the repository's GPL-2.0 text (the ParaLLEl plugin glue, `z64.h`, Zilmar's plugin spec
  header, five small libretro headers): replaced by our own MIT files written from the interfaces (native/n64_machine/glue).
* The new dynamic recompiler: the core's interpreters run, and our native blocks replace hot code.

The adaptation splits the core's pure interpreter (mupen64plus-core/src/device/r4300/pure_interp.c): everything up to its opcode
switch, made an always-inlined `execute_op(r4300, op)`, becomes `n64_exec.h`, which the generated native blocks compile (the core's
own instruction functions with constant opcodes); its run loop gains the hooks of the native blocks and of the observation, both
implemented in our own MIT file (native/n64_machine/n64_cpu.c). Each replacement must find its pinned text exactly once.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from .paths import ROOT

CORE_REPOSITORY = 'https://github.com/libretro/mupen64plus-libretro-nx.git'
CORE_REV = '15bada85906593376e8fd697f1b0b3af3a20f512'
FORMAT = 1

# Folders and files of the checkout the build needs, copied as they are (minus EXCLUDED below).
COPIED = ('LICENSE', 'mupen64plus-core', 'mupen64plus-rsp-hle', 'mupen64plus-rsp-cxd4', 'mupen64plus-rsp-paraLLEl',
          'mupen64plus-video-paraLLEl/parallel-rdp', 'libretro-common', 'xxHash', 'custom',
          'libretro/libretro.c', 'libretro/libretro_core_options.h', 'libretro/link.T',
          'GLideN64/src/osal/osal_files.h', 'GLideN64/src/osal/osal_files_win32.c', 'GLideN64/src/osal/osal_files_unix.c',
          'GLideN64/src/osal/osal_keys.h', 'GLideN64/LICENSE')
# Unmarked files inside the copied folders (replaced by our own glue/ headers) and anything of GLideN64 or angrylion.
EXCLUDED = ('custom/GLideN64',)

INTERP = 'mupen64plus-core/src/device/r4300/pure_interp.c'
INTERP_HEAD = ('void InterpretOpcode(struct r4300_core* r4300)\n{\n\tuint32_t* op_address = fast_mem_access(r4300, *r4300_pc(r4300));\n'
               '\tif (op_address == NULL)\n\t\treturn;\n\tuint32_t op = *op_address;\n\tswitch ((op >> 26) & 0x3F) {')
INTERP_FORWARD = 'static void InterpretOpcode(struct r4300_core* r4300);'
INTERP_LOOP_START = 'void run_pure_interpreter(struct r4300_core* r4300)'
INTERP_LOOP = ('void run_pure_interpreter(struct r4300_core* r4300)\n{\n   *r4300_stop(r4300) = 0;\n'
               '   *r4300_pc_struct(r4300) = &r4300->interp_PC;\n'
               '   *r4300_pc(r4300) = r4300->cp0.last_addr = r4300->start_address;\n\n'
               '   while (!*r4300_stop(r4300))\n   {\n#ifdef COMPARE_CORE\n     CoreCompareCallback();\n#endif\n'
               '#ifdef DBG\n     if (g_DebuggerActive) update_debugger(*r4300_pc(r4300));\n#endif\n'
               '     InterpretOpcode(r4300);\n   }\n}')
INTERP_BODY = '''#include "n64_exec.h"

void InterpretOpcode(struct r4300_core* r4300)
{
	uint32_t* op_address = fast_mem_access(r4300, *r4300_pc(r4300));
	if (op_address == NULL)
		return;
	execute_op(r4300, *op_address);
}

/* Retro-Recomp modification (GPL-2.0-or-later, like this file): the hooks of the native blocks and of the observation; both are
 * implemented in native/n64_machine/n64_cpu.c (MIT). Mode 0: interpreter only; 1: observe; 2: native blocks first. */
extern int rr_n64_cpu_mode;
extern uint64_t rr_n64_interpreted;
void rr_n64_cpu_start(struct r4300_core* r4300);
int rr_n64_run_blocks(struct r4300_core* r4300);
void rr_n64_observe(uint32_t pc);

void run_pure_interpreter(struct r4300_core* r4300)
{
   *r4300_stop(r4300) = 0;
   *r4300_pc_struct(r4300) = &r4300->interp_PC;
   *r4300_pc(r4300) = r4300->cp0.last_addr = r4300->start_address;
   rr_n64_cpu_start(r4300);

   while (!*r4300_stop(r4300))
   {
     if (rr_n64_cpu_mode == 2 && rr_n64_run_blocks(r4300))
        continue;
     if (rr_n64_cpu_mode == 1)
        rr_n64_observe(*r4300_pc(r4300));
     rr_n64_interpreted++;
     InterpretOpcode(r4300);
   }
}
'''

CACHED_LOOP = ('void run_cached_interpreter(struct r4300_core* r4300)\n{\n    while (!*r4300_stop(r4300))\n    {\n')
INIT_DATABASE = r'''    environ_cb(RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY, &sys_pathname);
    char pathname[PATH_SIZE];
    strncpy(pathname, sys_pathname, PATH_SIZE);
    if (pathname[(strlen(pathname)-1)] != '/' && pathname[(strlen(pathname)-1)] != '\\')
        strcat(pathname, "/");
    strcat(pathname, "Mupen64plus/");
    mbstowcs(w_pathname, pathname, PATH_SIZE);
    if (!osal_path_existsW(w_pathname) || !osal_is_directory(w_pathname))
        osal_mkdirp(w_pathname);
    copy_file(inifile, "mupen64plus.ini");
'''
VI = 'mupen64plus-video-paraLLEl/parallel-rdp/parallel-rdp/video_interface.cpp'
STATE_JOB = ('        if (savestates_get_job() == savestates_job_{job})\n        {{\n            savestates_{job}();\n'
             '            return;\n        }}\n')
STATE_RETURN = ('        if (savestates_get_job() == savestates_job_{job})\n        {{\n            savestates_{job}();\n'
                '            /* Retro-Recomp modification (GPL-2.0-or-later, like this file): back to the frontend at once. */\n'
                '            {{ void retro_return(void); retro_return(); }}\n            return;\n        }}\n')
CACHED_DEBUG = '        if (g_DebuggerActive) update_debugger((*r4300_pc_struct(r4300))->addr);\n#endif\n'
CACHED_OPS = CACHED_DEBUG + '        (*r4300_pc_struct(r4300))->ops();\n    }\n}'

RSP_STATE = '''\t/* Retro-Recomp modification (under this file's own licence): the RSP's registers for a quick state (native/n64_machine/
\t * n64_session.cpp): its PC and delay slot, the scalar registers, the vector unit (registers, flags, accumulators, divider), and the
\t * plugin's MFC0 counters and status wait. */
\tsize_t rr_n64_rsp_state_size(void)
\t{
\t\treturn sizeof(uint32_t) * 3 + sizeof(RSP::cpu.get_state().sr) + sizeof(RSP::CP2) + sizeof(RSP::MFC0_count) + sizeof(int);
\t}

\tvoid rr_n64_rsp_state(void *out, const void *in)
\t{
\t\tauto &s = RSP::cpu.get_state();
\t\tstruct Field { void *at; size_t size; } fields[] = {
\t\t\t{ &s.pc, sizeof s.pc }, { &s.has_delay_slot, sizeof s.has_delay_slot }, { &s.branch_target, sizeof s.branch_target },
\t\t\t{ s.sr, sizeof s.sr }, { &s.cp2, sizeof(RSP::CP2) }, { RSP::MFC0_count, sizeof RSP::MFC0_count },
\t\t\t{ &RSP::SP_STATUS_TIMEOUT, sizeof RSP::SP_STATUS_TIMEOUT } };
\t\tsize_t at = 0;
\t\tfor (auto &f : fields)
\t\t{
\t\t\tif (out)
\t\t\t\tmemcpy(static_cast<uint8_t *>(out) + at, f.at, f.size);
\t\t\tif (in)
\t\t\t\tmemcpy(f.at, static_cast<const uint8_t *>(in) + at, f.size);
\t\t\tat += f.size;
\t\t}
\t}

'''
SINC = 'libretro-common/audio/resampler/drivers/sinc_resampler.c'
AUDIO = 'custom/mupen64plus-core/plugin/audio_libretro/audio_backend_libretro.c'
SINC_STATE = '''/* Retro-Recomp modification (under this file's own licence): the resampler's running state, for a quick state (its position, its
 * time and the history of both channels; the phase table is fixed by its settings). rr_sinc_state copies it out when `out` is
 * given, in when `in` is. */
size_t rr_sinc_state_size(void *data)
{
   const rarch_sinc_resampler_t *re = (const rarch_sinc_resampler_t*)data;
   return re ? 3 * sizeof(uint32_t) + 4 * re->taps * sizeof(float) : 0;
}

void rr_sinc_state(void *data, void *out, const void *in)
{
   rarch_sinc_resampler_t *re = (rarch_sinc_resampler_t*)data;
   const size_t history = 2 * re->taps * sizeof(float);
   uint32_t head[3];
   if (out)
   {
      head[0] = re->taps;
      head[1] = re->ptr;
      head[2] = re->time;
      memcpy(out, head, sizeof head);
      memcpy((uint8_t*)out + sizeof head, re->buffer_l, history);
      memcpy((uint8_t*)out + sizeof head + history, re->buffer_r, history);
   }
   if (in)
   {
      memcpy(head, in, sizeof head);
      if (head[0] != re->taps)
         return;
      re->ptr  = head[1];
      re->time = head[2];
      memcpy(re->buffer_l, (const uint8_t*)in + sizeof head, history);
      memcpy(re->buffer_r, (const uint8_t*)in + sizeof head + history, history);
   }
}
'''
AUDIO_STATE = '''/* Retro-Recomp modification (GPL-2.0-or-later, like this file): the plugin's running state for a quick state, which the core's
 * own state leaves out: the game's audio rate and the resampler's position and history (native/n64_machine/n64_session.cpp). */
static void aiDacrateChanged(void *user_data, unsigned int frequency);
#ifndef __APPLE__
size_t rr_sinc_state_size(void *data);
void rr_sinc_state(void *data, void *out, const void *in);
#endif

size_t rr_n64_audio_state_size(void)
{
#ifdef __APPLE__
   return sizeof(int);
#else
   return sizeof(int) + rr_sinc_state_size(resampler_audio_data);
#endif
}

void rr_n64_audio_state_save(void *out)
{
   memcpy(out, &GameFreq, sizeof(int));
#ifndef __APPLE__
   rr_sinc_state(resampler_audio_data, (uint8_t*)out + sizeof(int), NULL);
#endif
}

int rr_n64_audio_state_load(const void *in, size_t size)
{
   int frequency;
   if (size != rr_n64_audio_state_size())
      return 0;
   memcpy(&frequency, in, sizeof(int));
   if (frequency > 0)
      aiDacrateChanged(NULL, (unsigned)frequency);
#ifndef __APPLE__
   rr_sinc_state(resampler_audio_data, NULL, (const uint8_t*)in + sizeof(int));
#endif
   return 1;
}
'''

FPU_ROUNDING = 'M64P_FPU_INLINE void set_rounding(uint32_t fcr31)\n{\n#if !defined(VITA) && !defined(__SWITCH__)\n    switch(fcr31 & 3) {\n'
FPU_ROUNDING_KEPT = '''M64P_FPU_INLINE void set_rounding(uint32_t fcr31)
{
#if !defined(VITA) && !defined(__SWITCH__)
#if defined(__x86_64__) && (defined(__GNUC__) || defined(__clang__))
    /* Retro-Recomp modification (GPL-2.0-or-later, like this file): fesetround only sets the rounding field of the x87 control
     * word (bits 10-11) and of MXCSR (bits 13-14), both coded by the hardware as 0 nearest, 1 down, 2 up, 3 toward zero (the FE_
     * constants differ between C libraries: mingw's are not these bits). When both fields already hold the wanted mode it would
     * change nothing, so it is skipped (mingw rewrites both words each time, a large share of an FPU-heavy frame). */
    {
        const unsigned wanted = (4u - (fcr31 & 3)) & 3u;   /* guest 0 nearest, 1 toward zero, 2 up, 3 down -> the hardware code */
        unsigned short x87;
        unsigned int sse;
        __asm__ __volatile__("fnstcw %0" : "=m"(x87));
        __asm__ __volatile__("stmxcsr %0" : "=m"(sse));
        if (((x87 >> 10) & 3u) == wanted && ((sse >> 13) & 3u) == wanted)
            return;
    }
#endif
    switch(fcr31 & 3) {
'''

REPLACEMENTS = [
    # Our glue's C interface (native/n64_machine/glue/parallel.h) instead of the unmarked one beside the plugin.
    ('libretro/libretro.c', '#include "../mupen64plus-video-paraLLEl/parallel.h"', '#include "parallel.h"'),
    # The cached interpreter (a game without native blocks runs it) counts its instructions too: the fallback is always counted.
    ('mupen64plus-core/src/device/r4300/cached_interp.c', CACHED_LOOP,
     '/* Retro-Recomp modification (GPL-2.0-or-later, like this file): the instructions run here are counted (native/n64_machine/'
     'n64_cpu.c). */\nextern uint64_t rr_n64_interpreted;\n\n' + CACHED_LOOP),
    ('mupen64plus-core/src/device/r4300/cached_interp.c', CACHED_OPS,
     CACHED_DEBUG + '        rr_n64_interpreted++;\n' + CACHED_OPS[len(CACHED_DEBUG):]),
    # A quick state is taken (and loaded) where the frame ended, and the core gives the frontend back control there: upstream
    # runs on to the next vertical interrupt inside retro_serialize/retro_unserialize, a whole frame whose picture is never
    # delivered, so saving moved the timeline by a frame.
    ('mupen64plus-core/src/device/r4300/interrupt.c', STATE_JOB.format(job='load'), STATE_RETURN.format(job='load')),
    ('mupen64plus-core/src/device/r4300/interrupt.c', STATE_JOB.format(job='save'), STATE_RETURN.format(job='save')),
    # The noise of the VI's dither filters is seeded by a frame counter the renderer keeps from its own start, which no quick state
    # holds: a resumed game drew other noise (±1 on most pixels). The seed is the session's frame number, which the state holds.
    (VI, '#include "video_interface.hpp"\n', '#include "video_interface.hpp"\n/* Retro-Recomp modification (MIT, like this file): '
     'the seed of the VI noise (native/n64_machine/n64_session.cpp). */\nextern "C" uint32_t rr_n64_vi_noise_frame(uint32_t own);\n'),
    (VI, '\tpush.frame_count = frame_count;\n', '\tpush.frame_count = rr_n64_vi_noise_frame(frame_count);\n'),
    # A quick state holds the renderer's own memory (native/n64_machine/glue/parallel_glue.cpp), which lives in the GPU's memory: the
    # glue copies it through a staging buffer and needs the two buffers, which the renderer keeps private.
    ('mupen64plus-video-paraLLEl/parallel-rdp/parallel-rdp/rdp_device.hpp', '\tsize_t get_hidden_rdram_size() const;\n',
     '\tsize_t get_hidden_rdram_size() const;\n\t/* Retro-Recomp modification (MIT, like this file): the buffers a quick state copies. */\n'
     '\tVulkan::Buffer &rr_hidden_rdram() { return *hidden_rdram; }\n\tVulkan::Buffer &rr_tmem() { return *tmem; }\n'
     '\tuint32_t &rr_base_primitive_index() { return renderer.rr_base_primitive_index(); }\n'),
    # ... and the renderer's count of primitives since it started, the seed of the RDP's dither noise per primitive: a fresh process
    # counted from its own start, so an effect drawn with noise came out otherwise after a load (GoldenEye 007, 95 frames on).
    ('mupen64plus-video-paraLLEl/parallel-rdp/parallel-rdp/rdp_renderer.hpp', '\texplicit Renderer(CommandProcessor &processor);\n',
     '\texplicit Renderer(CommandProcessor &processor);\n\t/* Retro-Recomp modification (MIT, like this file): the noise seed\'s base, for a quick state. */\n'
     '\tuint32_t &rr_base_primitive_index() { return base_primitive_index; }\n'),
    # The core's ROM database (save types, timing per game) is built in (custom/mupen64plus-core/main/mupen64plus.ini.h); upstream
    # writes it into a folder of the host at every start and reads it back. It is read from memory instead: nothing is written,
    # and a path the host's code page cannot spell does not lose it.
    ('libretro/libretro.c', INIT_DATABASE, '    /* Retro-Recomp modification: the ROM database is read from memory (rom.c); no folder is made. */\n'),
    ('mupen64plus-core/src/main/rom.c', '    const char *pathname = ConfigGetSharedDataFilepath("mupen64plus.ini");\n',
     '    /* Retro-Recomp modification (GPL-2.0-or-later, like this file): the built-in database, read from memory. */\n'
     '    extern char inifile[];\n    char *rr_n64_ini_gets(char *buffer, int size, const char **cursor);\n'
     '    const char *rr_cursor = inifile;\n    const char *pathname = "built-in mupen64plus.ini";\n'),
    ('mupen64plus-core/src/main/rom.c', '    if (pathname == NULL || (fPtr = fopen(pathname, "rb")) == NULL)\n',
     '    fPtr = NULL;\n    if (inifile[0] == 0)\n'),
    ('mupen64plus-core/src/main/rom.c', 'fgets(buffer, 255, fPtr) != NULL', 'rr_n64_ini_gets(buffer, 255, &rr_cursor) != NULL'),
    ('mupen64plus-core/src/main/rom.c', '    fclose(fPtr);\n    romdatabase_resolve();', '    (void)fPtr;\n    romdatabase_resolve();'),
    # A quick state holds the audio plugin's running state, which the core's own state leaves out: a resumed game delivered other
    # samples (and another number of them per frame) than the unbroken run. The sinc resampler's position and history ...
    (SINC, '} rarch_sinc_resampler_t;\n', '} rarch_sinc_resampler_t;\n\n' + SINC_STATE),
    # ... and the game's audio rate, read and written by the session (native/n64_machine/n64_session.cpp).
    (AUDIO, '#endif\n\nvoid deinit_audio_libretro(void)\n', '#endif\n\n' + AUDIO_STATE + '\nvoid deinit_audio_libretro(void)\n'),
    # A quick state holds the RSP's own registers, which ParaLLEl-RSP keeps outside the core's state: a task the RSP left on an
    # interrupt goes on from them, and a microcode may start from what the last task left (Banjo-Tooie's sound and RDRAM differed
    # from the first frame after a load).
    ('mupen64plus-rsp-paraLLEl/parallel.cpp', '\t// Hack entry point to use when loading savestates when we\'re tracing.\n',
     RSP_STATE + '\t// Hack entry point to use when loading savestates when we\'re tracing.\n'),
    # Every FPU operation sets the host's rounding mode to the guest's (fesetround), and mingw's fesetround rewrites the x87 and the
    # SSE control words each time: 13 % of a Super Mario 64 frame's main thread (.build/n64-perf-20261120.md). It is skipped when
    # both already hold the wanted mode, where fesetround would change nothing: the same mode is in force for every operation.
    ('mupen64plus-core/src/device/r4300/fpu.h', FPU_ROUNDING, FPU_ROUNDING_KEPT),
]


def adaptation_digest() -> str:
    """What the adapted tree depends on besides the pin: the copied parts, the replacements and the interpreter split."""
    value = hashlib.sha256(b'n64-mupen64plus-next-adaptation\0' + str(FORMAT).encode() + b'\0' + CORE_REV.encode())
    for part in (*COPIED, *EXCLUDED):
        value.update(b'\0part\0' + part.encode())
    for rel, old, new in REPLACEMENTS:
        value.update(b'\0' + rel.encode() + b'\0' + old.encode() + b'\0' + new.encode())
    for text in (INTERP_HEAD, INTERP_FORWARD, INTERP_LOOP, INTERP_BODY):
        value.update(b'\0interp\0' + text.encode())
    return value.hexdigest()


def source(emit=print) -> Path:
    """The pinned checkout under `.deps` (cloned when missing, refused when moved or edited)."""
    from .conversion_common import pinned_checkout
    from .core import run
    target = ROOT / '.deps' / 'mupen64plus-libretro-nx'

    def git(*arguments, **options):
        return run(['git', '-C', target, *arguments], **options)

    def clone():
        emit('Nintendo 64: fetching Mupen64Plus-Next at its pinned revision.')
        run(['git', 'clone', '--no-hardlinks', CORE_REPOSITORY, target])
        git('checkout', '--detach', CORE_REV)

    def refuse(head):
        raise ValueError('Mupen64Plus-Next revision differs from the pinned one.')
    pinned_checkout(target, CORE_REV, git, present=target.exists(), clone=clone, moved=refuse,
                    dirty=lambda: ValueError('Mupen64Plus-Next sources changed; the converter adapts a copy.'))
    return target


def split_interpreter(tree: Path) -> None:
    """The pure interpreter split into `n64_exec.h` (the core's instruction functions and execute_op) and its hooked run loop."""
    path = tree / INTERP
    text = path.read_text(encoding='utf-8').replace('\r\n', '\n')
    text = re.sub(r'(\tuint32_t op = \*op_address;)\n\s*\n(\tswitch)', r'\1\n\2', text, count=1)
    for anchor in (INTERP_HEAD, INTERP_FORWARD, INTERP_LOOP):
        if text.count(anchor) != 1:
            raise ValueError('Mupen64Plus pure_interp.c: a pinned text was not found exactly once.')
    text = text.replace(INTERP_HEAD, 'static inline __attribute__((always_inline)) void execute_op(struct r4300_core* r4300, '
                                     'uint32_t op)\n{\n\tswitch ((op >> 26) & 0x3F) {', 1)
    text = text.replace(INTERP_FORWARD, '/* Retro-Recomp modification (GPL-2.0-or-later, like this file): global, the jump functions of '
                                        'the native blocks call it for their delay slot. */\n#define InterpretOpcode rr_n64_interpret_opcode\n'
                                        'void InterpretOpcode(struct r4300_core* r4300);', 1)
    text = text.replace('#include "pure_interp.h"', '#include "device/r4300/pure_interp.h"', 1)
    cut = text.index(INTERP_LOOP_START)
    head = text[:cut]
    (tree / INTERP).with_name('n64_exec.h').write_text(
        '/* Retro-Recomp modification (GPL-2.0-or-later, like pure_interp.c from which the converter takes it at build time): the\n'
        ' * core\'s own instruction functions and execute_op(), compiled by the native blocks with constant opcodes. */\n'
        '#ifndef RR_N64_EXEC_H\n#define RR_N64_EXEC_H\n' + head + '\n#endif\n', encoding='utf-8', newline='\n')
    path.write_text('/* Mupen64Plus pure interpreter, split by Retro-Recomp at build time (retrorecomp/n64_core.py): its first part is\n'
                    ' * n64_exec.h. GPL-2.0-or-later, like the original file. */\n' + INTERP_BODY, encoding='utf-8', newline='\n')


def adapt(checkout: Path, target: Path) -> Path:
    """Copy the needed parts of the checkout to `target/core`, apply the replacements and split the interpreter; returns the
    adapted tree. Done once per adaptation digest (a `ready.json` beside it)."""
    ready = target / 'ready.json'
    digest = adaptation_digest()
    tree = target / 'core'
    try:
        if json.loads(ready.read_text(encoding='utf-8')).get('adaptation') == digest and tree.is_dir():
            return tree
    except (OSError, ValueError):
        pass
    if tree.exists():
        shutil.rmtree(tree)
    tree.mkdir(parents=True)
    for part in COPIED:
        origin = checkout / part
        destination = tree / part
        destination.parent.mkdir(parents=True, exist_ok=True)
        if origin.is_dir():
            shutil.copytree(origin, destination, ignore=shutil.ignore_patterns('.git', '*.o', '*.a'))
        else:
            shutil.copy2(origin, destination)
    for rel in EXCLUDED:
        excluded = tree / rel
        if excluded.is_dir():
            shutil.rmtree(excluded)
        else:
            excluded.unlink(missing_ok=True)
    for path in tree.rglob('*'):
        if 'angrylion' in path.name.casefold():
            raise ValueError('An angrylion file reached the adapted Nintendo 64 tree.')
    for rel, old, new in REPLACEMENTS:
        # The anchors are written with LF; a checkout with CRLF line ends (git on Windows) keeps them.
        path = tree / rel
        text = path.read_bytes().decode('utf-8')
        crlf = '\r\n' in text
        text = text.replace('\r\n', '\n')
        if text.count(old) != 1:
            raise ValueError(f'Mupen64Plus-Next {rel}: the pinned text was not found exactly once.')
        text = text.replace(old, new)
        path.write_bytes((text.replace('\n', '\r\n') if crlf else text).encode('utf-8'))
    split_interpreter(tree)
    ready.write_text(json.dumps({'revision': CORE_REV, 'adaptation': digest, 'replacements': len(REPLACEMENTS)}) + '\n',
                     encoding='utf-8')
    return tree
