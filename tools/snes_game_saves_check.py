"""The battery save of a delivered Super Nintendo game, across two processes (gate G7, on a real cartridge).

    python tools/snes_game_saves_check.py EXE [--frames 3000] [--out DIR]

`tools/snes_saves_check.py` proves the adapter and the file format on cartridges written for the purpose; this tool does the same
steps on the executable of a converted game, headless (SDL dummy drivers, no window), each run from an empty save folder:

  1. the game runs `--frames` frames with the built-in play input; its report says how large its save RAM is and whether it has a
     battery. A game with no battery must write no file; a game with one must write exactly one file of 112 bytes of header plus
     the whole RAM, the board code of the report, and a payload whose hash is the `sram_hash` the game reported at its last frame;
  2. a second process loads that file and runs a single frame: its report must give back the same `sram_hash` as the file (the
     game found its save and had not touched it in one frame) and the file must still hold the same bytes; or, when the game
     rewrote part of its save in that frame (some do, a checksum or a counter), a RAM that is not the one of a start without a
     file, and a file that holds the RAM the game ended with. A game that wrote nothing in its save RAM during the run has no
     file to check and is reported as not exercised;
  3. a copy of the file with one payload byte changed is set aside by a third process (`<name>.unusable-1`, byte for byte), which
     starts with a blank RAM and says so in its report (`save_set_aside`).

It proves that what the game wrote into its save RAM comes back, through the file, in another process, and that a damaged file
never costs the player the original bytes. It does not prove that a player's own save (the one made from the game's menu) is
reached by the routes: that stays with the player. It reads the executable and writes only under --out.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HEADER = 112
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
FNV_BASIS, FNV_PRIME, MASK = 14695981039346656037, 1099511628211, (1 << 64) - 1


def fnv(data: bytes) -> str:
    value = FNV_BASIS
    for byte in data:
        value = ((value ^ byte) * FNV_PRIME) & MASK
    return f'{value:016x}'


def boot(game: Path, save: Path, folder: Path, tag: str, frames: int, play: bool) -> dict:
    report = folder / f'{tag}.json'
    command = [str(game), '--frames', str(frames), '--report', str(report), '--cartridge-save', str(save)]
    if play:
        command.append('--play')
    environment = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    done = subprocess.run(command, cwd=folder, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          creationflags=NO_WINDOW, timeout=3600)
    if done.returncode or not report.is_file():
        raise SystemExit(f'{tag}: the game exited with {done.returncode}: {done.stdout[-300:]!r}')
    return json.loads(report.read_text(encoding='utf-8'))


def check(exe: Path, frames: int, out: Path) -> dict:
    with tempfile.TemporaryDirectory(dir=out) as scratch:
        folder = Path(scratch)
        game = folder / exe.name
        shutil.copy2(exe, game)
        game.chmod(0o755)
        save = folder / 'saves' / 'game.rrsram'
        first = boot(game, save, folder, 'first', frames, True)
        verdict = {'executable': exe.name, 'frames': frames, 'sram_bytes': first['sram_bytes'], 'battery': bool(first['sram_battery'])}
        if not first['sram_battery']:
            assert not save.exists() and not list(save.parent.glob('*')) if save.parent.exists() else True, 'a game with no battery wrote a file'
            verdict['result'] = 'no battery, no file'
            return verdict
        if not save.is_file():
            # A save file is written when the RAM changes: a game that left its save RAM as it found it in this many frames has
            # nothing to write, and this check has not exercised it.
            verdict['result'] = f'not exercised: the game wrote nothing in its save RAM in {frames} frames, so no file was written'
            return verdict
        raw = save.read_bytes()
        size = first['sram_bytes']
        assert len(raw) == HEADER + size, (len(raw), size)
        assert raw[:8] == b'RRSNRA1' + bytes(1), raw[:8]
        assert int.from_bytes(raw[12:16], 'little') == size
        assert int.from_bytes(raw[16:20], 'little') == first['sram_mapping'], 'the board code of the file is the report\'s'
        assert fnv(raw[HEADER:]) == first['sram_hash'], 'the payload is the RAM the game ended with'
        assert not list(save.parent.glob('*.tmp')), 'a half-written file was left behind'
        verdict.update(file_bytes=len(raw), written_nonzero=sum(1 for byte in raw[HEADER:] if byte), sram_hash=first['sram_hash'])
        blank = boot(game, folder / 'blank' / 'game.rrsram', folder, 'blank', 1, False)
        second = boot(game, save, folder, 'second', 1, False)
        if second['sram_hash'] == first['sram_hash']:
            assert save.read_bytes() == raw, 'the second process changed the file'
            verdict['reloaded'] = 'as it was'
        else:
            # The game rewrote part of its save RAM during its first frame (a checksum, a counter), and did so from what it
            # loaded: a start without a file gives another RAM.
            assert second['sram_hash'] != blank['sram_hash'], 'the second process did not find the first one\'s RAM'
            assert fnv(save.read_bytes()[HEADER:]) == second['sram_hash'], 'the file does not hold the RAM the game ended with'
            verdict['reloaded'] = 'found, then rewritten by the game in its first frame'
            raw = save.read_bytes()
        damaged = bytearray(raw)
        damaged[HEADER + size // 2] ^= 0x40
        save.write_bytes(damaged)
        third = boot(game, save, folder, 'third', 1, False)
        aside = save.with_name(save.name + '.unusable-1')
        assert aside.is_file() and aside.read_bytes() == bytes(damaged), 'the damaged file is kept byte for byte'
        assert third['save_set_aside'] == 1, third['save_set_aside']
        verdict['damaged_file_set_aside'] = True
        verdict['result'] = 'passed'
        return verdict


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('exe', type=Path)
    parser.add_argument('--frames', type=int, default=3000)
    parser.add_argument('--out', type=Path, default=Path('.build/snes-game-saves'))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    print(json.dumps(check(args.exe.resolve(), args.frames, args.out.resolve()), sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
