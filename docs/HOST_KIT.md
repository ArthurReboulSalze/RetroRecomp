# Host kit contract (exported games)

Every exported game currently ships with its own player shell. The survey of
27 October 2026 measured five host code bases — about 12,900 host-side lines,
of which only about 2,100 are really shared — and 21 silent behavioural
divergences between them (local surveys `hosts.md`, `host-divergences.md`,
`duplicates-glm.md`; `file:line` references below point into those files and
into the tracked sources). This document is the contract for the common host
kit that replaces them: what the kit owns, the interface each machine core
implements, the one behaviour chosen for every divergence, the preferences
layout and migration, the fingerprint rules, and the migration order with its
verification.

The behaviour decisions were taken on 27 October 2026. Each one applies the
project rule for host divergences: one behaviour for every family, measured A/B
and documented when it lands (`PLAN.md` decision 3; `hosts.md:543-548`). Where
the code does not follow this contract yet, the page says "target", as
[STANDARDS.md](STANDARDS.md) does.

## 1. Purpose and scope

The kit owns everything a generated executable does around the emulated or
recompiled machine: window, video presentation, input, menus, languages, audio
output, quick-state and battery files, preferences, command line and headless
options, window title and fallback notices (`hosts.md:3-6`). The CPU, PPU and
sound cores are out of scope (`hosts.md:6`).

The machine core provides picture, audio samples, a pad word per player (plus
pointers), state blobs, battery blobs and honesty counters (`hosts.md:207-209`).
Everything else is kit.

The kit has two layers, split by what headless runs use; this split decides the
fingerprint role of every file (section 6):

* `native/hostkit/core/` — headless-safe, game role: ini and path access,
  atomic file writes, state container, battery container, input-script parser,
  report/trace writer, command line, frame hashing (`hosts.md:212-214`).
* `native/hostkit/shell/` — SDL, host role, never used by headless runs:
  window, renderer, filters, pacing, audio output, pads/keyboard/pointer,
  bindings, menus, notices, titles (`hosts.md:215-217`).

The kit contains no machine header and no machine licence text; it is MIT like
the existing shells, and the machine adapter is the only file that sees both
sides, so the per-file licence separation stays visible (`hosts.md:218-221`).
During the migration there is no change of user-visible file formats: legacy
ini sections, state magics and paths are kept by a legacy table in each
adapter; only new machines start with the new names (`hosts.md:222-224`).

The contract grows from the existing 16-bit machine contract: `rr16_*`,
28 functions with four implementations (`hosts.md:34-36`,
[retro_console16.h](../native/retro_console16.h)). The pieces that are already
common — menu canvas ([retro_menu.h](../native/retro_menu.h)), fonts, language
catalogue, filters, options framework, autofire, audio cushion/filter — are kit
material and move unchanged (`hosts.md:340`).

## 2. C interface

### 2.1 Machine contract (sketch)

Adapted from the survey sketch (`hosts.md:226-296`). Phase 1 compiles the part
of it that the four 16-bit machines need, with the machine functions still the
`rr16_*` link-time symbols: see [hostkit.h](../native/hostkit/hostkit.h) for the
table the adapters fill (actions, geometry, frame function, state and audio
accessors, and the hooks that stand where the `#if` branches were). The
`RrhkStateId` and `RrhkBattery` fields follow the comments at `hosts.md:278-281`
and arrive with phase 6; the sketch below is the target.

```c
/* native/hostkit/hostkit.h -- target shape; phase 1 implements the 16-bit subset. */
typedef enum { RRHK_DIR, RRHK_FACE, RRHK_SYSTEM } RrhkGroup; /* FACE = autofire-eligible */

typedef struct {
    const char    *name;          /* "Button 1" (English, translated by the catalogue) */
    const wchar_t *ini_key;       /* legacy key kept per machine */
    uint32_t       bit;           /* bit in the pad word given to run_frame */
    RrhkGroup      group;
    /* default bindings per player: layout-aware scancodes, controller buttons */
    SDL_Scancode             key[RRHK_MAX_PLAYERS];
    SDL_GameControllerButton pad[RRHK_MAX_PLAYERS];
} RrhkAction;

typedef struct {
    const uint32_t *argb;         /* last completed picture, 0xAARRGGBB */
    int stride, width, height;    /* visible area inside the buffer */
    int raster_height;            /* aspect / interlace row geometry */
    int display_width;            /* after pixel-aspect correction (CPS-1, X68000) */
    int row_density;              /* 1 progressive, 2 interlace */
    int rotated;                  /* vertical monitor (CPS-1) */
    int crop_left;                /* VDP blanking crop (SMS) */
} RrhkFrame;

typedef struct { int x, y; bool offscreen, primary, secondary, aux, start; } RrhkPointer;

typedef struct { uint64_t native, interpreted_main, interpreted_audio, interpreted_device; } RrhkCoverage;

typedef struct { /* quick-state identity: magic, ABI string, compatible ABIs, ROM sha, PAL flag */
    /* fields per hosts.md:278 */
} RrhkStateId;

typedef struct { /* battery/memory card: size + load + save-if-dirty; kit owns file + atomic write */
    /* fields per hosts.md:280 */
} RrhkBattery;

typedef struct RrhkMachine {
    /* identity and layout */
    const char *ini_section;      /* "MegaDrive", "SNES", ... legacy names kept */
    const char *console_name;     /* "Mega Drive": help text, title */
    unsigned    players, pointers;
    const RrhkAction *actions; size_t action_count;
    int    max_width, max_height; double frame_seconds;
    int    audio_rate, audio_channels;      /* source rate; the kit converts, not the core */

    /* lifecycle */
    bool (*init)(bool headless);
    void (*reset)(void);
    void (*shutdown)(void);
    /* one guest frame; pads[p] holds that player's action bits; false = machine asks to stop */
    bool (*run_frame)(const uint32_t *pads, const RrhkPointer *pointers);
    void (*frame)(RrhkFrame *out);
    size_t (*audio)(int16_t *interleaved, size_t capacity);  /* PCM of the last frame */

    /* quick state: payload only; the kit owns header, ROM/ABI binding, CRC, atomic
       write, rollback, F8/F9 timing and the "state ready" boundary */
    bool     (*state_ready)(void);
    uint8_t *(*state_capture)(size_t *size);
    bool     (*state_restore)(const uint8_t *data, size_t size);
    RrhkStateId state;

    const RrhkBattery *battery;

    /* honesty counters shown in title, help and reports */
    void (*coverage)(RrhkCoverage *out);

    /* optional capabilities (NULL when absent) */
    const void *extra_pages;        /* DIP switches, gun page rows */
    const void *extra_options;      /* F5 enhanced / flicker, F11 AES, GB palette */
    void (*poll_input)(void);       /* guest-driven refresh (SMS/GG) */
    void (*on_discontinuity)(void); /* after reset/load: flush the machine's resampler */
    const void *trace;              /* extra columns for --trace / --report */
    const void *libretro;           /* optional libretro-shaped cores */
} RrhkMachine;

int rrhk_main(const RrhkMachine *machine, int argc, char **argv); /* windowed or headless */
```

### 2.2 From `rr16_*` to the kit

| Today (`retro_console16.h`) | Kit contract | Note |
| --- | --- | --- |
| `rr16_init`, `rr16_reset`, `rr16_shutdown` (lines 52-53, 62) | `init`, `reset`, `shutdown` | same lifecycle |
| `rr16_frame(p1, p2)` (54) | `run_frame(pads, pointers)` | one pad word per player; a false return means the machine asks to stop (`hosts.md:268-269`) |
| `rr16_pixels` (55) with `rr16_visible_width/height`, `rr16_raster_height`, `rr16_display_width` (69-79) | `frame()` filling `RrhkFrame` | visible area and geometry travel together (`hosts.md:242-248`) |
| `rr16_audio` (60) | `audio()` | PCM of the last frame; the source rate is table data (`hosts.md:262`) |
| `rr16_state_file` (63) | `state_ready` / `state_capture` / `state_restore` + `RrhkStateId` | the kit owns the envelope (magic, ABI, ROM binding, CRC, atomic write, rollback); payload code stays in the adapters (`hosts.md:273-278`, 336) |
| `rr16_cartridge_save` (80) | `battery` | the kit owns the file and the atomic write (`hosts.md:280-281`) |
| `rr16_interpreted`, `rr16_native_entries` (56-57), `rr16_audio_interpreted`, `rr16_audio_cpu` (65-66), `rr16_device_interpreted` (50) | `coverage()` | one struct; the device counter drives the cartridge-device title state |
| `rr16_game_mode`, `rr16_player_x` (58-59), `rr16_trace_details`, `rr16_report_details` (74, 77, 82) | `trace` | extra report/trace columns (`hosts.md:291`) |
| `rr16_audio_fingerprint`, `rr16_audio_frame_fingerprint` (67-68) | kit frame/audio hashing | (`hosts.md:320-321`) |
| `rr16_input_frame` (18, 31) | guest-frame counter | autofire counts guest frames (decision D4; `hosts.md:128`) |
| `rr16_host_frame_limit` (19), `rr16_host_test_tick` (20), `rr16_host_discontinuity` (21, 32) | pacing hook, hidden-window test hook, `on_discontinuity` | (`hosts.md:290`) |
| `rr16_pause` (61) | kit pause/menu loop | (`hosts.md:316`) |
| `rr16_sdl_main` (64) | `rrhk_main(machine, argc, argv)` | the loop moves into the kit (`hosts.md:295`) |

### 2.3 Kit services

Shell, one implementation for every family (`hosts.md:307-316`): SDL init and
hints chosen once per OS, window, icon, saved window rect, filters (sharp, xBR,
Scale2x, scanlines), integer and fit modes, one pacing loop with audio-lead
recovery, one audio output (callback ring, device-native format, optional FIR
source conversion, adaptive reserve), pad hotplug and slots, keyboard defaults
that follow the layout, one stick threshold, shift twin, autofire, quit and
restart combos, binding pages, gun/pointer mapping and reticle, F1 help
generated from the action and capability tables, F2 pages, options page,
notices, window title and fallback wording, catalogue lookup, pause/menu loop.

Core (`hosts.md:317-322`): ini access with one section schema plus legacy
readers, atomic writes, state container, battery container, one input-script
format (named actions from the adapter table), report and trace writer,
frame/audio hashing, and the command line (`--headless --frames --report
--trace --capture --input-script --save-state --save-at --load-state
--capture-every`, with machine extras forwarded to the adapter).

Machines that own their loop today (the Game Boy upstream platform, the NES
upstream runner) keep the loop and call kit functions (`rrhk_menu_event`,
`rrhk_present`, `rrhk_audio_push`) instead of `rrhk_main`; a libretro-shaped
core is wrapped by a small `rrhk_libretro_machine()` helper so future
libretro-shaped machines provide a core and a short action table only
(`hosts.md:298-303`).

## 3. Behaviour: one rule per divergence

Decisions (project owner, 27 October 2026), each applied as contract behaviour:

* **D1 — Stick dead zone 16000** for all families.
* **D2 — Windowed scaling: integer scale, centred**, for all; stretch exists
  only in a declared fullscreen mode.
* **D3 — Windows shell set for all families on Windows**: D3D11 renderer hint,
  joystick thread, per-monitor DPI, remembered window position/size.
* **D4 — One autofire behaviour**: `rr_autofire` semantics (each new press
  starts on, per button, guest-frame based) for all, X68000 included.
* **D5 — One audio delivery model**: callback ring for all.
* **D6 — F8/F9 always deferred** to a safe frame/CPU boundary.
* **D7 — Preferences in English sections and keys** for all (the layout of
  section 4), reading the old keys (SMS/GG French ones included) when the new
  key is absent, never deleting user settings.
* **D8 — One voice**: window title texts and the "physical latency unmeasured"
  honesty line identical for all families; fallback always shown per CPU and
  per cartridge device.

Rows marked **pending** have no decision yet; the kit rule above applies to
them (one behaviour for everyone, chosen with an A/B measurement and
documented before the phase that moves the family), and they are tracked in
section 8.

| # | Divergence today | Kit behaviour | Sources |
| --- | --- | --- | --- |
| 1 | Stick dead zone 12000 (SMS/GG, X68000) vs 16000 (NES, 16-bit); GB threshold upstream, unknown | 16000 for all (D1). The single kit threshold removes the GB fork | `host-divergences.md:12-22`; `hosts.md:127` |
| 2 | `rr_autofire` (SMS/GG, GB, NES, 16-bit) vs unconditional parity pulse with global clears (X68000) | `rr_autofire` semantics on every FACE-group action, per button, each new press starts on, guest frames (D4). The X68000 pulse is removed; its keyboard/mouse aliases are a capability to settle with that migration (open question 5) | `host-divergences.md:24-34`; `hosts.md:128,230` |
| 3 | F2 gamepad capture: selected-player guard (SMS/GG, 16-bit) vs any connected pad (NES, X68000); GB unknown | **Pending**: one rule for all, chosen and A/B measured before the first shell moves | `host-divergences.md:36-46` |
| 4 | Audio open flags and sample counts differ per family | One callback-ring output (D5) with one open-flag policy (format change allowed with retry, as SMS/GG/NES/GB today) and one requested period, fixed when the output is unified and re-measured before adoption; device negotiation changes land outside "unchanged" phases | `host-divergences.md:48-61`; `hosts.md:307-308,487-489` |
| 5 | Callback ring (SMS, GB, NES, MD runtime) vs `SDL_QueueAudio` push (SNES, NG, CPS-1, X68000) | Callback ring for all (D5). Machine source rates and channel layouts stay machine-specific | `host-divergences.md:63-68`; `hosts.md:131,187-191` |
| 6 | D3D11 driver hint, joystick thread, per-monitor DPI, renderer info line only on SMS/GG | The SMS/GG Windows set for every family (D3); POSIX keeps the vsync hint | `host-divergences.md:70-81`; `hosts.md:132` |
| 7 | Vsync: X68000 always requests it; others not on Windows, hint on POSIX | Within the single SMS/GG hint set (see row 4 sources): not requested on Windows, actual renderer state printed; POSIX hint kept; the X68000 always-on exception disappears; re-measured before adoption | `host-divergences.md:83-93`; `hosts.md:133,307-308` |
| 8 | Window position/size remembered only by SMS/GG, session-scope, not ini-persisted | Remembered for every family on Windows (D3), adopting the SMS/GG mechanism (restore at startup and when returning from fullscreen, save at shutdown). Persisting across runs is not claimed (open question 7) | `host-divergences.md:95-107`; `hosts.md:134,309` |
| 9 | Windowed scaling: integer+centred (SMS/GG) vs stretch/fit (NES, 16-bit, X68000); GB integer path patched upstream | Integer scale, centred, for all in windowed mode (D2); stretch only in a declared fullscreen mode | `host-divergences.md:109-120`; `hosts.md:135` |
| 10 | Pad slot policy: slot memory + swap + first-player preference (SMS) vs first free slot (others); GB policy upstream | Kit owns hotplug and slot assignment (`hosts.md:312`); the SMS swap and first-player preference stay declared machine capabilities (`hosts.md:175-178`). The base policy for the others is **pending** (open question 3) | `host-divergences.md:122-132` |
| 11 | Autofire feedback: SMS/GG toast, 16-bit/GB status lines, X68000 "Rapid fire", NES silent | One shared notice through the catalogue when the autofire step lands; wording chosen with it (**pending**, open question 4) | `host-divergences.md:134-144`; `hosts.md:137,315-316` |
| 12 | F8/F9: deferred to a safe CPU/state boundary (SMS/GG, 16-bit) vs executed from the event path (GB, NES, X68000 next frame) | Always deferred to a safe frame/CPU boundary (D6): the kit requests the operation and services it after `state_ready()` / the machine's safe boundary; GB, NES and X68000 stop executing it from the event path | `host-divergences.md:146-156`; `hosts.md:138,273-274` |
| 13 | Gun pages: `[LightPhaser]` 1..5 default 1; `[NES.Zapper]` 1..8 default 3; `[<Console>.Gun]` 1..12 default 3 + SNES turbo | One gun/pointer page, one mapping and one reticle in the kit, with per-machine size ranges and rows; ranges stay as today; sections rename to `[<Console>.Pointer]` through the mapping | `host-divergences.md:158-168`; `hosts.md:139,172-174,331`; `ini-migration.md:208-212,302-306` |
| 14 | Preference layouts: French sections/keys (SMS/GG), numeric English (NES, 16-bit), `[X68000] p0_key0`, flat GB file | English sections and keys for all (D7), per section 4; old keys read when the new one is absent; nothing deleted | `host-divergences.md:170-178`; `hosts.md:140`; `ini-migration.md:174-240` |
| 15 | Autofire stored in `[Manettes]`, `[X68000]`, GB flat `input.autofire` | `[Options] autofire` for every family (D7) | `host-divergences.md:180-188`; `ini-migration.md:192,286,307,315,338` |
| 16 | Title texts differ per family; the cartridge-device state is compiled away on NG/CPS/MD | One set of title states, worded once in the shared catalogue, identical for all families (D8); the cartridge-device state appears exactly when the machine's coverage reports a device; fallback always shown per CPU and per cartridge device | `host-divergences.md:190-200`; `hosts.md:142`; STANDARDS.md rule 8 |
| 17 | "physical latency unmeasured" printed by SMS/GG, 16-bit, X68000; silent on NES and GB | Every family prints the same honesty line (D8). No other latency claim is allowed | `host-divergences.md:202-212`; `hosts.md:143` |
| 18 | Diagnostic tags `[host]`, `[SDL]` (GB patches), `[player]` (X68000) | **Pending**: one tag or a fixed per-layer set, decided before the first shell moves | `host-divergences.md:214-225`; `hosts.md:144` |
| 19 | At least eight distinct ini writer paths | One kit ini layer: table-driven readers/writers; a write touches only the key being set and never deletes other sections; POSIX keeps lock-and-rename | `host-divergences.md:227-245`; `hosts.md:145`; `ini-migration.md:13-14,360-362` |
| 20 | Dead second renderer block in the X68000 shell, unreachable | Removed when the X68000 shell moves; zero behaviour change, covered by the unchanged proof | `host-divergences.md:247-257`; `hosts.md:146` |
| 21 | Help language lookup: inline `TR(en,fr)` pairs (SMS/GG), `tr()`+`rr_tr()` mix (NES, 16-bit), catalogue only (X68000, GB partly) | One lookup: the shared catalogue for everything; the inline pairs retire; rendered help must stay pixel-identical per language (EN, FR, IT, ES, DE) | `host-divergences.md:259-274`; `hosts.md:147,315-316,490-495` |

## 4. Preferences: one English layout, old keys still read

Files: Windows and POSIX use `datas/Retro-Recomp.ini`; Game Boy additionally
uses `datas/Retro-Recomp-GameBoy.ini`; POSIX reads the same logical keys
through `native/platform_io.c` with a lock-and-rename writer
(`ini-migration.md:4-7,13-14`).

Proposed layout (`ini-migration.md:174-227`):

```ini
[Interface]
language=en                ; en|fr|it|es|de

[Options]
quit_key0=0                ; SDL scancode integer
quit_key1=0
quit_key2=0
restart_key0=0
restart_key1=0
restart_key2=0
quit_pad=<bitmask>         ; integer controller-button bit mask
restart_pad=<bitmask>
autofire=0                 ; 0|1

[Audio]
filter=0                   ; 0 off, 1 light, 2 soft

[<Console>.Keyboard.PlayerN]
<Action>=<scancode>        ; numeric SDL scancode

[<Console>.Gamepad.PlayerN]
<Action>=<button>          ; numeric SDL_GameControllerButton, -1 unassigned

[<Console>.Video]
filter=0                   ; 0..3
display_mode=0             ; 0 window, 1 pixel/fullscreen integer, 2 fit
reduce_sprite_flicker=0    ; only SMS/NES

[<Console>.Pointer]
shape=0                    ; 0 cross, 1 dot
size=<range>               ; SMS 1..5; NES 1..8; MD/SNES 1..12
color=0                    ; 0 red, 1 green, 2 white
turbo=1                    ; SNES Super Scope only

[<Console>.Options]
fkeys_machine=0            ; only computer-like F-key machines, e.g. X68000

[<Console>.Runtime]
; console-specific runtime settings (Neo Geo enhanced/AES, X68000 guest keyboard)

[FallbackRecording]
<system>.<identity>=1
```

`<Console>` is one of `MasterSystem`, `GameGear`, `NES`, `MegaDrive`, `SNES`,
`NeoGeo`, `CPS1`, `X68000`, `GameBoy`; player numbering stays 1-based, and
`[CPS1.Dips.<set>] DSWA/DSWB/DSWC` keeps its schema-name sections
(`ini-migration.md:224-226`). Bindings use one English action name per action
per console, numeric values everywhere (`ini-migration.md:228-240`).

Migration rules (`ini-migration.md:342-358`):

1. Read the proposed new key.
2. If absent, read the exact listed old key with the listed value conversion
   (SMS/GG French keys included; `SMSRecomp.ini` stays a whole-file fallback
   only when `datas/Retro-Recomp.ini` does not exist, with the current
   copy-before-first-write behaviour).
3. Validate range/type after conversion; otherwise use the same default as an
   absent key.
4. Write only the new key when the user changes the setting.
5. Never delete old keys, old sections, or unknown keys.
6. For duplicated sources, use the source with the most specific new schema;
   X68000's `player.cfg` never overwrites values already loaded from the ini.
7. The helper is table-driven and unit-tested in both directions: the new
   reader reads every key the old writer produced and the reverse; a file with
   mixed old and new keys loses nothing.

The exact old→new mapping — shared keys, the SMS/GG French keys, NES/16-bit,
X68000 and Game Boy — is section 5 of the local survey `ini-migration.md`;
it is the authoritative table this contract points to. It stays a development
document until the kit lands, like the other local documents listed in
[INDEX.md](INDEX.md).

## 5. Machine-specific capabilities kept outside the kit

These stay behind capabilities in the adapter (`hosts.md:156-199`):

* **X68000**: full guest keyboard (scancode map, guest keyboard mode, F1-F10
  handover, Ctrl+Alt chords), captured relative mouse with the mouse-game
  profile, floppy drives (swap, eject, saved choices, disk snapshots,
  `--disk-events`), the fast-loading detector, variable resolution and
  RGB565/XRGB frames with 4:3 aspect from the core's AV info, IPL/CGROM/RAM
  identity in states, 61.46 fps timing taken from the core
  (`hosts.md:160-167`).
* **Light guns and pointers**: SMS Light Phaser (sensor timing on the cycle
  counter, P2 trigger alias), NES Zapper, Mega Drive Menacer/Justifier, SNES
  Super Scope/Justifier with Scope turbo and pause. The host-side part — mouse
  to picture coordinates, reticle, the F2 gun page — is kit; the sensor/IRQ
  emulation is the machine's (`hosts.md:168-174`).
* **Pads and buttons**: SMS/GG pause as a host-side Enter/P action and the Game
  Gear Start row; two-pad swap; Mega Drive six-button pad with Mode; SNES
  shoulders; Neo Geo A-D, coin and AES/MVS; CPS-1 six buttons, per-player coin,
  players 3 and 4 (`hosts.md:175-178`).
* **Pages and options with no other owner**: CPS-1 DIP switch page, Neo Geo F5
  enhanced mode and F11 AES/MVS restart, NES and SMS/GG sprite flicker
  reduction, Game Boy palette, Neo Geo boot cover (`hosts.md:179-183`).
* **Picture geometry**: CPS-1 rotated vertical monitors and non-square pixels,
  Mega Drive interlace row density, SMS VDP left-border blanking crop
  (`hosts.md:184-186`).
* **Sound sources**: each machine's native rate and channel layout (NG
  55,556 Hz, CPS-1 OKI/YM, GB 44.1 kHz, NES 48 kHz mono, X68000 44.1 kHz,
  SMS/GG PSG with FIR SRC, MD YM/PSG loop-bridge). The conversion to the device
  format and the ring are kit; only the source rate and layout are
  machine-specific (`hosts.md:187-191`).
* **Persistence payloads**: what a quick state or battery contains; cartridge
  SRAM/EEPROM mapping (MD, SNES), Neo Geo memory card, GB RTC
  (`hosts.md:192-193`).
* **Interpreter-fallback counters**: which CPU or device counts as
  "interpreted". Their display is common; their definition is the machine's
  (`hosts.md:194-195`).
* **Guest-driven input refresh** (SMS/GG): the guest polls a host callback at
  port reads, rate-limited to 1 ms, instead of one sample per frame. The
  `poll_input` capability keeps it; it is not a general requirement
  (`hosts.md:196-199`).

## 6. Fingerprints and file roles

Mechanics today (`hosts.md:348-359`): `role()` is host for a listed name,
build for the toolchain, **game for everything else, including every new
file**; `owners()` scopes by base-name prefix; `_resource_paths` hashes every
file under `native/`; Python modules are fingerprinted by compiled bytecode
including line tables.

Target, once the reproducible-stamp work lands — explicit stamp file lists and
fixed line endings — together with the kit phase 0 (role classification,
directory rule, directory-aware `owners()`), inside the single stamp-breaking
release (`PLAN.md:25-26,34-36,40,43,52`): every `native/hostkit/shell/*` file
and `retrorecomp/hostkit.py` is host role. Exports that link them are
**rebuilt, never rediscovered** (`hosts.md:389,392`); kit core files
(`native/hostkit/core/*`) stay game role because headless runs use them, and
are paid for once in the planned phase 6 campaign (`hosts.md:391`).

Status after phase 1: the stamp inputs are explicit lists, so every kit file is
listed in `retrorecomp/stamp_inputs.py` (host role, owned by Mega Drive, SNES,
Neo Geo and CPS-1; each adapter by its own console) and `retrorecomp/hostkit.py`
is a host module. The kit files live in `native/hostkit/{shell,adapters}/` with
unique `rrhk_` names (several engines own files called `audio.c` or `menu.c`
and a project builds one object per name). The staging code that copies host
files into a project belongs to the game-role modules `console16.py`,
`cps1_build.py` and `neogeo_build.py`; calling `hostkit.stage()` changed those
three modules once, which moves the game stamp of the four consoles once, and
every later kit edit is host-only (`tests/test_compilation_inputs.py`). Phase 2 (1.6.2)
adds the NES to the owners of the shell files and of `retrorecomp.hostkit`
(`rrhk_nes.c` by the NES alone, `rrhk_ring.c` with the shell); the staging call entered
the game-role module `nes_runtime.py` once, which moves the NES game stamp once. The
text below is the original reasoning, kept for the record.

Until that release, **no kit file goes into `native/`**: an unclassified new
file defaults to game role for all nine systems, and everything under
`native/` is hashed, so an unscoped `native/hostkit/` directory would change
every system's game stamp on arrival (full rediscovery of every export) and
keep invalidating all nine systems on every kit edit — the same
over-invalidation the survey measured for the unprefixed SMS/GG shell files
(`hosts.md:350-355,371,391-393`). The one-time cost is accepted and planned:
phase 0 moves all nine game stamps exactly once, and phases 1-5 edit no
game-role file (`hosts.md:393,404,412-414`).

## 7. Migration order and verification

Order (`hosts.md:426-461`), with the stamp effect of each phase
(`hosts.md:402-410`):

| Phase | Families | Content |
| --- | --- | --- |
| 0 | — | Kit skeleton, role classification and scoping, tests for roles, byte-identical project proofs; the one change that moves every game stamp; nothing else starts without it |
| 1 | Mega Drive, SNES, Neo Geo, CPS-1 | `console16_host_ui.c` splits into kit + adapters; 1a moves code with zero behaviour change, 1b removes the `#if` branches; waits for the in-flight CPS-1/X68000 branches |
| 2 | NES | Proves the kit on a second, non-16-bit-shaped loop (upstream runner). **Done in 1.6.2**, see "Phase 2" below |
| 3 | X68000 | Already MIT, already on the shared headers, libretro-shaped; resolves divergences 2, 3, 5 and 7 |
| 4 | Master System / Game Gear | Largest single shell; French ini legacy table, guest-driven input refresh, reset unwinding, window rect, the Windows hint set |
| 5 | Game Boy | Kit functions called from the patched upstream code, never the loop owner |
| 6 | all | Core flag day (state container with legacy magics, battery container, CLI/script/report, one OS layer), one planned requalification campaign; new machines can adopt shell and core from the first day after phase 1 |

Phases 2-5 touch disjoint files and can run in parallel after phase 1;
**no edit of a game-role file happens during phases 2-5** — adapters call the
existing game-role functions unchanged (`hosts.md:412-414`). Phase 1 is the one
exception: the staging call (`hostkit.stage()`) enters the game-role modules
`console16.py`, `cps1_build.py` and `neogeo_build.py` once, so the game stamp of
md, snes, ng and cps1 moves once, inside the 1.6.0 stamp break (the generated
code is unchanged, so the 1.5.6 stamps can be declared upgradable). Not covered
by the phase 1 A/B battery, so to be added in a later phase: menus driven by a
pad, pad capture from another pad, hot unplug, mouse clicks on option rows, F9
with no state or a failed save, audio open failures, quit by Escape, a fourth
CPS-1 player and a SNES cartridge-chip game.

Verification, per phase and per family — old executable A (current release)
against new executable B (kit build), same game, same inputs
(`hosts.md:463-511`):

* **Frames and audio source, bit identical**: headless runs with the same
  input script; `sequence_hash`, per-frame `frame_hash` and
  `audio_frame_fingerprint` equal.
* **States**: a state written by A loads in B and the continuation trace
  equals A's own; a state written by B loads in A; file bytes equal while the
  container is unchanged (phases 1-5 keep every magic, path and header; phase 6
  adds a versioned reader and tests the old files).
* **Audio output stage, sample identical** for fixed PCM input; device
  negotiation changes (divergence 4) are made one at a time, outside
  "unchanged" phases, with their own measurement.
* **Interface, pixel identical**: offscreen SDL capture (dummy video driver) of
  help, every F2 page, options, pause/notice, per language (EN, FR, IT, ES,
  DE) before and after, driven by scripted key and pad events.
* **Preferences**: B reads every key written by A and the reverse (including
  `[Clavier]`, `p0_key0`, the Game Boy file); no key is lost when two games
  share one ini.
* **Generated project**: where only staging changes, the generated project is
  byte-identical before and after.
* **Linux**: the same set on the Linux host with dummy SDL drivers or Xvfb;
  native Linux build is part of every phase.
* **Fingerprint tests**: the compilation-input tests are extended with the kit
  directories and scoping; a test fails if a game-role file changes during
  phases 1-5.

One or two test games per console (including a gun game for the pointer path,
an MVS and an AES Neo Geo, a two-player and a four-player CPS-1 game, a Zapper
game, an X68000 keyboard game, a mouse game and a two-disk game, a Light Phaser
game, a palette game); outputs under `.build/`, nothing placed in Export
(`hosts.md:507-511,468-469`).

Phase 1 measurements (Windows, MSVC build, offscreen SDL): `tools/hostkit_ab.py`
builds the old and the new host of the same game against a virtual clock, a
modelled audio device, scripted keys, pads and mouse, and compares the picture
read back at every frame, every push to the audio device, the window log, the
preferences file and the state files. It is the tool of every later phase.

The options page of F2 was unreadable on Linux (GCC) in every export that builds `game_options.h` (a returned `RrOptionRows` kept pointers into the callee's frame, which MSVC hides); the struct now holds its text only, and the page is proven readable on Linux and byte-identical to the Windows capture of the same game (CPS-1, 27 October 2026); `--no-options-page` only serves to compare against builds made before the fix.

Discipline: a host refactor claims only "unchanged" — never native-code
coverage, CPU fidelity, hardware fidelity, gameplay validation or physical
latency (`hosts.md:465-467`). Every behaviour change in section 3 is its own
documented step with its own A/B measurement and never rides on a phase that
claims "unchanged" (`hosts.md:487-489,546-548`).

### Phase 2: the NES (1.6.2)

`nes_host_ui.c` (511 lines) and `nes_audio_output.inc` (150) are gone. The NES runs the same shell as the 16-bit
consoles with `native/hostkit/adapters/rrhk_nes.c` (the action table, the F5 sprite-flicker option, the Zapper hook, the
runner's `cyc_sdl_main` entry) and one new shell file, `rrhk_ring.c`, the callback-ring sound output of the NES host
moved unchanged in its logic (`RRHK_AUDIO_RING`, selected by the adapter; the 16-bit consoles keep the queue model).
The runner's quick-state functions (`rr_nes_state_*`, `nes_state.c`) are called as they were: the state file, its magic,
its ABI key and the datas path are untouched, so exports and quick states of 1.6.0 and 1.6.1 carry over. Staging goes
through `hostkit.stage(project, 'nes')`, called once from `nes_runtime.py` (the one converter edit; it moves the NES game
stamp once, see [UPGRADES.md](UPGRADES.md#nes-exports-of-161-in-162-host-kit-phase-2)).

Kit switches the NES needed, each one a named per-machine setting of `RrhkMachine`, not an `if` on the machine:
`audio_model` / `audio_rate` / `audio_enable` (ring output), `capture_any_pad` (divergence 3), `pointer_section` and
`pointer_max` (the `[NES.Zapper]` section and its 1..8 size range, divergence 13), `pointer_keeps_player2` (the Zapper
game still reads the second pad), `save_failed_*` (the F8 failure wording).

Divergences, for this family:

| # | Status for the NES |
| --- | --- |
| 1 stick 16000 | decided (D1); the NES already used it, nothing changed |
| 2 autofire | decided (D4); the NES already used `rr_autofire` on A and B per guest frame; nothing changed |
| 3 F2 pad capture | **pending**: the NES keeps "any connected pad" (`capture_any_pad`) |
| 4 audio open flags and period | **pending** with the unified output: the NES keeps its flags (format change allowed with retry) and its 256-sample request |
| 5 callback ring | decided (D5); the NES already had it, and the kit now owns it (`rrhk_ring.c`); the 16-bit queue model is not moved in this phase |
| 6, 7, 8, 9 Windows set, vsync, window rectangle, integer scaling | decided (D2, D3) but they need the SMS/GG mechanism: landing with phase 4, not applied. The NES keeps its fit/integer rule, except that Pixel mode in a window smaller than 256 x 240 now fits the picture instead of cropping it (the kit's rectangle function) |
| 10 pad slots | **pending**: the NES keeps the first-free-slot policy (same as the kit's base) |
| 11 autofire notice | **pending**: the NES stays silent (its F6 goes through the adapter's `key_event`) |
| 12 F8/F9 deferred | decided (D6), applied: the kit services them at the top of the loop, after the events, instead of from the event path; the NES boundary is the frame boundary, so no observable change in the battery |
| 13 gun page, mapping, reticle | decided, applied: the NES uses the kit's pointer page, mapping and reticle. Visible changes on Zapper games only: the F2 page has no `>` marker (the highlight stays), the reticle is the kit's (thin cross, 2 pixels; dot sized in picture pixels), the system cursor shows over the window outside the picture, the mouse must have input focus, a setting change writes only its own key |
| 14, 15 preference layout, autofire key | decided (D7), **later** with the preferences phase: the NES still writes `[Manettes] autofire` and `[NES.Zapper]` |
| 16 title texts | decided (D8): the NES texts were already those of the kit |
| 17 latency line | decided (D8), applied: the NES ring output's closing line ends with "physical latency unmeasured" |
| 18 diagnostic tags | **pending**: `[host]` kept |
| 19 ini writers | decided: the NES already used the shared ini layer |
| 20 dead renderer block | X68000 only |
| 21 help language lookup | decided: rendered help is identical in the five languages (A/B captures) |

Also differing from the old NES host, with no decision on file and no observable effect in the battery: the window title
is set once at the start (the same text), the kit's hidden-window test hooks (`RETRORECOMP_HOST_TEST_FRAMES`, ...) and
the explicit timing report (`RETRORECOMP_TIMING_REPORT`) now exist for the NES too, and the pad word is sampled while a
menu is open (autofire memory only).

Measurements (Windows, MSVC, offscreen SDL, `tools/hostkit_ab.py`, one script of 3,700 loop iterations: every key and
controller button of both players, the stick around its threshold, autofire, filters and display modes, F8/F9, reset,
every F2 page and the help in five languages, rebinding, quit/restart combinations, F5 sprites, hot-plug):

* Donkey Kong (NES, mapper 0, NTSC; no Zapper): old host against kit host, same generated game, 3,707 loop iterations.
  **Identical**: 3,707 presented pictures (hash of every one), 11,486 audio callback blocks (hash of each, 2,694,634
  samples produced, 2,671,515 played, 0 missing, 0 trimmed, both sides), both controller words at every frame, the window
  and fullscreen log, the preferences file, the quick-state file (330,024 bytes, byte equal), and 36 saved captures (help
  and every F2 page in five languages, rebinding, combinations, options, sprites). Only stderr differs, by the one
  sentence decision D8 adds ("physical latency unmeasured"), left out of the comparison.
* Duck Hunt (NES, Zapper): the same battery with the mouse outside the window (`--ignore-events C`): 3,745 pictures, all
  identical but the 41 in which the Zapper page of F2 is on screen (the missing `>` marker); audio, pads, states and
  preferences identical. A second script with the mouse moved, clicked and taken off the picture (3,910 iterations): the
  3,462 aim calls (position, trigger, off-picture flag) are identical in both runs; the pictures differ by the reticle, the
  gun page and the cursor lines, as listed above; the preferences hold the same keys and values (the old host wrote
  `shape` first, the kit writes the key it changes).
* Mega Drive (Alex Kidd in the Enchanted Castle), regression of the shared shell: the shell of 1.6.1 against this one,
  same project, 3,694 iterations: **identical** pictures, window log, state file and 35 captures.
* ROM-free: `tools/nes_audio_selftest.py` (the ring against 160 authored timelines, now compiled from `rrhk_ring.c`),
  `tools/autofire_selftest.py` and `tools/start_select_selftest.py` (the NES fixture is now the kit's input module with the
  adapter's action table), all passing; a fresh conversion of Donkey Kong with the kit builds, validates and keeps the
  same quick-state key (`RR_NES_STATE_ABI`).

Not covered by this battery (as for phase 1): menus driven by a pad, hot unplug, mouse clicks on option rows, F9 with no
state or a failed save, audio open failures, a NES game with PAL timing or an expansion-audio mapper, Linux.

## 8. Open questions

1. **Game Boy upstream rows**: the exact behaviour of divergences 1, 3, 5, 8
   and 9 needs the upstream `platform_sdl.cpp`, absent from the survey
   checkout (`host-divergences.md:285-286`; `hosts.md:538-540`).
2. **F2 capture rule** for all families: selected-player guard or any pad
   (`host-divergences.md:36-46`).
3. **Base pad-slot policy** (first free vs slot memory); the SMS swap and
   first-player preference stay machine capabilities (`hosts.md:175-178`).
4. **Autofire notice wording and diagnostic tag**: one text and one tag for
   all, or a fixed per-layer set (`host-divergences.md:134-144,214-225`).
5. **X68000 autofire aliases**: what guest-keyboard keys and mouse buttons do
   once autofire follows `rr_autofire` semantics (`host-divergences.md:32`).
6. **One requested audio period** (256 vs 512 today) and the Mega Drive final
   period, not visible in the checkout (`host-divergences.md:55-67`).
7. **Window rect scope**: session memory (today's SMS/GG mechanism) vs
   persisted across runs (`host-divergences.md:95-107`).
8. **Not yet examined**: SMS/GG battery handling and the X68000 libretro
   bridge (`hosts.md:541-542`).
9. **Product docs to update when the kit lands**: `docs/UPGRADES.md` (shell
   table), `docs/CONTROLS.md`, `docs/COMPILATION_LIBRARY.md`, and the local
   `PROJECT_STATE.md` (`hosts.md:549-551`).

The kit's own effort estimates stay in the local plan (`hosts.md:513-531`);
they are not part of this public contract.
