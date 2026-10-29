# Controls

The shortcut table below applies to the console profiles in the current build,
including the experimental Sharp X68000.
Console-specific F5 functions and cartridge buttons are described below.
Keyboard labels use the active Windows layout: pressing W on an AZERTY
keyboard displays W in F2. Unsaved letter defaults also follow that layout.
Saved mappings keep their physical key positions; changing the UI language
does not change the keyboard layout or overwrite custom controls.
The NES profile shares the menu canvas, F8/F9 quick states and display modes.
On every console, F2 gathers all settings on pages, including the gun page of
recognised Light Phaser, Zapper, Menacer and Super Scope games: see
[F2 settings pages](#f2-settings-pages), [NES controls](NES.md) and
[16-bit gun controls](GUNS_16BIT.md).

| Key | Action |
| --- | --- |
| F1 | Help; **Shift+F1** restarts at once, without confirmation |
| F2 | Settings pages: controls, gun, display & game, options |
| F3 | Next filter: sharp, Scale2x, scanlines, xBR smooth |
| F4 | Window → pixel-perfect fullscreen → fit fullscreen → window |
| F5 | Master System, Game Gear and NES: toggle extra sprites (flicker reduction); Neo Geo: toggle enhanced mode |
| F6 | Keyboard/gamepad autofire on/off for mapped fire buttons |
| F7 | Next menu language: EN → FR → IT → ES → DE |
| F8 | Save/replace the game's quick state |
| F9 | Load that state, including after quitting/restarting |
| F10 | Free: the options are the last F2 page |
| F11 | Neo Geo: switch arcade MVS / console AES and restart (compatible cartridge and AES BIOS required); arcade-only cartridges show "Arcade Only" without restarting |
| F12 | Toggle shutdown-only fallback recording; on by default, remembered for this exact game |
| Enter / keypad Enter / P | Pause/resume: the Master System uses Enter, its default Start/Menu key (its Pause button is on the console). Game Gear and Game Boy use P. On Mega Drive, SNES, NES, Neo Geo and CPS-1, P is free: Enter (the cartridge Start) pauses the game itself |
| Esc | Close a menu or quit |

On every console whose controller has a **Start** button (Game Gear, Game Boy,
NES, Mega Drive, SNES, Neo Geo, CPS-1), the default keyboard layout is the
same since 1.5.0: **Enter** is Start and **Shift** is Select (the coin on
arcade boards; Mode on a six-button Mega Drive pad). Either Shift works: a
binding on one Shift also answers to the other one, unless that other key has
a binding of its own on any player's page. F2 shows the bound key ("Left
Shift"); everything stays rebindable there, and saved bindings are kept. The
Master System has no Start on its pad, so Enter remains its Pause/Menu key.

Every console uses the same two system shortcuts: **F1** opens help and
**Shift+F1** restarts the game. The help lists the function keys in order,
from F1 to F12, followed by the console's own controls.
On a controller, **Start+Select (Back)** held for one second restarts and
**L3+R3** held for one second quits; both can be changed or cleared at the
bottom of player 1's F2 gamepad page (keyboard combinations: keyboard page).

### Capcom CPS-1

Arrows move; W/X/C are buttons 1–3 and A/S/D buttons 4–6 (Light Punch to
Heavy Kick in Street Fighter II). Enter is Start and Shift (or Back on a
controller) inserts a coin. On a controller, A/B/X/Y and the two shoulder
buttons are buttons 1–6. Player 2 uses the numeric keypad or the second
controller. Only the buttons a game reads do anything; its F2 page still lists
all six. Three- and four-player boards (Captain Commando, The King of Dragons,
Knights of the Round, Mercs) add F2 pages for players 3 and 4, played with
the third and fourth controllers; they have no keyboard keys until you bind
some there. Each player has a coin and Start of their own.

The **DIP switches** page, after the control pages, lists the board's
switches with MAME's names and settings (coinage, difficulty, lives, number
of players…); Up/Down choose one, Enter/A or + the next setting, - the
previous. Switches that only apply under another setting appear when it is
chosen. Most boards read their switches at power-on: restart with Shift+F1.
The choice is kept per game; conversions always check the default settings.
Captain Commando needs **Play Mode: 4 Players** for four players.

## F2 settings pages

F2 gathers every setting in one place, on every console, as pages:

1. the control pages: keyboard then gamepad for each player (Game Gear and
   Game Boy: keyboard, gamepad). Player 1's pages end with the **Quit** and
   **Restart** combinations: keyboard ones on the keyboard page, controller
   ones on the gamepad page; the X68000 has the same pages since 1.6.3 (it
   used one page per player, keys and buttons side by side);
2. on recognised gun games, the gun page (Light Phaser, Zapper, Menacer,
   Justifier or Super Scope): cross or dot, size, colour, and Super Scope turbo;
3. **Options**: the function-key settings with their current value (F3
   filter, F4 display mode, F5 sprite reduction, Game Boy palette or Neo Geo
   enhanced mode where they exist, F6 autofire, F7 language, F11 Neo Geo
   MVS/AES, F12 fallback recording), then the **audio filter** and, on
   computers, the function-key row below. Enter/A on a function-key row does
   exactly what its shortcut does; the shortcuts keep working outside the menu.

Left/Right, Tab/Shift+Tab, LB/RB or the D-pad turn pages and wrap around:
Left from the first page reaches the options. Small squares at the top right
show how many pages there are: those up to the current page are filled, the
current one brightest. Up/Down choose a row; Enter/A binds a control or changes
a value (+ next, - previous on gun and option rows); Esc or B closes F2, and F2
closes it from any page. F2 opens on the first page; moving between control
pages keeps the selected row, and every control of a page is shown at once.
The game stays paused while F2 is open.

F10 is free on every console, and so are the former gun shortcuts: F10 and G on
the Master System, F5 on Mega Drive and SNES gun games. The controller Guide
button opens F2 on its options page.

### Computer function keys (X68000)

Some computer games need F1–F10 themselves. The X68000 options page has a row
**F1-F10 keys: Retro-Recomp / X68000**, off (Retro-Recomp) by default and saved
as `[X68000.Options] fkeys_machine` in `datas/Retro-Recomp.ini`. Set to X68000,
F1–F10 reach the computer and **Ctrl+F1 to Ctrl+F12** reach Retro-Recomp:
Ctrl+F2 opens F2, Ctrl+Shift+F1 restarts, Ctrl+F8/F9 save and load, a held
Ctrl+F5 accelerates loading. F11 (pause) and F12, absent from the X68000
keyboard, keep working without Ctrl, and every function key acts on Retro-Recomp
while a menu is open. Ctrl+F1–F12 also work with the row on Retro-Recomp and in
full guest typing (Ctrl+Alt+K), which still sends F2–F10 to the computer.

## Game options (1.1.8)

The audio filter is on the options page, the last page of F2; the controller
**Guide** button opens F2 directly on it. The quit and restart combinations
close player 1's control pages. F10, O and Y no longer open anything. The game
pauses while F2 is open. Use Up/Down, Enter/A (or +) for the next value, - for
the previous one, Esc/B to close, or click a row with the mouse; Left/Right turn
pages.

- **Audio filter:** Off (default), Light, Soft. These optional tone controls
  gently reduce high frequencies at the final PCM output. Off bypasses sample
  processing byte for byte. They add no audio queue or lookahead; physical
  latency and personal listening preferences still require real-device tests.
  They do not replace each console's existing chip behavior or resampling.
- **Quit (keyboard page / gamepad page):** select the row, release the activation button,
  press a single key or button, or the desired combination together, then
  release it. Keyboard combinations accept up to three keys. Each controller
  combination belongs to one controller, not buttons split between players.
  The keyboard row is unassigned by default; the gamepad default is
  **L3+R3**. Delete/Backspace or controller X clears the selected
  combination; Esc cancels capture.
- **Restart (keyboard page / gamepad page):** assigned the same way. The keyboard row is
  unassigned by default (Shift+F1 always restarts); the gamepad default is
  **Start+Select (Back)**. A held restart fires once, then waits for release.
- **Hold the key, button or combination for one second** to quit through the normal shutdown
  path, preserving ordinary saves and shutdown-only fallback hints. Configured
  quit buttons take priority over host pause/reset shortcuts; cartridge inputs
  otherwise retain their usual behavior. Focus loss or disconnect cancels an
  incomplete hold.

Settings are saved by console in `datas/Retro-Recomp.ini`, alongside the games,
on Windows and Linux. Existing game executables must be regenerated; updating
the converter does not modify games already exported.

F12 changes recording only: the interpreter still runs when necessary and its
use remains visible. Interpreter disabling is deferred; no such
shortcut is added. See [fallback recovery and moved games](RUNTIME_FEEDBACK.md).

The xBR implementation is shared by Master System, Game Gear, Game Boy, NES,
Mega Drive, Super Nintendo, the local Neo Geo profile, CPS-1 and the X68000.
New exports cache
unchanged image regions while producing the same filtered pixels. It remains
last in the F3 cycle and requires no new setting. Existing EXEs need regeneration
to receive this improvement; updating the converter alone does not alter them.

In F2, Enter selects a binding instead of pausing. Left/Right (or Tab) turns
the pages: player 1 keyboard, player 1 gamepad, player 2 keyboard, player 2
gamepad. Up/Down selects a row, and Enter begins capture. Press the desired key
or the selected player's controller button. Esc cancels capture; D restores
that player's defaults for the input type. On each gamepad page the last row,
Gamepad, chooses the controller of that player ([pad slots](HOST_KIT.md): Automatic
by default, a connected controller, or None).

Game Gear has one player and no gun. Arrows and W/X control the game; **Enter**
is the cartridge Start button (S before 1.5.0). On a gamepad, A/B are the two
game buttons, Start reaches the cartridge and Back opens the pause/menu. **P**
opens that menu on the keyboard (Enter did before 1.5.0; a saved Pause/Menu
binding is kept, and a saved Enter there wins over the cartridge Start), while
F1 opens help and Shift+F1 restarts the game. F2 maps the single player's keys
and buttons; there is no second-player or Light Phaser page. Game Gear key
bindings have their own INI sections so they do not overwrite Master System
controls when games share an executable folder.

The Neo Geo MVS profile shares the same menus and four filters.
Player 1: arrows, **W/X/C/V** for **A/B/C/D**, **Enter** for Start and either
**Shift** for Coin. Player 2: keypad **5/2/1/3**, **8/9/6/4**, keypad Enter and
keypad 0 respectively. Two controllers use D-pad/left stick, A/B/X/Y, Start
and Back (Coin in arcade MVS). In console AES, the Coin action is inactive:
Back/Select does not open the BIOS menu. **P** pauses; **F1** opens help and **Shift+F1** restarts. Stick clicks have no game action by default. F2 remaps each player's keyboard and gamepad on their own pages;
there is no gun page. P no longer pauses: Enter is the cartridge Start. F3/F4/F6/F7 preferences persist in the common local INI
with independent NeoGeo video/mapping sections. F8/F9 includes fresh-process
loading with exact cartridge/BIOS identity. See [Neo Geo scope](NEOGEO.md).

Neo Geo **F5** directly switches enhanced mode on/off. It doubles the virtual
68000 clock and extends rendering from 96 to 381 sprite columns per line.
The video and sound clocks retain their normal rates. Enhanced mode is the
default since 1.0.2; the last F5 choice is remembered under `NeoGeo.Runtime/enhanced` in
`datas/Retro-Recomp.ini`. F1 help shows the active setting. Quick states retain their
saved machine mode, so loading an older standard state returns to standard mode;
press F5 after F9 to compare the same scene in enhanced mode. This is an optional
change to the console's original limits, qualified on the documented Metal Slug 3
paths rather than every game.

Game Boy has one player and no gun. Arrows move, **W/X** are A/B,
**Enter** is cartridge Start and either **Shift** is cartridge Select.
These letter bindings follow the active keyboard layout. On a controller, the
D-pad/left stick moves, the two primary face buttons are A/B, Start and
Back are cartridge Start/Select, and the Guide button opens pause. Since
1.6.3 Game Boy runs the same player shell as every other console (the host kit):
F2 has the keyboard and gamepad pages of player 1 with the Quit and Restart
combinations and the Gamepad row, then the options; the Pause/Menu action
(P, the Guide button) is a row of the page like the Game Gear's. F3 cycles all four
filters, including Scale2x and scanlines; F4 keeps the same three display
modes. F5 immediately switches between pseudo black-and-white monochrome
(the default) and classic green, without opening a menu or pausing the game.
The palette choice is saved with the other Game Boy settings.
F6 toggles autofire for held keyboard/gamepad A/B (with the shared "Autofire ON/OFF" notice), F7 changes menu language,
and F8/F9 use one quick state, taken between two frames. P pauses, F2 maps controls, F1 opens help
and Shift+F1 restarts. Enter selects a binding inside F2. Escape closes a menu or quits.
Fallback stays visible in the window title and pause menu, with no overlay
in fullscreen. The upstream fast-forward, maximum-speed and mute keys and the
second binding of each button (the shoulders) no longer exist.

Master System defaults:

| Player | Directions | Buttons | Menu |
| --- | --- | --- | --- |
| J1 keyboard | Arrows | W / X | Enter (P no longer pauses) |
| J2 keyboard | Keypad 5 / 2 / 1 / 3 | Keypad 8 / 9 | Keypad 7 |
| Each gamepad | D-pad / left stick | A / B | Start/Menu |

Start/Menu is configurable on both keyboard and gamepad pages. A button used
for gameplay must be freed before serving as the menu button. Like every other
console, the Master System restarts with Shift+F1 or the held restart
combination (Start+Select by default); it has no separate Select/Reset row.
Earlier `select` entries for either player are ignored without rewriting the
INI. J2 binding details appear only on its mapping page.

Since 1.6.3 the Master System and the Game Gear run on the common host kit, with the same pad rules as the other
consoles: controllers go to players in plug order (Automatic), and each player's Gamepad row in F2 can pin a
controller to that player or leave the player on the keyboard (None); the first-player preference and the C swap of earlier
releases are gone. The stick threshold is 16000 like everywhere else, opposite directions cancel, autofire
(F6) follows the common rule and shows the common "Autofire ON / OFF" notice, and F2 captures a pad press only from the
selected player's own controller. The Start/Menu key (Enter by default) or button of any player opens the Pause menu; F1 and F2
opened from it come back to it. Settings are shared in `datas/Retro-Recomp.ini` under
`[MasterSystem.*]` and `[GameGear.*]` sections (keyboard and gamepad bindings per player, `[MasterSystem.Pointer]`
for the Light Phaser reticle, `device` and `name` of each pinned controller); the French sections of earlier
releases (`[Clavier]`, `[Manette]`, `[Video]`, `[LightPhaser]`, and `SMSRecomp.ini` while no `Retro-Recomp.ini` exists)
are still read where the new key is absent and never deleted or rewritten.
Defaults live in memory. Starting a game, opening a menu or reading an INI
creates no files; only a changed setting creates/updates the shared INI
(a legacy `SMSRecomp.ini` is copied first, on the first write).

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
and lasting priority changes retain cartridge ordering. Game Gear uses the same
renderer and option, saved in `[GameGear.Video] reduce_sprite_flicker`.

On NES, **F5** draws objects 9 to 64 of a scanline where none of the eight
original sprite units is opaque, in OAM order and with their own background
priority. Secondary OAM, the overflow flag, sprite-0 hit, OAM, PPU bus fetches
and mapper counters/latches are unchanged: extra patterns are read from the
mapped CHR window without a bus access. MMC5 keeps the original limit. The
choice is saved in `[NES.Video] reduce_sprite_flicker`; off by default.

All console menus share the converter's identity: near-black panels, gold
lettering and its brown-gold selection, defined once in `native/retro_menu.h`
(colours only, no new asset in games). Menu text uses the public-domain X.Org
Misc Fixed 10x20 bitmap (3.8 KB in each game), drawn for the window's scale by
area coverage in 5 x 10 cells of the 256 x 192 menu grid: solid pixels stay
solid and only the edges blend. The cells are a sixth smaller than before, so
help lists one function key per line and every control of a page fits without
scrolling (up to fourteen rows: twelve SNES or six-button Mega Drive actions
plus quit and restart). A 256x192 window keeps the 6x10 font, narrowed to the
cell. Game menus draw plain ASCII: accents are dropped and German umlauts
become ae/oe/ue, so games carry no glyph table.

The first fullscreen mode keeps integer pixel sizes. Press F4 again for the
largest image that fits the display while preserving the visible game's
aspect ratio; some letterboxing remains when the display has a different
ratio. Press it a third time to restore the previous window size and position.
The fit mode also supports all filters and mouse aiming, including HiDPI and
the automatically cropped left hardware border.

The last F4 mode and F3 filter are saved when changed and restored on the next
launch. Settings are shared by games of the same console. Master System,
Game Gear, NES, Mega Drive and SNES use distinct video sections in their shared
`datas/Retro-Recomp.ini` (Game Boy since 1.6.3, `[GameBoy.Video]`, with its
monochrome/green palette; the `datas/Retro-Recomp-GameBoy.ini` of earlier releases is only read). Reading settings creates no folders or files.
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
**both keyboard and gamepad**, independently for each player and button; on the
X68000 (since 1.6.3) both game buttons pulse, a key or a mouse button bound to
one of them is that button, and Ctrl+Alt+F is the same switch as F6. A new
press fires immediately. Each pulse is one guest frame pressed and one released:
about 30 pulses per second on 60 Hz consoles, 25 in PAL, and 29.6 on Neo Geo.
This replaces the earlier 40 Hz timer, whose pulses could be missed by games
sampling once per frame. Repeated reads within a frame stay stable; pausing
freezes the phase. Directions, Start/Select/Coin and mouse gun triggers are not
pulsed. The game's own firing limits still apply.

L3/R3 (stick clicks) have no default game binding and remain assignable to game
actions through F2. Together, held for one second, they quit by default (game
options). Existing explicitly saved bindings remain in effect. Use P to pause
and Shift+F1 to restart.

The setting is shared through `Manettes/autofire` in `datas/Retro-Recomp.ini`
(the X68000 keeps `X68000/autofire`);
since 1.6.3 the Game Boy writes it there too and reads its former `input.autofire` setting while that key is absent. Existing games need
regeneration to receive these input changes.

Starting with 0.10.6, catalogue-selected Light Phaser games use the mouse on
port 1: left click triggers, right click shoots off-screen. The Light Phaser
page of F2, after the four control pages, holds the gun options. In 0.10.7 the
default is a small red cross. Choose cross or dot, a common size from 1 to 5,
and red, white or pure green. Up/Down selects a row; Enter/A or + changes it,
- goes back. Clicking the left part of a row steps back, elsewhere forward.
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
