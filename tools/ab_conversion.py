"""A/B proof of a converter refactor: one real conversion with two trees, compared byte for byte.

    python tools/ab_conversion.py ROM --a REF_OR_DIR [--b REF_OR_DIR] [--work DIR] [--keep-work]
                                  [--backend functions|banked]
                                  [--ng-bios ARCHIVE] [--x68-ipl FILE --x68-cgrom FILE]

A is the tree before the change (a git ref such as `v1.6.2`, checked out as a detached worktree, or an existing
folder), B the tree after it (default: `HEAD`, also checked out detached, so that B is what was committed).
Each side converts the same ROM with the batch command (`--jobs 1 --no-shared-base --no-online-cover --keep-build`,
the default scan level unless `--scan-level` is given), into its own output folder, with its own EMPTY learning library
(`RETRO_RECOMP_LIBRARY_DIR`) and its own `Export/datas` (a fresh tree has none): nothing the player has learned, no
cover, no shared base, so the two runs start from the same state. The pinned engines (`.deps`) and the portable compiler
(`Export/datas/tools`) are shared read-only through links to the main checkout, never copied or written. The tool never
writes into the main checkout's `Export`.

It compares, between A and B:
  * every file of each kept build folder (`.build/<game>`; for Neo Geo `.build/ng-*`, for CPS-1 `.build/cps1/<set>-*`,
    for the X68000 `.build/x68/<toolchain>/<stamp>`) that is a source or a data file: SHA-256 of the bytes, with
    the tree and output paths replaced by placeholders in text files (CMake files name their folder) - this covers
    every `generated/` folder and every adapted host source;
  * `conversion-report.json` without its volatile keys (creation time, timings, wall times, stamps, version) and with
    the paths replaced;
  * the evidence under `checks/` and the other probe folders: frame images, traces, hashes, audio and state files by
    their bytes, and the JSON results without their volatile keys.
It leaves out what differs by construction: compiled objects and executables, logs and the build tree.
Keep `--work` SHORT (a few characters under the drive root, not a deep folder): a Game Boy export writes its battery file
through a temporary name that must stay under the 260 characters of a Windows path, and a failed save changes what the later probes of
the same conversion play.
Exit 0 only when everything is identical (and both conversions succeeded and kept the same set of files).

The kept build folders hold a copy of the ROM: they are deleted at the end unless `--keep-work`. The ROM is read in
place and never copied elsewhere by this tool. SDL runs with its dummy drivers: no window, no sound.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0

# Directories of a kept build that are build products or tool caches, and files that differ by construction.
SKIP_DIRECTORIES = {'build', 'CMakeFiles', '.git', '__pycache__'}
SKIP_SUFFIXES = {'.exe', '.o', '.obj', '.a', '.lib', '.dll', '.pdb', '.ilk', '.exp', '.log', '.lock', '.tmp', '.pyc'}
TEXT_SUFFIXES = {'.c', '.h', '.inc', '.cpp', '.cmake', '.txt', '.toml', '.rc', '.md', '.json', '.csv', '.tsv', '.inputs',
                 '.hash', '.patterns', '.manifest', '.trace', '.ini', '.cfg', ''}
VOLATILE_KEY = re.compile(r'(created|elapsed|seconds|wall|stamp|timing|_utc|duration|_ms$|started|finished)', re.I)
VOLATILE_TOP = {'version', 'tool', 'converter_version'}
EXECUTABLE_SECTIONS = {'packed', 'packing', 'export_receipt'}
# The receipt's game stamp hashes the converter's code, and its request is derived from it: they differ when the code does.
STAMP_DERIVED = {'game', 'request'}
# Digests of things built inside the tree (the NES emitter binary, its log with its path): they differ between two trees
# by construction, as a run of one tree against itself shows. The generated sources they produced are compared.
BUILT_IN_TREE = {'generation.json': {'compiler', 'log'},
                 # The X68000: the digest of the machine module built into a reference bundle, and the SDK stamp of the
                 # discovery build (derived from the converter's code, like the game stamp).
                 'reference-build.json': {'module_sha256'}, 'ready.json': {'sdk'},
                 # The digests of the executables a Neo Geo build compared (reference, native, packed or unpacked).
                 'native-validation.json': {'reference_sha256', 'native_sha256', 'packed_sha256', 'unpacked_sha256'}}
# A quick state (.rrstate) holds the key of the code that wrote it at bytes 96 to 160 of its header (64 hex digits,
# derived from the converter's code like the game stamp): masked, so that the rest of the state is compared.
STATE_KEY = slice(96, 160)
# An X68000 quick state (magic RRX68KS1) holds a checksum at bytes 160 to 167. It covers the key of the code that wrote the
# state, so it follows the key and is masked with it. The rest of the state (19 MB of RAM, video and devices) is compared as
# it is: since 1.6.3 two states of one game and moment are byte-identical (the FM chip's storage is zeroed when it is
# allocated), where a converter of 1.6.2 or before carried heap garbage in a window of the OPM section and differs from
# itself there.
X68_STATE_MAGIC = b'RRX68KS1'
X68_STATE_CHECKSUM = slice(160, 168)
# A state key derived from the game stamp (so from the converter's code), written into a header.
STAMP_TEXT = re.compile(rb'(STATE_ABI ")[0-9a-f]{64}(")')
REPORT = 'conversion-report.json'
# What the X68000 names after the converter's code or at random: the folder of a workspace is the start of the SDK stamp
# (`.build/x68/<toolchain>/<stamp12>`), and every run makes its evidence folder with `tempfile.mkdtemp` (`qa-xxxxxxxx`,
# `reference-xxxxxxxx`). Replaced by placeholders in names and texts, so that the two trees line up.
X68_STAMP_FOLDER = re.compile(rb'(x68[/\\]+(?:win|linux)(?:-llvm)?[/\\]+)[0-9a-f]{12}')
RANDOM_FOLDER = re.compile(rb'\b(qa|reference)-[a-z0-9_]{8}\b')


def run(command, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run([str(part) for part in command], creationflags=NO_WINDOW, **kwargs)


def git(*args, cwd=REPO) -> str:
    return run(['git', *args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
               encoding='utf-8', errors='replace', check=True).stdout.strip()


def main_checkout() -> Path:
    """The checkout that owns `.deps` and `Export/datas/tools` (the common git dir's parent)."""
    common = Path(git('rev-parse', '--path-format=absolute', '--git-common-dir'))
    return common.parent


def link(source: Path, target: Path) -> None:
    """A read-only view of `source` at `target` (a junction on Windows, a symbolic link elsewhere)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        return
    if os.name == 'nt':
        run(['cmd', '/c', 'mklink', '/J', target, source], stdout=subprocess.DEVNULL, check=True)
    else:
        target.symlink_to(source, target_is_directory=True)


def unlink(target: Path) -> None:
    """Remove a link made by `link` without touching what it points at."""
    try:
        if target.is_symlink() or (os.name == 'nt' and os.path.isjunction(target)):
            os.rmdir(target) if os.name == 'nt' else target.unlink()
    except OSError:
        pass


def prepare_tree(spec: str, label: str, work: Path, deps: Path, tools: Path | None) -> tuple[Path, bool]:
    """(tree, created): a folder to convert with. A git ref becomes a detached worktree under `work`."""
    given = Path(spec)
    if given.is_dir():
        tree, created = given.resolve(), False
    else:
        tree, created = work / label, True
        git('worktree', 'add', '--detach', tree, spec)
    link(deps, tree / '.deps')
    if tools is not None:
        link(tools, tree / 'Export/datas/tools')
    return tree, created


def release_tree(tree: Path, created: bool, keep: bool = False) -> None:
    for path in (tree / '.deps', tree / 'Export/datas/tools'):
        unlink(path)
    if created and not keep:
        run(['git', 'worktree', 'remove', '--force', tree], cwd=REPO, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        shutil.rmtree(tree, ignore_errors=True)


def convert(tree: Path, rom: Path, side: Path, extra: list[str]) -> tuple[int, Path]:
    """One batch conversion with the dummy SDL drivers and an empty library. Returns (exit code, output folder)."""
    output, library = side / 'output', side / 'library'
    for folder in (output, library):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
    env = os.environ.copy()
    env.update(SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', PYINSTALLER_SUPPRESS_SPLASH_SCREEN='1',
               RETRO_RECOMP_LIBRARY_DIR=str(library), RETRO_RECOMP_KEEP_BUILD='1', PYTHONDONTWRITEBYTECODE='1')
    env.pop('SMSRECOMP_LIBRARY_DIR', None)
    command = [sys.executable, '-B', 'RetroRecomp.py', 'batch', rom, '--output', output, '--jobs', '1',
               '--no-shared-base', '--no-online-cover', '--keep-build', *extra]
    with (side / 'conversion.log').open('wb') as log:
        done = run(command, cwd=tree, env=env, stdout=log, stderr=subprocess.STDOUT)
    return done.returncode, output


def kept_builds(tree: Path) -> list[Path]:
    """The game folders the conversion kept under `.build` (they hold the ROM copy, or data made from it).

    A folder with `rom.*` (Sega, Game Boy, NES), a 16-bit project (`md-*`, `snes-*`), a Neo Geo project (`ng-*`, with
    its cartridge and BIOS copies), a CPS-1 project (`cps1/<set>-<sha>`) and an X68000 workspace
    (`x68/<toolchain>/<stamp12>`)."""
    root = tree / '.build'
    if not root.is_dir():
        return []
    found = [path for path in root.iterdir()
             if path.is_dir() and (any(path.glob('rom.*')) or path.name.startswith(('ng-', 'md-', 'snes-')))]
    if (root / 'cps1').is_dir():
        found += [path for path in (root / 'cps1').iterdir() if path.is_dir()]
    if (root / 'x68').is_dir():
        # One workspace per toolchain and SDK stamp: the discovery build, the machine tree and the game's folder.
        found += [stamp for toolchain in (root / 'x68').iterdir() if toolchain.is_dir()
                  for stamp in toolchain.iterdir() if stamp.is_dir()]
    return sorted(found)


def variants(path: Path) -> list[str]:
    text = str(path)
    forms = {text, text.replace('\\', '/'), text.replace('/', '\\'), text.replace('\\', '\\\\')}
    forms |= {form.lower() for form in forms}
    return sorted(forms, key=len, reverse=True)


class Normaliser:
    def __init__(self, replacements: dict[Path, str], drop: frozenset = frozenset()):
        self.drop = drop
        self.pairs = [(form, token) for path, token in replacements.items() for form in variants(path)]
        self.pairs.sort(key=lambda pair: len(pair[0]), reverse=True)

    def text(self, value: str) -> str:
        for form, token in self.pairs:
            value = value.replace(form, token)
        return self.names(value.encode('utf-8')).decode('utf-8')

    def data(self, value: bytes) -> bytes:
        for form, token in self.pairs:
            value = value.replace(form.encode('utf-8'), token.encode('utf-8'))
        return self.names(value)

    @staticmethod
    def names(value: bytes) -> bytes:
        """The X68000's stamp folder and random evidence folders replaced by placeholders (a no-op elsewhere)."""
        return RANDOM_FOLDER.sub(rb'\1-<X>', X68_STAMP_FOLDER.sub(rb'\1<stamp>', value))

    def json(self, value, top=True, context=()):
        if isinstance(value, dict):
            # The executable embeds the folder it was built in: its hash and size differ between two trees by
            # construction. What it does is compared by the probes and the generated sources.
            binary = bool(set(context) & EXECUTABLE_SECTIONS)
            return {key: self.json(item, False, (*context, key)) for key, item in value.items()
                    if not VOLATILE_KEY.search(key) and not (top and key in VOLATILE_TOP)
                    and not (binary and key in ('sha256', 'bytes'))
                    and not (context[-1:] == ('export_receipt',) and key in STAMP_DERIVED)
                    and not key.endswith('executable_sha256') and not key.endswith('candidate_sha256')
                    and key not in self.drop}
        if isinstance(value, list):
            return [self.json(item, False, context) for item in value]
        if isinstance(value, str):
            return self.text(value)
        return value


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fingerprint(path: Path, normaliser: Normaliser) -> str:
    data = path.read_bytes()
    if path.suffix.lower() == '.json':
        try:
            local = Normaliser({}, frozenset(BUILT_IN_TREE.get(path.name, ())))
            local.pairs = normaliser.pairs
            return digest(json.dumps(local.json(json.loads(data.decode('utf-8'))), sort_keys=True,
                                     ensure_ascii=False).encode('utf-8'))
        except ValueError:
            pass
    if path.suffix.lower() == '.rrstate' and data.startswith(X68_STATE_MAGIC):
        data = bytearray(data)
        data[X68_STATE_CHECKSUM] = bytes(len(data[X68_STATE_CHECKSUM]))
        data = bytes(data)
    if path.suffix.lower() == '.rrstate' and len(data) >= STATE_KEY.stop:
        data = data[:STATE_KEY.start] + b'\0' * (STATE_KEY.stop - STATE_KEY.start) + data[STATE_KEY.stop:]
    if path.suffix.lower() in TEXT_SUFFIXES and b'\0' not in data[:4096]:
        data = STAMP_TEXT.sub(rb'<stamp>', normaliser.data(data))
    return digest(data)


def project_files(project: Path, normaliser: Normaliser) -> dict[str, str]:
    result = {}
    for path in sorted(project.rglob('*')):
        relative = path.relative_to(project)
        if (not path.is_file() or any(part in SKIP_DIRECTORIES or part.startswith('build-') for part in relative.parts[:-1])
                or path.suffix.lower() in SKIP_SUFFIXES or path.name == 'entry.lock'):
            continue
        result[relative.as_posix()] = fingerprint(path, normaliser)
    return result


def gather(tree: Path, side: Path, output: Path) -> dict:
    """Everything a side is compared by: per kept project, the files by SHA-256, and the report."""
    normaliser = Normaliser({tree: '<TREE>', side: '<SIDE>', output: '<OUT>', REPO: '<TREE>'})
    projects = {}
    for project in kept_builds(tree):
        # The folder name carries the game and revision, not the tree: it is the same on both sides.
        name = normaliser.names(project.relative_to(tree / '.build').as_posix().encode('utf-8')).decode('utf-8')
        files = project_files(project, normaliser)
        projects[name] = {normaliser.names(key.encode('utf-8')).decode('utf-8'): value for key, value in files.items()}
    reports = {}
    for path in sorted(output.rglob(REPORT)):
        reports[path.relative_to(output).as_posix()] = normaliser.json(json.loads(path.read_text(encoding='utf-8')))
    return {'projects': projects, 'reports': reports}


def flatten(value, prefix=''):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from flatten(item, f'{prefix}.{key}' if prefix else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from flatten(item, f'{prefix}[{index}]')
    else:
        yield prefix, value


def compare(a: dict, b: dict) -> list[str]:
    problems = []
    if sorted(a['projects']) != sorted(b['projects']):
        problems.append(f"kept build folders differ: A {sorted(a['projects'])} / B {sorted(b['projects'])}")
    for name in sorted(set(a['projects']) & set(b['projects'])):
        left, right = a['projects'][name], b['projects'][name]
        only_a, only_b = sorted(set(left) - set(right)), sorted(set(right) - set(left))
        changed = sorted(key for key in set(left) & set(right) if left[key] != right[key])
        problems += [f'{name}: only in A: {key}' for key in only_a]
        problems += [f'{name}: only in B: {key}' for key in only_b]
        problems += [f'{name}: differs: {key}' for key in changed]
    if sorted(a['reports']) != sorted(b['reports']):
        problems.append(f"report files differ: A {sorted(a['reports'])} / B {sorted(b['reports'])}")
    for name in sorted(set(a['reports']) & set(b['reports'])):
        left, right = dict(flatten(a['reports'][name])), dict(flatten(b['reports'][name]))
        for key in sorted(set(left) | set(right)):
            if left.get(key, '<absent>') != right.get(key, '<absent>'):
                problems.append(f"{name}: {key}: A {left.get(key, '<absent>')!r} / B {right.get(key, '<absent>')!r}")
    return problems


def summary(data: dict) -> str:
    files = sum(len(project) for project in data['projects'].values())
    return f"{len(data['projects'])} kept build folder(s), {files} compared files, {len(data['reports'])} report(s)"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('rom', type=Path, help='the ROM, read in place')
    parser.add_argument('--a', required=True, help='tree before the change: a git ref or an existing folder')
    parser.add_argument('--b', default='HEAD', help='tree after the change: a git ref or an existing folder')
    parser.add_argument('--work', type=Path, help='working folder (default: a new temporary one)')
    parser.add_argument('--deps', type=Path, help='the pinned engines to share (default: .deps of the main checkout)')
    parser.add_argument('--tools', type=Path,
                        help='the portable compiler folder to share (default: Export/datas/tools of the main checkout)')
    parser.add_argument('--scan-level', choices=('quick', 'standard', 'extended', 'thorough'),
                        help='default: the converter default')
    parser.add_argument('--backend', choices=('functions', 'banked'),
                        help='the Master System / Game Gear engine, passed to the batch (default: the converter default)')
    parser.add_argument('--ng-bios', type=Path, help='the Neo Geo BIOS archive (read in place), for a Neo Geo game')
    parser.add_argument('--x68-ipl', type=Path, help='the X68000 IPL ROM (read in place), for an X68000 game')
    parser.add_argument('--x68-cgrom', type=Path, help='the X68000 font ROM (read in place), for an X68000 game')
    parser.add_argument('--keep-work', action='store_true',
                        help='keep the working folder and the checked-out trees (they hold copies of the ROM in the '
                             'kept builds; remove a tree with `git worktree remove --force`)')
    options = parser.parse_args(argv)
    rom = options.rom.resolve()
    if not rom.is_file():
        parser.error(f'No such ROM: {rom}')
    main_tree = main_checkout()
    deps = (options.deps or main_tree / '.deps').resolve()
    tools = options.tools or main_tree / 'Export/datas/tools'
    tools = tools.resolve() if tools.is_dir() else None
    work = (options.work or Path(tempfile.mkdtemp(prefix='ab-conversion-'))).resolve()
    work.mkdir(parents=True, exist_ok=True)
    extra = ['--scan-level', options.scan_level] if options.scan_level else []
    if options.backend:
        extra += ['--backend', options.backend]
    if options.ng_bios:
        extra += ['--ng-bios', options.ng_bios.resolve()]
    if options.x68_ipl and options.x68_cgrom:
        extra += ['--x68-ipl', options.x68_ipl.resolve(), '--x68-cgrom', options.x68_cgrom.resolve()]
    elif options.x68_ipl or options.x68_cgrom:
        parser.error('--x68-ipl and --x68-cgrom go together')
    results, trees, failed = {}, [], False
    try:
        for label, spec in (('a', options.a), ('b', options.b)):
            tree, created = prepare_tree(spec, label, work, deps, tools)
            trees.append((tree, created))
            side = work / f'run-{label}'
            side.mkdir(parents=True, exist_ok=True)
            print(f'{label.upper()}: converting with {tree} ...', flush=True)
            code, output = convert(tree, rom, side, extra)
            results[label] = gather(tree, side, output)
            print(f'{label.upper()}: exit {code}; {summary(results[label])}', flush=True)
            failed |= code != 0 or not results[label]['projects'] or not results[label]['reports']
        problems = compare(results['a'], results['b'])
        for problem in problems:
            print('DIFFERENT ' + problem)
        if failed:
            print(f"FAILED: a conversion did not succeed; see {work / 'run-a/conversion.log'} and "
                  f"{work / 'run-b/conversion.log'}")
            options.keep_work = True
        print('IDENTICAL' if not problems and not failed else f'{len(problems)} difference(s)')
        return 0 if not problems and not failed else 1
    finally:
        for tree, created in trees:
            release_tree(tree, created, options.keep_work)
        if options.keep_work:
            print(f'Working folder kept: {work}')
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(main())
