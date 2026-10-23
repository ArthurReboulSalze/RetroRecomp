# Capcom CPS-1

Experimental profile (`cps1`) for the standard CPS-1 arcade boards (10 and 12 MHz
68000, Z80 sound with a YM2151 and an OKI MSM6295). QSound boards, the
CPS-1.5/CPS-2 families and bootlegs are outside this scope. The board's
sources and licences are listed in [cps1-machine.md](../licenses/cps1-machine.md)
and [cps1-ymfm.md](../licenses/cps1-ymfm.md).

## Converting

Add MAME or FBNeo ZIP romsets with **Automatic** detection, or choose
**Capcom CPS-1**. No BIOS is needed. Sets are recognised by the CRC of their
program ROMs, then every file is checked against the catalogue's SHA-1, so
renamed members and both romset dialects work. A split clone (for example
`sf2ua.zip`) needs its parent ZIP (`sf2.zip`) in the same folder; nothing is
written there. 129 sets of the catalogue are in scope; the converter names the
reason when a set is not (QSound, unverified graphics mapper, bootleg).

Exports go to `Games/CPS-1`. The conversion:

1. assembles the board's memory regions from the ZIPs (in the build folder);
2. translates the whole 68000 program ROM and the Z80 sound ROM (every byte
   position, both banks) into guarded native code;
3. runs every route twice in the same executable: once with every instruction
   interpreted (the fresh reference), once with the native code. The per-frame
   CPU registers and clocks, work/graphics/sound RAM, image and sound must be
   identical;
4. learns work-RAM code that was still interpreted and repeats (passes);
5. compresses the executable and compares it again with the reference;
6. saves a quick state, loads it in a fresh process and requires the same
   continuation, and checks that a damaged state is refused.

Scan levels: **quick** runs one credited play route; **standard** adds the
attract mode; **extended** and **thorough** add one or two 18,000-frame
pseudo-random routes. Routes insert a coin, press Start, then move and press
buttons; each route is reproducible from the romset identity.

The report (`datas/reports/…/conversion-report.json`) separates native code,
interpreter fallback (68000 and Z80 counted separately), the board model's
status and what was not measured: board fidelity against real hardware, full
playthroughs and physical latency are not claimed.

## Playing

The game uses the shared 16-bit menus (F1 help, F2 controls, F3 filter, F4
display, F6 autofire, F7 language, F8/F9 quick state, F12 gameplay feedback).
See [controls](CONTROLS.md#capcom-cps-1). The 384×224 picture is shown at 4:3;
vertical games (1941, Varth, Mercs…) are rotated and shown at 3:4. DIP
switches keep the catalogue defaults. The board keeps no non-volatile memory,
so there are no ordinary saves besides F8/F9.

The window title says **Native code** or **Interpreter fallback**; F1 also shows
the sound CPU's state. With F12 enabled, interpreted instructions met while
playing are recorded beside the game and used at the next conversion.

## First qualified sets (23 October 2026, Windows)

| Set | Routes | 68000 fallback | Z80 fallback | F8/F9 |
| --- | --- | --- | --- | --- |
| ffight | attract + play, 3,600 frames each | 0 | 0 | fresh-process match |
| 1941 (vertical) | play, 3,600 frames (quick) | 0 | 0 | fresh-process match |

Earlier native/reference agreement (step 3) also covered sf2, ghouls,
captcomm, megaman and strider. Final Fight and Ghouls'n Ghosts matched MAME
0.289 pixel for pixel over 214 compared frames; that comparison is a
development check, not part of each conversion.
