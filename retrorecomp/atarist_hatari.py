"""Hatari at its pin, adapted for Retro-Recomp at build time (MIT script; the files it changes stay GPL-2.0, like Hatari).

The Atari ST machine is Hatari (Thomas Huth and the Hatari team, GPL-2.0-or-later, effectively GPL-2.0-only in a build that
holds its CPU core: three WinUAE headers say "version 2" only; licenses/hatari.md). Its CPU is WinUAE's cycle-exact 68000. The
converter clones Hatari at the pinned revision into the workspace's `.deps`, copies the tree (without its git folder, its
documentation, tests and tools) into a build folder and applies the replacements below. Each one must find its pinned text exactly
once, so an upstream change fails loudly instead of building something else. Our changes to Hatari's files are GPL-2.0 too.

Hatari is built as its own CMake project (its build files name `CMAKE_SOURCE_DIR` and `CMAKE_BINARY_DIR`, so it cannot be a
subdirectory of ours) with its libretro frontend (`src/retro`, no SDL) and none of its optional libraries: no capsimg (its licence
forbids any commercial use and is not free software, so it never enters an export), no zlib, PNG, readline, Capstone or PortMidi.
IPF disks are read by Hatari's own reader (`src/floppies/ipf_dsk.c`, BSD-3-Clause, from MAME).

What the replacements do: build the libretro core as a static library that the player links (instead of a loadable module).
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from .paths import ROOT

HATARI_REPOSITORY = 'https://github.com/hatari/hatari.git'
HATARI_REV = 'c453b85f811fc11bed10e19e5e48fe95377e5a23'
FORMAT = 1

# The parts of the checkout the build needs (the top-level CMakeLists, its modules and the sources); the rest (documentation,
# tests, tools, the Python UI, icons) is left out, and so are their `add_subdirectory` lines.
COPIED = ('CMakeLists.txt', 'cmake', 'src', 'gpl.txt', 'readme.txt')

REPLACEMENTS = [
    # Retro-Recomp modifications (GPL-2.0, like this file): only the sources are built; the documentation, tests, Python UI and
    # shared icons are not copied.
    ('CMakeLists.txt', 'add_subdirectory(src)\nadd_subdirectory(doc)\n', 'add_subdirectory(src)\n'),
    ('CMakeLists.txt', 'if(NOT CMAKE_CROSSCOMPILING)\n\tadd_subdirectory(tests)\nendif(NOT CMAKE_CROSSCOMPILING)\n', ''),
    ('CMakeLists.txt', '\t\tadd_subdirectory(python-ui)\n', ''),
    ('CMakeLists.txt', 'if(UNIX AND NOT ENABLE_OSX_BUNDLE)\n\tadd_subdirectory(share)\nendif()\n', ''),
    # Upstream omission (c453b85, src/retro/file_retro.c, a frontend added on 1 Nov 2026): its Windows branch uses TCHAR,
    # MAX_PATH and GetTempPath without including windows.h.
    ('src/retro/file_retro.c',
     '#if defined(WIN32)\nstatic TCHAR szTempFileName[MAX_PATH];\n',
     '#if defined(WIN32)\n/* Retro-Recomp modification (GPL-2.0, like this file): the declarations this branch uses. */\n#include <windows.h>\n'
     'static TCHAR szTempFileName[MAX_PATH];\n'),
    # Upstream omission (same file): the log and trace "files" default to the special names "stderr" and "stdout", which this
    # frontend opened as real files, so every run created an empty file named "stderr" in the current folder (beside an exported
    # game). Our change: those names are the standard streams (as in Hatari's own SDL file layer), never closed.
    ('src/retro/file_retro.c',
     '\t/* empty name signifies file that shouldn\'t be opened/enabled */\n\tif (!path || !*path)\n\t\treturn NULL;\n',
     '\t/* empty name signifies file that shouldn\'t be opened/enabled */\n\tif (!path || !*path)\n\t\treturn NULL;\n'
     '\t/* Retro-Recomp modification (GPL-2.0, like this file): the special log names are the standard streams. */\n'
     '\tif (!strcmp(path, "stderr"))\n\t\treturn stderr;\n\tif (!strcmp(path, "stdout"))\n\t\treturn stdout;\n'),
    ('src/retro/file_retro.c', 'FILE *File_Close(FILE *fp)\n{\n\tif (fp)\n\t\tfclose(fp);\n',
     'FILE *File_Close(FILE *fp)\n{\n\t/* Retro-Recomp modification (GPL-2.0, like this file): the standard streams stay open. */\n'
     '\tif (fp && fp != stdin && fp != stdout && fp != stderr)\n\t\tfclose(fp);\n'),
    # States go through the libretro file system like every other file (the player keeps them in memory): the plain-file branch
    # of the snapshot code (no zlib in this build) uses Hatari's VFS functions instead of the C library's. This build never
    # links Hatari's own SDL program, so the core's files may call the frontend's VFS.
    ('src/memorySnapShot.c', '#else\n\ntypedef FILE* MSS_File;\n\n#endif\n',
     '#else\n\n/* Retro-Recomp modification (GPL-2.0, like this file): snapshots through the libretro VFS. */\n#include "retro/vfs.h"\n'
     'typedef VFS_FILE MSS_File;\n\n#endif\n'),
    ('src/memorySnapShot.c', '\treturn fopen(pszFileName, pszMode);\n#endif\n', '\treturn VFS_fopen(pszFileName, pszMode);\n#endif\n'),
    ('src/memorySnapShot.c', '\tfclose(fhndl);\n#endif\n', '\tVFS_fclose(fhndl);\n#endif\n'),
    ('src/memorySnapShot.c', '\treturn fread(buf, 1, len, fhndl);\n', '\treturn (int)VFS_fread(buf, 1, len, fhndl);\n'),
    ('src/memorySnapShot.c', '\treturn fwrite(buf, 1, len, fhndl);\n', '\treturn (int)VFS_fwrite(buf, 1, len, fhndl);\n'),
    ('src/memorySnapShot.c', '\treturn fseek(fhndl, pos, SEEK_CUR);\t\t/* return -1 if error, 0 if OK */\n',
     '\treturn VFS_fseek(fhndl, pos, SEEK_CUR) < 0 ? -1 : 0;\t/* return -1 if error, 0 if OK */\n'),
    # Upstream defect (c453b85, src/floppies/ipf_dsk.c, the built-in IPF reader): capturing a state ejected and reinserted every
    # IPF disk, which decoded it again (new random weak cells) and reset its stream, so a save changed the running machine. Our
    # change: a save only stores; a restore decodes the image again (its track descriptions point into the image) and then puts
    # back the saved flux of every track, so the restored disk is the saved one, weak cells included.
    ('src/floppies/ipf_dsk.c',
     '\t\tIPF_Eject(drive);\n\n\t\tif (ipf_memsnapshot_state(bSave, &IPF_State[drive]))',
     '\t\t/* Retro-Recomp modification (BSD-3-Clause, like this file): a save leaves the drive alone. */\n'
     '\t\tif (!bSave)\n\t\t\tIPF_Eject(drive);\n\n\t\tif (ipf_memsnapshot_state(bSave, &IPF_State[drive]))'),
    ('src/floppies/ipf_dsk.c',
     '\t\tif (EmulationDrives[drive].ImageType == FLOPPY_IMAGE_TYPE_IPF)\n\t\t{\n\t\t\tif (!IPF_Insert_internal(drive,',
     '\t\t/* Retro-Recomp modification (BSD-3-Clause, like this file): the stream as the state saved it (the reinsertion below\n'
     '\t\t * forgets its track and its position in it). */\n'
     '\t\tstruct ipf_stream saved = IPF_State[drive].stream;\n'
     '\t\tif (!bSave && EmulationDrives[drive].ImageType == FLOPPY_IMAGE_TYPE_IPF)\n\t\t{\n\t\t\tif (!IPF_Insert_internal(drive,'),
    # Upstream defect, same function: after a restore the track was never selected again (the reinsertion had set it to -1) and,
    # when it was, the position in the track went back to its start, so a state saved while a disk was being read continued the
    # read from the wrong place. Our change: select the saved track, then put back the position, the jitter and the revolutions.
    ('src/floppies/ipf_dsk.c',
     '\t\t\tif (IPF_State[drive].stream.track != (unsigned int)-1)\n\t\t\t{\n\t\t\t\tint track = IPF_State[drive].stream.track;\n'
     '\t\t\t\tIPF_State[drive].stream.track = (unsigned int)-1;\n\t\t\t\tipf_select_track(&MFM_STREAMS[drive], track);\n\t\t\t}\n',
     '\t\t\t/* Retro-Recomp modification (BSD-3-Clause, like this file): the saved track and the position in it. */\n'
     '\t\t\tif (saved.track != (unsigned int)-1)\n\t\t\t{\n'
     '\t\t\t\tuint32_t revolutions = MFM_STREAMS[drive].max_revolutions, number = MFM_STREAMS[drive].RevolutionsNbr;\n'
     '\t\t\t\tIPF_State[drive].stream.track = (unsigned int)-1;\n\t\t\t\tipf_select_track(&MFM_STREAMS[drive], saved.track);\n'
     '\t\t\t\tIPF_State[drive].stream.flux_idx = saved.flux_idx;\n\t\t\t\tIPF_State[drive].stream.acc_ns = saved.acc_ns;\n'
     '\t\t\t\tIPF_State[drive].stream.jitter = saved.jitter;\n'
     '\t\t\t\tMFM_STREAMS[drive].max_revolutions = revolutions;\n\t\t\t\tMFM_STREAMS[drive].RevolutionsNbr = number;\n\t\t\t}\n'),
    ('src/floppies/ipf_dsk.c',
     '\tIPF_State[Drive].decoder = IPF_DecodeImage(pImageBuffer, ImageSize);\n\tif (!IPF_State[Drive].decoder)\n\t{\n'
     '\t\tLog_Printf(LOG_ERROR, "IPF: failed to decode image in drive %d\\n", Drive);\n\t\treturn false;\n\t}\n',
     '\t/* Retro-Recomp modification (BSD-3-Clause, like this file): when a state is restored (KeepState), the decoder read from\n'
     '\t * the state keeps the flux of every track; the fresh decode gives the track descriptions, then takes that flux. */\n'
     '\tipf_decode *restored = KeepState ? IPF_State[Drive].decoder : NULL;\n'
     '\tIPF_State[Drive].decoder = IPF_DecodeImage(pImageBuffer, ImageSize);\n\tif (!IPF_State[Drive].decoder)\n\t{\n'
     '\t\tLog_Printf(LOG_ERROR, "IPF: failed to decode image in drive %d\\n", Drive);\n\t\treturn false;\n\t}\n'
     '\tif (restored)\n\t{\n\t\tfor (int c = 0; c < IPF_MAX_CYLINDER; c++)\n\t\t\tfor (int h = 0; h < IPF_MAX_HEAD; h++)\n\t\t\t{\n'
     '\t\t\t\tfree(IPF_State[Drive].decoder->tracks[c][h].flux);\n'
     '\t\t\t\tIPF_State[Drive].decoder->tracks[c][h] = restored->tracks[c][h];\n\t\t\t}\n\t\tfree(restored);\n\t}\n'),
    # Hatari's random numbers (weak floppy cells, a timer jitter) came from the C library's rand(): not saved in states and not
    # the same sequence on Windows and Linux. Our change: a portable generator whose state is saved with the machine (last, so a
    # restore that decodes an IPF image again does not change the sequence that follows).
    ('src/utils.c', '#include "utils.h"\n',
     '#include "utils.h"\n/* Retro-Recomp modification (GPL-2.0, like this file): the generator below is saved in states. */\n'
     '#include "main.h"\n#include "memorySnapShot.h"\n'),
    ('src/utils.c',
     'void\tHatari_srand ( unsigned int seed )\n{\n\tsrand(seed);\n}\n\n\nint\tHatari_rand ( void )\n{\n\treturn rand();\n}\n',
     '/* Retro-Recomp modification (GPL-2.0, like this file): a portable linear congruential generator (15-bit results, as\n'
     ' * the smallest RAND_MAX), the same on every system, and its state saved in memory snapshots. */\n'
     'static uint32_t Hatari_rand_state = 1;\n\n'
     'void\tHatari_srand ( unsigned int seed )\n{\n\tHatari_rand_state = seed;\n}\n\n\n'
     'int\tHatari_rand ( void )\n{\n\tHatari_rand_state = Hatari_rand_state * 1103515245u + 12345u;\n'
     '\treturn (int)((Hatari_rand_state >> 16) & 0x7fff);\n}\n\n\n'
     'void\tHatari_rand_MemorySnapShot_Capture ( int bSave )\n{\n\t(void)bSave;\n'
     '\tMemorySnapShot_Store(&Hatari_rand_state, sizeof(Hatari_rand_state));\n}\n'),
    ('src/includes/utils.h', 'extern int\tHatari_rand\t\t( void );\n',
     'extern int\tHatari_rand\t\t( void );\n/* Retro-Recomp modification (GPL-2.0, like this file). */\n'
     'extern void\tHatari_rand_MemorySnapShot_Capture\t( int bSave );\n'),
    ('src/memorySnapShot.c', '#include "falcon/nvram.h"\n', '#include "falcon/nvram.h"\n#include "utils.h"\n'),
    ('src/memorySnapShot.c', '\t\tMC146818_MemorySnapShot_Capture(true);\n',
     '\t\tMC146818_MemorySnapShot_Capture(true);\n\t\tHatari_rand_MemorySnapShot_Capture(true);\t/* Retro-Recomp modification */\n'),
    ('src/memorySnapShot.c', '\t\tMC146818_MemorySnapShot_Capture(false);\n',
     '\t\tMC146818_MemorySnapShot_Capture(false);\n\t\tHatari_rand_MemorySnapShot_Capture(false);\t/* Retro-Recomp modification */\n'),
    # The hook of the cycle-exact 68000 loop (the loop of a plain ST): before each instruction runs, the player's step function
    # is asked first; it counts the instruction, records it when the conversion observes, or runs a guarded native step of it
    # (the very handler the table would call) and answers true. NULL (Hatari alone): the table, as before.
    ('src/cpu/newcpu.c', 'static void m68k_run_1_ce (void)\n{\n\tstruct regstruct *r = &regs;\n',
     '/* Retro-Recomp modification (GPL-2.0, like this file): the step hook of the cycle-exact 68000 loop. */\n'
     'bool (*rr_hatari_step)(uae_u32 pc, uae_u32 opcode) = NULL;\n\n'
     'static void m68k_run_1_ce (void)\n{\n\tstruct regstruct *r = &regs;\n'),
    ('src/cpu/newcpu.c',
     '\t\t\t\t(*cpufunctbl_noret[r->opcode])(r->opcode);\n\t\t\t\tif (!regs.loop_mode)\n\t\t\t\t\tregs.ird = regs.opcode;\n'
     '\t\t\t\tregs.instruction_cnt++;\n\t\t\t\twait_memory_cycles();',
     '\t\t\t\t/* Retro-Recomp modification (GPL-2.0, like this file): the step hook first, else the table. */\n'
     '\t\t\t\tif (!(rr_hatari_step && rr_hatari_step(r->instruction_pc, r->opcode)))\n'
     '\t\t\t\t\t(*cpufunctbl_noret[r->opcode])(r->opcode);\n\t\t\t\tif (!regs.loop_mode)\n\t\t\t\t\tregs.ird = regs.opcode;\n'
     '\t\t\t\tregs.instruction_cnt++;\n\t\t\t\twait_memory_cycles();'),
    ('src/CMakeLists.txt',
     'add_library(retro-hatari MODULE\n',
     '# Retro-Recomp modification (GPL-2.0, like this file): the core is linked into the player.\n'
     'add_library(retro-hatari STATIC\n'),
]

# What the configure step is given: the libretro frontend only, every optional library left out (found or not on the host).
DISABLED_PACKAGES = ('SDL3', 'SDL2', 'CapsImage', 'ZLIB', 'PNG', 'Readline', 'Capstone', 'PortMidi', 'X11', 'LibArchive',
                     'PortAudio', 'Udev')
OPTIONS = ('-DENABLE_HATARI=OFF', '-DENABLE_TOOLS=OFF', '-DENABLE_LIBRETRO=ON', '-DENABLE_DSP_EMU=OFF',
           '-DENABLE_TRACING=OFF', '-DENABLE_MAN_PAGES=OFF', '-DENABLE_SMALL_MEM=OFF')


def adaptation_digest() -> str:
    """What the adapted tree depends on besides the pin: the copied parts, the replacements and the configure options."""
    value = hashlib.sha256(b'atarist-hatari-adaptation\0' + str(FORMAT).encode() + b'\0' + HATARI_REV.encode())
    for part in COPIED:
        value.update(b'\0copy\0' + part.encode())
    for rel, old, new in REPLACEMENTS:
        value.update(b'\0' + rel.encode() + b'\0' + old.encode() + b'\0' + new.encode())
    for item in (*DISABLED_PACKAGES, *OPTIONS):
        value.update(b'\0opt\0' + item.encode())
    return value.hexdigest()


def source(emit=print) -> Path:
    """The pinned Hatari checkout under `.deps` (cloned when missing, refused when moved or edited)."""
    from .conversion_common import pinned_checkout
    from .core import run
    target = ROOT / '.deps' / 'hatari'

    def git(*arguments, **options):
        return run(['git', '-C', target, *arguments], **options)

    def clone():
        emit('Atari ST: fetching Hatari at its pinned revision.')
        run(['git', 'clone', '--no-hardlinks', HATARI_REPOSITORY, target])
        git('checkout', '--detach', HATARI_REV)

    def refuse(head):
        raise ValueError('Hatari revision differs from the pinned one.')
    pinned_checkout(target, HATARI_REV, git, present=target.exists(), clone=clone, moved=refuse,
                    dirty=lambda: ValueError('Hatari sources changed; the converter adapts a copy.'))
    return target


def adapt(checkout: Path, target: Path) -> Path:
    """Copy the needed parts of the checkout to `target/hatari` and apply the replacements; returns the adapted tree. Done once
    per adaptation digest (a `ready.json` beside it)."""
    ready = target / 'ready.json'
    digest = adaptation_digest()
    tree = target / 'hatari'
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
        (shutil.copytree if origin.is_dir() else shutil.copy2)(origin, tree / part)
    for rel, old, new in REPLACEMENTS:
        path = tree / rel
        text = path.read_text(encoding='utf-8')
        if text.count(old) != 1:
            raise ValueError(f'Hatari {rel}: the pinned text was not found exactly once.')
        path.write_text(text.replace(old, new), encoding='utf-8', newline='\n')
    ready.write_text(json.dumps({'revision': HATARI_REV, 'adaptation': digest, 'replacements': len(REPLACEMENTS)}) + '\n',
                     encoding='utf-8')
    return tree


def configure_arguments(libretro_include: Path) -> list[str]:
    """The options of Hatari's own configure step (the toolchain's arguments are added by the caller)."""
    return [*OPTIONS, f'-DLIBRETRO_INCLUDE_DIR={libretro_include.as_posix()}', '-DCMAKE_BUILD_TYPE=Release',
            *(f'-DCMAKE_DISABLE_FIND_PACKAGE_{name}=TRUE' for name in DISABLED_PACKAGES)]
