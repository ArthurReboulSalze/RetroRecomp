"""The upstream repositories Retro-Recomp pins, declared per machine (docs/UPSTREAMS.md).

This module is data and a small reader; it imports nothing of the converter. Every machine of
`retrorecomp.systems.ALL_PROFILES` has an entry in `MACHINE_UPSTREAMS` (an empty tuple needs a reason in
`NO_UPSTREAM`), and the shared ones (SDL, the toolchain, the independent CPU vectors) are in `COMMON`.
An upstream used by several machines is defined once and listed under each of them, so `all_upstreams()`
returns it once, with all its consoles.

The pins themselves are NOT copied here: a `Pin` says where the code holds the revision (a module constant,
a dictionary entry, a key of a JSON fixture, or a submodule of another upstream) and `read_pin` reads it from
that place without importing anything (`ast`). `tools/check_upstreams.py` and `tests/test_upstreams.py` iterate
over this registry, so a new machine brings its rows by declaring its upstreams here.

This module is an interface module of `stamp_inputs`: no stamp hashes it, so declaring an upstream moves no
game, host or build stamp.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Pin:
    """Where the code fixes one revision.

    kind 'python'    -- a module constant holding a string: `file`, `name`;
    kind 'dict'      -- `name` is a dictionary of tuples: `key`, then the tuple `index`;
    kind 'json'      -- a key `name` of a JSON object in `file`;
    kind 'submodule' -- a submodule `path` of the parent upstream (the commit its pinned tree records).
    """
    kind: str
    file: str = ''
    name: str = ''
    key: str = ''
    index: int = 0
    path: str = ''

    @property
    def where(self) -> str:
        if self.kind == 'submodule':
            return f'submodule {self.path}'
        stem = self.file[:-3] if self.file.endswith('.py') else self.file
        if stem.startswith('retrorecomp/'):
            stem = stem[len('retrorecomp/'):]
        if self.kind == 'python':
            return f'{stem}.{self.name}'
        if self.kind == 'dict':
            return f"{stem}.{self.name}['{self.key}']"
        return f'{stem} ("{self.name}")'


@dataclass(frozen=True)
class Upstream:
    key: str                 # short name, unique
    repo: str                # GitHub owner/name
    branch: str              # default branch compared with the pin
    role: str                # engine, reference CPU, library, tool, test vectors...
    licence: str
    compiled: str            # what we actually compile or use from it
    pin: Pin
    also: tuple = ()         # other places that must hold the same revision
    checkout: str = ''       # folder of the pinned checkout under .deps (for submodule lookups)
    tag: str = ''            # version pins only: how a release tag is spelled ('v{}' or '{}')
    watch: tuple = ()        # files that matter when the whole repository is too large to follow
    parent: object = None    # a submodule: the Upstream whose tree records it
    shared_by: tuple = ()    # COMMON entries: the machines that use it ('*' for all)

    @property
    def is_version(self) -> bool:
        return bool(self.tag)

    @property
    def url(self) -> str:
        return f'https://github.com/{self.repo}'


def _py(file: str, name: str) -> Pin:
    return Pin('python', file, name)


# --- engines and runtimes, per machine ---------------------------------------------------------------------------
SMSGGRECOMP = Upstream(
    'smsggrecomp', 'mstan/smsggrecomp', 'main', 'Z80 recompiler and runner for the Master System and Game Gear',
    'no licence declared; noncommercial permission reported by the owner (THIRD_PARTY_NOTICES.md)',
    'recompiler (rebuilt with our patches) and runner glue; the engine is downloaded on first conversion',
    _py('retrorecomp/core.py', 'ENGINE_REV'), checkout='smsggrecomp')
Z80_RECOMP_CORE = Upstream(
    'z80-recomp-core', 'mstan/z80-recomp-core', 'main', 'Z80 decoder and runtime headers (submodule)',
    'PolyForm Noncommercial 1.0.0', 'shared Z80 runtime headers and sources of the SMS/GG and Mega Drive engines',
    Pin('submodule', path='external/z80-recomp-core'), parent=SMSGGRECOMP)
GB_RECOMPILED = Upstream(
    'gb-recompiled', 'arcanite24/gb-recompiled', 'main', 'Game Boy recompiler and generated runtime', 'MIT',
    'compiler and runtime sources', _py('retrorecomp/gameboy.py', 'ENGINE_REV'), checkout='gb-recompiled')
NESRECOMP = Upstream(
    'nesrecomp', 'mstan/nesrecomp', 'master', 'NES recompiler and cycle runtime', 'PolyForm Noncommercial 1.0.0',
    'compiler and the cycle runtime under runner/cyc (with its vendored emu2413)',
    _py('retrorecomp/nes.py', 'ENGINE_REV'), checkout='nesrecomp')
SEGAGENESISRECOMP = Upstream(
    'segagenesisrecomp', 'mstan/segagenesisrecomp', 'master',
    'Mega Drive recompiler and runner; source of the 68000 instruction bodies of four machines',
    'PolyForm Noncommercial 1.0.0 plus retained vendor licences',
    'the recompiler, runner/ and m68k_interp.c (adapted by m68000.adapt_semantics for Mega Drive, Neo Geo, CPS-1, '
    'X68000); runner/cd is not used',
    Pin('dict', 'retrorecomp/console16.py', 'REPOSITORIES', 'md', 1), checkout='segagenesisrecomp')
M68K_RECOMP_CORE = Upstream(
    'm68k-recomp-core', 'mstan/m68k-recomp-core', 'main', '68000 decoder (submodule of segagenesisrecomp)',
    'PolyForm Noncommercial 1.0.0', 'common/m68k_decoder.h, read by the Mega Drive, Neo Geo, CPS-1 and X68000 generators',
    Pin('submodule', path='external/m68k-recomp-core'), parent=SEGAGENESISRECOMP)
RBENGINE = Upstream(
    'rbengine', 'RetroPortingToolKit/rbengine', 'main', 'rollback engine (submodule of segagenesisrecomp)', 'MIT',
    'nothing: initialised with the checkout, but only upstream\'s own tests link it',
    Pin('submodule', path='external/rbengine'), parent=SEGAGENESISRECOMP)
SNESRECOMP = Upstream(
    'snesrecomp', 'RetroPortingToolKit/snesrecomp', 'main', 'Super Nintendo interpreter and runner',
    'PolyForm Noncommercial 1.0.0 plus MIT/ISC and other retained vendor licences',
    'the 65816 interpreter, SPC700/DSP core and runner/ (runtime and adapters); the analyser is not used',
    Pin('dict', 'retrorecomp/console16.py', 'REPOSITORIES', 'snes', 1), checkout='snesrecomp')
GEOLITH = Upstream(
    'geolith-libretro', 'libretro/geolith-libretro', 'master',
    'Neo Geo hardware runtime; its Musashi 68000 is the reference CPU of Neo Geo, CPS-1 and X68000', 'BSD-3-Clause',
    'the Neo Geo machine, video and audio sources and src/m68k (Musashi)',
    _py('retrorecomp/neogeo_build.py', 'GEOLITH_REV'), checkout='geolith-libretro')
LITHOGEN = Upstream(
    'lithogen', 'carmiker/lithogen', 'master', 'Neo Geo cartridge layout and decryption knowledge', 'BSD-3-Clause',
    'the loader behind our ROM-free layout catalogue',
    _py('retrorecomp/neogeo_build.py', 'LITHOGEN_REV'), also=(_py('retrorecomp/neogeo_catalogue.py', 'LOADER'),),
    checkout='lithogen')
YMFM = Upstream(
    'ymfm', 'aaronsgiles/ymfm', 'main', 'YM2151 (OPM) emulation for CPS-1', 'BSD-3-Clause',
    'ymfm.h, ymfm_fm.h, ymfm_fm.ipp, ymfm_opm.h, ymfm_opm.cpp',
    _py('retrorecomp/cps1_build.py', 'YMFM_REVISION'), checkout='ymfm')
MAME = Upstream(
    'mame', 'mamedev/mame', 'master', 'CPS-1 board catalogue and OKI MSM6295, adapted from the driver', 'BSD-3-Clause',
    'no code is built from the checkout; the ROM-free CPS-1 catalogue and the OKI model are adapted from it',
    _py('retrorecomp/cps1_catalogue.py', 'MAME_REVISION'), also=(_py('tools/build_cps1_catalogue.py', 'MAME_REVISION'),),
    watch=('src/mame/capcom/cps1.cpp', 'src/mame/capcom/cps1_v.cpp', 'src/mame/capcom/cps1.h',
           'src/devices/sound/okim6295.cpp'))
PX68K_LIBRETRO = Upstream(
    'px68k-libretro', 'libretro/px68k-libretro', 'master',
    'X68000 libretro port; private comparison mode only (GPL)', 'GPL-2.0',
    'nothing is compiled or shipped; fixes are rewritten from their description (native/x68000_machine/provenance.json)',
    _py('tools/x68000_reference.py', 'PX68K_REV'),
    also=(Pin('json', 'native/x68000_machine/provenance.json', 'upstream.pinned_checkout'),))
PX68K_HISSORII = Upstream(
    'px68k', 'hissorii/px68k', 'master', 'X68000 machine base (devices, FMGEN OPM), inactive since 2014',
    'Kenjo noncommercial terms (WinX68k lineage), BSD-2-Clause (NONAKA), FMGEN freeware terms',
    'the device sources of x68k/, fmgen/ and the x11 line composition, adapted by tools/x68000_base74.py',
    _py('tools/x68000_reference.py', 'HISSORII_REV'), also=(_py('tools/x68000_base74.py', 'COMMIT'),),
    checkout='px68k-hissorii')

# --- shared ------------------------------------------------------------------------------------------------------
SDL = Upstream(
    'SDL', 'libsdl-org/SDL', 'release-2.32.x', 'SDL2 window, audio and input library linked into every export', 'zlib',
    'the SDL2 library built from source and linked into the games (release 2.32.8)',
    _py('retrorecomp/core.py', 'SDL_REV'), checkout='SDL', shared_by=('*',))
LLVM_MINGW = Upstream(
    'llvm-mingw', 'mstorsjo/llvm-mingw', 'master', 'portable Windows C toolchain downloaded by the converter',
    'Apache-2.0 with LLVM exceptions; MinGW-w64 and winpthreads permissive licences',
    'the release archive (clang, libc++, MinGW-w64 runtime), checked by SHA-256',
    _py('retrorecomp/toolchain.py', 'LLVM_MINGW_VERSION'), tag='{}', shared_by=('*',))
CMAKE = Upstream(
    'CMake', 'Kitware/CMake', 'master', 'build generator downloaded with the portable toolchain', 'BSD-3-Clause',
    'the Windows release archive, checked by SHA-256',
    _py('retrorecomp/toolchain.py', 'CMAKE_VERSION'), tag='v{}', shared_by=('*',))
NINJA = Upstream(
    'Ninja', 'ninja-build/ninja', 'master', 'build tool downloaded with the portable toolchain', 'Apache-2.0',
    'the Windows release archive, checked by SHA-256',
    _py('retrorecomp/toolchain.py', 'NINJA_VERSION'), tag='v{}', shared_by=('*',))
UPX = Upstream(
    'UPX', 'upx/upx', 'devel', 'executable packer for the finished games', 'GPL with special exception for packed executables',
    'the official 5.3.0 binaries (Windows and Linux) and the corresponding source archive in licenses/',
    _py('retrorecomp/packing.py', 'UPX_VERSION'), tag='v{}', shared_by=('*',))
SST_Z80 = Upstream(
    'SingleStepTests/z80', 'SingleStepTests/z80', 'main', 'independent Z80 test vectors (development tests only)', 'MIT',
    'fetched on demand by tools/fetch_z80_vectors.py into .deps; not shipped',
    _py('tools/fetch_z80_vectors.py', 'REVISION'), shared_by=('sms', 'gg', 'md'))
SST_M68000 = Upstream(
    'SingleStepTests/m68000', 'SingleStepTests/m68000', 'main', 'independent 68000 test vectors (development tests only)',
    'MIT', 'a small extract stored in tests/fixtures (md-prefetch, md-exceptions); not shipped',
    Pin('json', 'tests/fixtures/md-prefetch/cases.json', 'revision'),
    also=(Pin('json', 'tests/fixtures/md-exceptions/cases.json', 'revision'),), shared_by=('md',))

COMMON: tuple[Upstream, ...] = (SDL, LLVM_MINGW, CMAKE, NINJA, UPX, SST_Z80, SST_M68000)

# --- the machines ------------------------------------------------------------------------------------------------
# A new machine adds its key here, in the same change as its profile (tests/test_upstreams.py fails otherwise),
# and a row to each table of docs/UPSTREAMS.md.
MACHINE_UPSTREAMS: dict[str, tuple[Upstream, ...]] = {
    'sms': (SMSGGRECOMP, Z80_RECOMP_CORE),
    'gg': (SMSGGRECOMP, Z80_RECOMP_CORE),
    'gb': (GB_RECOMPILED,),
    'nes': (NESRECOMP,),
    'md': (SEGAGENESISRECOMP, M68K_RECOMP_CORE, Z80_RECOMP_CORE, RBENGINE),
    'snes': (SNESRECOMP,),
    'ng': (GEOLITH, LITHOGEN, SEGAGENESISRECOMP, M68K_RECOMP_CORE),
    'cps1': (SEGAGENESISRECOMP, M68K_RECOMP_CORE, GEOLITH, YMFM, MAME),
    'x68': (PX68K_HISSORII, PX68K_LIBRETRO, SEGAGENESISRECOMP, M68K_RECOMP_CORE, GEOLITH),
}
# A machine with no upstream of its own says why (an empty tuple above is refused without a reason here).
NO_UPSTREAM: dict[str, str] = {}


def all_upstreams() -> list[Upstream]:
    """Every upstream once, in declaration order (machines first, then the shared ones)."""
    seen: dict[str, Upstream] = {}
    for items in MACHINE_UPSTREAMS.values():
        for item in items:
            seen.setdefault(item.key, item)
    for item in COMMON:
        seen.setdefault(item.key, item)
    return list(seen.values())


def consoles_of(upstream: Upstream) -> tuple[str, ...]:
    """The machine ids that use this upstream, in registry order ('*' entries mean all of them)."""
    if '*' in upstream.shared_by:
        return tuple(MACHINE_UPSTREAMS)
    ids = [machine for machine, items in MACHINE_UPSTREAMS.items() if upstream in items]
    ids += [machine for machine in upstream.shared_by if machine not in ids]
    return tuple(ids)


# --- reading a pin -----------------------------------------------------------------------------------------------
def _constant(tree: ast.AST, name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                return None
    return None


def read_pin(pin: Pin, root: Path = ROOT) -> str | None:
    """The revision or version the code holds, or None when it cannot be read. Submodules are not handled here."""
    try:
        path = root / pin.file
        if pin.kind == 'python':
            value = _constant(ast.parse(path.read_text(encoding='utf-8')), pin.name)
        elif pin.kind == 'dict':
            value = _constant(ast.parse(path.read_text(encoding='utf-8')), pin.name)[pin.key][pin.index]
        elif pin.kind == 'json':
            value = json.loads(path.read_text(encoding='utf-8'))
            for part in pin.name.split('.'):
                value = value[part]
        else:
            return None
    except (OSError, ValueError, KeyError, IndexError, TypeError, SyntaxError):
        return None
    return value if isinstance(value, str) and value else None


def pin_of(upstream: Upstream, root: Path = ROOT, *, allow_git: bool = True) -> str | None:
    """The upstream's pin; a submodule is read from the pinned checkout under .deps when it is there."""
    if upstream.pin.kind != 'submodule':
        return read_pin(upstream.pin, root)
    parent = upstream.parent
    revision = read_pin(parent.pin, root) if parent is not None else None
    checkout = root / '.deps' / parent.checkout if parent is not None else None
    if not (allow_git and revision and checkout and (checkout / '.git').exists()):
        return None
    try:
        done = subprocess.run(['git', '-C', str(checkout), 'ls-tree', revision, upstream.pin.path],
                              capture_output=True, text=True, timeout=30, check=True,
                              creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
    except (OSError, subprocess.SubprocessError):
        return None
    fields = done.stdout.split()
    return fields[2] if len(fields) >= 3 and fields[0] == '160000' else None


def release_tag(upstream: Upstream, version: str) -> str:
    return upstream.tag.format(version)
