# Controls

The shortcut table below applies to the seven console profiles in the current
development build.
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
| F3 | Next filter: sharp, Scale2x, scanlines, xBR smooth |
| F4 | Window → pixel-perfect fullscreen → fit fullscreen → window |
| F5 | Master System: toggle sprite flicker reduction; Neo Geo: toggle enhanced mode |
| F11 | Neo Geo: switch arcade MVS / console AES and restart (AES BIOS required) |
| F6 | Keyboard/gamepad autofire on/off for mapped fire buttons |
| F7 | Next menu language: EN → FR → IT → ES → DE → ZH → JA → RU |
| F8 | Save/replace the game's quick state |
| F9 | Load that state, including after quitting/restarting |
| F10 | Master System: Light Phaser options, in catalogue-selected gun games |
| F12 | Toggle shutdown-only fallback recording; on by default, remembered for this exact game |
| H | Help |
| P / Enter / keypad Enter | Pause/resume on Master System and Game Gear; Game Boy uses P only |
| Esc | Close a menu or quit |

F12 changes recording only: the interpreter still runs when necessary and its
use remains visible. Interpreter disabling is deferred; no such
shortcut is added. See [fallback recovery and moved games](RUNTIME_FEEDBACK.md).

The xBR implementation is shared by Master System, Game Gear, Game Boy, NES,
Mega Drive, Super Nintendo and the local Neo Geo profile. New exports cache
unchanged image regions while producing the same filtered pixels. It remains
last in the F3 cycle and requires no new setting. Existing EXEs need regeneration
to receive this improvement; updating the converter alone does not alter them.

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

The Neo Geo MVS profile shares the same menus and four filters.
Player 1: arrows, **W/X/C/V** for **A/B/C/D**, **Enter** for Start and either
**Shift** for Coin. Player 2: keypad **5/2/1/3**, **8/9/6/4**, keypad Enter and
keypad 0 respectively. Two controllers use D-pad/left stick, A/B/X/Y, Start
and Back. **P** pauses; **F1** resets. Stick clicks are unassigned by default. F2 remaps each player's keyboard/gamepad with Left/Right and Tab;
there is no gun page. F3/F4/F6/F7 preferences persist in the common local INI
with independent NeoGeo video/mapping sections. F8/F9 includes fresh-process
loading with exact cartridge/BIOS identity. See [Neo Geo scope](NEOGEO.md).

Neo Geo **F5** directly switches enhanced mode on/off. It doubles the virtual
68000 clock and extends rendering from 96 to 381 sprite columns per line.
The video and sound clocks retain their normal rates. Enhanced mode is the
default since 1.0.2; the last F5 choice is remembered under `NeoGeo.Runtime/enhanced` in
`datas/Retro-Recomp.ini`. H shows the active setting. Quick states retain their
saved machine mode, so loading an older standard state returns to standard mode;
press F5 after F9 to compare the same scene in enhanced mode. This is an optional
change to the console's original limits, qualified on the documented Metal Slug 3
paths rather than every game.

Game Boy has one player and no gun. Arrows move, **W/X** are A/B,
**Enter** is cartridge Start and either **Shift** is cartridge Select.
These letter bindings follow the active keyboard layout. On a controller, the
D-pad/left stick moves, the two primary face buttons are A/B, Start and
Back are cartridge Start/Select, and the Guide button opens pause. Game Boy
uses the same RetroRecomp menu layout as the Sega profiles. F3 cycles all four
filters, including Scale2x and scanlines; F4 keeps the same three display
modes. F5 immediately switches between pseudo black-and-white monochrome
(the default) and classic green, without opening a menu or pausing the game.
The palette choice is saved with the other Game Boy settings.
F6 toggles autofire for held keyboard/gamepad A/B, F7 changes menu language,
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

On Master System, **F5** switches sprite flicker reduction on/off immediately.
The initial default retains the console's eight sprites per scanline. When
enabled, extra sprites submitted by the game can also be drawn, and confirmed
rapid sprite-list reversals are stabilized to reduce overlap flicker. Current
positions/animation pixels are used without frame blending. Collision and overflow flags still use the
original eight slots. The choice is shared by Master System games in
`[MasterSystem.Video] reduce_sprite_flicker`, saved only when changed. This is
an optional display enhancement, not a recompilation coverage setting. It cannot
restore sprites a game deliberately leaves out. Stabilization can change which
overlapping character appears in front; ambiguous identities, raster rewrites
and lasting priority changes retain cartridge ordering. Game Gear retains its
own original sprite limit.

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

F6 autofire is off by default. It pulses held, mapped fire/face buttons from
**both keyboard and gamepad**, independently for each player and button. A new
press fires immediately. Each pulse is one guest frame pressed and one released:
about 30 pulses per second on 60 Hz consoles, 25 in PAL, and 29.6 on Neo Geo.
This replaces the earlier 40 Hz timer, whose pulses could be missed by games
sampling once per frame. Repeated reads within a frame stay stable; pausing
freezes the phase. Directions, Start/Select/Coin and mouse gun triggers are not
pulsed. The game's own firing limits still apply.

L3/R3 (stick clicks) have **no forced pause/reset action** and no default game
binding. They remain assignable to game actions through F2. Existing explicitly
saved bindings remain in effect. Use P to pause and F1 to restart.

The setting is shared through `Manettes/autofire` in `datas/Retro-Recomp.ini`;
Game Boy keeps its own persistent `input.autofire` setting. Existing games need
regeneration to receive these input changes.

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
