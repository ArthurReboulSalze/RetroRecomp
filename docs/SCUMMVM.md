# Adventure games (ScummVM)

**Purpose.** "Adventure (ScummVM)" is a category of its own: **emulated, 0 % native code**, and it stays so. There is no
native-code goal, no recompilation plan and no native-share target. What Retro-Recomp adds is the packaging: one simple
executable per game, holding the whole game, to click and play, with its saves and settings in `datas/`, on Windows and Linux.

**Experimental.** An adventure game made of data files and script bytecode (LucasArts SCUMM, Sierra
SCI, Westwood Kyrandia, Revolution, Coktel and the other engines ScummVM runs) becomes one executable: ScummVM with the
player's own game files appended to it. Nothing is recompiled: ScummVM interprets the game, so the measures of native code and
CPU fidelity do not apply, and none is claimed. Gameplay is validated game by game; physical latency is not measured.

## What the converter does

One method for every game; no game is named in the code.

1. **Detection by ScummVM itself.** The converter starts ScummVM's detection (a separate program) on the folder the player
   gives. It answers with the game id, the engine, the language, the platform and the edition. A folder that matches several
   editions (for example data shared by several languages) asks the player to choose; the choice is stored in the executable.
2. **One runtime per engine family.** The engine ScummVM reports picks the build family (`retrorecomp/scummvm_build.py`,
   `FAMILY_OF_ENGINE`); an engine missing from the table is its own family.
3. **The pack.** The game's files are appended to a copy of that runtime, byte for byte and uncompressed. The executable reads
   them from inside itself; nothing is extracted. Executables of 1 to 2 GB are normal for CD games.
4. **Name, id and cover.** The executable is named after the detected title, as the other machines name theirs. Its id is a
   digest of the folder's file names and sizes. The cover comes from the converter's cover pipeline, by title (images of the
   game folder first, then the configured sources), and becomes the executable's icon.

## The exported game

Started with no argument, `<Game>.exe` runs its game. Next to it, `datas/` has the same structure as for every machine:
`datas/Retro-Recomp.ini` (common settings) and `datas/games/<Game>-<id>/` (ScummVM's configuration of the game, its log and its
saves). Nothing is written anywhere else.

* **Menu**: Ctrl+F5, or Start on a pad, opens ScummVM's menu (save, load, options, quit). Alt+Enter switches to full screen,
  Ctrl+U mutes, Ctrl+Q or Alt+F4 quits. The host shortcuts of the other machines (F1, F2, F3, F8, F9, Tab, backquote) do not
  exist here: F1 to F12, Esc and Tab belong to the games, and typing reaches text parsers.
* **Languages**: the five game-menu languages (English, French, Italian, Spanish, German). The interface language of
  `datas/Retro-Recomp.ini` sets ScummVM's menu language at every start; another value gives English. The game's own language
  comes from its data and is never changed.
* **Music**: without an MT-32 ROM, the default AdLib or General MIDI music, with no error.
* **Pad**: the left stick moves the pointer, A clicks, B right-clicks, Start opens the menu (ScummVM's defaults, editable in its
  options).

## Licences

ScummVM is under the GNU General Public License version 3 or later. Retro-Recomp's patch of it lives in
[native/scummvm](../native/scummvm/README.md) under the same licence, separate from Retro-Recomp's own MIT code; ScummVM and
FreeType themselves are fetched at build time at the pins of [UPSTREAMS.md](UPSTREAMS.md). Every executable carries the GPL text
and a written offer of the corresponding source ([licenses/scummvm.md](../licenses/scummvm.md)); each release publishes that source
as an archive. The game files are the player's own and stay private: an executable that holds them is not to be shared.

## Limits

* The Linux build of the runtime is prepared; its witness on a Debian 13 PC is still to come.
* No Ogg Vorbis, FLAC or MP3 decoder yet: games that need CD audio rips or compressed speech are not supported yet.
* A folder ScummVM does not recognise (a renamed file, a missing file) is refused with the reason.
* No splash, no CRT shaders (they need an OpenGL build).

## Evidence so far

Prototype of 6 November 2026 (ScummVM v2026.4.0 and Retro-Recomp's patch): ten games of eight engine families, from 55 MB to
2.1 GB, ran from their own executable, offscreen, with nothing extracted and nothing written outside `datas/`; an authored test
covers the pack's file semantics (negative and end-relative seeks). The owner played the ten executables on 6 November 2026
("ça marche parfaitement"). This is a play trial of prototypes, not a qualification.
