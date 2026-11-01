"""Gate G7 for the Game Boy: the battery RAM and the real-time clock of the delivered file survive without F8/F9.

Cartridges are authored here (no original bytes): one per mapper that has a battery (MBC1, MBC2, MBC3 with its clock, MBC5), one
with RAM and no battery, and one with a battery whose program never writes. Each is converted by the converter and the delivered
executable is run twice in an empty folder, headless, with `--dump-state`. The first run finds no magic bytes in its RAM and writes a
pattern; the second must find the magic, copy the pattern to work RAM and report that it did. Then the damaged-file cases: a
battery file cut short, one of the wrong size and one that is not a save at all must not stop the game from starting.

    python tools/gameboy_saves_check.py [--work FOLDER] [--only NAME] [--reuse]

Nothing here says anything about hardware fidelity or about the games' own save code; it checks the files and the reload.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MAGIC = (0x52, 0x52, 0x53)            # 'R', 'R', 'S'
PATTERN_LENGTH = 28                   # bytes written after the magic and the version byte
WRAM_FLAG = 0xC000                    # 1 when the magic was found at start
WRAM_COPY = 0xC010                    # the 32 bytes of RAM read back
WRAM_RTC = 0xC030                     # the five clock registers read back (MBC3)


class Assembler:
    """The few SM83 instructions the cartridges need, with labels for the relative jumps."""

    def __init__(self, origin: int):
        self.origin, self.code, self.labels, self.fixups = origin, bytearray(), {}, []

    def label(self, name):
        self.labels[name] = self.origin + len(self.code)

    def emit(self, *values):
        self.code += bytes(values)

    def ld_a(self, value): self.emit(0x3E, value & 0xFF)
    def ld_nn_a(self, address): self.emit(0xEA, address & 0xFF, address >> 8)
    def ld_a_nn(self, address): self.emit(0xFA, address & 0xFF, address >> 8)
    def cp(self, value): self.emit(0xFE, value & 0xFF)
    def and_(self, value): self.emit(0xE6, value & 0xFF)
    def ld_hl(self, value): self.emit(0x21, value & 0xFF, value >> 8)
    def ld_de(self, value): self.emit(0x11, value & 0xFF, value >> 8)
    def ld_b(self, value): self.emit(0x06, value & 0xFF)
    def ld_a_hli(self): self.emit(0x2A)
    def ld_hli_a(self): self.emit(0x22)
    def ld_de_a(self): self.emit(0x12)
    def inc_de(self): self.emit(0x13)
    def dec_b(self): self.emit(0x05)
    def inc_c(self): self.emit(0x0C)
    def ld_c(self, value): self.emit(0x0E, value & 0xFF)
    def ld_a_c(self): self.emit(0x79)
    def add_a(self, value): self.emit(0xC6, value & 0xFF)

    def jr(self, condition, target):
        """`condition` is '' (always), 'nz' or 'z'."""
        self.emit({'': 0x18, 'nz': 0x20, 'z': 0x28}[condition], 0)
        self.fixups.append((len(self.code) - 1, target))

    def finish(self) -> bytes:
        for position, target in self.fixups:
            offset = self.labels[target] - (self.origin + position + 1)
            assert -128 <= offset <= 127, target
            self.code[position] = offset & 0xFF
        return bytes(self.code)


def program(kind: str, writes: bool = True) -> bytes:
    """The cartridge program for `kind` ('mbc1', 'mbc2', 'mbc3', 'mbc5', 'plain'): enable RAM, look for the magic; if it is
    there copy the RAM to work RAM and set the flag, else write the magic and a pattern (when `writes`), clear the flag."""
    a = Assembler(0x150)
    a.emit(0x31, 0xFE, 0xFF)                                      # LD SP,$FFFE
    a.ld_a(0x0A); a.ld_nn_a(0x0000)                               # RAM (and clock) enable
    nibble = kind == 'mbc2'                                       # MBC2 keeps four bits per cell
    if kind == 'mbc3':
        a.ld_a(0x00); a.ld_nn_a(0x4000)                           # RAM bank 0
    for index, value in enumerate(MAGIC):
        a.ld_a_nn(0xA000 + index)
        if nibble:
            a.and_(0x0F)
        a.cp(value & 0x0F if nibble else value)
        a.jr('nz', 'first')
    a.ld_a(1); a.ld_nn_a(WRAM_FLAG)
    a.ld_hl(0xA000); a.ld_de(WRAM_COPY); a.ld_b(32)
    a.label('copy')
    a.ld_a_hli()
    if nibble:
        a.and_(0x0F)
    a.ld_de_a(); a.inc_de(); a.dec_b(); a.jr('nz', 'copy')
    if kind == 'mbc3':
        a.ld_a(0x00); a.ld_nn_a(0x6000); a.ld_a(0x01); a.ld_nn_a(0x6000)    # latch the clock
        a.ld_de(WRAM_RTC); a.ld_c(0x08)
        a.label('clock')
        a.ld_a_c(); a.ld_nn_a(0x4000)                              # select register 08..0C
        a.ld_a_nn(0xA000); a.ld_de_a(); a.inc_de(); a.inc_c()
        a.ld_a_c(); a.cp(0x0D); a.jr('nz', 'clock')
    a.jr('', 'done')
    a.label('first')
    a.ld_a(0); a.ld_nn_a(WRAM_FLAG)
    if writes:
        for index, value in enumerate(MAGIC):
            a.ld_a(value & 0x0F if nibble else value); a.ld_nn_a(0xA000 + index)
        a.ld_a(0xC3); a.ld_nn_a(0xA003)                            # a version byte
        a.ld_hl(0xA004); a.ld_b(PATTERN_LENGTH); a.ld_c(7)
        a.label('fill')
        a.ld_a_c()
        if nibble:
            a.and_(0x0F)
        a.ld_hli_a(); a.add_a(3); a.emit(0x4F)                     # LD C,A
        a.dec_b(); a.jr('nz', 'fill')
        if kind == 'mbc3':
            a.ld_a(0x08 + 4); a.ld_nn_a(0x4000)
            a.ld_a(0x41); a.ld_nn_a(0xA000)                        # DH: halted, day bit 8 (the clock stops here)
            for register, value in ((0x08, 17), (0x09, 11), (0x0A, 7), (0x0B, 42)):
                a.ld_a(register); a.ld_nn_a(0x4000); a.ld_a(value); a.ld_nn_a(0xA000)
    a.label('done')
    a.jr('', 'done')
    return a.finish()


CARTRIDGES = {
    # name: (header type, RAM size code, program kind, writes, saved by the battery)
    'mbc1': (0x03, 0x02, 'mbc1', True, True),
    'mbc2': (0x06, 0x00, 'mbc2', True, True),
    'mbc3': (0x10, 0x02, 'mbc3', True, True),
    'mbc5': (0x1B, 0x02, 'mbc5', True, True),
    'nobattery': (0x02, 0x02, 'plain', True, False),        # MBC1+RAM, no battery: nothing is kept
    'readonly': (0x03, 0x02, 'mbc1', False, False),          # a battery, but the program never writes: no file, no folder
}


def authored_rom(name: str) -> bytes:
    header_type, ram_code, kind, writes, _kept = CARTRIDGES[name]
    rom = bytearray(0x8000)
    rom[0x100:0x104] = bytes.fromhex('00 c3 50 01')               # NOP ; JP 0150
    title = f'RRSAVE {name}'.upper().encode('ascii')[:15]
    rom[0x134:0x134 + len(title)] = title
    rom[0x147], rom[0x148], rom[0x149] = header_type, 0x00, ram_code
    checksum = 0
    for index in range(0x134, 0x14D):
        checksum = (checksum - rom[index] - 1) & 0xFF
    rom[0x14D] = checksum
    code = program(kind, writes)
    rom[0x150:0x150 + len(code)] = code
    return bytes(rom)


def expected_copy(kind: str) -> list[int]:
    """The 32 bytes the second run copies from RAM: the magic, the version byte and the pattern of the first run."""
    mask = 0x0F if kind == 'mbc2' else 0xFF
    values = [value & mask for value in MAGIC] + [0xC3 & mask]
    c = 7
    for _ in range(PATTERN_LENGTH):
        values.append(c & mask)
        c = ((c & mask) + 3) & 0xFF         # the program adds to the masked value it has just stored
    return values


EXPECTED_CLOCK = [17, 11, 7, 42, 0x41]       # S, M, H, DL, DH (halted, so it does not move between the runs)


def environment() -> dict:
    return dict(os.environ, PYTHONUTF8='1', SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy',
                PYINSTALLER_SUPPRESS_SPLASH_SCREEN='1')


def convert(name: str, work: Path) -> Path:
    """The delivered executable of the authored cartridge `name`."""
    rom = work / 'roms' / f'{name}.gb'
    rom.parent.mkdir(parents=True, exist_ok=True)
    rom.write_bytes(authored_rom(name))
    out = work / f'out_{name}'
    shutil.rmtree(out, ignore_errors=True)
    result = subprocess.run([sys.executable, '-B', str(ROOT / 'RetroRecomp.py'), 'convert', str(rom), '--system', 'gb',
                             '--scan-level', 'quick', '--no-online-cover', '--output', str(out)],
                            env=environment(), capture_output=True, text=True, timeout=1800, cwd=ROOT)
    executable = out / 'Game Boy' / f'{name}.exe'
    if result.returncode or not executable.is_file():
        raise SystemExit(f'conversion of {name} failed:\n{result.stdout[-1500:]}\n{result.stderr[-800:]}')
    return executable


def run_game(executable: Path, folder: Path, tag: str) -> dict:
    """One headless run of the delivered executable in `folder` (it keeps its saves under `folder/datas`)."""
    state_file = folder / f'state-{tag}.json'
    state_file.unlink(missing_ok=True)
    result = subprocess.run([str(executable), '--headless', '--limit-frames', '3', '--dump-state', str(state_file)],
                            env=environment(), capture_output=True, text=True, timeout=300, cwd=folder)
    state = json.loads(state_file.read_text(encoding='utf-8')) if state_file.is_file() else None
    wram = state['wram_bank_0_c000_cfff'] if state else None
    return {'exit': result.returncode, 'state': state is not None, 'output': result.stdout + result.stderr,
            'flag': wram[WRAM_FLAG - 0xC000] if wram else None,
            'copy': wram[WRAM_COPY - 0xC000:WRAM_COPY - 0xC000 + 32] if wram else None,
            'clock': wram[WRAM_RTC - 0xC000:WRAM_RTC - 0xC000 + 5] if wram else None}


def saves(folder: Path) -> dict[str, bytes]:
    """The files of the game's data folder, by name."""
    root = folder / 'datas' / 'games'
    return {str(path.relative_to(root)): path.read_bytes() for path in sorted(root.rglob('*')) if path.is_file()} if root.is_dir() else {}


def check(condition: bool, message: str, failures: list[str]) -> None:
    print(('  ok   ' if condition else '  FAIL ') + message, flush=True)
    if not condition:
        failures.append(message)


def run_cartridge(name: str, executable: Path, work: Path, failures: list[str]) -> dict:
    _type, _ram, kind, writes, kept = CARTRIDGES[name]
    folder = work / f'run_{name}'
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    shutil.copy2(executable, folder / executable.name)
    game = folder / executable.name
    record: dict = {'cartridge': name, 'battery': kept}
    print(f'{name}: header type {CARTRIDGES[name][0]:02X}, program {kind}, writes {writes}, kept by a battery {kept}')
    first = run_game(game, folder, 'first')
    check(first['exit'] == 0 and first['state'], 'the first run ends normally', failures)
    check(first['flag'] == 0, 'the first run finds no save', failures)
    files = saves(folder)
    record['files_after_first_run'] = {key: len(value) for key, value in files.items()}
    if not kept:
        check(not (folder / 'datas').exists() or not files,
              'no save file and no data folder is created' + ('' if writes else ' by a program that never writes'), failures)
        second = run_game(game, folder, 'second')
        check(second['flag'] == 0, 'the second run does not find the first run\'s RAM (nothing is kept)', failures)
        return record
    check(bool(files), 'the first run leaves a save file', failures)
    sav = [key for key in files if key.endswith('.sav')]
    check(len(sav) == 1, 'one battery file', failures)
    if kind != 'mbc2' and sav:
        check(len(files[sav[0]]) == 8192, 'the battery file holds the 8 KiB of RAM of the header', failures)
    mask = 0x0F if kind == 'mbc2' else 0xFF
    if sav:
        check(bytes(value & mask for value in MAGIC) == bytes(byte & mask for byte in files[sav[0]][:3]),
              'the magic is in the battery file', failures)
    if kind == 'mbc3':
        check(any(key.endswith('.rtc') for key in files), 'the first run leaves a clock file', failures)
    second = run_game(game, folder, 'second')
    check(second['exit'] == 0 and second['flag'] == 1, 'the second run finds its save', failures)
    check(second['copy'] == expected_copy(kind), 'the second run reads back the pattern byte for byte', failures)
    if kind == 'mbc3':
        check(second['clock'] == EXPECTED_CLOCK, f"the clock registers come back (halted clock): {second['clock']}", failures)
    after = saves(folder)
    check(after == files, 'a run that wrote nothing leaves every save file as it was', failures)
    record['second_run'] = {'flag': second['flag'], 'clock': second['clock']}
    if name in ('mbc1', 'mbc3'):
        record['damaged'] = damaged_cases(game, folder, work, files, sav[0] if sav else None, failures)
    return record


def damaged_cases(game: Path, folder: Path, work: Path, files: dict, battery: str | None, failures: list[str]) -> dict:
    """A battery file cut short, too long, empty or not a save: the game starts, the file is left as it was, and the automatic save
    is suppressed (the log says so). The same for the clock file of a cartridge that has one."""
    outcomes = {}
    targets = [(battery, 'battery')] + ([(key, 'clock') for key in files if key.endswith('.rtc')][:1])
    for target, label in targets:
        if target is None:
            continue
        for case, data in (('short', files[target][:7]), ('long', b'\xff' * (len(files[target]) + 800)),
                           ('empty', b''), ('junk', b'this is not a save file\n')):
            copy = work / f'damaged_{folder.name}_{label}_{case}'
            shutil.rmtree(copy, ignore_errors=True)
            shutil.copytree(folder, copy)
            path = copy / 'datas' / 'games' / target
            path.write_bytes(data)
            result = run_game(copy / game.name, copy, 'damaged')
            same = path.read_bytes() == data
            check(result['exit'] == 0 and result['state'], f'{label} file {case}: the game starts and ends normally', failures)
            if label == 'battery':
                check(result['flag'] == 0, f'{label} file {case}: the game starts with blank RAM, not with a half save', failures)
            else:
                check(result['flag'] == 1 and result['clock'] != EXPECTED_CLOCK,
                      f"{label} file {case}: the RAM still loads, the clock is not taken from the damaged file ({result['clock']})", failures)
            check(same, f'{label} file {case}: the file is left as it was (not overwritten, not deleted)', failures)
            check('suppressed' in result['output'].lower() or 'rejected' in result['output'].lower(),
                  f'{label} file {case}: the log says the data was rejected', failures)
            outcomes[f'{label}_{case}'] = {'exit': result['exit'], 'flag': result['flag'], 'file_kept': same}
            shutil.rmtree(copy, ignore_errors=True)
    return outcomes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--work', type=Path, default=ROOT / '.build' / 'gb-saves')
    parser.add_argument('--only', choices=sorted(CARTRIDGES), action='append')
    parser.add_argument('--reuse', action='store_true', help='use the executables already converted in the work folder')
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    records = []
    for name in args.only or list(CARTRIDGES):
        executable = work / f'out_{name}' / 'Game Boy' / f'{name}.exe'
        if not (args.reuse and executable.is_file()):
            executable = convert(name, work)
        records.append(run_cartridge(name, executable, work, failures))
    (work / 'results.json').write_text(json.dumps({'records': records, 'failures': failures}, indent=2) + '\n', encoding='utf-8')
    print(f'{len(failures)} failure(s)')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
