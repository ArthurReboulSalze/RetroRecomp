"""The PC Engine CD's drive, CD audio, ADPCM, Super System Card RAM and backup memory against MAME 0.289, on the player's own discs (development check; nothing is shipped).

    python -B tools/pcecd_mame_compare.py CARD.pce DISC.chd [DISC.chd ...] --mame MAME.exe [--frames 3600] [--work DIR]

Both sides boot the player's Japanese Super System Card 3.0 (MAME's software `scdsys`, the same file by its hash) with the same disc and play the same pad script
(Run on the System Card's "push RUN" screen, then I and Run now and then). Our side is native/pcecd_mame_probe.cpp: the machine of the game with every instruction on
the interpreter, built with a copy of the pinned runtime/src/bus_trace.cpp in which the observer of bus accesses calls the probe (nothing of the engine's behaviour
changes). MAME runs headless (-video none -sound none, no window) with a Lua script that taps the same addresses and holds its taps in globals.

The two drives do not take the same time (MAME's CD timing is not the engine's), so nothing is compared frame by frame: the events are compared **in the order the
guest made them**, which is what a program sees:

* **commands**: the bytes written to the drive after each selection ($1800 then $1801), in order: the same opcodes with the same parameters (a READ's sector and
  count, a play's track or sector);
* **interrupts**: the values written to the interrupt mask ($1802, its acknowledge bit removed), in order;
* **CD audio**: the audio commands among them (D8 set start, D9 play) with their parameters, and each time the drive starts playing, the first and last sector it plays
  (our engine's audio state, MAME's `m_cdda_status`, `m_current_frame` and `m_end_frame`), read once per frame;
* **ADPCM**: the writes of the address, length, control and rate ports ($1808, $1809, $180B-$180F), in order, and the bytes written to the ADPCM RAM ($180A), counted
  and hashed;
* **Super System Card RAM**: the hash of $68-$7F and of the CD RAM ($80-$87) at each selection of the drive, where both sides have issued the same commands (the data
  of the transfers before is then in memory on both), and the signature read at $18C1-$18C3;
* **backup memory lock**: the writes of the unlock port ($1807) in order, and the 2 KiB of backup memory at the end.

It prints, for each disc, how far the two agree (the number of leading events equal) and where they first part, and for each zero a positive control (the count of
events seen on each side). It says nothing of a real console (MAME is not hardware), of timing, of gameplay or of latency. MAME is your own local copy; nothing of
it, no ROM, no sound and no frame enters the repository: the work folder (default .build/pcecd-mame) is ignored by git.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.paths import ASSETS  # noqa: E402

WORK = ROOT / '.build' / 'pcecd-mame'
SYSTEM_CARD_NAME = '[cd] super cd-rom system (japan) (v3.0).pce'       # MAME's file name in its software `scdsys`
SYSTEM_CARD_SHA1 = '79f5ff55dd10187c7fd7b8daab0b3ffbd1f56a2c'
RUN, I = 0x008, 0x001
MAME_FIELDS = {0x001: (':ctrl:joypad2:BUTTONS', 'P1 Button I'), 0x002: (':ctrl:joypad2:BUTTONS', 'P1 Button II'), 0x004: (':ctrl:joypad2:BUTTONS', 'P1 Select'),
               0x008: (':ctrl:joypad2:BUTTONS', 'P1 Run'), 0x010: (':ctrl:joypad2:DIRECTION', 'P1 Up'), 0x020: (':ctrl:joypad2:DIRECTION', 'P1 Right'),
               0x040: (':ctrl:joypad2:DIRECTION', 'P1 Down'), 0x080: (':ctrl:joypad2:DIRECTION', 'P1 Left')}

LUA = r'''
local SCRIPT = { %(script)s }
local FIELDS = { %(fields)s }
frame = 0
held = 0
adpcm_count = 0
adpcm_hash = 0xcbf29ce484222325
lock_reads = 0
selects = 0
port_reads = { [1] = 0, [8] = 0 }
port_hash = { [1] = 0xcbf29ce484222325, [8] = 0xcbf29ce484222325 }
cpu = manager.machine.devices[":maincpu"]
space = cpu.spaces["program"]
out = io.open("%(log)s", "w")
local function hash_range(first, last)
  local h = 0xcbf29ce484222325
  local block = space:read_range(first, last, 8)
  for i = 1, #block do h = (h ~ string.byte(block, i)) * 1099511628211 end
  return h
end
local items = manager.machine.devices[":pce_cd"].items
local adpcm_item = emu.item(items["0/m_adpcm_ram"])
local locked_item = emu.item(items["0/m_bram_locked"])
function adpcm_ram_hash()
  local h = 0xcbf29ce484222325
  local block = adpcm_item:read_block(0, 65536)
  for i = 1, #block do h = (h ~ string.byte(block, i)) * 1099511628211 end
  return h
end
function bram_locked() return (locked_item:read(0) ~= 0) and 1 or 0 end
local function dump_memory(n)
  local f = io.open("%(dumps)s/mem-" .. n .. ".bin", "wb")
  f:write(space:read_range(0x0d0000, 0x0fffff, 8))
  f:write(space:read_range(0x100000, 0x10ffff, 8))
  f:close()
end
local audio_status = emu.item(items["0/m_cdda_status"])
local audio_first = emu.item(items["0/m_current_frame"])
local audio_last = emu.item(items["0/m_end_frame"])
playing, first_frame, last_frame = 0, 0, 0
tap_w = space:install_write_tap(0x1ff800, 0x1ff80f, "cdw", function(offset, data, mask)
  local reg = offset - 0x1ff800
  if reg == 10 then
    adpcm_count = adpcm_count + 1
    adpcm_hash = (adpcm_hash ~ data) * 1099511628211
    return
  end
  out:write(string.format("W %%d %%X %%02X\n", frame, reg, data))
  if reg == 0 then
    selects = selects + 1
    out:write(string.format("S %%d %%d %%016x %%016x %%016x %%d\n", frame, selects, hash_range(0x100000, 0x10ffff), hash_range(0x0d0000, 0x0fffff), adpcm_ram_hash(), bram_locked()))
    dump_memory(selects)
  end
end)
local function port_tap(port)
  return space:install_read_tap(0x1ff800 + port, 0x1ff800 + port, "port" .. port, function(offset, data, mask)
    port_reads[port] = port_reads[port] + 1
    port_hash[port] = (port_hash[port] ~ data) * 1099511628211
  end)
end
tap_data1 = port_tap(1)
tap_data8 = port_tap(8)
tap_lock = space:install_read_tap(0x1ff803, 0x1ff803, "lock", function(offset, data, mask) lock_reads = lock_reads + 1 end)
tap_sig = space:install_read_tap(0x1ff8c0, 0x1ff8c7, "sig", function(offset, data, mask) out:write(string.format("R %%d %%X %%02X\n", frame, offset - 0x1ff800, data)) end)
local fields = {}
for bit, spec in pairs(FIELDS) do fields[bit] = manager.machine.ioport.ports[spec[1]].fields[spec[2]] end
next_row = 1
sub_frame = emu.add_machine_frame_notifier(function()
  frame = frame + 1
  local now, a, b = (audio_status:read(0) == 1) and 1 or 0, audio_first:read(0), audio_last:read(0)
  if now ~= playing or (now == 1 and (a ~= first_frame or b ~= last_frame)) then
    playing, first_frame, last_frame = now, a, b
    out:write(string.format("D %%d %%d %%d %%d\n", frame, now, a, b))
  end
  if frame == 700 then for reg = 0xc1, 0xc3 do out:write(string.format("C %%X %%02X\n", reg, space:read_u8(0x1ff800 + reg))) end end
  while next_row <= #SCRIPT and SCRIPT[next_row][1] <= frame do held = SCRIPT[next_row][2]; next_row = next_row + 1 end
  for bit, field in pairs(fields) do field:set_value(((held & bit) ~= 0) and 1 or 0) end
  if frame == %(frames)d then
    out:write(string.format("A %%016x %%d\n", adpcm_ram_hash(), bram_locked()))
    for _, port in ipairs({1, 8}) do out:write(string.format("P %%d %%d %%016x\n", port, port_reads[port], port_hash[port])) end
    out:write(string.format("END %%d adpcm_data %%d %%016x lock_reads %%d selects %%d\n", frame, adpcm_count, adpcm_hash, lock_reads, selects))
    out:close()
    manager.machine:exit()
  end
end)
'''


def pad_script(frames: int) -> list[tuple[int, int]]:
    """Run on the "push RUN" screen at the start, then I and, less often, Run: presses of six frames, the same on both sides."""
    rows = []
    for at in (600, 900):
        rows += [(at, RUN), (at + 6, 0)]
    frame, count = 1500, 0
    while frame < frames - 10:
        word = RUN if count % 4 == 3 else I
        rows += [(frame, word), (frame + 6, 0)]
        frame += 300
        count += 1
    return rows


def build_probe(project: Path) -> Path:
    from retrorecomp import core, pce_build, pcecd_build
    from retrorecomp.platforms import build_executable
    pce_build.ensure_engine(print)
    pcecd_build.ensure_libchdr(print)
    engine = pce_build.checkout_path()
    native = (ASSETS / 'native').resolve()
    project.mkdir(parents=True, exist_ok=True)
    source = (engine / 'runtime' / 'src' / 'bus_trace.cpp').read_text(encoding='utf-8').replace('\r\n', '\n')
    head = 'void observe_bus_access(Bus& bus,const Cpu& cpu,BusTraceDirection direction,BusTraceSpace space,\n                        std::optional<std::uint16_t> logical,std::uint32_t physical,std::uint8_t value) {\n'
    if source.count(head) != 1:
        raise SystemExit('The pinned engine\'s observe_bus_access moved: review the probe\'s hook.')
    hooked = source.replace(head, head + '    rr_pcecd_probe_access(direction == BusTraceDirection::write, physical, value);\n', 1)
    marker = 'namespace pce {'
    hooked = hooked.replace(marker, 'extern "C" void rr_pcecd_probe_access(int write, std::uint32_t physical, std::uint8_t value);\n' + marker, 1)
    (project / 'bus_trace_hooked.cpp').write_text(hooked, encoding='utf-8', newline='\n')
    engine_posix = engine.as_posix()
    lines = [
        'cmake_minimum_required(VERSION 3.20)', 'project(RetroPcecdMameProbe LANGUAGES C CXX)', 'set(CMAKE_C_STANDARD 11)', 'set(CMAKE_CXX_STANDARD 20)',
        'set(CMAKE_CXX_STANDARD_REQUIRED ON)', 'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")',
        'if(MSVC)', '  add_compile_options(/utf-8 /wd4996 /wd4244 /wd4267)', 'endif()',
        'set(PCE_BUILD_TOOLS OFF CACHE BOOL "" FORCE)', 'set(PCE_BUILD_TESTS OFF CACHE BOOL "" FORCE)', 'set(PCE_BUILD_DESKTOP OFF CACHE BOOL "" FORCE)',
        f'add_subdirectory("{engine_posix}" engine EXCLUDE_FROM_ALL)',
        *pce_build.engine_patch_lines(engine_posix, f'{native.as_posix()}/pce_engine'),
        f'set_property(SOURCE "{engine_posix}/runtime/src/bus_trace.cpp" TARGET_DIRECTORY pce-runtime PROPERTY HEADER_FILE_ONLY TRUE)',
        f'target_sources(pce-runtime PRIVATE "{(project / "bus_trace_hooked.cpp").as_posix()}")',
        f'target_include_directories(pce-runtime PRIVATE "{engine_posix}/runtime/src")',
        *pcecd_build.libchdr_cmake_lines(),
        f'pce_add_native_module(PCE_MODULE MODULE "{engine_posix}/runtime/src/no_module.cpp")',
        'get_target_property(PCE_MODULE_SOURCES ${PCE_MODULE} SOURCES)', 'add_library(pce_module OBJECT ${PCE_MODULE_SOURCES})',
        'target_link_libraries(pce_module PUBLIC pce-runtime)', 'set_target_properties(pce_module PROPERTIES CXX_EXTENSIONS OFF)',
        f'add_executable(pcecd_mame_probe "{native.as_posix()}/pcecd_mame_probe.cpp" "{native.as_posix()}/pce_machine.cpp" "{native.as_posix()}/pcecd_disc.cpp" $<TARGET_OBJECTS:pce_module>)',
        f'target_include_directories(pcecd_mame_probe PRIVATE "{native.as_posix()}")', 'target_compile_definitions(pcecd_mame_probe PRIVATE RR_PCE_DISC=1)',
        'target_link_libraries(pcecd_mame_probe PRIVATE pce-runtime chdr-static)',
    ]
    (project / 'CMakeLists.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    cmake, generator = core.toolchain()
    log = project / 'build.log'
    core.run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *core.cmake_target_args()], log=log, timeout=900)
    core.run([cmake, '--build', project / 'build', '--config', 'Release', '--target', 'pcecd_mame_probe', '--parallel', core.build_jobs()], log=log, timeout=3600)
    return build_executable(project / 'build', 'pcecd_mame_probe')


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def run_ours(probe: Path, card: Path, disc: Path, script: list, frames: int, folder: Path, memory: bytes) -> tuple[list[str], bytes]:
    inputs, dumps = folder / 'pads.txt', folder / 'ours-memory'
    shutil.rmtree(dumps, ignore_errors=True)
    dumps.mkdir()
    inputs.write_text(''.join(f'{at} {word:03x}\n' for at, word in script), encoding='ascii', newline='\n')
    bram, seed = folder / 'ours.bram', folder / 'seed.bram'
    seed.write_bytes(memory)
    done = subprocess.run([str(probe), str(card), str(disc), sha256_of(disc), str(inputs), str(frames), '--bram-in', str(seed), '--bram', str(bram), '--dump', str(dumps)], capture_output=True, text=True,
                          timeout=7200, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    (folder / 'ours.log').write_text(done.stdout, encoding='ascii')
    if done.returncode:
        raise SystemExit(f'our probe stopped ({done.returncode}): {done.stdout.strip().splitlines()[-1:]} {done.stderr[-300:]}')
    return done.stdout.splitlines(), bram.read_bytes()


def run_mame(mame: Path, card: Path, disc: Path, script: list, frames: int, folder: Path, memory: bytes) -> tuple[list[str], bytes | None]:
    roms = folder / 'roms' / 'pce' / 'scdsys'
    roms.mkdir(parents=True, exist_ok=True)
    shutil.copy2(card, roms / SYSTEM_CARD_NAME)
    log, dumps = folder / 'mame.log', folder / 'mame-memory'
    shutil.rmtree(dumps, ignore_errors=True)
    dumps.mkdir()
    lua = folder / 'tap.lua'
    lua.write_text(LUA % {'script': ', '.join(f'{{{at}, {word}}}' for at, word in script),
                          'fields': ', '.join(f'[{bit}] = {{"{port}", "{name}"}}' for bit, (port, name) in MAME_FIELDS.items()),
                          'log': log.as_posix(), 'frames': frames, 'dumps': dumps.as_posix()}, encoding='ascii', newline='\n')
    nvram = folder / 'nvram'
    shutil.rmtree(nvram, ignore_errors=True)
    (nvram / 'pce').mkdir(parents=True)
    (nvram / 'pce' / 'pce_cd_bram').write_bytes(memory)        # the same memory as ours starts with
    command = [str(mame), 'pce', 'scdsys', '-cdrom', str(disc), '-rompath', str(folder / 'roms'), '-hashpath', str(mame.parent / 'hash'),
               '-video', 'none', '-sound', 'none', '-nowindow', '-skip_gameinfo', '-nothrottle', '-nvram_directory', str(nvram), '-cfg_directory', str(folder / 'cfg'),
               '-autoboot_script', str(lua), '-autoboot_delay', '0']
    done = subprocess.run(command, capture_output=True, text=True, timeout=7200, cwd=folder, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if done.returncode or not log.is_file():
        raise SystemExit(f'MAME stopped ({done.returncode}): {done.stdout[-600:]} {done.stderr[-600:]}')
    saved = nvram / 'pce' / 'pce_cd_bram'
    return log.read_text(encoding='ascii').splitlines(), saved.read_bytes() if saved.is_file() else None


def events(lines: list[str]) -> dict:
    """The comparable streams of one side: commands (tuple of bytes with the frame of their selection), the interrupt mask values, the unlock writes, the ADPCM port
    writes, the signature reads, the memory hashes at each selection, and the counts of the end line."""
    commands, current, irq, unlock, adpcm, signature, memory, direct = [], None, [], [], [], [], [], []
    adpcm_memory, locked, end_adpcm, played, ports = [], [], None, [], {}
    end = {}
    for line in lines:
        words = line.split()
        if not words:
            continue
        if words[0] == 'W':
            frame, reg, value = int(words[1]), int(words[2], 16), int(words[3], 16)
            if reg == 0:
                if current and current[1]:
                    commands.append(current)
                current = [frame, []]
            elif reg == 1 and current is not None:
                current[1].append(value)
            elif reg == 2:
                masked = value & 0x7F
                if not irq or irq[-1] != masked:
                    irq.append(masked)
            elif reg == 7:
                unlock.append(value & 0x80)
            elif reg in (0x08, 0x09, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F):
                adpcm.append((reg, value))
        elif words[0] == 'S':
            memory.append((words[3], words[4]))
            adpcm_memory.append(words[5])
            locked.append(int(words[6]))
        elif words[0] == 'D':
            if words[2] == '1' and (not played or played[-1] != (int(words[3]), int(words[4]))):
                played.append((int(words[3]), int(words[4])))
        elif words[0] == 'P':
            ports[words[1]] = (int(words[2]), words[3])
        elif words[0] == 'A':
            end_adpcm = words[1:3]
        elif words[0] == 'C':
            direct.append((int(words[1], 16), int(words[2], 16)))
        elif words[0] == 'R':
            signature.append((int(words[2], 16), int(words[3], 16)))
        elif words[0] == 'END':
            end = {'adpcm_bytes': int(words[3]), 'adpcm_hash': words[4], 'lock_reads': int(words[6]), 'selects': int(words[8])}
    if current and current[1]:
        commands.append(current)
    return {'commands': [(frame, command_of(bytes_)) for frame, bytes_ in commands], 'irq': irq, 'unlock': unlock, 'adpcm': adpcm, 'signature': signature,
            'memory': memory, 'end': end, 'direct': direct, 'adpcm_memory': adpcm_memory, 'locked': locked, 'end_adpcm': end_adpcm, 'played': played, 'ports': ports}


def command_of(written: list[int]) -> tuple:
    """The command the drive got: its length from the opcode (6 bytes for the SCSI ones, 10 for NEC's), the trailing bytes written after it dropped."""
    if not written:
        return ()
    length = 10 if written[0] >= 0xD8 else 6
    return tuple(written[:length])


def common(a: list, b: list) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n


def memory_differences(ours: Path, theirs: Path, count: int) -> dict:
    """Over the first `count` selections: the first at which the two memories differ (how many of the 256 KiB, in which banks) and the largest such count."""
    first, sizes = None, []
    for number in range(1, count + 1):
        a, b = ours / f'mem-{number}.bin', theirs / f'mem-{number}.bin'
        if not a.is_file() or not b.is_file():
            break
        x, y = a.read_bytes(), b.read_bytes()
        at = [i for i, (p, q) in enumerate(zip(x, y)) if p != q]
        sizes.append(len(at))
        if at and first is None:
            first = {'selection': number, 'bytes': len(at), 'banks': sorted({f'{0x68 + i // 0x2000:02X}' for i in at}),
                     'first_offsets': [f'{i:05x}' for i in at[:12]], 'ours': x[at[0]:at[0] + 8].hex(), 'mame': y[at[0]:at[0] + 8].hex()}
    return {'first': first, 'largest_count_of_differing_bytes': max(sizes, default=0), 'selections_dumped': len(sizes)}


def compare(ours: dict, theirs: dict, bram_ours: bytes, bram_theirs: bytes | None) -> dict:
    cmd_a = [c for _, c in ours['commands']]
    cmd_b = [c for _, c in theirs['commands']]
    same_cmd = common(cmd_a, cmd_b)
    memory = list(zip(ours['memory'], theirs['memory']))[:same_cmd + 1]
    equal_memory = sum(1 for a, b in memory if a == b)
    first_diff_memory = next((n for n, (a, b) in enumerate(memory) if a != b), None)
    adpcm = common(ours['adpcm'], theirs['adpcm'])
    irq = common(ours['irq'], theirs['irq'])
    unlock = common(ours['unlock'], theirs['unlock'])
    audio_a = [c for c in cmd_a[:same_cmd] if c and c[0] in (0xD8, 0xD9)]
    return {
        'commands': {'ours': len(cmd_a), 'mame': len(cmd_b), 'equal_from_the_start': same_cmd,
                     'first_difference': None if same_cmd >= min(len(cmd_a), len(cmd_b)) else [hexs(cmd_a[same_cmd]), hexs(cmd_b[same_cmd])],
                     'opcodes': opcode_counts(cmd_a[:same_cmd]), 'last_equal_frame': ours['commands'][same_cmd - 1][0] if same_cmd else 0},
        'irq_mask': {'ours': len(ours['irq']), 'mame': len(theirs['irq']), 'equal_from_the_start': irq,
                     'first_difference': None if irq >= min(len(ours['irq']), len(theirs['irq'])) else [ours['irq'][irq], theirs['irq'][irq]]},
        'cd_audio': {'play_commands_in_the_common_part': [hexs(c) for c in audio_a][:8], 'count': len(audio_a),
                     'playing_ranges_ours': ours['played'][:8], 'playing_ranges_mame': theirs['played'][:8],
                     'equal_ranges_from_the_start': common(ours['played'], theirs['played'])},
        'adpcm_ports': {'ours': len(ours['adpcm']), 'mame': len(theirs['adpcm']), 'equal_from_the_start': adpcm,
                        'first_difference': None if adpcm >= min(len(ours['adpcm']), len(theirs['adpcm'])) else [list(ours['adpcm'][adpcm]), list(theirs['adpcm'][adpcm])]},
        'adpcm_data': {'ours': ours['end'].get('adpcm_bytes'), 'mame': theirs['end'].get('adpcm_bytes'),
                       'same_hash': ours['end'].get('adpcm_hash') == theirs['end'].get('adpcm_hash')},
        'memory_at_selections': {'compared': len(memory), 'equal_cd_ram_and_super_ram': equal_memory, 'first_difference_at': first_diff_memory},
        'data_port_reads': {port: {'ours': ours['ports'].get(port, (0, ''))[0], 'mame': theirs['ports'].get(port, (0, ''))[0],
                                   'same_hash': ours['ports'].get(port) == theirs['ports'].get(port)} for port in ('1', '8')},
        'signature_reads': {'ours': sorted(set(ours['signature'])), 'mame': sorted(set(theirs['signature'])), 'mame_read_directly': theirs['direct']},
        'adpcm_ram_at_selections': {'compared': len(memory), 'equal': sum(1 for a, b in list(zip(ours['adpcm_memory'], theirs['adpcm_memory']))[:len(memory)] if a == b),
                                    'distinct_values': len(set(ours['adpcm_memory'][:len(memory)])), 'at_the_end': None if not (ours['end_adpcm'] and theirs['end_adpcm']) else ours['end_adpcm'][0] == theirs['end_adpcm'][0]},
        'backup_locked_at_selections': {'equal': sum(1 for a, b in list(zip(ours['locked'], theirs['locked']))[:len(memory)] if a == b), 'compared': len(memory),
                                        'ours_states': sorted(set(ours['locked'])), 'mame_states': sorted(set(theirs['locked']))},
        'unlock_writes': {'ours': len(ours['unlock']), 'mame': len(theirs['unlock']), 'equal_from_the_start': unlock},
        'lock_reads': {'ours': ours['end'].get('lock_reads'), 'mame': theirs['end'].get('lock_reads')},
        'backup_memory': {'ours_non_blank': sum(1 for b in bram_ours if b), 'mame': None if bram_theirs is None else sum(1 for b in bram_theirs[:2048] if b),
                          'equal': None if bram_theirs is None else bram_ours[:2048] == bram_theirs[:2048]},
    }


def hexs(command) -> str:
    return ' '.join(f'{b:02X}' for b in command)


def opcode_counts(commands: list) -> dict:
    out: dict = {}
    for c in commands:
        if c:
            out[f'{c[0]:02X}'] = out.get(f'{c[0]:02X}', 0) + 1
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('card', type=Path)
    parser.add_argument('discs', type=Path, nargs='+')
    parser.add_argument('--mame', type=Path, default=os.environ.get('RETRO_RECOMP_MAME'), required=not os.environ.get('RETRO_RECOMP_MAME'))
    parser.add_argument('--frames', type=int, default=3600)
    parser.add_argument('--work', type=Path, default=WORK)
    arguments = parser.parse_args()
    card = arguments.card.resolve()
    if hashlib.sha1(card.read_bytes()).hexdigest() != SYSTEM_CARD_SHA1:
        raise SystemExit('The card must be the Japanese Super System Card 3.0 (MAME\'s software scdsys).')
    probe = build_probe(arguments.work.resolve() / 'probe')
    script = pad_script(arguments.frames)
    from retrorecomp.pce_conversion import BACKUP_FORMATTED
    results = {}
    for disc in arguments.discs:
        folder = arguments.work.resolve() / disc.stem.split(' (')[0].replace(' ', '_')
        folder.mkdir(parents=True, exist_ok=True)
        ours_lines, bram_ours = run_ours(probe, card, disc.resolve(), script, arguments.frames, folder, BACKUP_FORMATTED)
        mame_lines, bram_theirs = run_mame(arguments.mame.resolve(), card, disc.resolve(), script, arguments.frames, folder, BACKUP_FORMATTED)
        report = compare(events(ours_lines), events(mame_lines), bram_ours, bram_theirs)
        report['memory_bytes'] = memory_differences(folder / 'ours-memory', folder / 'mame-memory', report['commands']['equal_from_the_start'])
        results[disc.name] = report
        (folder / 'report.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
        print(f'== {disc.name}')
        for key, value in report.items():
            print(f'  {key}: {value}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
