"""A/B runs of the windowed host shell of a 16-bit game (Mega Drive, SNES, Neo Geo, CPS-1).

    python tools/hostkit_ab.py build PROJECT WORK [--plain] [--state-config FILE] [--sdl-defs]
    python tools/hostkit_ab.py run EXE SCRIPT OUT [--timeout S]
    python tools/hostkit_ab.py compare OUT_A OUT_B

PROJECT is the folder of a kept build (`--keep-build`) holding CMakeLists.txt. `build`
copies it, builds target `game` and prints the executable; with the harness
(tools/hostkit_ab/hooks.c) the host sources are compiled against a virtual clock, a modelled
audio device, a scripted keyboard, mouse and controllers, and a picture read back at every
frame. `run` plays a script (see hooks.c) in an empty folder with the dummy SDL drivers and
keeps the frame hashes, the audio and window log, the preferences file and the state files.
`compare` says whether two runs agree, byte for byte.

A host refactor is "unchanged" when the old and the new build of the SAME game give the same
runs. Both sides must be built the same way, from the same project, with the same
retro16_state_config.h (--state-config), so that quick states cross over.
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
             'SetWindowTitle', 'SetWindowFullscreen', 'RenderPresent')
HOST_SOURCE = re.compile(r'console16_host_ui\.c|hostkit/(?:shell|adapters)/rrhk_\w+\.c')


def build(project: Path, work: Path, plain: bool, state_config: Path | None, refresh_kit: bool = False,
          patches=(), legacy_host: Path | None = None) -> Path:
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args, sdl_install
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(project, work, ignore=shutil.ignore_patterns('build', 'build.log', 'entry.lock'))
    if state_config:
        shutil.copyfile(state_config, work / 'retro16_state_config.h')
    if refresh_kit and (work / 'hostkit').is_dir():
        shutil.rmtree(work / 'hostkit')   # the kit as it stands in this tree, not as the kept project has it
        shutil.copytree(ROOT / 'native/hostkit', work / 'hostkit')
    for name, old, new in patches:   # a property of the game for the variant under test (six buttons, a gun)
        text = (work / name).read_text(encoding='utf-8')
        if old not in text:
            raise SystemExit(f'{name} has no {old!r}')
        (work / name).write_text(text.replace(old, new), encoding='utf-8')
    cmake_file = work / 'CMakeLists.txt'
    text = cmake_file.read_text(encoding='utf-8')
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


def play(exe: Path, script: Path, out: Path, timeout: int, extra=(), seed: Path | None = None) -> int:
    if out.exists():
        shutil.rmtree(out)
    box = out / 'box'
    box.mkdir(parents=True)
    shutil.copy2(exe, box / exe.name)
    if seed:   # quick states (datas/states) another run left behind
        shutil.copytree(seed, box / 'datas' / 'states')
    environment = {**os.environ, 'SDL_VIDEODRIVER': 'offscreen', 'SDL_RENDER_DRIVER': 'software',
                   'SDL_AUDIODRIVER': 'dummy', 'RRAB_SCRIPT': str(script), 'RRAB_OUT': str(out)}
    for name in ('RETRORECOMP_HOST_TEST_FRAMES', 'RETRORECOMP_HOST_TEST_FILTER', 'RETRORECOMP_TIMING_REPORT',
                 'RETRORECOMP_HOST_TEST_NO_AUDIO'):
        environment.pop(name, None)
    for pair in extra:   # NAME=VALUE; @OUT@ stands for the output folder
        name, value = pair.split('=', 1)
        environment[name] = value.replace('@OUT@', str(out))
    done = subprocess.run([str(box / exe.name)], cwd=box, env=environment, capture_output=True, timeout=timeout)
    (out / 'stderr.txt').write_bytes(done.stderr)
    (out / 'returncode.txt').write_text(str(done.returncode))
    return done.returncode


def collect(out: Path) -> dict:
    """Everything a run left behind, by name."""
    result = {}
    for name in ('frames.log', 'events.log', 'stderr.txt', 'returncode.txt', 'timing.json'):
        path = out / name
        result[name] = path.read_bytes() if path.is_file() else b''
    datas = out / 'box' / 'datas'
    if datas.is_dir():
        for path in sorted(datas.rglob('*')):
            if path.is_file():
                result['datas/' + path.relative_to(datas).as_posix()] = path.read_bytes()
    for path in sorted(out.glob('*.bmp')):
        result[path.name] = path.read_bytes()
    return result


def compare(a: Path, b: Path) -> int:
    first, second = collect(a), collect(b)
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

    def text(self):
        return '\n'.join(self.lines) + '\n'


def battery(family: str, players: int = 2, gun: bool = False, pages: int = 5, lead: int = 40, soak: int = 2400,
            options: bool = True) -> str:
    """One long script for the whole shell: input, menus in every language, preferences, states.

    `pages` is the number of F2 pages (2 per player, the machine's own page, the options)."""
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
        for page in range(1, swept):
            s.tap('Right', 3).say(f'capture f2-{language}-{page}.bmp', 2)
        for _ in range(swept - 1):
            s.tap('Left', 2)
        s.tap('F2', 4)
        s.tap('F7', 5)        # next language; five turns come back to the first
    # 8. Bindings: rebind a key and a controller button of player 1 and player 2, quit/restart combinations.
    s.tap('F2', 3).tap('Down', 2).tap('Return', 3).tap('J', 3).say('capture bound-key.bmp', 2)
    s.tap('Down', 2).tap('Return', 3).tap('Escape', 3).tap('Up', 2)
    s.tap('Right', 3).tap('Return', 3).say('button 0 leftstick 1', 2).say('button 0 leftstick 0', 4)
    s.say('capture bound-pad.bmp', 2).tap('Down', 2).tap('Return', 3).say('button 0 rightstick 1', 2).say('button 0 rightstick 0', 4)
    for _ in range(3):      # the combination rows sit after the actions: go round from the top
        s.tap('Up', 2)
    s.tap('Return', 3).say('hold K', 4).say('release K', 4)
    s.say('capture combo.bmp', 2).tap('Delete', 3).tap('Left', 3).tap('Up', 2).tap('Return', 3).tap('Escape', 3)
    s.tap('Right', 3).tap('Right', 3)      # player 2's pages
    s.tap('Down', 2).tap('Return', 3).tap('L', 3).tap('Escape', 3).tap('F2', 3)
    # 9. The machine's own page and the options.
    if gun or family == 'cps1':
        s.tap('F2', 3)
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
        for _ in range(pages - 1):
            s.tap('Right', 3)
    if options:
        s.say('capture options.bmp', 2)
        for _ in range(3):
            s.tap('Down', 2).tap('Return', 3)       # an option row runs its function key or changes the filter
        s.tap('Left', 3)
    s.tap('F2', 4)
    s.tap('Escape', 3)
    # 10. Pointer: aim, fire, secondary, aux, leave the window.
    if gun:
        for x, y, mask in ((300, 200, 0), (300, 200, 1), (450, 250, 2), (450, 250, 4), (600, 300, 1), (10, 10, 0), (2000, 2000, 1)):
            s.say(f'mouse {x} {y} {mask}', 4)
        s.say('mouse 300 200 0', 3).tap('F2', 3).tap('Right', 3).tap('Right', 3).tap('Right', 3)
        s.tap('F4', 4).say('mouse 400 300 1', 4).say('mouse 400 300 0', 3)
    # 10b. Neo Geo: enhanced mode on and off; the AES/MVS switch restarts the game, so it comes last.
    if family == 'ng':
        s.tap('F5', 6).say('capture enhanced.bmp', 2).tap('F5', 6).tap('F11', 6).say('capture aes.bmp', 2)
    # 11. Close like a user: the window's close button.
    s.at(s.now + 20).say('capture end.bmp', 2).say('quit')
    return s.text()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('build'); p.add_argument('project', type=Path); p.add_argument('work', type=Path)
    p.add_argument('--plain', action='store_true', help='no harness: the executable as the game ships it (unpacked)')
    p.add_argument('--state-config', type=Path)
    p.add_argument('--patch', nargs=3, action='append', default=[], metavar=('FILE', 'OLD', 'NEW'),
                   help='replace text in a project file before building, e.g. retro_gun_game.h "RR16_GUN 0" "RR16_GUN 3"')
    p.add_argument('--legacy-host', type=Path, help='build the old console16_host_ui.c over this project instead of the kit')
    p.add_argument('--refresh-kit', action='store_true', help="copy native/hostkit of this tree over the kit of the project")
    p = sub.add_parser('run'); p.add_argument('exe', type=Path); p.add_argument('script', type=Path)
    p.add_argument('out', type=Path); p.add_argument('--timeout', type=int, default=900)
    p.add_argument('--seed-states', type=Path, help='a datas/states folder (of another run) to start from')
    p.add_argument('--env', action='append', default=[], metavar='NAME=VALUE', help='extra environment; @OUT@ is the output folder')
    p = sub.add_parser('compare'); p.add_argument('a', type=Path); p.add_argument('b', type=Path)
    p = sub.add_parser('script', help='write the standard battery of the shell for one machine')
    p.add_argument('family', choices=('md', 'snes', 'ng', 'cps1')); p.add_argument('out', type=Path)
    p.add_argument('--players', type=int, default=2); p.add_argument('--gun', action='store_true')
    p.add_argument('--no-options-page', action='store_true', help='leave the options page of F2 alone (see the Linux note in the report)')
    p.add_argument('--soak', type=int, default=2400, help='iterations of play between the sweeps and the menus')
    p.add_argument('--pages', type=int, default=0, help='F2 pages (default: 2 per player, the machine page, the options)')
    args = parser.parse_args()
    if args.command == 'script':
        pages = args.pages or 2 * args.players + (1 if args.gun or args.family == 'cps1' else 0) + 1
        args.out.write_text(battery(args.family, args.players, args.gun, pages, soak=args.soak, options=not args.no_options_page), encoding='ascii')
        return 0
    if args.command == 'build':
        print(build(args.project.resolve(), args.work.resolve(), args.plain, args.state_config, args.refresh_kit, args.patch, args.legacy_host))
        return 0
    if args.command == 'run':
        code = play(args.exe.resolve(), args.script.resolve(), args.out.resolve(), args.timeout, args.env, args.seed_states)
        print('exit', code)
        return 0 if code == 0 else 1
    return compare(args.a.resolve(), args.b.resolve())


if __name__ == '__main__':
    raise SystemExit(main())
