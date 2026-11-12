# MSX

Experimental profiles (`msx`, and `msx2` for the MSX2, described in section 8), in development: they are not in a release yet. The `msx` profile converts an MSX1 cartridge into a standalone Windows
executable whose Z80 code, as far as the conversion saw it run, is translated ahead of time to C, with a counted interpreter for the rest.
The cartridge boots on C-BIOS 0.29a or on the player's own MSX BIOS. Nothing here says that a game plays completely, that the hardware is
reproduced faithfully or how long input takes to reach the screen: those are separate measures, listed below with what is known of each, and
for the MSX most of them are not known yet.

## 1. What is converted, and what is not

| Converted (experimental) | Not yet |
| --- | --- |
| MSX1 cartridges, read from a `.rom`, a `.mx1` or a ZIP holding one (a `.rom` or `.bin` is the MSX's when its bytes hold an MSX cartridge header; a `.mx1` always is) | MSX2+ and the turbo R (the MSX2 is the `msx2` profile, section 8) |
| Plain cartridges of 8 KiB to 64 KiB, and the Konami, Konami SCC, ASCII 8 KiB and ASCII 16 KiB mappers | The other mappers (the rare ones), FM-PAC, cartridge SRAM and the saves that depend on it |
| C-BIOS 0.29a (BSD-2-Clause), fetched by the converter from its official release on first use and pinned by SHA-256; or the player's own MSX1 BIOS (a 32 KiB main ROM; an MSX2 or later BIOS is refused), chosen in Options > MSX | Disks, cassettes, MSX-BASIC under C-BIOS |
| The keyboard, joysticks 1 and 2 (the keyboard's arrows and keys or a gamepad, and a second gamepad), the TMS9918A picture and sprites, the AY-3-8910 sound, the key click and the Konami SCC sound; quick states (F8/F9) | The FM-PAC's sound |
| Windows | Linux (the profile says `pending`: no witness) |

C-BIOS runs cartridges only: it has no MSX-BASIC, so a BASIC cartridge is refused under C-BIOS, and it has no disk and no cassette. A game that needs
those, or a BASIC cartridge, needs the player's own MSX BIOS. The input is read in place and never changed. The player supplies the cartridge (and
their BIOS if they want one); Retro-Recomp publishes no game and no firmware, and an MSX BIOS is never shipped. A game converted with your own BIOS holds
that BIOS and code translated from it, as on the other machines that take your own firmware: keep it for yourself.

## 2. How the conversion works

1. **Reading the input.** `retrorecomp/msx_rom.py` reads the cartridge (or the ZIP holding one) and takes its SHA-256 as the identity of the game. It
   guesses the mapper from the cartridge's own bytes; for an MSX2 mapper cartridge, when that guess is not enough, short probe runs of the reference under each mapper settle it (the share of the program's cartridge writes that land on that mapper's registers, among runs that do not fall into empty memory; Aleste was guessed Konami SCC and is ASCII 16). `retrorecomp/msx_cbios.py` fetches C-BIOS 0.29a from its official release on first use and checks
   its SHA-256 against the pin. A BIOS of your own (a 32 KiB main ROM) is checked by its content and its SHA-256 is the identity of the firmware, in the
   request, instead of the pin of C-BIOS.
2. **Native code.** The cartridge and the BIOS are translated ahead of time to C by the shared banked Z80 chain, the one the Master System and the Game
   Gear use (`retrorecomp/z80_chain.py`), on the MSX's own description: a region map of eight 8 KiB regions with the cartridge and the BIOS as sources,
   one wait state per M1 cycle, and /INT read at the end of each instruction. Code run from RAM is learned and translated with byte guards. What the
   translation does not cover runs on a reference Z80 interpreter and is counted.
3. **The machine.** The TMS9918A video, the AY-3-8910 sound, the Konami SCC sound, the PPI (keyboard and slot select), the slots and the mappers are
   Retro-Recomp's own C (`native/msx_machine/`, MIT). No emulator core is inside the executable: this is not a machine that runs on an emulator core.
4. **Routes.** A conversion plays the routes of its scan level, as the PC Engine does: `attract` (no input), `play` and, at the extended and thorough
   levels, one or two long routes of 18,000 frames. A route presses what a player's default mapping presses (a direction on joystick 1 and the cursor
   key together, fire on trigger A and SPACE together, RETURN, 1 and 2). How `play` starts is chosen on the reference interpreter for each
   cartridge: fire pressed 1, 2, 3, 4 or 6 times, or 1 to 3 times each followed by RETURN; the variant kept stays alive to its end and reaches the most
   pictures of its own, then a walk seeded by the cartridge. The report records the choice and every variant's numbers.
5. **Comparison.** Native code is compared with the reference Z80 interpreter on the same machine, on every route: the state fields at its last frame
   and one row per frame (CPU, RAM, picture, sound). A conversion whose native run differs is refused. The delivered (compressed) game is then replayed
   on every route and must give the same rows. An external emulator (openMSX) is used privately for comparisons during development and is never
   shipped.

## 3. The five measures

Kept separate here, as everywhere. Interpreter fallback is always counted, per CPU (the Z80) and reported by the conversion.

| Measure | What is known | What is not |
| --- | --- | --- |
| Native code | On the Windows panel of 12 November 2026 (extended level: attract, play and an 18,000-frame route), six MSX1 cartridges (Road Fighter, Knightmare, Space Invaders, Nemesis, Salamander, Spy vs Spy II; plain, Konami, Konami SCC, NTSC and PAL) end at 0 interpreted instructions on every route, Salamander also with an MSX BIOS of its owner | No release-level run, no Linux witness; nothing is said of the games not named here |
| CPU fidelity | On the same games the native code is equal to the reference Z80 interpreter on every route, on the state fields at its end and on one row per frame (CPU, RAM, picture, sound); the delivered (compressed) game gives the same rows. This is agreement with our own reference interpreter, not with a real MSX | No independent comparison on a real machine or a second emulator is claimed; no CPU vector set is run for the MSX yet |
| Hardware fidelity | Nothing is claimed. The mixing levels of the sound (PSG, key click, SCC) are a stated choice, not validated | The TMS9918A, the AY-3-8910 and the SCC against an independent reference |
| Gameplay validation | None: no game has been played through by the owner | Everything |
| Physical latency | Not measured | No latency figure; none is claimed |

These were development checks and are not a qualification (see section 7). They say nothing for other games, other mappers or the player's own BIOS.

## 4. Controls

The keys of a converted game, also in [CONTROLS.md](CONTROLS.md#msx-and-msx2-experimental):

| Key | MSX |
| --- | --- |
| Arrow keys | Joystick 1; they also press the MSX cursor keys |
| X | Trigger A (it also presses SPACE) |
| W | Trigger B |
| Start (Enter, pad Start) | The MSX SPACE key |
| Select (right Shift, pad Back) | The MSX F1 key |
| Ctrl+Alt+K | Hands the whole keyboard to the MSX; F1 to F5 then go to the MSX, and the help is at Ctrl+F1 |

F8 saves a quick state and F9 loads it, at the end of a frame, in the game's folder beside its settings (`datas/games/msx-<identity>`, or `msx2-<identity>`
on the MSX2). A state is refused, and the game goes on untouched, when anything differs: the cartridge, the BIOS, the options or the build. Each conversion
checks it on the delivered file: a state saved near the end of the route is loaded by a fresh process, which must continue the same frames for 600 frames,
and damaged or missing states must be refused and left as they were. The F2 pages, autofire and the speed and sound controls are the common ones of the host kit.

## 5. Known C-BIOS failures

C-BIOS is a free BIOS, not Microsoft's, and a few games depend on what only the original has.

- **Salamander (Japan).** Its stage stays black under C-BIOS 0.29a: the score and the lives change, nothing is drawn. The same happens on openMSX 22.0
  with the same C-BIOS, so it is C-BIOS's behaviour with this game and not the conversion's. With the player's own MSX BIOS the game plays. Answer: choose
  your own MSX BIOS in Options > MSX.
- **BASIC cartridges** are refused under C-BIOS, which has no MSX-BASIC.

Other known limits: the SRAM, FM-PAC, disk and cassette are not converted (MSX2 cartridges are the `msx2` profile, section 8), and no game other than the ones named in section 3 has been checked.

## 6. Licences

Original code, the machine, the translator glue and the checks are MIT, like the rest of Retro-Recomp. C-BIOS is BSD-2-Clause and is downloaded by the
converter from its official release, not kept in this repository. The player's own MSX BIOS is never shipped. openMSX is used privately for comparisons only
and nothing of it is in an executable or in this repository. The Z80 translator and the reference Z80 interpreter are the ones of the Master System and the Game Gear, under
their own licences, listed in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) (z80-recomp-core, superzazu/z80).

## 7. Where it stands in the qualification

G1 is partial: the profile is declared experimental and `tools/status_lint.py`, the README, [COMPATIBILITY.md](COMPATIBILITY.md) and the interface
strings agree. Every other gate of [QUALIFICATION.md](QUALIFICATION.md) is unknown (`?`), and G16 is not applicable (`-`): the MSX shares no paths. The
development checks of section 3 are listed in its caveats and are not a qualification. Leaving the experimental status is the owner's own decision (G14),
and nothing here asks for it.

## 8. The MSX2 (`msx2`)

Experimental profile `msx2`, the second profile of the MSX family, beside `msx` as the Game Gear is beside the Master System. It shares the Z80 chain, the
keyboard, the sound and the cartridge mappers of the MSX1 and adds the V9938, a memory mapper and a clock. It is in development, not in a release yet, and
**the V9938 command engine exists since stage 7, with its timing approximated**.

**Converted:** MSX2 cartridges (plain, Konami, Konami SCC, ASCII 8 KiB and ASCII 16 KiB mappers), from a `.mx2` (always MSX2), or from a `.rom` or ZIP that you
choose as MSX2 in the console list or that sits in a folder named `msx2`. The machine: the V9938 drawn line by line (all screen modes, sprite mode 2, the
palette, scrolling, the line interrupt, the display pages; VRAM is held as the chip holds it, in two banks, so Graphic 6 and 7 reach their logical addresses interleaved), the V9938 command engine (all twelve commands, HMMC, YMMM, HMMM, HMMV, LMMC, LMCM, LMMM, LMMV, LINE, SRCH, PSET and POINT, and STOP, with the logical operations, in the bitmap modes G4 to G7 only; V9938 commands: all twelve, timing approximated), the memory mapper (128, 256 or 512 KiB of RAM, chosen in Options > MSX2, default 256) and the
RP5C01 clock, frozen at 2000-01-01 12:00:00 and then running on machine time (not your PC's clock). The picture is 544 x 228 (see [CONTROLS.md](CONTROLS.md#msx-and-msx2-experimental)).

**Firmware:** C-BIOS 0.29a MSX2 images (main ROM, logo and sub-ROM), fetched and pinned like the MSX1's, or your own MSX2 BIOS pair: the main ROM
(`msx2_bios`) and its 16 KiB sub-ROM (`msx2_subrom`, the file beginning "CD"), chosen in Options > MSX2 and never shipped. The same rules as for the MSX1:
the input is never changed, and a game converted with your own BIOS holds it and code translated from it.

**Timing approximated** means an average cost per byte or dot in three classes (display off or outside the picture; picture with sprites off; with sprites on) plus a line-end cost; the chip's access slots and the slots the CPU takes are not modelled. C-BIOS's MSX2 logo, drawn by an HMMC, now appears.

**Not yet:** disks,
cassettes, FM-PAC, MSX2+, the turbo R, a Linux witness.

**Not modelled in the V9938:** the access-slot timing of port 98h and of the command engine, the F and FH status flags' lost windows, the change of frame length when R#9's LN bit
switches, mid-line effects, the field offset of interlace, superimpose and digitise, and expansion RAM, and a flags-only sprite pass after the picture. The audio of an MSX2 game under heavy load is an open point, to check on a quiet PC. Where hardware reports disagree on sprite mode 2's rules,
the profile follows openMSX's reading; that is a choice, not a proof.

**The five measures for the MSX2**, kept separate:

| Measure | What is known | What is not |
| --- | --- | --- |
| Native code | On 14 authored cases, on both boards, 0 interpreted instructions after learning; on the Windows panel of 12 November 2026 (extended level) Metal Gear, Space Manbow, Aleste and Hydlide 3 end at 0 interpreted instructions on every route, equal to our reference interpreter frame by frame | No release-level run, no Linux witness; Hydlide 3's routes stay in its character set-up menu, so its play is not covered |
| CPU fidelity | On the same 14 cases the native code equals the reference Z80 interpreter on 39 compared fields (the 37 of the MSX1 plus the V9938 state and the mapper). This is agreement with our own reference, not with a real MSX2 | No independent comparison on a real machine |
| Hardware fidelity | Nothing is claimed as exact. 682 hand-worked checks of the V9938, the engine and the MSX2 board pass (development checks, not a qualification): they check our model against our own reading of the documents. Against openMSX (a private comparison emulator, never shipped) the 128 KiB VRAM, the 47 VDP registers and the palette are equal at chosen still frames for the C-BIOS logo, two authored cartridges, Metal Gear, Space Manbow, Aleste and Hydlide 3; at other frames the differences are timing (a command still running, a palette fade step, a sprite double-buffer phase) | Other frames; command timing; the RP5C01; everything in the list above |
| Gameplay validation | None: no game has been played through | Everything |
| Physical latency | Not measured | No latency figure; none is claimed |

Section 3's remarks apply here too: these are development checks, not a qualification. The `msx2` column of [QUALIFICATION.md](QUALIFICATION.md) has G1 partial,
G16 not applicable and every other gate unknown.
