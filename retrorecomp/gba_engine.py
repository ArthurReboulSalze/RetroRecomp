"""The pinned Game Boy Advance engine: a verified checkout and the staged, patched copy one conversion builds.

The checkout (`.deps/gbarecomp`) is `mstan/gbarecomp` at `gba_conversion.ENGINE_REV` with the three submodules its tree
records; it is never edited. A conversion copies what the build needs into its own project folder (`stage`) and applies our
patches there (`gba_patches.PATCHES`, anchored text replacements: a pinned engine whose text moved is refused, not patched
blindly). The copy is written file by file with `write_if_changed`, so an unchanged file keeps its timestamp and a second
pass recompiles nothing.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Callable, Iterable

from .conversion_common import replace_counted, write_if_changed
from .core import ConversionError, run, serialized_setup
from .gba_conversion import ARM_CORE_REV, ENGINE_REV, ENGINE_URL, NET_REV, RBENGINE_REV
from .paths import ROOT

# The submodules the engine's tree records, and the revision each must be at.
SUBMODULES = (('external/arm-recomp-core', ARM_CORE_REV), ('external/recomp-net', NET_REV),
              ('external/rbengine', RBENGINE_REV))
# What a build never reads: the checkout's own history, the engine's documents, packaging for other platforms and
# the oracle tooling (it links an emulator we do not use).
SKIPPED_FOLDERS = frozenset({'.git', 'docs', 'packaging', 'platform', 'oracle', 'tcc'})
SKIPPED_SUFFIXES = frozenset({'.log', '.png', '.bmp', '.mp4', '.pdf'})
# Text of the engine is copied with LF line ends whatever the checkout's (a Windows checkout may hold CRLF): the patches are
# written in LF, and the same engine gives the same staged bytes on every platform.
TEXT_SUFFIXES = frozenset({'.c', '.cc', '.cpp', '.h', '.hpp', '.inc', '.cmake', '.txt', '.in', '.toml', '.md', '.py', '.json'})


def checkout_path() -> Path:
    return ROOT / '.deps' / 'gbarecomp'


@serialized_setup
def checkout(emit: Callable[[str], None]) -> Path:
    """The engine checkout at its pinned revision, cloned on first use. An edited checkout is refused."""
    engine = checkout_path()

    def git(*arguments, timeout=900):
        return run(['git', '-C', engine, *arguments], timeout=timeout)
    if not engine.exists():
        emit('Downloading the pinned Game Boy Advance engine (PolyForm Noncommercial)…')
        run(['git', 'clone', '--no-checkout', ENGINE_URL, engine], timeout=1800)
    populated = (engine / 'CMakeLists.txt').is_file()
    if populated and git('status', '--porcelain', '--untracked-files=no').strip():
        raise ConversionError('The cached Game Boy Advance engine has local changes; refusing to use or replace them.')
    if git('rev-parse', 'HEAD').strip() != ENGINE_REV or not populated:
        emit('Checking out the pinned Game Boy Advance engine revision…')
        git('fetch', '--depth', '1', 'origin', ENGINE_REV)
        git('checkout', '--detach', ENGINE_REV)
    if git('rev-parse', 'HEAD').strip() != ENGINE_REV:
        raise ConversionError('Unexpected Game Boy Advance engine revision.')
    for path, revision in SUBMODULES:
        recorded = git('ls-tree', 'HEAD', path).split()
        if len(recorded) < 3 or recorded[0] != '160000' or recorded[2] != revision:
            raise ConversionError(f'The engine records another revision of {path} than the one pinned here.')
        if not (engine / path / 'CMakeLists.txt').is_file():
            git('submodule', 'update', '--init', '--depth', '1', path)
        if run(['git', '-C', engine / path, 'rev-parse', 'HEAD'], timeout=60).strip() != revision:
            raise ConversionError(f'The {path} submodule is not at its pinned revision.')
    return engine


def patch_digest(patches: Iterable[tuple]) -> str:
    """Names the patch set: part of the recompiler's and the game's build identity."""
    return hashlib.sha256(json.dumps([list(patch) for patch in patches], sort_keys=True).encode('utf-8')).hexdigest()


def patched_text(file: str, text: str, edits: Iterable[tuple]) -> tuple[str, list[str]]:
    """`text` of `file` with each `(old, new, note)` applied: each `old` must occur exactly once."""
    notes = []
    for old, new, note in edits:
        text = replace_counted(text, old, new, count=1, error=lambda anchor: ConversionError(
            f'The pinned Game Boy Advance engine moved: {file} no longer holds {anchor[:70]!r} exactly once.'))
        notes.append(note)
    return text, notes


def _by_file(patches: Iterable[tuple]) -> dict:
    by_file = defaultdict(list)
    for file, old, new, note in patches:
        by_file[file].append((old, new, note))
    return by_file


def apply_patches(root: Path, patches: Iterable[tuple]) -> list[str]:
    """Apply `(file, old, new, note)` to the copy under `root`. Returns the notes."""
    notes = []
    for file, edits in _by_file(patches).items():
        try:
            text = (root / file).read_text(encoding='utf-8', newline='')
        except OSError as exc:
            raise ConversionError(f'The pinned Game Boy Advance engine has no {file} any more.') from exc
        text, applied = patched_text(file, text, edits)
        write_if_changed(root / file, text.encode('utf-8'))
        notes += applied
    return notes


def stage(project: Path, engine: Path, patches: Iterable[tuple]) -> tuple[Path, list[str]]:
    """The copy of the engine a conversion builds, patched. Returns (its folder, the notes of the patches applied).

    A patched file is written once, already patched, so a second call leaves every file as it was."""
    target = project / 'engine'
    edits = _by_file(patches)
    notes = []
    for path in sorted(engine.rglob('*')):
        relative = path.relative_to(engine)
        if not path.is_file() or SKIPPED_FOLDERS & set(relative.parts) or path.suffix in SKIPPED_SUFFIXES:
            continue
        if path.name == '.git':                      # the pointer file of a submodule
            continue
        data = path.read_bytes()
        if path.suffix in TEXT_SUFFIXES:
            data = data.replace(b'\r\n', b'\n')
        if relative.as_posix() in edits:
            text, applied = patched_text(relative.as_posix(), data.decode('utf-8'), edits[relative.as_posix()])
            data, notes = text.encode('utf-8'), notes + applied
        write_if_changed(target / relative, data)
    missing = sorted(set(edits) - {name for name in edits if (engine / name).is_file()})
    if missing:
        raise ConversionError(f'The pinned Game Boy Advance engine has no {missing[0]} any more.')
    return target, notes
