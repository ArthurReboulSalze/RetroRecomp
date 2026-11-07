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
   game folder first, then the configured sources), and becomes the executable's icon; when nothing is found, the
   converter's own picture is used. A cover the player chooses always wins. The reviewed cover references of the other
   machines (keyed by a ROM file's hash) are not looked up for a game folder.

## The exported game

Started with no argument, `<Game>.exe` runs its game. Next to it, `datas/` has the same structure as for every machine:
`datas/Retro-Recomp.ini` (common settings) and `datas/games/<Game>-<id>/` (ScummVM's configuration of the game, its log and its
saves). Nothing is written anywhere else.

* **Menu**: **Ctrl+F2** opens the options dialog on the Retro-Recomp page and **Ctrl+F1** on its Help tab, from anywhere in a game, as
  F2 and F1 do on the other machines; Ctrl+F5, or Start on a pad, opens ScummVM's own menu (save, load, options, quit) as in every
  ScummVM. A message "Help: Ctrl+F1 · Menu: Ctrl+F2" (menu language, Retro-Recomp's dark and gold colours) is shown over the game for
  three seconds as soon as the game is running. Alt+Enter switches to full screen, Ctrl+U mutes, Ctrl+Z or Alt+F4 quits on Windows (Ctrl+Q on Linux). **Ctrl+F4** switches
  full screen with integer (pixel-perfect) scaling on and off, and **Ctrl+F3** cycles the picture effect in the order of the host
  kit's F3: sharp pixels, HQ2x, Scale2x and scanlines. The first three are ScummVM's own software scalers (no OpenGL); the scanlines are the host kit's mask
  (`native/scanlines.h`: a darker band in the last third of every source row), drawn over the scaled picture, never over the menus. Both are remembered. The plain host shortcuts of the other machines (F1 to F4, F8, F9, Tab, backquote)
  do not exist here (the Ctrl+ keys above stand in for them): F1 to F12, Esc and Tab belong to the games, and typing reaches text parsers.
* **Languages**: the five game-menu languages (English, French, Italian, Spanish, German). The interface language of
  `datas/Retro-Recomp.ini` sets ScummVM's menu language at every start; another value gives English. The game's own language
  comes from its data and is never changed.
* **Retro-Recomp page**: the in-game options (Ctrl+F5, then Options) have a "Retro-Recomp" tab in place of ScummVM's empty
  "Backend" tab: the menu language (the five languages, from the next start), full screen, scaling, keep the aspect ratio,
  the music, effects and speech volumes, "mute all", and a "Keys and pad..." button that opens ScummVM's keymaps tab. A "Help" tab
  ("Aide", "Hilfe", "Ayuda", "Aiuto") lists the shortcuts. The values are ScummVM's own keys (`fullscreen`, `stretch_mode`,
  `aspect_ratio`, `scaler`, `scale_factor`, the volumes and `mute`). When a run ends they are copied to `datas/Retro-Recomp.ini` (section `[Adventure]`, and `[Interface]` for the
  language) and applied again at the start of every adventure executable of the folder, so a choice made in one game holds for all
  of them. Screenshots go to `datas/games/<Game>-<id>/screenshots`. The host kit's own overlay (F1 menu, F2 mapping, the F3
  graphics page, F12, pause, GLSL shaders) is not wired: the host F-keys belong to the games.
* **Errors**: an executable never opens a window of the system. A fatal error of ScummVM or of the game's engine ("Error running game",
  missing data) is written to `scummvm.log` and the program ends with exit code 1; a crash, an abort or an uncaught exception
  writes one line to `crash.log` beside it. ScummVM's launcher never appears: the program ends with its game. Dialogs the engines
  draw inside the game window (saving, loading, the game's own prompts) stay.
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

* Linux is witnessed on one small game only (see the evidence below): no big game and no other engine family has been built or run there.
  The runtime is built with the system's GCC; it links the C and C++ runtime libraries dynamically, so an exe needs the libstdc++ of the
  distribution that runs it.
* No Ogg Vorbis, FLAC or MP3 decoder yet: games that need CD audio rips or compressed speech are not supported yet.
* A folder ScummVM does not recognise (a renamed file, a missing file) is refused with the reason.
* No splash, no CRT shaders (they need an OpenGL build).

## Evidence so far

Linux witness of 6 November 2026 (a Debian 13 PC, GCC 14.2, the tree of the branch merged with main): the converter built the
detection runtime and the Lure runtime with the system's GCC, CMake and Ninja, the pinned static SDL and the fetched FreeType, detected
the folder of Lure of the Temptress (4.4 MB, DOS/French) and wrote a 40 MB executable. Started alone in an empty folder, offscreen
(dummy video and audio drivers, hard kill after 25 s), with an empty `HOME`: it read the game from inside itself, created only `datas/`
beside itself (`Retro-Recomp.ini`, `games/<Game>-<id>/` with its config, log and `saves/`), logged the game start without a warning
about missing GUI files, and left the home folder empty. This witnesses the packaging on Linux for one small game and one engine; it
does not play the game, and it is not a qualification.

Prototype of 6 November 2026 (ScummVM v2026.4.0 and Retro-Recomp's patch): ten games of eight engine families, from 55 MB to
2.1 GB, ran from their own executable, offscreen, with nothing extracted and nothing written outside `datas/`; an authored test
covers the pack's file semantics (negative and end-relative seeks). The owner played the ten executables on 6 November 2026
("ça marche parfaitement"). This is a play trial of prototypes, not a qualification.
