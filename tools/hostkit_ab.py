"""A/B runs of the windowed host shell of a game (Mega Drive, SNES, Neo Geo, CPS-1, NES, X68000).

    python tools/hostkit_ab.py build PROJECT WORK [--plain] [--state-config FILE] [--kit nes]
    python tools/hostkit_ab.py build-x68 KEPT_BUILD WORK [--tree TREE]                     the X68000 (see below)
    python tools/hostkit_ab.py run EXE SCRIPT OUT [--timeout S]
    python tools/hostkit_ab.py compare OUT_A OUT_B
    python tools/hostkit_ab.py script FAMILY SCRIPT [--pad-pages row|skip]    the standard battery
    python tools/hostkit_ab.py pads SCENARIO SCRIPT                           a pad slot scenario (writes SCRIPT.probes)
    python tools/hostkit_ab.py check-pads OUT SCRIPT.probes FAMILY            which player each probe drove

PROJECT is the folder of a kept build (`--keep-build`) holding CMakeLists.txt. `build`
copies it, builds target `game` and prints the executable (`--kit nes` puts the host kit's NES
adapter in place of the NES host the project was converted with); with the harness
(tools/hostkit_ab/hooks.c) the host sources are compiled against a virtual clock, a modelled
audio device, a scripted keyboard, mouse and controllers, and a picture read back at every
frame. `run` plays a script (see hooks.c) in an empty folder with the dummy SDL drivers and
keeps the frame hashes, the audio and window log, the preferences file and the state files.
`compare` says whether two runs agree, byte for byte.

The X68000 is built from the repository, not from a project: `build-x68` takes the CMake folder of a kept
conversion (`.build/x68/win/<hash>/<hash>/native/build`) and compiles its host sources against the harness, from the
working tree (the kit) or from an unpacked archive of the release tag (`native` and `tools`: the former host).
`script x68 --x68 play|autofire|keyboard|mouse|states|ui` writes its scripts; `run --arg=--trace --arg=datas/trace.tsv`
makes the game write the per-frame trace of the machine (video, sound and RAM hashes, CPU registers), which is what proves
the machine saw the same inputs. The former host presents nothing for its first frame, so the script of the kit side is
written with `--shift 1`.

A host refactor is "unchanged" when the old and the new build of the SAME game give the same
runs. Both sides must be built the same way, from the same project, with the same
retro16_state_config.h (--state-config), so that quick states cross over.

Neo Geo: the clock of the board follows the wall clock, so two runs of one build already differ in saves,
states and audio. Fix it on both sides with --patch neogeo_reference.c "int rr_ng_test_clock_enabled;"
"int rr_ng_test_clock_enabled=1;" and --patch neogeo_reference.c "int64_t rr_ng_test_clock;"
"int64_t rr_ng_test_clock=1760000000;".
"""
import argparse
import filecmp
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The SDL calls of the host, renamed to the harness's versions in the host sources only.
SDL_CALLS = ('PollEvent', 'GetKeyboardState', 'GetMouseState', 'GetWindowFlags', 'GetPerformanceFrequency',
             'GetPerformanceCounter', 'GetTicks64', 'Delay', 'OpenAudioDevice', 'QueueAudio',
             'GetQueuedAudioSize', 'PauseAudioDevice', 'ClearQueuedAudio', 'CloseAudioDevice',
             'LockAudioDevice', 'UnlockAudioDevice', 'SetWindowTitle', 'SetWindowFullscreen', 'ShowCursor',
             'RenderPresent', 'GetTicks')
# The X68000 host also reads the captured mouse; its frontend answers the core through libretro callbacks.
X68_SDL_CALLS = (*SDL_CALLS, 'GetRelativeMouseState', 'SetRelativeMouseMode')
# The host sources of a project: the 16-bit shell before the kit, the kit, and the NES host before the kit.
HOST_SOURCE = re.compile(r'console16_host_ui\.c|hostkit/(?:shell|adapters)/rrhk_\w+\.c|\$\{RETRO_NATIVE_DIR\}/nes_host_ui\.c')
NES_OLD_HOST = '${RETRO_NATIVE_DIR}/nes_host_ui.c'


def rehome(work: Path, project: Path) -> None:
    """A NES project names its own folder in its CMake files: point them at the copy."""
    old = project.as_posix().encode()
    new = work.as_posix().encode()
    for path in work.rglob('*'):
        if path.is_file() and path.relative_to(work).parts[0] != 'build' and path.stat().st_size < 4_000_000:
            data = path.read_bytes()
            if old in data:
                path.write_bytes(data.replace(old, new))


def build(project: Path, work: Path, plain: bool, state_config: Path | None, refresh_kit: Path | bool = False,
          patches=(), legacy_host: Path | None = None, kit: str | None = None) -> Path:
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args, sdl_install
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(project, work, ignore=shutil.ignore_patterns('build', 'build.log', 'entry.lock'))
    nes = (work / 'cyc_host.c').is_file()
    if nes:
        rehome(work, project)
    if state_config:
        shutil.copyfile(state_config, work / 'retro16_state_config.h')
    if refresh_kit and (work / 'hostkit').is_dir():
        tree = ROOT if refresh_kit is True else refresh_kit   # a tree of the repository, e.g. `git archive main native`
        shutil.rmtree(work / 'hostkit')   # the kit as it stands in that tree, not as the kept project has it
        shutil.copytree(tree / 'native/hostkit', work / 'hostkit')
        for catalogue in (work / 'runtime_catalog.inc', work / 'native/runtime_catalog.inc'):   # the kit's strings
            if catalogue.is_file():
                shutil.copyfile(tree / 'native/runtime_catalog.inc', catalogue)
    for name, old, new in patches:   # a property of the game for the variant under test (six buttons, a gun)
        text = (work / name).read_text(encoding='utf-8')
        if old not in text:
            raise SystemExit(f'{name} has no {old!r}')
        (work / name).write_text(text.replace(old, new), encoding='utf-8')
    cmake_file = work / 'CMakeLists.txt'
    text = cmake_file.read_text(encoding='utf-8')
    if kit:   # the NES host of the kit instead of the one the project was converted with
        from retrorecomp import hostkit
        if kit != 'nes' or NES_OLD_HOST not in text:
            raise SystemExit('--kit nes needs a NES project converted with the host of before the kit')
        text = text.replace(NES_OLD_HOST, ' '.join(hostkit.stage(work, kit)))
    if legacy_host:   # the host as it was before the kit, over the same generated project
        shutil.rmtree(work / 'hostkit', ignore_errors=True)
        shutil.copyfile(legacy_host, work / 'console16_host_ui.c')
        text = re.sub(r'(?:hostkit/(?:shell|adapters)/rrhk_\w+\.c\s*)+', 'console16_host_ui.c ', text)
    if not plain:
        hosts = sorted(set(HOST_SOURCE.findall(text)))
        if not hosts:
            raise SystemExit('no host source in CMakeLists.txt')
        shutil.copyfile(ROOT / 'tools/hostkit_ab/hooks.c', work / 'rrab_hooks.c')
        calls = [f'SDL_{name}=rrab_{name}' for name in SDL_CALLS] + ['rr16_frame=rrab_frame']
        own = []
        if nes:
            calls = [c for c in calls if not c.startswith('rr16_')] + ['cyc_set_controller=rrab_set_controller',
                                                                      'rr_nes_zapper_aim=rrab_zapper_aim']
            own.append('RRAB_NES=1')
        if 'RR16_CPS1=1' in text:
            calls.append('rr_cps1_set_extra_pads=rrab_extra_pads'); own.append('RRAB_CPS1=1')
        if 'gun16.c' in text:
            calls.append('rr16_gun_input=rrab_gun_input'); own.append('RRAB_GUN=1')
        text += (f'\ntarget_sources(game PRIVATE rrab_hooks.c)\n'
                 f'set_source_files_properties({" ".join(hosts)} PROPERTIES COMPILE_DEFINITIONS "{";".join(calls)}")\n'
                 f'set_source_files_properties(rrab_hooks.c PROPERTIES COMPILE_DEFINITIONS "{";".join(own) or "RRAB_NONE=1"}")\n')
    cmake_file.write_text(text, encoding='utf-8')
    cmake, generator = toolchain()
    sdl = sdl_install()
    log = work / 'build.log'
    run([cmake, '-S', work, '-B', work / 'build', '-G', generator, *cmake_target_args(),
         f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'], log=log)
    run([cmake, '--build', work / 'build', '--config', 'Release', '--target', 'game', '--parallel', build_jobs()],
        log=log, timeout=3600)
    return build_executable(work / 'build', 'game')


def build_x68(tree: Path, kept: Path, work: Path) -> Path:
    """The X68000 export of a kept build (its CMake cache says where its payload, CPU and machine sources are), compiled from
    the host sources of `tree` against the harness. `tree` is the working tree for the host kit, or an unpacked `git archive`
    of the release tag (native and tools) for the former host: both sides are built the same way, from the same kept build."""
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args, sdl_install
    cache = {}
    for line in (kept / 'CMakeCache.txt').read_text(encoding='utf-8', errors='replace').splitlines():
        match = re.match(r'([A-Za-z0-9_]+):[A-Z]+=(.*)', line)
        if match:
            cache[match.group(1)] = match.group(2)
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    hooks = ROOT / 'tools/hostkit_ab/hooks.c'
    host = [tree / 'native/x68000_reference/reference_host.c', *sorted((tree / 'native/hostkit/shell').glob('rrhk_*.c'))]
    calls = ';'.join([f'SDL_{name}=rrab_{name}' for name in X68_SDL_CALLS] + ['retro_set_input_state=rrab_set_input_state'])
    text = ('cmake_minimum_required(VERSION 3.20)\nproject(RrabX68 LANGUAGES C CXX)\n'
            f'add_subdirectory("{(tree / "native/x68000_native").as_posix()}" native)\n'
            f'target_sources(x68000_reference_host PRIVATE "{hooks.as_posix()}")\n'
            f'set_source_files_properties("{hooks.as_posix()}" TARGET_DIRECTORY x68000_reference_host PROPERTIES COMPILE_DEFINITIONS "RRAB_X68=1")\n'
            f'set_source_files_properties({" ".join(chr(34) + p.as_posix() + chr(34) for p in host)} TARGET_DIRECTORY x68000_reference_host '
            f'PROPERTIES COMPILE_DEFINITIONS "{calls}")\n')
    (work / 'CMakeLists.txt').write_text(text, encoding='utf-8', newline='\n')
    cmake, generator = toolchain()
    defines = [f'-D{name}={cache[name]}' for name in ('RR_X68000_GENERATED', 'RR_X68000_PAYLOAD_DIR', 'RR_X68000_B74_TREE',
                                                      'RR_X68000_TOOL_STAMP', 'RR_B74_SOURCE', 'RR_GEOLITH_DIR', 'RR_RECOMP_VERSION')
               if name in cache]
    log = work / 'build.log'
    run([cmake, '-S', work, '-B', work / 'build', '-G', generator, *cmake_target_args(),
         f'-DCMAKE_PREFIX_PATH={sdl_install().as_posix()}', *defines], log=log)
    run([cmake, '--build', work / 'build', '--config', 'Release', '--target', 'x68000_reference_host', '--parallel', build_jobs()],
        log=log, timeout=3600)
    return build_executable(work / 'build' / 'native' / 'reference', 'RetroRecomp-X68000-Native')


def play(exe: Path, script: Path, out: Path, timeout: int, extra=(), seed: Path | None = None,
         seed_datas: Path | None = None, arguments=()) -> int:
    if out.exists():
        shutil.rmtree(out)
    box = out / 'box'
    box.mkdir(parents=True)
    shutil.copy2(exe, box / exe.name)
    if seed_datas:   # the whole datas folder (preferences included) another run left behind
        shutil.copytree(seed_datas, box / 'datas')
    if seed:   # quick states (datas/states) another run left behind
        shutil.copytree(seed, box / 'datas' / 'states', dirs_exist_ok=True)
    environment = {**os.environ, 'SDL_VIDEODRIVER': 'offscreen', 'SDL_RENDER_DRIVER': 'software',
                   'SDL_AUDIODRIVER': 'dummy', 'RRAB_SCRIPT': str(script), 'RRAB_OUT': str(out)}
    for name in ('RETRORECOMP_HOST_TEST_FRAMES', 'RETRORECOMP_HOST_TEST_FILTER', 'RETRORECOMP_TIMING_REPORT',
                 'RETRORECOMP_HOST_TEST_NO_AUDIO'):
        environment.pop(name, None)
    for pair in extra:   # NAME=VALUE; @OUT@ stands for the output folder
        name, value = pair.split('=', 1)
        environment[name] = value.replace('@OUT@', str(out))
    done = subprocess.run([str(box / exe.name), *arguments], cwd=box, env=environment, capture_output=True, timeout=timeout)
    (out / 'stderr.txt').write_bytes(done.stderr)
    (out / 'returncode.txt').write_text(str(done.returncode))
    return done.returncode


def collect(out: Path) -> dict:
    """Everything a run left behind, by name."""
    result = {}
    for name in ('frames.log', 'events.log', 'stderr.txt', 'returncode.txt', 'timing.json'):
        path = out / name
        result[name] = path.read_bytes() if path.is_file() else b''
    # Every family prints the same honesty line since the NES moved to the kit (decision D8).
    result['stderr.txt'] = result['stderr.txt'].replace(b'; physical latency unmeasured', b'')
    datas =out / 'box' / 'datas'
    if datas.is_dir():
        for path in sorted(datas.rglob('*')):
            if path.is_file():
                result['datas/' + path.relative_to(datas).as_posix()] = path.read_bytes()
    for path in sorted(out.glob('*.bmp')):
        result[path.name] = path.read_bytes()
    return result


def compare(a: Path, b: Path, ignore_events: tuple = (), ignore_files: tuple = ()) -> int:
    """`ignore_events` drops the lines of events.log (and frames.log when 'P') that start with one of the
    prefixes, `ignore_files` skips files: both are for differences a change documents on purpose."""
    first, second = collect(a), collect(b)
    for run in (first, second):
        for name in ('events.log', 'frames.log'):
            if ignore_events or ignore_files:
                run[name] = b''.join(line for line in run[name].splitlines(True)
                                     if not line.startswith(tuple(p.encode() + b' ' for p in ignore_events)))
        for name in [n for n in run if n in ignore_files]:
            del run[name]
    differing = []
    for name in sorted(set(first) | set(second)):
        if first.get(name) != second.get(name):
            differing.append(name)
    frames = first['frames.log'].count(b'\n')
    pushes = [line.split() for line in first['events.log'].splitlines() if line.startswith(b'A q ')]
    samples = sum(int(push[3]) for push in pushes) // 4          # stereo 16-bit frames
    states = [n for n in first if n.startswith('datas/states/')]
    others = second['frames.log'].count(b'\n')
    print(f'frames presented: {frames} (second run {others}); audio pushes: {len(pushes)}, {samples} stereo samples; '
          f'state files: {len(states)}; pictures saved: {sum(n.endswith(".bmp") for n in first)}; '
          f'files compared: {len(set(first) | set(second))}')
    for name in differing:
        print('DIFFERENT:', name)
    if not differing:
        print('IDENTICAL')
    return 1 if differing else 0


PLAYER1_KEYS = ('W', 'X', 'C', 'V', 'A', 'S', 'D', 'Q', 'E', 'Return', 'Left_Shift', 'Right_Shift', 'Up', 'Down', 'Left', 'Right')
PLAYER2_KEYS = ('Keypad_8', 'Keypad_9', 'Keypad_6', 'Keypad_4', 'Keypad_7', 'Keypad_0', 'Keypad_.', 'Keypad_Enter',
                'Keypad_/', 'Keypad_*', 'Keypad_+', 'Keypad_5', 'Keypad_2', 'Keypad_1', 'Keypad_3')
PAD_BUTTONS = ('a', 'b', 'x', 'y', 'back', 'start', 'leftshoulder', 'rightshoulder', 'leftstick', 'rightstick',
               'dpup', 'dpdown', 'dpleft', 'dpright')
LANGUAGES = 5


class Script:
    """Builds a script: `at(n)` moves the clock, `say` adds a command at the current iteration."""

    def __init__(self):
        self.lines, self.now = [], 0

    def at(self, iteration):
        self.now = max(self.now, iteration)
        return self

    def say(self, command, after=0):
        self.lines.append(f'{self.now} {command}')
        self.now += after
        return self

    def tap(self, key, after=2, shift=False):
        return self.say(f'press {key}' + (' shift' if shift else ''), after)

    def hold(self, key, frames):
        self.say(f'hold {key}', frames)
        return self.say(f'release {key}', 1)

    def jump(self, key, count, after=3):
        """`count` presses of a key in ONE iteration: F2 pages in between are never drawn."""
        for _ in range(count):
            self.say(f'press {key}')
        self.now += after
        return self

    def text(self):
        return '\n'.join(self.lines) + '\n'


def battery(family: str, players: int = 2, gun: bool = False, pages: int = 5, lead: int = 40, soak: int = 2400,
            options: bool = True, pad_pages: str = '') -> str:
    """One long script for the whole shell: input, menus in every language, preferences, states.

    `pages` is the number of F2 pages (2 per player, the machine's own page, the options).
    `pad_pages` is for the Gamepad row of the F2 gamepad pages (HOST_KIT.md divergence 10), which adds a row to those
    pages: '' is the script as it was; 'row' adds the one `Up` that keeps the combination rows reached by wrapping
    round the page (use it on the build with the row); 'skip' never draws a gamepad page (pages are crossed with several
    presses in one iteration and the controller bindings are left out), so that every picture of the run is comparable
    with a build that has no such row."""
    skip = pad_pages == 'skip'
    pad_index = {2 * n + 1 for n in range(players)}        # the F2 pages of the gamepads
    shown = [n for n in range(pages if options else pages - 1) if not (skip and n in pad_index)]
    s = Script()
    s.at(lead)
    # Controllers appear while the game runs (hot-plug), one per player.
    for p in range(players):
        s.say(f'attach {p}', 3)
    # 1. Every keyboard default of both players, one key at a time.
    for key in (*PLAYER1_KEYS, *PLAYER2_KEYS):
        s.hold(key, 3)
    # 2. Every button of the controllers, then the stick around its threshold.
    for p in range(players):
        for button in PAD_BUTTONS:
            s.say(f'button {p} {button} 1', 3).say(f'button {p} {button} 0', 2)
        for axis, value in (('leftx', -32000), ('leftx', -16001), ('leftx', -15999), ('leftx', 16000), ('leftx', 16001),
                            ('leftx', 32000), ('lefty', -16001), ('lefty', 15999), ('lefty', 16001), ('lefty', 32000)):
            s.say(f'axis {p} {axis} {value}', 3).say(f'axis {p} {axis} 0', 2)
    # 3. Opposite directions cancel; two buttons at once.
    s.say('hold Left', 0).say('hold Right', 0).say('hold Up', 0).say('hold Down', 0).say('hold W', 0).say('hold X', 3)
    for key in ('Left', 'Right', 'Up', 'Down', 'W', 'X'):
        s.say(f'release {key}', 0)
    s.at(s.now + 3)
    # 4. Autofire: off, on, held for 24 iterations, off again.
    s.hold('W', 12).tap('F6', 3).hold('W', 24).hold('Right_Shift', 6).tap('F6', 3).hold('W', 10)
    # 4b. A few thousand iterations of play: a key now and then, as a person would.
    keys = ('Return', 'W', 'Right', 'X', 'Left', 'C', 'Down', 'Up', 'S', 'Return')
    for n in range(soak // 40):
        s.hold(keys[n % len(keys)], 5).at(s.now + 34)
    # 5. Filters and display modes, with a few frames of each.
    for _ in range(4):
        s.tap('F3', 8)
    for _ in range(3):
        s.tap('F4', 6)
    s.tap('F4', 4).at(s.now + 130)       # long enough for the notice of the last key to expire
    # 6. State: save, play on, load, reset, save again.
    s.tap('F8', 12).hold('Right', 15).tap('F9', 12).tap('F1', 2, shift=True).at(s.now + 20).tap('F8', 12).at(s.now + 130)
    # 7. The menus in each language: help, every F2 page, back to the game.
    for language in range(LANGUAGES):
        s.tap('F1', 4).say(f'capture help-{language}.bmp', 2).tap('F1', 4)
        s.tap('F2', 4).say(f'capture f2-{language}-0.bmp', 2)
        swept = pages if options else pages - 1
        for before, page in zip(shown, shown[1:]):
            s.jump('Right', page - before) if skip else s.tap('Right', 3)
            s.say(f'capture f2-{language}-{page}.bmp', 2)
        if skip:
            s.jump('Left', swept - 1, 2)
        else:
            for _ in range(swept - 1):
                s.tap('Left', 2)
        s.tap('F2', 4)
        s.tap('F7', 5)        # next language; five turns come back to the first
    # 8. Bindings: rebind a key and a controller button of player 1 and player 2, quit/restart combinations.
    s.tap('F2', 3).tap('Down', 2).tap('Return', 3).tap('J', 3).say('capture bound-key.bmp', 2)
    s.tap('Down', 2).tap('Return', 3).tap('Escape', 3).tap('Up', 2)
    if skip:      # keyboard page only: back to the first row, then round to the combination rows
        for _ in range(2):
            s.tap('Up', 2)
    else:
        s.tap('Right', 3).tap('Return', 3).say('button 0 leftstick 1', 2).say('button 0 leftstick 0', 4)
        s.say('capture bound-pad.bmp', 2).tap('Down', 2).tap('Return', 3).say('button 0 rightstick 1', 2).say('button 0 rightstick 0', 4)
        for turn in range(3):      # the combination rows sit after the actions: go round from the top
            if pad_pages == 'row' and turn == 2:   # the Gamepad row is now the last one: a second up, in the same iteration
                s.say('press Up')
            s.tap('Up', 2)
    s.tap('Return', 3).say('hold K', 4).say('release K', 4)
    if skip:
        s.say('capture combo.bmp', 2).tap('Delete', 3).tap('Up', 2).tap('Return', 3).tap('Escape', 3)
        s.jump('Right', 2)      # player 2's keyboard page
    else:
        s.say('capture combo.bmp', 2).tap('Delete', 3).tap('Left', 3).tap('Up', 2).tap('Return', 3).tap('Escape', 3)
        s.tap('Right', 3).tap('Right', 3)      # player 2's pages
    if pad_pages == 'row':      # player 2's gamepad page (the old script got there): its Gamepad row is one more to step over
        s.say('press Down')
    s.tap('Down', 2).tap('Return', 3).tap('L', 3).tap('Escape', 3).tap('F2', 3)
    # 9. The machine's own page and the options.
    if gun or family == 'cps1':
        s.tap('F2', 3)
        if skip:
            s.jump('Right', pages - 2)
        else:
            for _ in range(pages - 2):
                s.tap('Right', 3)
        s.say('capture machine-page.bmp', 2)
        for _ in range(4):
            s.tap('Down', 2).tap('Return', 3)
        s.tap('-', 3).tap('Return', 3).tap('Up', 2).tap('Return', 3).tap('-', 3)
        s.say('capture machine-page-2.bmp', 2)
        if options:
            s.tap('Right', 3)
    elif options:
        s.tap('F2', 3)
        if skip:
            s.jump('Right', pages - 1)
        else:
            for _ in range(pages - 1):
                s.tap('Right', 3)
    if options:
        s.say('capture options.bmp', 2)
        for _ in range(3):
            s.tap('Down', 2).tap('Return', 3)       # an option row runs its function key or changes the filter
        s.jump('Left', 1 if gun or family == 'cps1' else 2) if skip else s.tap('Left', 3)
    s.tap('F2', 4)      # closes the page the sweep ended on; another Escape would quit the game
    # 10. Pointer: aim, fire, secondary, aux, leave the window; then the pointer page of F2.
    if gun:
        shots = ((300, 200, 0), (300, 200, 1), (450, 250, 2), (450, 250, 4), (600, 300, 1), (10, 10, 0), (2000, 2000, 1))
        for n, (x, y, mask) in enumerate(shots):
            s.say(f'mouse {x} {y} {mask}', 4).say(f'capture pointer-{n}.bmp', 3)
        s.say('mouse 300 200 0', 3).tap('F2', 3)
        if skip:
            s.jump('Right', 2 * players)
        else:
            for _ in range(2 * players):
                s.tap('Right', 3)
        s.say('capture pointer-page.bmp', 2)
        for _ in range(4):
            s.tap('Down', 2).tap('Return', 3)       # shape, size, colour, turbo
        s.say('capture pointer-page-2.bmp', 2).tap('F2', 4)
        s.say('mouse 400 300 1', 4).say('capture pointer-new.bmp', 3).say('mouse 400 300 0', 3)
        s.tap('F4', 4).say('mouse 400 300 1', 4).say('capture pointer-display.bmp', 3).say('mouse 400 300 0', 3).tap('F4', 4).tap('F4', 4)
    # 10a. NES: sprite flicker reduction on and off.
    if family == 'nes':
        s.tap('F5', 6).say('capture sprites.bmp', 2).tap('F5', 6)
    # 10b. Neo Geo: enhanced mode on and off; the AES/MVS switch restarts the game, so it comes last.
    if family == 'ng':
        s.tap('F5', 6).say('capture enhanced.bmp', 2).tap('F5', 6).tap('F11', 6).say('capture aes.bmp', 2)
    # 11. Close like a user: the window's close button.
    s.at(s.now + 20).say('capture end.bmp', 2).say('quit')
    return s.text()


def x68_script(kind: str) -> str:
    """Scripts for the Sharp X68000 (HOST_KIT.md phase 3). The player is a libretro frontend whose F2 pages, notices and
    audio priming differ from the former host on purpose, so the scripts are split by what they prove:

    play       the machine's input and the pictures: keys, controllers, sticks (beyond the dead zone of both hosts),
               filters and display modes with the pictures taken after the notices are gone. The traces of the two
               hosts must agree to the bit.
    autofire   F6 and Ctrl+Alt+F, a held button, the bound key and the second player's pad (decision D4: the common rule).
    keyboard   the guest keyboard (Ctrl+Alt+K): keys, function keys and Escape reach the guest, the host keys do not.
    mouse      a click captures the mouse, Ctrl+Alt+M releases it, motion and buttons are handed on.
    states     F9 with no state, F8, F9: the machine resumes what followed the save (read the trace).
    ui         help and its second page, every F2 page and the options in the five languages, pause, rebinding, clearing,
               the Pause binding, quit combinations, Ctrl+Alt chords: the pictures are read by eye."""
    s = Script()
    s.at(40)
    if kind == 'play':
        for p in range(2):
            s.say(f'attach {p}', 3)
        for key in ('Up', 'Down', 'Left', 'Right', 'W', 'X', 'Return', 'Z', 'C'):
            s.hold(key, 4)
        for p in range(2):
            for button in ('a', 'b', 'dpup', 'dpdown', 'dpleft', 'dpright', 'start', 'x', 'y', 'back', 'leftshoulder', 'leftstick'):
                s.say(f'button {p} {button} 1', 3).say(f'button {p} {button} 0', 2)
            for axis, value in (('leftx', -32000), ('leftx', -16001), ('leftx', 16001), ('leftx', 32000),
                                ('lefty', -32000), ('lefty', -16001), ('lefty', 16001), ('lefty', 32000)):
                s.say(f'axis {p} {axis} {value}', 3).say(f'axis {p} {axis} 0', 2)
        s.say('hold W', 0).say('hold X', 3).say('release W', 0).say('release X', 3)
        keys = ('Return', 'W', 'Right', 'X', 'Left', 'Down', 'Up', 'Return')
        for n in range(40):
            s.hold(keys[n % len(keys)], 5).at(s.now + 20)
        for shot in range(4):                    # sharp, xBR, Scale2x, scanlines
            s.tap('F3', 8).at(s.now + 230).say(f'capture filter-{shot}.bmp', 2)
        for shot in range(3):                    # pixel, fit, window
            s.tap('F4', 8).at(s.now + 230).say(f'capture display-{shot}.bmp', 2)
        s.tap('F4', 8).at(s.now + 230).say('capture display-3.bmp', 2)
    elif kind == 'autofire':
        s.say('attach 0', 3).say('attach 1', 3)
        s.hold('W', 12).tap('F6', 3).hold('W', 24).hold('X', 24).hold('Return', 24)
        s.say('button 0 a 1', 0).say('button 1 a 1', 20).say('button 0 a 0', 0).say('button 1 a 0', 4)
        s.say('hold W', 0).say('button 0 a 1', 10).say('release W', 0).say('button 0 a 0', 4)
        s.tap('F6', 3).hold('W', 12)
        s.say('press F ctrlalt', 3).hold('W', 24).say('press F ctrlalt', 3).hold('W', 12)
    elif kind == 'states':
        # F8 at 100, F9 at 200, with no input: the machine after the load runs again what followed the save. F9 with no state first.
        s.at(60).tap('F9', 4).at(100).tap('F8', 4).at(200).tap('F9', 4).at(300)
    elif kind == 'keyboard':
        s.say('press K ctrlalt', 4)
        for key in ('W', 'X', 'Return', 'Escape', 'F2', 'F5', 'F8', 'F9', 'F10', 'A', 'Space', 'Tab', 'Left_Shift'):
            s.hold(key, 4)
        s.tap('F8', 4).tap('F9', 4)
        s.say('press K ctrlalt', 4)
        for key in ('W', 'X', 'F8', 'F9'):
            s.hold(key, 4)
    elif kind == 'mouse':
        s.say('attach 0', 3).say('mouse 300 200 0', 4).say('click', 4).say('mouse 330 190 0', 4).say('mouse 340 180 1', 4)
        s.say('mouse 340 180 0', 4).say('mouse 300 200 2', 4).say('mouse 300 200 0', 4)
        s.say('press M ctrlalt', 6).say('mouse 400 300 1', 4).say('mouse 400 300 0', 4).say('press M ctrlalt', 6)
        s.say('mouse 410 310 1', 4).say('mouse 410 310 0', 4)
    elif kind == 'ui':
        for language in range(LANGUAGES):
            s.tap('F1', 4).say(f'capture ui-help-{language}.bmp', 2).tap('Tab', 4).say(f'capture ui-help2-{language}.bmp', 2).tap('Tab', 3).tap('F1', 4)
            s.tap('F2', 4).say(f'capture ui-f2-{language}-0.bmp', 2)
            for page in range(1, 5):
                s.tap('Right', 3).say(f'capture ui-f2-{language}-{page}.bmp', 2)
            for _ in range(4):
                s.tap('Left', 2)
            s.tap('F2', 4)
            s.tap('F11', 4).say(f'capture ui-pause-{language}.bmp', 2).tap('F11', 4)
            s.tap('F7', 5)
        # rebinding: a key and a button of player 1, then Delete clears them; the Pause binding
        s.tap('F2', 3).tap('Down', 2).tap('Down', 2).tap('Down', 2).tap('Down', 2).tap('Down', 2).tap('Down', 2).tap('Down', 2)   # the Pause row
        s.tap('Return', 3).tap('P', 3).say('capture ui-bound-key.bmp', 2)
        s.tap('Right', 3).tap('Return', 3).say('attach 0', 3).say('button 0 leftstick 1', 2).say('button 0 leftstick 0', 4)
        s.say('capture ui-bound-pad.bmp', 2).tap('Delete', 3).say('capture ui-cleared.bmp', 2).tap('Left', 3).tap('F2', 4)
        s.tap('P', 4).say('capture ui-pause-key.bmp', 2).tap('P', 4)
        s.say('press H ctrlalt', 4).say('capture ui-chord-help.bmp', 2).say('press H ctrlalt', 4)
        s.say('press O ctrlalt', 4).say('capture ui-chord-options.bmp', 2).tap('F2', 4)
        s.say('press Return ctrlalt', 6).say('press Return ctrlalt', 6)
    else:
        raise SystemExit(f'unknown X68000 script {kind}')
    s.at(s.now + 20).say('capture end.bmp', 2).say('quit')
    return s.text()


PAD_A = '4369 4369 Pad One'          # attachx: vendor 0x1111, product 0x1111, name
PAD_B = '8738 8738 Pad Two'          # vendor 0x2222
PAD_TWIN = '13107 13107 Twin Pad'    # two pads with this identity share a GUID and a name


def pad_scenario(name: str) -> tuple[str, list]:
    """Scripts for the pad slot policy (HOST_KIT.md divergence 10): which player a virtual controller drives, how
    the Gamepad row of the F2 gamepad pages changes it, hot-plug, and the capture on a player without a pad.

    Returns the script and its probes: (iteration, expected) where a probe presses button A of a virtual
    controller (and, for 'kb+pad', the first player's W key) and `expected` is the set of players
    whose pad word must show it. `check_pads` reads them back from events.log."""
    s, probes, shots = Script(), [], []

    def probe(slot, expect, key=False):
        probes.append((s.now, sorted(expect)))
        if key:
            s.say('hold W', 0)
        s.say(f'button {slot} a 1', 2)
        s.say(f'button {slot} a 0', 0)
        if key:
            s.say('release W', 0)
        s.at(s.now + 3)

    def row(page_presses, *steps):
        """F2, `page_presses` times Right (page 1 is player 1's gamepad, 3 player 2's), Up to the Gamepad row, then steps."""
        s.tap('F2', 3)
        for _ in range(page_presses):
            s.tap('Right', 3)
        s.tap('Up', 3)
        for step in steps:
            if step == 'capture':
                shots.append(1)
                s.say(f'capture {name}-{len(shots)}.bmp', 2)
            else:
                s.tap(step, 3)
        s.tap('F2', 4)

    s.at(40)
    if name == 'one':          # one pad: Automatic gives it to player 1; player 1 on None gives it to player 2
        s.say(f'attachx 0 {PAD_A}', 4)
        probe(0, [0])
        row(1, 'capture', 'Return', 'capture', 'Return', 'capture')
        probe(0, [1])                     # player 1 None: the pad drives player 2
        probe(0, [0, 1], key=True)        # ... and the keyboard still drives player 1
        row(1, 'Return', 'capture')       # None -> Automatic
        probe(0, [0])
        row(1, 'Delete')
    elif name == 'two':        # two different pads: pinning the second to player 1 swaps them
        s.say(f'attachx 0 {PAD_A}', 4).say(f'attachx 1 {PAD_B}', 4)
        probe(0, [0]); probe(1, [1])
        row(1, 'capture', 'Return', 'Return', 'capture')        # Automatic -> Pad One -> Pad Two (taken from player 2)
        probe(1, [0]); probe(0, [1])
        row(3, 'capture')
        row(1, 'Delete'); probe(0, [0]); probe(1, [1])           # back to Automatic: the pads are dealt again in plug order
    elif name == 'twin':       # two identical pads: numbered; pinning the second one to player 1 swaps them
        s.say(f'attachx 0 {PAD_TWIN}', 4).say(f'attachx 1 {PAD_TWIN}', 4)
        probe(0, [0]); probe(1, [1])
        row(1, 'capture', 'Return', 'Return', 'capture')
        probe(1, [0]); probe(0, [1])
    elif name == 'twin-unplug':  # both players pinned to identical pads: unplugging one never moves the other
        s.say(f'attachx 0 {PAD_TWIN}', 4).say(f'attachx 1 {PAD_TWIN}', 4)
        row(3, 'Return', 'Return')                               # player 2: Automatic -> Twin #1 -> Twin #2
        row(1, 'Return', 'capture')                              # player 1: Automatic -> Twin #1
        probe(0, [0]); probe(1, [1])
        s.say('detach 0', 4)
        probe(1, [1])                                            # player 2 keeps its pad; player 1 has none
        row(1, 'capture')                                        # "Twin Pad (disconnected)"
        s.say(f'attachx 0 {PAD_TWIN}', 4)
        probe(0, [0]); probe(1, [1])                             # plugged in again: back to player 1
    elif name == 'next-missing':  # Enter on a pinned pad that is missing goes on with the connected pads, then None
        s.say(f'attachx 0 {PAD_A}', 4).say(f'attachx 1 {PAD_B}', 4)
        row(3, 'Return', 'Return')                               # player 2: Automatic -> Pad One -> Pad Two
        s.say('detach 1', 4)
        row(3, 'Return', 'capture')                              # missing Pad Two -> Pad One (taken from player 1)
        probe(0, [1])
        row(3, 'Return', 'capture')                              # Pad One is the last pad -> None
        probe(0, [0])                                            # player 1, automatic, gets Pad One back
    elif name == 'replug':     # player 2 pinned to a pad that is unplugged and plugged again; no fallback meanwhile
        s.say(f'attachx 0 {PAD_A}', 4).say(f'attachx 1 {PAD_B}', 4)
        probe(0, [0]); probe(1, [1])
        row(3, 'Return', 'Return', 'capture')                    # player 2: Automatic -> Pad One -> Pad Two
        probe(1, [1]); probe(0, [0])
        s.say('detach 1', 4)
        probe(0, [0])
        row(1, 'Return', 'Return', 'capture')                    # player 1: Automatic -> Pad One -> None
        probe(0, [])                                             # player 2's pad is missing: Pad One goes to nobody
        row(3, 'capture')                                        # "Pad Two (disconnected)"
        s.say(f'attachx 1 {PAD_B}', 4)
        probe(1, [1])                                            # plugged in again: back to player 2
        row(3, 'capture')
    elif name == 'persist':    # a second run on the preferences of 'replug': the pads plug in the other order
        s.say(f'attachx 1 {PAD_B}', 4).say(f'attachx 0 {PAD_A}', 4)
        probe(1, [1]); probe(0, [])
        row(1, 'capture'); row(3, 'capture')
    elif name == 'capture':    # the F2 binding of a player without a pad says so
        s.tap('F2', 3).tap('Right', 3).tap('Return', 3).say(f'capture {name}-p1.bmp', 2).tap('Escape', 3)
        s.say(f'capture {name}-p1-after.bmp', 2)
        s.tap('Right', 3).tap('Right', 3).tap('Return', 3).say(f'capture {name}-p2.bmp', 2).tap('Escape', 3).tap('F2', 4)
        s.say(f'attachx 0 {PAD_A}', 4)
        s.tap('F2', 3).tap('Right', 3).tap('Right', 3).tap('Right', 3).tap('Return', 3).say(f'capture {name}-p2-with-pad1.bmp', 2)
        s.tap('Escape', 3).tap('Left', 3).tap('Left', 3).tap('Return', 3).say(f'capture {name}-p1-with-pad.bmp', 2)
        s.say('button 0 leftstick 1', 2).say('button 0 leftstick 0', 4).say(f'capture {name}-p1-bound.bmp', 2).tap('F2', 4)
    else:
        raise SystemExit(f'unknown scenario {name}')
    s.at(s.now + 20).say(f'capture {name}-end.bmp', 2).say('quit')
    return s.text(), probes


def check_pads(out: Path, probes: list, family: str) -> int:
    """Each probe must show up in the pad words of exactly the expected players (and nowhere else)."""
    words = {}
    for line in (out / 'events.log').read_text(encoding='ascii').splitlines():
        part = line.split()
        if part and part[0] == 'G':
            iteration = int(part[1])
            if family == 'x68':       # one line per answer to the core: G iteration port device id value (device 1: the joypad)
                if int(part[3]) == 1 and int(part[2]) < 2:
                    words.setdefault(iteration, [0, 0])[int(part[2])] |= 1
            elif family == 'nes':     # one line per port: G iteration port byte
                words.setdefault(iteration, [0, 0])[int(part[2])] = int(part[3], 16)
            else:                     # G iteration p1 p2
                words[iteration] = [int(part[2], 16), int(part[3], 16)]
    failures = 0
    for iteration, expected in probes:
        seen = [0, 0]
        for n in (iteration, iteration + 1):
            for player, word in enumerate(words.get(n, [0, 0])):
                seen[player] |= word
        got = [player for player in (0, 1) if seen[player]]
        verdict = 'ok' if got == expected else 'WRONG'
        failures += got != expected
        print(f'iteration {iteration:4d}: expected players {expected}, saw {got} (words {seen[0]:04x} {seen[1]:04x}) {verdict}')
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('build'); p.add_argument('project', type=Path); p.add_argument('work', type=Path)
    p.add_argument('--plain', action='store_true', help='no harness: the executable as the game ships it (unpacked)')
    p.add_argument('--state-config', type=Path)
    p.add_argument('--patch', nargs=3, action='append', default=[], metavar=('FILE', 'OLD', 'NEW'),
                   help='replace text in a project file before building, e.g. retro_gun_game.h "RR16_GUN 0" "RR16_GUN 3"')
    p.add_argument('--legacy-host', type=Path, help='build the old console16_host_ui.c over this project instead of the kit')
    p.add_argument('--refresh-kit', nargs='?', const=True, default=False, type=Path, metavar='TREE',
                   help="copy native/hostkit (and the runtime catalogue) of this tree, or of TREE, over the kit of the project")
    p.add_argument('--kit', choices=('nes',), help="build the host kit's adapter of this machine over a project converted before the kit")
    p = sub.add_parser('build-x68', help='the X68000 export of a kept build, host sources of TREE, against the harness')
    p.add_argument('kept', type=Path, help='the kept build folder holding CMakeCache.txt (.build/x68/win/<hash>/<hash>/native/build)')
    p.add_argument('work', type=Path); p.add_argument('--tree', type=Path, default=ROOT, help='working tree, or an unpacked archive of the release tag (native and tools)')
    p = sub.add_parser('run'); p.add_argument('exe', type=Path); p.add_argument('script', type=Path)
    p.add_argument('out', type=Path); p.add_argument('--timeout', type=int, default=900)
    p.add_argument('--arg', action='append', default=[], help='command-line argument of the game (e.g. --trace datas/trace.tsv)')
    p.add_argument('--seed-states', type=Path, help='a datas/states folder (of another run) to start from')
    p.add_argument('--seed-datas', type=Path, help='a whole datas folder (of another run, preferences included) to start from')
    p.add_argument('--env', action='append', default=[], metavar='NAME=VALUE', help='extra environment; @OUT@ is the output folder')
    p = sub.add_parser('pads', help='write the script of a pad slot scenario (one, two, twin, replug, persist, capture); probes go to OUT.probes')
    p.add_argument('scenario'); p.add_argument('out', type=Path)
    p = sub.add_parser('check-pads', help='check the probes of a pad scenario against the events.log of a run')
    p.add_argument('out', type=Path, help='the run folder'); p.add_argument('probes', type=Path); p.add_argument('family', choices=('md', 'snes', 'ng', 'cps1', 'nes', 'x68'))
    p = sub.add_parser('compare'); p.add_argument('a', type=Path); p.add_argument('b', type=Path)
    p.add_argument('--ignore-events', nargs='*', default=[], metavar='TAG', help='events.log line tags to leave out, e.g. C (cursor)')
    p.add_argument('--ignore-files', nargs='*', default=[], metavar='NAME', help='files to leave out, e.g. f2-0-4.bmp')
    p = sub.add_parser('script', help='write the standard battery of the shell for one machine')
    p.add_argument('family', choices=('md', 'snes', 'ng', 'cps1', 'nes', 'x68')); p.add_argument('out', type=Path)
    p.add_argument('--x68', choices=('play', 'autofire', 'keyboard', 'mouse', 'ui', 'states'), default='play', help='the X68000 script to write')
    p.add_argument('--shift', type=int, default=0, help='X68000: add this to every iteration (the former host presents nothing for its first frame, the kit does)')
    p.add_argument('--players', type=int, default=2); p.add_argument('--gun', action='store_true')
    p.add_argument('--no-options-page', action='store_true', help='leave the options page of F2 alone (for hosts built before the Linux fix of game_options.h)')
    p.add_argument('--soak', type=int, default=2400, help='iterations of play between the sweeps and the menus')
    p.add_argument('--pad-pages', choices=('row', 'skip'), default='',
                   help="the Gamepad row of the F2 gamepad pages: 'row' for the build that has it, 'skip' to never draw those pages")
    p.add_argument('--pages', type=int, default=0, help='F2 pages (default: 2 per player, the machine page, the options)')
    args = parser.parse_args()
    if args.command == 'script' and args.family == 'x68':
        text = x68_script(args.x68)
        if args.shift:
            text = ''.join(f'{int(line.split(" ", 1)[0]) + args.shift} {line.split(" ", 1)[1]}' for line in text.splitlines(True))
        args.out.write_text(text, encoding='ascii')
        return 0
    if args.command == 'script':
        pages = args.pages or 2 * args.players + (1 if args.gun or args.family == 'cps1' else 0) + 1
        args.out.write_text(battery(args.family, args.players, args.gun, pages, soak=args.soak, options=not args.no_options_page, pad_pages=args.pad_pages), encoding='ascii')
        return 0
    if args.command == 'pads':
        text, probes = pad_scenario(args.scenario)
        args.out.write_text(text, encoding='ascii')
        lines = [' '.join(map(str, [i, *e])) for i, e in probes]
        args.out.with_name(args.out.name + '.probes').write_text('\n'.join(lines) + '\n', encoding='ascii')
        return 0
    if args.command == 'check-pads':
        probes = [(int(line.split()[0]), [int(n) for n in line.split()[1:]]) for line in args.probes.read_text(encoding='ascii').splitlines() if line.strip()]
        return check_pads(args.out.resolve(), probes, args.family)
    if args.command == 'build-x68':
        print(build_x68(args.tree.resolve(), args.kept.resolve(), args.work.resolve()))
        return 0
    if args.command == 'build':
        print(build(args.project.resolve(), args.work.resolve(), args.plain, args.state_config,
                     args.refresh_kit if args.refresh_kit is True or not args.refresh_kit else args.refresh_kit.resolve(), args.patch, args.legacy_host, args.kit))
        return 0
    if args.command == 'run':
        code = play(args.exe.resolve(), args.script.resolve(), args.out.resolve(), args.timeout, args.env, args.seed_states, args.seed_datas, args.arg)
        print('exit', code)
        return 0 if code == 0 else 1
    return compare(args.a.resolve(), args.b.resolve(), tuple(args.ignore_events), tuple(args.ignore_files))


if __name__ == '__main__':
    raise SystemExit(main())
