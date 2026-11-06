"""Check the CPS-2 opcode decryption against MAME (gate: independent evidence for the decrypted program images).

    python -B tools/cps2_crypt_check.py SET [SET ...] --mame MAME.exe --roms ROMS_FOLDER [--mame-roms FOLDER] [--bios FOLDER]

For each set, the program is assembled from the set's ZIP (read the way the converter reads it, from --roms), decrypted with the 20-byte
key that ZIP carries (`retrorecomp.cps2_crypt`), and both images are compared word for word with what MAME 0.289 gives the 68000 over
0x000000-0x3fffff: the `program` space (what data reads see: our stored image) and the `opcodes` space (what instruction fetches see: our
decrypted image). MAME is run once per set, headless and without sound, only to dump those two spaces; the ROMs and the key stay where
they are and nothing is written in the repository. A key is the player's data: it is read from the archive and never printed.

What it shows: our decryption equals MAME's for the checked sets, range limits included. It says nothing about the board, the video or
the sound, and MAME is a model, not the hardware.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp import cps1_board, cps2, cps2_catalogue, cps2_crypt

LUA = '''
local cpu = manager.machine.devices[":maincpu"]
local function dump(space, path)
  local s = cpu.spaces[space]
  local out = io.open(path, "wb")
  local parts, n = {}, 0
  for a = 0, 0x3ffffe, 2 do
    n = n + 1
    parts[n] = string.pack(">I2", s:read_u16(a))
    if n == 4096 then out:write(table.concat(parts)); parts, n = {}, 0 end
  end
  if n > 0 then out:write(table.concat(parts)) end
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
                              '-nvram_directory', str(work / 'nvram')], capture_output=True, text=True, timeout=600,
                             cwd=mame.parent, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
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
    game_set = cps2.read_set(archive, set_name=name)
    game = cps2_catalogue.by_set()[name]
    files = cps1_board.member_bytes(game_set)
    regions = cps1_board.assemble(game, files)
    program = bytes(regions['maincpu'])
    return cps2_crypt.decrypt(program, files[cps2_catalogue.key_file(game)['name']]), program


def check(name: str, roms: Path, mame: Path, mame_roms: Path, bios: Path | None, work: Path) -> bool:
    started = time.time()
    archive = roms / f'{name}.zip'
    if not archive.is_file() and cps2_catalogue.by_set()[name]['parent']:     # a merged romset keeps the clones in the parent's archive
        archive = roms / (cps2_catalogue.by_set()[name]['parent'] + '.zip')
    opcodes, program = our_images(archive, name)
    ours = time.time() - started
    mame_opcodes, mame_program = mame_images(mame, name, mame_roms, bios, work)
    size = len(mame_opcodes)
    different = sum(a != b for a, b in zip(opcodes[:size], mame_opcodes)), sum(a != b for a, b in zip(program[:size], mame_program))
    ok = not any(different) and size == 0x400000
    print(f'{name}: {size} bytes per space, opcode image {"equal" if not different[0] else str(different[0]) + " bytes differ"}, '
          f'program image {"equal" if not different[1] else str(different[1]) + " bytes differ"}'
          f'{"" if opcodes[:size] != program[:size] else " (WARNING: the two views are equal)"} ({ours:.1f} s to decrypt on our side)')
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
        results = []
        for name in options.sets:
            try:
                results.append(check(name, options.roms, options.mame, options.mame_roms or options.roms, options.bios, Path(folder)))
            except (ValueError, SystemExit) as error:
                print(f'{name}: not checked: {str(error)[:160]}')
                results.append(False)
    return 0 if all(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
