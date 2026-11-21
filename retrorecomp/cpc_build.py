"""The Amstrad CPC on the banked Z80 chain: the generated bodies of the player's firmware, the staging of the machine's files
beside them (docs/AMSTRAD_CPC.md). MIT, Retro-Recomp.

* The generator is the shared banked Z80 generator built for the CPC's own machine description (systems/amstrad_cpc.py,
  `CPC_MACHINE`: a region map of four 16 KiB regions, the system ROM as source 0 and AMSDOS as source 1, the CPC's costs in
  whole microseconds), in its own folders (`z80_chain_build.generator`).
* Source 0 is the player's 32 KiB system ROM as it is: bank 0 the OS (shown at 0000h), bank 1 BASIC (shown at C000h); the
  machine takes its two halves. Source 1 is AMSDOS (the upper ROM 7). A CPC game runs from RAM, loaded from its disk: what the
  interpreter runs there is learned (`--learn`) and translated with byte guards on the next generation, as the MSX does.
* The reference copy of the interpreter counts the CPC's costs (`z80_chain_build.generate_bodies` passes `Z80Machine.costs`).

Game role, the cpc group of retrorecomp/stamp_inputs.py. It imports nothing of the converter at load time.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import z80_chain_build

GAME_TOML = '''# Amstrad CPC: the system ROM is source 0 of the region map; AMSDOS is named in banked.sources.
[game]
output_prefix = "game"
platform = "sms"
rom = "rom.sms"
crc32 = 0x00000000
[mapper]
kind = "sega"
[functions]
extra = []
blacklist = []
'''
# The machine's C sources, compiled into every program, and the files they include; the uPD765 and the DSK reader, from
# native/upd765 (machine-neutral), staged with them.
MACHINE_SOURCES = ('cpc_machine.c', 'cpc_crtc.c', 'cpc_gate_array.c', 'cpc_ppi.c')
MACHINE_FILES = (*MACHINE_SOURCES, 'cpc_machine.h', 'cpc_bus.h', 'cpc_crtc.h', 'cpc_gate_array.h', 'cpc_ppi.h', 'cpc_glue.inc')
DISK_SOURCES = ('upd765.c', 'dsk_image.c')
DISK_FILES = (*DISK_SOURCES, 'upd765.h', 'dsk_image.h')
CHAIN_FILES = ('z80_chain_glue.inc',)
LOOP = 'cpc_banked_loop.inc'
ACCEPT = 'cpc_reference_accept'


class CpcBuildError(RuntimeError):
    """The generator, the build or a run failed."""


def sources(system: bytes, amsdos: bytes) -> tuple[bytes, tuple[tuple[str, bytes], ...]]:
    """(source 0, the other sources) as the generator reads them: the 32 KiB system ROM, then AMSDOS. Their sizes are checked
    (retrorecomp/cpc_firmware.py has already checked their digests)."""
    from .cpc_firmware import AMSDOS_BYTES, SYSTEM_BYTES
    if len(system) != SYSTEM_BYTES or len(amsdos) != AMSDOS_BYTES:
        raise CpcBuildError('The CPC firmware is a 32 KiB system ROM and a 16 KiB AMSDOS ROM.')
    from .systems.amstrad_cpc import CPC_MACHINE
    return CPC_MACHINE.regions.image(system), (('amsdos.rom', CPC_MACHINE.regions.image(amsdos)),)


def generate(work: Path, system: bytes, amsdos: bytes, emit: Callable[[str], None] = print, *, keep_rom: bool = True) -> None:
    """The bodies of the firmware in `work/generated`, with the learned patterns; the reference copy and the loop beside them."""
    from .systems.amstrad_cpc import CPC_MACHINE
    first, others = sources(system, amsdos)
    z80_chain_build.generate_bodies(work, CPC_MACHINE, first, others, GAME_TOML, emit, loop_name=LOOP, accept=ACCEPT,
                                    keep_rom=keep_rom, error=CpcBuildError)


def stage_sources(work: Path) -> None:
    """The machine's files, the disk controller's and the chain's glue, beside the generated bodies."""
    from .paths import ASSETS
    native = ASSETS / 'native'
    z80_chain_build.stage_files(work, ((native / 'cpc_machine', MACHINE_FILES), (native / 'upd765', DISK_FILES),
                                       (native, CHAIN_FILES)))
