# MSX

Experimental profile (`msx`), in development: it is not in a release yet. It converts an MSX1 cartridge into a standalone Windows
executable whose Z80 code, as far as the conversion saw it run, is translated ahead of time to C, with a counted interpreter for the rest.
The cartridge boots on C-BIOS 0.29a or on the player's own MSX BIOS. Nothing here says that a game plays completely, that the hardware is
reproduced faithfully or how long input takes to reach the screen: those are separate measures, listed below with what is known of each, and
for the MSX most of them are not known yet.

## 1. What is converted, and what is not

| Converted (experimental) | Not yet |
| --- | --- |
| MSX1 cartridges, read from a `.rom`, a `.mx1` or a ZIP holding one (a `.rom` or `.bin` is the MSX's when its bytes hold an MSX cartridge header; a `.mx1` always is) | MSX2 (the V9938 video chip), MSX2+, the turbo R |
| Plain cartridges of 8 KiB to 64 KiB, and the Konami, Konami SCC, ASCII 8 KiB and ASCII 16 KiB mappers | The other mappers (the rare ones), FM-PAC, cartridge SRAM and the saves that depend on it |
| C-BIOS 0.29a (BSD-2-Clause), fetched by the converter from its official release on first use and pinned by SHA-256; or the player's own MSX1 BIOS (a 32 KiB main ROM; an MSX2 or later BIOS is refused), chosen in Options > MSX | Disks, cassettes, MSX-BASIC under C-BIOS |
| The keyboard, joysticks 1 and 2 (the keyboard's arrows and keys or a gamepad, and a second gamepad), the TMS9918A picture and sprites, the AY-3-8910 sound, the key click and the Konami SCC sound | Quick states (F8/F9) |
| Windows | Linux (the profile says `pending`: no witness) |

C-BIOS runs cartridges only: it has no MSX-BASIC, so a BASIC cartridge is refused under C-BIOS, and it has no disk and no cassette. A game that needs
those, or a BASIC cartridge, needs the player's own MSX BIOS. The input is read in place and never changed. The player supplies the cartridge (and
their BIOS if they want one); Retro-Recomp publishes no game and no firmware, and an MSX BIOS is never shipped. A game converted with your own BIOS holds
that BIOS and code translated from it, as on the other machines that take your own firmware: keep it for yourself.

## 2. How the conversion works

1. **Reading the input.** `retrorecomp/msx_rom.py` reads the cartridge (or the ZIP holding one) and takes its SHA-256 as the identity of the game. It
   guesses the mapper from the cartridge's own bytes. `retrorecomp/msx_cbios.py` fetches C-BIOS 0.29a from its official release on first use and checks
   its SHA-256 against the pin. A BIOS of your own (a 32 KiB main ROM) is checked by its content and its SHA-256 is the identity of the firmware, in the
   request, instead of the pin of C-BIOS.
2. **Native code.** The cartridge and the BIOS are translated ahead of time to C by the shared banked Z80 chain, the one the Master System and the Game
   Gear use (`retrorecomp/z80_chain.py`), on the MSX's own description: a region map of eight 8 KiB regions with the cartridge and the BIOS as sources,
   one wait state per M1 cycle, and /INT read at the end of each instruction. Code run from RAM is learned and translated with byte guards. What the
   translation does not cover runs on a reference Z80 interpreter and is counted.
3. **The machine.** The TMS9918A video, the AY-3-8910 sound, the Konami SCC sound, the PPI (keyboard and slot select), the slots and the mappers are
   Retro-Recomp's own C (`native/msx_machine/`, MIT). No emulator core is inside the executable: this is not a machine that runs on an emulator core.
4. **Comparison.** Native code is compared with the reference Z80 interpreter on the same machine, on a route that boots, waits and presses SPACE and the trigger: 37 state fields at its last frame and a running hash of every frame's picture. A conversion whose native run differs is refused. An external emulator (openMSX) is used
   privately for comparisons during development and is never shipped.

## 3. The five measures

Kept separate here, as everywhere. Interpreter fallback is always counted, per CPU (the Z80) and reported by the conversion.

| Measure | What is known | What is not |
| --- | --- | --- |
| Native code | In development checks, authored test cartridges and three plain games (Road Fighter, Knightmare, Antarctic Adventure) end at 0 interpreted instructions after one learning pass | No panel and no release-level run; nothing is said of the mapper cartridges or of the games not named here |
| CPU fidelity | On the same games and cartridges the native code is equal to the reference Z80 interpreter on 37 state fields after 300 to 1,200 frames. This is agreement with our own reference interpreter, not with a real MSX | No independent comparison on a real machine or a second emulator is claimed; no CPU vector set is run for the MSX yet |
| Hardware fidelity | Nothing is claimed. The mixing levels of the sound (PSG, key click, SCC) are a stated choice, not validated | The TMS9918A, the AY-3-8910 and the SCC against an independent reference |
| Gameplay validation | None: no game has been played through by the owner | Everything |
| Physical latency | Not measured | No latency figure; none is claimed |

These were development checks and are not a qualification (see section 7). They say nothing for other games, other mappers or the player's own BIOS.

## 4. Controls

The keys of a converted game, also in [CONTROLS.md](CONTROLS.md#msx-experimental):

| Key | MSX |
| --- | --- |
| Arrow keys | Joystick 1; they also press the MSX cursor keys |
| X | Trigger A (it also presses SPACE) |
| W | Trigger B |
| Start (Enter, pad Start) | The MSX SPACE key |
| Select (right Shift, pad Back) | The MSX F1 key |
| Ctrl+Alt+K | Hands the whole keyboard to the MSX; F1 to F5 then go to the MSX, and the help is at Ctrl+F1 |

The quick states (F8/F9) are not available on the MSX yet. The F2 pages, autofire and the speed and sound controls are the common ones of the host kit.

## 5. Known C-BIOS failures

C-BIOS is a free BIOS, not Microsoft's, and a few games depend on what only the original has.

- **Salamander (Japan).** Its stage stays black under C-BIOS 0.29a: the score and the lives change, nothing is drawn. The same happens on openMSX 22.0
  with the same C-BIOS, so it is C-BIOS's behaviour with this game and not the conversion's. With the player's own MSX BIOS the game plays. Answer: choose
  your own MSX BIOS in Options > MSX.
- **BASIC cartridges** are refused under C-BIOS, which has no MSX-BASIC.

Other known limits: the SRAM, FM-PAC, disk, cassette and MSX2 cartridges are not converted, and no game other than the ones named in section 3 has been checked.

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
