# Controls

The shortcut table below applies to all six console profiles.
Console-specific F5 functions and cartridge buttons are described below.
Keyboard labels use the active Windows layout: pressing W on an AZERTY
keyboard displays W in F2. Unsaved letter defaults also follow that layout.
Saved mappings keep their physical key positions; changing the UI language
does not change the keyboard layout or overwrite custom controls.
The NES profile shares the menu canvas, F8/F9 quick states and display modes.
F5 opens Zapper options on recognised gun games. See [NES controls](NES.md).
On qualified Mega Drive and SNES gun profiles, F5 opens the same cross/dot,
size and colour settings. See [16-bit gun controls](GUNS_16BIT.md).

| Key | Action |
| --- | --- |
| F1 | Restart |
| F2 | Control mappings |
| F3 | Next filter: sharp, bilinear, Scale2x, scanlines |
| F4 | Window → pixel-perfect fullscreen → fit fullscreen → window |
| F5 | Light Phaser options, in catalogue-selected gun games |
| F6 | Gamepad autofire on/off, both fire buttons |
| F7 | English/French |
| F8 | Save/replace the game's quick state |
| F9 | Load that state, including after quitting/restarting |
| H | Help |
| P / Enter / keypad Enter | Pause/resume on Master System and Game Gear; Game Boy uses P only |
| Esc | Close a menu or quit |

In F2, Enter selects a binding instead of pausing. On Master System,
Left/Right chooses the player. Tab switches keyboard/gamepad, Up/Down selects a row, and Enter begins
capture. Press the desired key or the selected player's controller button.
Esc cancels capture; D restores that player's defaults for the input type.
C on the Master System gamepad page swaps controller assignments.

Game Gear has one player and no gun. Arrows and W/X control the game; **S** is
the cartridge Start button. On a gamepad, A/B are the two game buttons,
Start reaches the cartridge and Back opens the pause/menu. **P** and Enter also
open that menu, while F1 restarts the game. F2 maps the single player's keys
and buttons; there is no second-player or Light Phaser page. Game Gear key
bindings have their own INI sections so they do not overwrite Master System
controls when games share an executable folder.

Game Boy has one player and no gun. Arrows move, **W/X** are A/B,
**Enter** is cartridge Start and either **Shift** is cartridge Select.
These letter bindings follow the active keyboard layout. On a controller, the
D-pad/left stick moves, the two primary face buttons are A/B, Start and
Back are cartridge Start/Select, and a left-stick click opens pause. Game Boy
uses the same RetroRecomp menu layout as the Sega profiles. F3 cycles all four
filters, including Scale2x and scanlines; F4 keeps the same three display
modes. F5 selects pseudo black-and-white monochrome (the default) or classic
green. F6 toggles autofire for held gamepad A/B, F7 changes menu language,
and F8/F9 use one quick state. P pauses, F2 maps controls, and H opens
help. Enter selects a binding inside F2. Escape closes a menu or quits.
Fallback stays visible in the window title and pause menu, with no overlay
in fullscreen. Game Boy settings use a separate shared INI file.

Master System defaults:

| Player | Directions | Buttons | Menu | Restart |
| --- | --- | --- | --- | --- |
| J1 keyboard | Arrows | W / X | P; Enter also available | F1 |
| J2 keyboard | Keypad 5 / 2 / 1 / 3 | Keypad 8 / 9 | Keypad 7 | Disabled |
| Each gamepad | D-pad / left stick | A / B | Start/Menu | Select/Back, J1 only |

Start/Menu and J1 Select/Reset are configurable on both keyboard and gamepad
pages. A button used for gameplay must be freed before serving a system action.
J2 has no reset row; old J2 reset entries are ignored without rewriting the INI. J2 binding
details appear only on its mapping page.

The first controller is J1 and the next J2; swapping supports one gamepad for
J2 while J1 uses the keyboard. Settings are shared in `datas/Retro-Recomp.ini`.
Disconnecting one controller keeps the other assigned to its player.
Defaults live in memory. Starting a game, opening a menu or reading an INI
creates no files; only a changed setting creates/updates the shared INI.
Legacy settings can be read in place and are copied only on an explicit edit.

The first fullscreen mode keeps integer pixel sizes. Press F4 again for the
largest image that fits the display while preserving the visible game's
aspect ratio; some letterboxing remains when the display has a different
ratio. Press it a third time to restore the previous window size and position.
The fit mode also supports all filters and mouse aiming, including HiDPI and
the automatically cropped left hardware border.

The last F4 mode and F3 filter are saved when changed and restored on the next
launch. Settings are shared by games of the same console. Master System,
Game Gear, NES, Mega Drive and SNES use distinct video sections in their shared
`datas/Retro-Recomp.ini`; Game Boy uses `datas/Retro-Recomp-GameBoy.ini`, including
its monochrome/green palette. Reading settings creates no folders or files.
Older Sega `[Video] filtre` entries remain readable until an explicit change.

Scanlines use one gap per original console raster row. Fractional fullscreen
scaling integrates partial opacity, keeping the bands proportional to the
image instead of snapping them to uneven thicknesses. Below 2× resolution the
mask is omitted to preserve game detail. Window status text always uses English
("Native code", "Interpreter fallback"); menu language remains configurable.

F8/F9 also save and restore the qualified 16-bit games after closing the EXE.
Each quick state uses the game's name and exact ROM identity in `datas/states`.
See [state formats and compatibility](GAME_STATES.md#mega-drive-and-super-nintendo).

F6 autofire is off by default. It pulses both mapped gamepad fire buttons
while they are held, independently for each player/button. New presses fire
immediately; directions, menu/reset, keyboard buttons and mouse gun triggers
are unaffected. Starting with 0.10.14, the cadence is forty pulses per simulated
second (12.5 ms down, 12.5 ms up), four times the previous speed. Timing uses
guest microseconds, so pause freezes it and display refresh does not set its
speed. The game's input sampling and firing rules determine the actual shots;
a game can miss pulses when it reads the controller less often than they occur.
The setting is shared through `Manettes/autofire` in `datas/Retro-Recomp.ini`.

Starting with 0.10.6, catalogue-selected Light Phaser games use the mouse on
port 1: left click triggers, right click shoots off-screen. F5 (or G in F2)
opens gun options. In 0.10.7 the default is a small red cross. Choose cross or
dot, a common size from 1 to 5, and red, white or pure green. Up/Down selects a
row; Left/Right changes it. The mouse arrows or controller D-pad also work.
These settings are shared;
fullscreen, HiDPI and the cropped left border use the image's actual viewport.
See [Light Phaser support and limits](LIGHT_PHASER.md).

Game states are available in newly generated native banked executables; one
slot per ROM is stored in its own `datas/games` directory. F8/F9 closes an
open menu and resumes the game. See [storage and compatibility](GAME_STATES.md).
F9 with no state creates nothing. Gameplay learning and automatic disk logs
are disabled; fallback remains counted and reported in the window title.
Fullscreen hides interpreter overlays, not counters. The left
hardware mask is cropped automatically when the rendered frame requests it;
there is no manual border switch.
