"""Beetle PSX at its pin, prepared for Retro-Recomp at build time (MIT script; the files it copies stay under their own licences).

The PlayStation machine is Beetle PSX (libretro/beetle-psx-libretro, derived from Mednafen: GPL-2.0-or-later for the files that say
so, GPL v2 for the files that say nothing, so the game executable is treated as GPL-2.0-only as a whole). The converter clones it
at the pinned revision into the workspace's `.deps` and copies the files the game compiles into a build folder; nothing else of the
repository is built. Left out on purpose (licences/AGENTS decisions of 6 November 2026, .build/psx-study/agent-beetle.md):

* `mednafen/cdrom/CDAccess_PBP.c`: it embeds GPL-3.0 code (KIRK, amctrl) and PlayStation Portable keys. EBOOTs are read by our
  own reader (retrorecomp/psx_disc.py) and reach the core as raw sectors through the disc pack.
* `deps/lightrec`, `deps/lightning` (LGPL-2.1+ / LGPL-3.0+): the dynamic recompiler; the core's interpreter runs instead.
* `parallel-psx`, `rhi/rhi_lib_vulkan.c`, `rhi/rhi_lib_gl.c` and the texture-replacement files: the hardware renderers (Apache-2.0
  SPIRV-Cross, unlicensed ACES2 tables, a Blender-derived LUT). The software renderer is the reference.

Each replacement below must find its pinned text exactly once, so an upstream change fails loudly instead of building something
else; our changes to a GPL file are GPL like it (licenses/beetle-psx.md).
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from .paths import ROOT

BEETLE_REPOSITORY = 'https://github.com/libretro/beetle-psx-libretro.git'
BEETLE_REV = '71ee81e77acd49296ecf4a683f5a61568ba80bf9'
FORMAT = 1

# The C files of the software-rendered machine (Beetle's Makefile.common with HAVE_CHD=0, HAVE_LIGHTREC=0, no HW, no PBP,
# NEED_THREADING=0), in its order; the headers they include are copied with their folders.
SOURCES = (
    'mednafen/psx/cpu.c', 'mednafen/psx/cdc.c', 'mednafen/psx/vcd.c',
    'libretro-common/formats/mpeg1/rmpeg1_ps.c', 'libretro-common/formats/mpeg1/rmpeg1_video.c',
    'libretro-common/formats/mp3/rmp3.c', 'mednafen/psx/frontio.c', 'mednafen/psx/gpu.c',
    'libretro-common/formats/vorbis/rvorbis.c',
    'mednafen/cdrom/CDAccess.c', 'mednafen/cdrom/CDAccess_CCD.c', 'mednafen/cdrom/CDAccess_Image.c',
    'mednafen/cdrom/audioreader.c', 'mednafen/cdrom/cdromif.c', 'mednafen/cdrom/cdaccess_track.c',
    'mednafen/cdrom/CDUtility.c', 'mednafen/cdrom/galois.c', 'mednafen/cdrom/l-ec.c', 'mednafen/cdrom/lec.c',
    'mednafen/cdrom/recover-raw.c', 'mednafen/cdrom/edc_crc32.c',
    'libretro.c', 'libretro_game_database.c',
    'mednafen/mempatcher.c', 'mednafen/general.c', 'mednafen/error.c', 'mednafen/video/Deinterlacer.c',
    'input.c', 'mc_async.c', 'input_compatibility.c',
    'mednafen/psx/dma.c', 'mednafen/psx/gpu_polygon_sub.c', 'mednafen/psx/gte.c', 'mednafen/psx/irq.c',
    'mednafen/psx/mdec.c', 'mednafen/psx/sio.c', 'mednafen/psx/spu.c', 'mednafen/psx/timer.c',
    'rhi/rhi_intf.c', 'rhi/hdr_display.c', 'rhi/rhi_defer.c',
    'mednafen/cdstream.c', 'mednafen/settings.c', 'mednafen/state.c',
    'libretro-common/streams/file_stream.c', 'libretro-common/streams/file_stream_transforms.c',
    'libretro-common/file/file_path.c', 'libretro-common/file/file_path_io.c', 'libretro-common/file/retro_dirent.c',
    'libretro-common/vfs/vfs_implementation.c', 'libretro-common/lists/dir_list.c', 'libretro-common/lists/string_list.c',
    'libretro-common/string/stdstring.c', 'libretro-common/string/rstrtod.c', 'libretro-common/compat/compat_strl.c',
    'libretro-common/compat/fopen_utf8.c', 'libretro-common/compat/compat_strcasestr.c',
    'libretro-common/compat/compat_posix_string.c', 'libretro-common/encodings/encoding_utf.c',
    'libretro-common/encodings/encoding_crc32.c', 'libretro-common/memmap/memalign.c', 'libretro-common/time/rtime.c',
    'libretro-common/hash/lrc_hash.c', 'libretro-common/formats/data_transfer.c', 'libretro-common/memmap/memmap.c',
    'pgxp/pgxp_cpu.c', 'pgxp/pgxp_gpu.c', 'pgxp/pgxp_gte.c', 'pgxp/pgxp_main.c', 'pgxp/pgxp_mem.c', 'pgxp/pgxp_value.c',
    # The frontend's virtual file system (the disc is served from the game's pack) and the MIT inflater of its EBOOT blocks.
    'libretro-common/vfs/vfs_hybrid.c', 'libretro-common/encodings/encoding_deflate.c',
    # Referenced by the CD reader and the file layer even when they run synchronously (cd_access_method=sync starts no
    # thread), and the CPU-feature probe the inflater asks.
    'libretro-common/rthreads/rthreads.c', 'libretro-common/rthreads/retro_eventcount.c',
    'libretro-common/queues/retro_spsc.c', 'libretro-common/queues/retro_waitable_spsc.c',
    'libretro-common/features/features_cpu.c',
)
# Folders copied whole (headers, files included by other files: gpu.c includes gpu_polygon.c, gpu_sprite.c, gpu_line.c).
FOLDERS = ('mednafen', 'libretro-common', 'pgxp', 'rhi', 'deps/openbios', 'include')
FILES = ('COPYING', 'libretro_core_options.h', 'libretro_core_options_intl.h', 'libretro_options.h', 'libretro_cbs.h',
         'libretro_game_database.h', 'input.h', 'input_compatibility.h', 'mc_async.h', 'osd_message.h',
         'beetle_psx_globals.h', 'database/psx_games.inc')
# Files of the copied folders that are never compiled nor shipped with the sources (licence reasons above).
EXCLUDED = ('mednafen/cdrom/CDAccess_PBP.c', 'mednafen/cdrom/CDAccess_PBP.h')
DEFINES = ('__LIBRETRO__', 'NEED_CD', 'NEED_DEINTERLACER', 'WANT_32BPP', 'MEDNAFEN_VERSION_NUMERIC=9386', 'STDC_HEADERS',
           '__STDC_LIMIT_MACROS', '__STDC_CONSTANT_MACROS', '_FILE_OFFSET_BITS=64')
INCLUDES = ('.', 'mednafen', 'mednafen/include', 'libretro-common/include')

REPLACEMENTS: list[tuple[str, str, str]] = [
    # The player's BIOS comes from memory (it is embedded in the game), never from a file: the session sets rr_psx_bios_data
    # before loading the disc; NULL keeps Beetle's own behaviour (its built-in OpenBIOS when no BIOS file is found).
    ('libretro.c',
     '   if (BIOSFile)\n   {\n      int64_t bios_size      = filestream_get_size(BIOSFile);',
     '   /* Retro-Recomp modification (GPL-2.0, like this file): the BIOS embedded in the game, given by the host. */\n'
     '   if (rr_psx_bios_data)\n   {\n'
     '      if (BIOSFile)\n         filestream_close(BIOSFile);\n'
     '      bios_addr_mask       = BIOS_SIZE_STD - 1;\n'
     '      bios_mapped_size     = BIOS_SIZE_STD;\n'
     '      psx_bios_is_scph5903 = false;\n'
     '      memset(BIOSROM->data8, 0, BIOS_SIZE);\n'
     '      memcpy(BIOSROM->data8, rr_psx_bios_data, BIOS_SIZE_STD);\n'
     '   }\n'
     '   else if (BIOSFile)\n   {\n      int64_t bios_size      = filestream_get_size(BIOSFile);'),
    ('libretro.c',
     '#include <vfs/vfs_hybrid.h>\n',
     '#include <vfs/vfs_hybrid.h>\n'
     '/* Retro-Recomp modification (GPL-2.0, like this file): the BIOS image the host gives (512 KiB), NULL: none. */\n'
     'const unsigned char *rr_psx_bios_data = NULL;\n'),
    # Every instruction the interpreter runs is fetched here once (the loop head and the replicated dispatch both call it):
    # the count of interpreted instructions the report and the game's honesty counter show.
    ('mednafen/psx/cpu.c',
     'static INLINE uint32_t ReadInstruction(int32_t *timestamp, uint32_t address)\n{\n   uint32_t instr;\n',
     '/* Retro-Recomp modification (GPL-2.0, like this file): instructions run by the interpreter. */\n'
     'uint64_t rr_psx_interpreted_count = 0;\n'
     'static INLINE uint32_t ReadInstruction(int32_t *timestamp, uint32_t address)\n{\n   uint32_t instr;\n\n'
     '   ++rr_psx_interpreted_count;\n'),
    # The EBOOT reader (CDAccess_PBP.c) is not compiled, so the disc count it keeps is defined here, at 0 (no EBOOT).
    ('libretro.c',
     'extern int PBP_DiscCount;\n',
     '/* Retro-Recomp modification (GPL-2.0, like this file): the EBOOT reader is not compiled; no disc comes from it. */\n'
     'int PBP_DiscCount = 0;\n'),
]


def adaptation_digest() -> str:
    """What the prepared tree depends on besides the pin: the file lists and the replacements."""
    value = hashlib.sha256(b'psx-beetle-adaptation\0' + str(FORMAT).encode() + b'\0' + BEETLE_REV.encode())
    for part in (SOURCES, FOLDERS, FILES, EXCLUDED, DEFINES, INCLUDES):
        value.update(b'\0' + '\n'.join(part).encode())
    for rel, old, new in REPLACEMENTS:
        value.update(b'\0' + rel.encode() + b'\0' + old.encode() + b'\0' + new.encode())
    return value.hexdigest()


def source(emit=print) -> Path:
    """The pinned Beetle PSX checkout under `.deps` (cloned when missing, refused when moved or edited)."""
    from .conversion_common import pinned_checkout
    from .core import run
    target = ROOT / '.deps' / 'beetle-psx'

    def git(*arguments, **options):
        return run(['git', '-C', target, *arguments], **options)

    def clone():
        emit('PlayStation: fetching Beetle PSX at its pinned revision.')
        run(['git', 'clone', '--no-hardlinks', '--filter=blob:none', '--no-checkout', BEETLE_REPOSITORY, target])
        git('checkout', '--detach', BEETLE_REV)

    def refuse(head):
        raise ValueError('Beetle PSX revision differs from the pinned one.')
    pinned_checkout(target, BEETLE_REV, git, present=target.exists(), clone=clone, moved=refuse,
                    dirty=lambda: ValueError('Beetle PSX sources changed; the converter prepares a copy.'))
    return target


def adapt(checkout: Path, target: Path) -> Path:
    """Copy what the game compiles to `target/beetle` and apply the replacements; returns that folder. Done once per adaptation
    digest (a `ready.json` beside it)."""
    ready = target / 'ready.json'
    digest = adaptation_digest()
    tree = target / 'beetle'
    try:
        if json.loads(ready.read_text(encoding='utf-8')).get('adaptation') == digest and tree.is_dir():
            return tree
    except (OSError, ValueError):
        pass
    if tree.exists():
        shutil.rmtree(tree)
    for folder in FOLDERS:
        shutil.copytree(checkout / folder, tree / folder)
    for rel in (*SOURCES, *FILES):
        destination = tree / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(checkout / rel, destination)
    for rel in EXCLUDED:
        (tree / rel).unlink(missing_ok=True)
    for rel, old, new in REPLACEMENTS:
        path = tree / rel
        text = path.read_text(encoding='utf-8')
        if text.count(old) != 1:
            raise ValueError(f'Beetle PSX {rel}: the pinned text was not found exactly once.')
        path.write_text(text.replace(old, new), encoding='utf-8', newline='\n')
    (tree / 'rr_sources.cmake').write_text(
        'set(RR_BEETLE_SOURCES\n' + ''.join(f'    "${{RR_BEETLE_TREE}}/{rel}"\n' for rel in SOURCES) + ')\n'
        'set(RR_BEETLE_DEFINES ' + ' '.join(DEFINES) + ')\n'
        'set(RR_BEETLE_INCLUDES\n' + ''.join(f'    "${{RR_BEETLE_TREE}}/{rel}"\n' for rel in INCLUDES) + ')\n',
        encoding='utf-8', newline='\n')
    ready.write_text(json.dumps({'revision': BEETLE_REV, 'adaptation': digest, 'replacements': len(REPLACEMENTS)}) + '\n',
                     encoding='utf-8')
    return tree
