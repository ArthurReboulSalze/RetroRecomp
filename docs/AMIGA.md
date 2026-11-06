# Commodore Amiga

Experimental profile (`amiga`), opened in 1.7.0: the converter offers it when the installation carries the Amiga files, and
it is not shared through the compilation library yet. It converts an Amiga 500 game installed for WHDLoad into a standalone Windows
executable, with guarded native code for the 68000 code the game runs from RAM and a counted interpreter for everything else.
Nothing here says that a game plays completely, that the hardware is reproduced faithfully or how long input takes to reach the
screen: those are separate measures, listed below with what is known of each.

## 1. What is converted, and what is not

| Converted (experimental) | Not yet |
| --- | --- |
| Amiga 500 (68000, OCS/ECS) games installed for WHDLoad: one `.lha` archive holding exactly one `.Slave` and the game's files or `Disk.N` images | Installs that need a Kickstart (the slave asks for KickEmu): nearly half of the 2,992 Amiga 500 installs of the maintainer's library, which stay refused until the player's own Kickstart is supported |
| The joystick (port 2, two buttons), the mouse (port 1, captured on a click) and the keyboard; quick states (F8/F9) and the files an install saves | ADF disk images, IPF, hard-disk images, Amiga 1200 (68020, AGA), CD32, CDTV |
| Windows | Linux (`linux = 'pending'`) |
| | A library of qualified paths: the profile is not in the sharing |

A `.lha` that holds no slave, or more than one, is refused with a sentence, never guessed. The archive is read in place and never
changed; the converter needs no Kickstart, and none is supplied, stored or fetched. The player supplies the install; Retro-Recomp
publishes no game, no disk and no firmware.

## 2. How the conversion works

1. **Reading the install.** `retrorecomp/amiga_lha.py` lists and extracts the members of the archive (LHA levels 0 to 2, methods
   `-lh0-` and `-lh5-` to `-lh7-`, CRC-16 checked); `retrorecomp/amiga_whdload.py` reads the slave's AmigaDOS hunk file and its
   `ws_` header (memory sizes, flags, the Kickstart it asks for) and lays out the install: the slave, its data folder, the disk
   images. The identity of a game is the SHA-256 of the archive.
2. **No WHDLoad, no Kickstart.** WHDLoad is closed source with all rights reserved; it is neither run nor copied. The slave is a
   68000 program that calls a table of `resload_*` services, so `native/amiga_whdload/` answers those calls itself (our own MIT
   code, written from the public autodoc; every call is counted and a service it does not provide is refused with its number,
   never answered with a pretended success). The machine boots through an authored boot ROM that enters the slave in supervisor
   mode; no code runs from Commodore's firmware.
3. **The machine.** The games run on the Amiga machine of [vAmiga](https://github.com/dirkwhoffmann/vAmiga) (Agnus, Denise, Paula,
   the CIAs, the floppy drive), pinned at one revision and adapted at build time by `retrorecomp/amiga_vamiga.py`, which drives it
   frame by frame inside the game. Its 68000 core, Moira, is the reference CPU of the Amiga profile.
4. **Native code.** A conversion first runs the install on the interpreted machine and records the 68000 instructions seen
   executing from RAM. Each one becomes a native step, grouped by form, that calls the very instruction template Moira dispatches
   the opcode to, so the bus accesses and their cycles (chip-RAM contention included) stay Moira's. Every step starts with a live
   comparison of the instruction's words in RAM: a word that changed (unpacked, patched or self-modified code) sends execution
   back to the counted interpreter. The generator is the one the X68000 uses (`retrorecomp/m68k_observed.py`); the Amiga declares
   its own bodies (`retrorecomp/amiga_codegen.py`).
5. **Validation.** The game executable is copied alone and replayed headless on the same bounded scripts (a main route of joystick,
   mouse and keyboard inputs, and at the Standard level a joystick exploration route, 3,000 frames each): the picture, sound, RAM
   and CPU registers of every frame and the resload calls must equal those of the fresh interpreted reference. So must the
   compressed copy that is delivered. A quick state saved by it is loaded by a fresh process, which must continue the same
   timeline (CPU, RAM and picture; the sound samples after a load are not compared, because vAmiga does not save the state of its
   audio resampler and filters). A conversion that fails any of these keeps the earlier export.
6. **Report.** The conversion report (schema v2, shape `amiga_conversion`) carries the interpreter fallback per CPU and keeps the
   five measures in separate objects.

## 3. The five measures

| Measure | What is known today |
| --- | --- |
| Native code | One game converted: Rick Dangerous (5 November 2026, Standard level): 30,050,479 native instructions and 0 interpreted on the main route, 30,114,205 and 0 on the exploration route (3,000 frames each). Other installs not yet converted. |
| CPU fidelity | The steps call Moira's own templates. Moira (MIT) was compared with the SingleStepTests 68000 vectors; its deviations from them are recorded in 15 families (private engine-gate notes). On Rick Dangerous the trace of every frame (picture, sound, RAM, CPU registers) and the resload log of the native game are identical to the interpreted reference machine's, on both routes. |
| Hardware fidelity | Not claimed. As a development check, the same installs were run privately in an independent emulator with the real WHDLoad and its pictures compared with ours on 59 reference frames each: Lotus 2 matched 59/59, Lemmings 58/59, Speedball 2 54/59, Elite 51/59, Turrican 2 49/59. Pinball Dreams (NTSC) first scored 19/59; looked for at any offset at the Amiga's 4-bit colour depth, all 59 of its pictures are in the other emulator's stream (the two tools crop some display windows differently). These are counts of equal pictures on a few frames, not a fidelity claim. |
| Gameplay validation | None. No game has been played through. |
| Physical latency | Not measured. |

## 4. Known limits

- Kickstart installs, ADF, Amiga 1200, CD32 and CDTV are out of scope; Linux is pending.
- The first conversion needs the pinned vAmiga sources (fetched into the workspace) and the C++ toolchain of the converter.
- The slave is entered in the CPU state WHDLoad 20.1 gives it (supervisor, interrupt mask 0, marked registers), read once in a
  private run of the real WHDLoad; installs that depend on other WHDLoad behaviour stop with the reason in the report.
- After a quick state is loaded, the sound samples are not bit-identical to an unbroken run (see Validation above).
- The profile is hidden unless the installation carries the Amiga files (`retrorecomp/amiga.py`, `developer_available`).

## 5. Licences

- Retro-Recomp's Amiga files (the converter modules, `native/amiga_whdload/`, `native/amiga_machine/`, the host-kit adapter) are MIT.
- vAmiga's `Core/` is **MPL-2.0** per file; our changes to those files, applied at build time, are MPL-2.0 too. Moira, the CPU
  inside it, is **MIT**. The vAmiga application (GPL-3.0 or later) is not used. Notice: [licenses/vamiga.md](../licenses/vamiga.md).
- Each exported game carries its notices as resource 203, like the other machines: Retro-Recomp's licence, vAmiga and Moira, the
  68000 decoder of m68k-recomp-core (compiled into the index of native steps), SDL and the host kit's parts
  (`amiga_conversion.NOTICE_FILES`).
- WHDLoad is freeware with all rights reserved and is not distributed or run. The JST resload emulation (MIT) was read as a
  reference only; none of its decrunchers is copied.
- Upstream pins and review: [UPSTREAMS.md](UPSTREAMS.md).

## 6. Where it stands in the qualification

The Amiga column of [QUALIFICATION.md](QUALIFICATION.md) is mostly `?`: only the rows above are measured. Leaving the
experimental status is the maintainer's own decision, after a very high evidence bar.
