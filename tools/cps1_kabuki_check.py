"""Check the Kabuki decryption of the CPS-1.5 sound CPU against MAME (gate: independent evidence for the Z80 images).

    python -B tools/cps1_kabuki_check.py SET [SET ...] --mame MAME.exe --roms ROMS_FOLDER [--mame-roms FOLDER] [--bios FOLDER_WITH_qsound.zip]

For each set, `retrorecomp.cps1_kabuki.decode` is applied to the sound ROM assembled from the set's ZIP (read the way the
converter reads it, from --roms), and the two images are compared byte for byte with what MAME 0.289 gives the sound Z80 over the same range:
the `opcodes` space (instruction fetches) and the `program` space (data), addresses 0000-7FFF. MAME is run once, headless and without
sound, only to dump those two spaces; it needs the set in a ROM folder (--mame-roms, default --roms; a FBNeo zip can lack the PLD files MAME wants) and `qsound.zip` (the QSound DSP ROM,
a device ROM of MAME's QSound that the player supplies) in the BIOS folder. The tool reads and writes nothing in the repository; the
ROMs stay where they are. The keys are catalogue numbers; the comparison is the proof that they are the right ones for these ROMs.

What it shows: the decryption equals MAME's for the checked sets. It says nothing about the QSound DSP, the board or the game.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp import cps1, cps1_board, cps1_catalogue, cps1_kabuki

LUA = '''
local cpu = manager.machine.devices[":audiocpu"]
local function dump(space, path)
  local out = io.open(path, "wb")
  local parts = {}
  for a = 0, 0x7fff do parts[#parts + 1] = string.char(cpu.spaces[space]:read_u8(a)) end
  out:write(table.concat(parts))
  out:close()
end
dump("opcodes", "%(opcodes)s")
dump("program", "%(program)s")
manager.machine:exit()
'''


def mame_images(mame: Path, name: str, roms: Path, bios: Path | None, work: Path) -> tuple[bytes, bytes]:
    stub = work / 'stub'
    paths = [str(roms)] + ([str(bios)] if bios else []) + [str(stub)]
    files = {'opcodes': work / f'{name}.opcodes', 'program': work / f'{name}.program'}
    script = work / f'{name}.lua'
    script.write_text(LUA % {key: value.as_posix() for key, value in files.items()}, encoding='ascii')
    for attempt in range(2):
        run = subprocess.run([str(mame), name, '-rompath', ';'.join(paths), '-video', 'none', '-sound', 'none', '-nothrottle',
                              '-skip_gameinfo', '-nomouse', '-autoboot_script', str(script), '-cfg_directory', str(work / 'cfg'),
                              '-nvram_directory', str(work / 'nvram')], capture_output=True, text=True, timeout=300,
                             cwd=mame.parent, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        # A FBNeo or MAME zip can lack a PLD dump that MAME wants. A stand-in file of one byte (MAME only warns about a wrong
        # length or checksum) lets it start; the comparison below would show any stand-in that mattered.
        missing = re.findall(r'^(\S+) NOT FOUND \(tried in (\S+)\)', run.stdout + run.stderr, re.M)
        if not missing or attempt:
            break
        for file_name, folder in missing:
            (stub / folder).mkdir(parents=True, exist_ok=True)
            (stub / folder / file_name).write_bytes(b'\0')
    if not all(path.is_file() for path in files.values()):
        raise SystemExit(f'{name}: MAME did not dump the images (exit {run.returncode}):\n{(run.stdout + run.stderr)[-600:]}')
    return files['opcodes'].read_bytes(), files['program'].read_bytes()


def our_images(archive: Path, name: str) -> tuple[bytes, bytes]:
    game_set = cps1.read_set(archive, set_name=name)
    game = cps1_catalogue.by_set()[name]
    keys = cps1_kabuki.keys_for(game)
    if keys is None:
        raise SystemExit(f'{name}: the catalogue names no Kabuki keys (init {game["init"]}).')
    regions = cps1_board.assemble(game, cps1_board.member_bytes(game_set))
    return cps1_kabuki.decode(bytes(regions['audiocpu']), keys)


def check(name: str, roms: Path, mame: Path, mame_roms: Path, bios: Path | None, work: Path) -> bool:
    opcodes, data = our_images(roms / f'{name}.zip', name)
    mame_opcodes, mame_data = mame_images(mame, name, mame_roms, bios, work)
    size = len(mame_opcodes)
    ok = opcodes[:size] == mame_opcodes and data[:size] == mame_data
    different = sum(a != b for a, b in zip(opcodes[:size], mame_opcodes)), sum(a != b for a, b in zip(data[:size], mame_data))
    print(f'{name}: {size} bytes per space, opcode image {"equal" if not different[0] else str(different[0]) + " differ"}, '
          f'data image {"equal" if not different[1] else str(different[1]) + " differ"}'
          f'{"" if opcodes[:size] != data[:size] else " (WARNING: the two views are equal)"}')
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sets', nargs='+')
    parser.add_argument('--mame', type=Path, required=True)
    parser.add_argument('--roms', type=Path, required=True)
    parser.add_argument('--mame-roms', type=Path)
    parser.add_argument('--bios', type=Path)
    options = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        results = [check(name, options.roms, options.mame, options.mame_roms or options.roms, options.bios, Path(folder)) for name in options.sets]
    return 0 if all(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
