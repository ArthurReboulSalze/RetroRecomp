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

Machines that own their loop (the Master System and Game Gear guest, the Game Boy upstream platform, the NES
upstream runner) keep the loop and call the kit's functions instead of `rrhk_main`: the driven mode (`rrhk_open`,
`rrhk_frame_done`, `rrhk_close`, phases 4 and 5); a libretro-shaped
core is wrapped by a small `rrhk_libretro_machine()` helper so future
libretro-shaped machines provide a core and a short action table only
(`hosts.md:298-303`).

## 3. Behaviour: one rule per divergence

Decisions (project owner, 27 October 2026; D9, D10 and D11 on 28 October 2026), each applied as contract behaviour. A
standing rule of the maintainer (28 October 2026): **every host behaviour rule decided for one machine applies to the
X68000 too, without asking again**.

* **D1 — Stick dead zone 16000** for all families.
* **D2 — Windowed scaling: integer scale, centred**, for all; stretch exists
  only in a declared fullscreen mode.
* **D3 — Windows shell set for all families on Windows**: D3D11 renderer hint,
  joystick thread, per-monitor DPI, remembered window position/size.
* **D4 — One autofire behaviour**: `rr_autofire` semantics (each new press
  starts on, per button, guest-frame based) for all, X68000 included. Settled for the X68000 on 28 October 2026 ("same
  rules on every machine", maintainer): its face buttons follow the common rule exactly, a key or a mouse button bound
  to such a button *is* that button, and no X68000-specific pulse remains (open question 5).
* **D5 — One audio delivery model**: callback ring for all.
* **D6 — F8/F9 always deferred** to a safe frame/CPU boundary.
* **D7 — Preferences in English sections and keys** for all (the layout of
  section 4), reading the old keys (SMS/GG French ones included) when the new
  key is absent, never deleting user settings.
* **D8 — One voice**: window title texts and the "physical latency unmeasured"
  honesty line identical for all families; fallback always shown per CPU and
  per cartridge device.
* **D9 — F2 gamepad capture takes the selected player's pad only** (28 October
  2026, Arthur), for every console: a press on another connected pad is ignored
  while a row waits for a control.
* **D10 — One autofire notice** (28 October 2026, Arthur), for every console:
  F6 shows a short pop-up, "Autofire ON" / "Autofire OFF", about 1.8 s like the
  shell's other notices, from the shared eight-language catalogue.
* **D11 — Pad slot policy: Automatic by default, a Gamepad row per player** (28 October 2026, Arthur), for every
  console. By default pads go to players in plug order, the first free player. On each player's gamepad page of F2 a
  "Gamepad" row cycles Automatic, each connected controller (by its SDL name, numbered when two share a name) and
  None. Choosing a controller pins it to that player and takes it from the player that holds it, who falls back to
  Automatic among the remaining pads; None leaves that player without a pad (the keyboard still works, so player 1 on
  None and one pad gives keyboard for player 1 and pad for player 2). The choice is kept in the game's preferences
  (section 4): `device` is `auto`, `none` or the SDL joystick GUID, `name` the controller's name for display. A pinned
  controller that is not plugged in is shown as "disconnected", its player has no pad meanwhile (never another pad), and
  hot-plug gives it back; two identical pads share a GUID and the first unclaimed one matches (the "#n" of the row is
  the plug order of the moment, not a saved identity: after a restart the first identical pad found goes to the first
  pinned player); every player keeps the pad it holds before a pinned player looks for a missing one, so unplugging one
  of two identical pinned pads never moves the other; an Automatic player never takes a pad pinned to another player. Setting a player back to Automatic deals the automatic players' pads again in
  plug order, as at the next start. The F2 binding of a player who has no pad shows "No gamepad for player N" instead
  of waiting silently (Esc still leaves). Keyboard and pad keep working together, and the stick, autofire and pointer
  rules are unchanged. This policy replaces the SMS/GG first-player toggle and pad swap, which went away when SMS/GG moved to the kit (phase 4, 1.6.3).

* <a id="d12"></a>**D12 — The Game Boy's former sound and speed controls, on every console** (29 October 2026, maintainer: "same rules on
  every machine" means harmonising up, never removing a feature; this settles open question 10). Phase 5 had retired five things the
  upstream Game Boy shell offered behind keys no page listed; they are kit features, with their former keys and behaviour, on the nine
  consoles:
  * **Fast-forward**: **Tab held** or the **right trigger** (a pad a player holds; past the stick threshold, D1): 250% of the machine's
    speed. **Maximum speed**: **backquote** (`SDL_SCANCODE_GRAVE`) or the **left trigger** toggles 500% until pressed again. Both ran at
    those ratios upstream (`GB_FAST_FORWARD_SPEED_PERCENT` 250, `GB_MAX_SHORTCUT_SPEED_PERCENT` 500), and the maximum wins over the hold.
    Only the pacing changes: the deadline of each guest frame is divided by the speed, the picture of every frame is still presented,
    the machine runs the same frames in the same order, autofire counts guest frames (D4), a quick state still waits for its safe
    boundary (D6) and the driven machines (Master System, Game Gear, Game Boy) are paced from the same call. A menu or a pause stops the
    machine at any speed. **Sound meanwhile is dropped**, as upstream played it only at 100%: the shell takes what the machine
    produced and throws it away (kit ring and queue), the machine is told to hold its own output through its `pause` hook (Mega Drive
    engine playback, the Master System and Game Gear device, the Neo Geo and CPS-1 resamplers) and the stage below also silences
    whatever still arrives; the output is cleared at each change of speed, so that it starts again clean at 100%.
  * **Mute**: **M** toggles, kept. **Volume**: 0 to 200% (100% is the machine's sound as it is), a row of the options page. **Output
    device**: a row of the options page, the system default or one of the devices SDL lists (the upstream panel's combo); a device
    that cannot be opened falls back to the default with a line on stderr, and a device unplugged while in use (SDL's
    `SDL_AUDIODEVICEREMOVED`) is replaced by the default, **on every console**: the machines that own their device say which one it is
    (`RrhkMachine.audio_device_id`: the Master System and Game Gear output, the Mega Drive engine's `rr_md_audio_device_id`). A kit
    device that is gone (a queue closed after a failed push, a ring that could not open) is opened again through the opening path
    when another device is chosen. The cycle lists at most 32 devices (the rest of SDL's list is not offered). A choice **applies even
    when the preferences file cannot be written** (a read-only install): the page then says "Config unavailable", as F3 does, and the
    choice lasts until the program ends. All of it acts on what reaches the device, never on the machine, so the guest's own sound state is unchanged.
  * **Keys**: Tab, backquote and M are in no machine's default controls (checked on the nine action tables) and in no kit key; a key a
    player has bound to a control keeps that control (the shortcut is then off), they are not offered while a binding is being
    captured, nor to a machine that has the keyboard (`keyboard_pad` false: the X68000 in full guest typing, where the options rows
    remain), and a Tab pressed in a menu does not start a hold. A key that is part of the Quit or Restart combination (keyboard) is not a sound key
    either, as it is not the Pause key. Plugging or unplugging a pad ends a fast-forward held with a trigger (the slots are dealt again). The X68000 keeps its **F5** fast loading (unthrottled, silent, one
    picture in eight) as it is, and the Tab help page; in game-shortcut mode its keyboard is not passed to the guest, so the three
    keys are free there. Documented in the F1 help of every console (one line) and in [CONTROLS.md](CONTROLS.md#speed-and-sound).
  * **Where**: one sound stage, `rrhk_options_audio` (volume, mute, hold, then the audio filter), which every output already called
    for the audio filter: the kit's ring (NES, Game Boy), the kit's queue (Super Nintendo, Neo Geo, CPS-1, X68000), the Master System
    and Game Gear output (`audio_output.inc`) and, since 1.6.3, the Mega Drive engine's callback (`megadrive_audio.py`; this also makes
    the audio-filter row, offered there and never applied, work on the Mega Drive). The device is asked of the kit by every opener
    (`rrhk_audio_device()`); the machines that own their device reopen it through `RrhkMachine.audio_reopen` (Mega Drive, Master
    System, Game Gear) and attach the stage through `sound_ready`. Preferences: `audio_volume`, `audio_muted` and `audio_device` in
    `[<Console>.Options]`; the Game Boy's flat file of 1.6.2 (`audio.volume_percent`, `audio.muted`, `audio.device_name`) is read
    where they are absent.
  * **Not restored**: the upstream speed slider (10 to 500%, not kept between runs), the audio latency setting and the second binding
    of each button: it needs a second key and button per action in the contract (`RrhkAction`, the binding pages and the preferences),
    which is a contract change and a divergence of its own; it stays retired, and no other console has it.

Rows marked **pending** have no decision yet; the kit rule above applies to
them (one behaviour for everyone, chosen with an A/B measurement and
documented before the phase that moves the family), and they are tracked in
section 8.

| # | Divergence today | Kit behaviour | Sources |
| --- | --- | --- | --- |
| 1 | Stick dead zone 12000 (SMS/GG, X68000) vs 16000 (NES, 16-bit); GB threshold upstream, unknown | 16000 for all (D1). The single kit threshold removes the GB fork | `host-divergences.md:12-22`; `hosts.md:127` |
| 2 | `rr_autofire` (SMS/GG, GB, NES, 16-bit) vs unconditional parity pulse with global clears (X68000) | `rr_autofire` semantics on every FACE-group action, per button, each new press starts on, guest frames (D4). **Applied to the X68000 in phase 3** (decided 28 October 2026, "same rules on every machine", maintainer, which settles open question 5): both game buttons are FACE actions, the key or mouse button bound to one of them is that button and is released with it, the unconditional pulse is gone | `host-divergences.md:24-34`; `hosts.md:128,230` |
| 3 | F2 gamepad capture: selected-player guard (SMS/GG, 16-bit) vs any connected pad (NES, X68000); GB unknown | **Decided on 28 October 2026 (Arthur, D9)**: the selected player's pad only, for every console. The kit shell applies one guard; the `capture_any_pad` setting is gone. The same rule covers the gamepad Quit/Restart combinations of F2 (1.6.3: the kit sets `capture_guard`/`capture_from` in `game_options.h` from the selected player's pad; same rules on every machine, Arthur, 28 October 2026). Applied to the consoles on the kit (Mega Drive, SNES, Neo Geo, CPS-1, NES: the NES changed; the X68000 took any connected pad before phase 3, and SMS/GG applied it to their combinations in phase 4: they already guarded the button bindings); applied to the Game Boy in phase 5 | `host-divergences.md:36-46` |
| 4 | Audio open flags and sample counts differ per family | One callback-ring output (D5) with one open-flag policy (format change allowed with retry, as SMS/GG/NES/GB today) and one requested period, fixed when the output is unified and re-measured before adoption; device negotiation changes land outside "unchanged" phases | `host-divergences.md:48-61`; `hosts.md:307-308,487-489` |
| 5 | Callback ring (SMS, GB, NES, MD runtime) vs `SDL_QueueAudio` push (SNES, NG, CPS-1, X68000) | Callback ring for all (D5). Machine source rates and channel layouts stay machine-specific | `host-divergences.md:63-68`; `hosts.md:131,187-191` |
| 6 | D3D11 driver hint, joystick thread, per-monitor DPI, renderer info line only on SMS/GG | The SMS/GG Windows set for every family (D3); POSIX keeps the vsync hint. **Applied in phase 4** (`rrhk_main.c`: the hints before `SDL_Init`, the renderer line after the renderer is made) | `host-divergences.md:70-81`; `hosts.md:132` |
| 7 | Vsync: X68000 always requests it; others not on Windows, hint on POSIX | Within the single SMS/GG hint set (see row 4 sources): not requested on Windows, actual renderer state printed; POSIX hint kept; the X68000 always-on exception disappears; re-measured before adoption | `host-divergences.md:83-93`; `hosts.md:133,307-308` |
| 8 | Window position/size remembered only by SMS/GG, session-scope, not ini-persisted | Remembered for every family on Windows (D3), adopting the SMS/GG mechanism (restore at startup and when returning from fullscreen, save at shutdown). Persisting across runs is not claimed (open question 7) | `host-divergences.md:95-107`; `hosts.md:134,309` |
| 9 | Windowed scaling: integer+centred (SMS/GG) vs stretch/fit (NES, 16-bit, X68000); GB integer path patched upstream | Integer scale, centred, for all in windowed mode (D2); stretch only in a declared fullscreen mode. **Opening window = the largest integer multiple of the machine's native picture that fits the usable display area** (at most 85% of `SDL_GetDisplayUsableBounds`, at least 1x; a remembered window rectangle (D3) wins); a machine whose opening size is already an exact multiple of its picture keeps it | `host-divergences.md:109-120`; `hosts.md:135` |
| 10 | Pad slot policy: slot memory + swap + first-player preference (SMS) vs first free slot (others); GB policy upstream | **Decided on 28 October 2026 (Arthur, D11)**: Automatic (first free player, plug order) stays the default, and each player's gamepad page of F2 gets a "Gamepad" row (Automatic, each connected controller, None) that pins a controller to that player or leaves the player without one; kept per player as `device` and `name` in the gamepad section of the preferences. The kit owns hot-plug and slot assignment (`hosts.md:312`); the SMS/GG first-player toggle and pad swap were replaced by this row when SMS/GG migrated (phase 4: they are no longer machine capabilities). Applied to the consoles on the kit (Mega Drive, SNES, Neo Geo, CPS-1, NES, X68000, and since phase 4 SMS/GG); applied to the Game Boy in phase 5 | `host-divergences.md:122-132` |
| 11 | Autofire feedback: SMS/GG toast, 16-bit/GB status lines, X68000 "Rapid fire", NES silent | **Decided on 28 October 2026 (Arthur, D10)**: one short shared pop-up on every console, "Autofire ON" / "Autofire OFF" (about 1.8 s), the two catalogue entries that already exist in the eight languages (`assets/locales/*.json`, section `runtime`; games draw the five Latin ones). F6 is the shell's key on every kit console, the NES included. Applied to the consoles on the kit (the X68000's "Rapid fire" retired in phase 3, the SMS/GG toast with its "Tir auto" wording in phase 4); Applied to the Game Boy in phase 5 (its status line retired) | `host-divergences.md:134-144`; `hosts.md:137,315-316` |
| 12 | F8/F9: deferred to a safe CPU/state boundary (SMS/GG, 16-bit) vs executed from the event path (GB, NES, X68000 next frame) | Always deferred to a safe frame/CPU boundary (D6): the kit requests the operation and services it after `state_ready()` / the machine's safe boundary; GB, NES and X68000 stop executing it from the event path | `host-divergences.md:146-156`; `hosts.md:138,273-274` |
| 13 | Gun pages: `[LightPhaser]` 1..5 default 1; `[NES.Zapper]` 1..8 default 3; `[<Console>.Gun]` 1..12 default 3 + SNES turbo | One gun/pointer page, one mapping and one reticle in the kit, with per-machine size ranges and rows; ranges stay as today; sections rename to `[<Console>.Pointer]` through the mapping | `host-divergences.md:158-168`; `hosts.md:139,172-174,331`; `ini-migration.md:208-212,302-306` |
| 14 | Preference layouts: French sections/keys (SMS/GG), numeric English (NES, 16-bit), `[X68000] p0_key0`, flat GB file | English sections and keys for all (D7), per section 4; old keys read when the new one is absent; nothing deleted | `host-divergences.md:170-178`; `hosts.md:140`; `ini-migration.md:174-240` |
| 15 | Autofire stored in `[Manettes]`, `[X68000]`, GB flat `input.autofire` | `[Options] autofire` for every family (D7) | `host-divergences.md:180-188`; `ini-migration.md:192,286,307,315,338` |
| 16 | Title texts differ per family; the cartridge-device state is compiled away on NG/CPS/MD | One set of title states, worded once in the shared catalogue, identical for all families (D8); the cartridge-device state appears exactly when the machine's coverage reports a device; fallback always shown per CPU and per cartridge device | `host-divergences.md:190-200`; `hosts.md:142`; STANDARDS.md rule 8 |
| 17 | "physical latency unmeasured" printed by SMS/GG, 16-bit, X68000; silent on NES and GB | Every family prints the same honesty line (D8). No other latency claim is allowed | `host-divergences.md:202-212`; `hosts.md:143` |
| 18 | Diagnostic tags `[host]`, `[SDL]` (GB patches), `[player]` (X68000) | **Pending**: one tag or a fixed per-layer set; the shells moved so far keep their tags until it is decided | `host-divergences.md:214-225`; `hosts.md:144` |
| 19 | At least eight distinct ini writer paths | One kit ini layer: table-driven readers/writers; a write touches only the key being set and never deletes other sections; POSIX keeps lock-and-rename | `host-divergences.md:227-245`; `hosts.md:145`; `ini-migration.md:13-14,360-362` |
| 20 | Dead second renderer block in the X68000 shell, unreachable | Removed when the X68000 shell moves; zero behaviour change, covered by the unchanged proof | `host-divergences.md:247-257`; `hosts.md:146` |
| 21 | Help language lookup: inline `TR(en,fr)` pairs (SMS/GG), `tr()`+`rr_tr()` mix (NES, 16-bit), catalogue only (X68000, GB partly) | One lookup: the shared catalogue for everything; the inline pairs retire; rendered help must stay pixel-identical per language (EN, FR, IT, ES, DE) | `host-divergences.md:259-274`; `hosts.md:147,315-316,490-495` |
| 22 | Fast-forward, maximum speed, mute, volume and output device: the Game Boy upstream shell only (behind keys no page listed), none elsewhere | **Decided on 29 October 2026 (maintainer, D12)**: kit features with the Game Boy's former keys and behaviour on every console; see D12 above, and the measurements in "Sound and speed controls: A/B" after phase 5 | `docs/CONTROLS.md` |

## 4. Preferences: one English layout, old keys still read

Files: Windows and POSIX use `datas/Retro-Recomp.ini`; Game Boy used to add
`datas/Retro-Recomp-GameBoy.ini` (since 1.6.3 it is only read, as the former file of that console: phase 5); POSIX reads the same logical keys
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
device=auto                ; D11, which controller the player uses: auto | none | the SDL joystick GUID (32 hex digits)
name=                      ; the pinned controller's name, for display only (empty unless device is a GUID)

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
audio_filter=0             ; 0 off, 1 light, 2 soft
audio_volume=100           ; D12: 0..200 percent
audio_muted=0              ; D12: 0|1
audio_device=              ; D12: the output device by the name SDL lists it, empty for the system default
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

* **X68000** (adapter `rrhk_x68k.inc`): full guest keyboard (scancode map, guest keyboard mode, F1-F10
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
* **Pads and buttons**: SMS/GG pause as a host-side Start/Menu action (a row with no pad bit, the Pause menu) and the Game
  Gear Start row; Mega Drive six-button pad with Mode; SNES
  shoulders; Neo Geo A-D, coin and AES/MVS; CPS-1 six buttons, per-player coin,
  players 3 and 4 (`hosts.md:175-178`). The SMS/GG two-pad swap and
  first-player toggle are not kept: the Gamepad row (D11) replaces them when
  SMS/GG migrates.
* **Pages and options with no other owner**: CPS-1 DIP switch page, Neo Geo F5
  enhanced mode and F11 AES/MVS restart, NES and SMS/GG sprite flicker
  reduction, Game Boy palette (F5, adapter `rrhk_gb.inc`), Neo Geo boot cover (`hosts.md:179-183`).
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

Phase 4 (1.6.3) adds the Master System and the Game Gear to the owners of the shell files, of `console16_video.h` and of
`retrorecomp.hostkit`; `rrhk_sms.c` is a host file owned by both (one adapter, `RETRO_GAME_GEAR` chooses the console). They
compile the kit from the common runtime folder: `core.prepare_native_source` stages it beside `native/CMakeLists.txt`
(`hostkit.stage(native_source, "sms")`), the one converter edit, game role, owned by every console like the rest of
`core.py`. `native/host.c`, `controls.c/.h` and `ui.c/.h` are removed from the host stamp of every console (they were owned
by all of them). See [UPGRADES.md](UPGRADES.md#master-system-and-game-gear-exports-in-163-host-kit-phase-4).

Phase 5 (1.6.3) adds the Game Boy to the owners of the shell files, of `console16_video.h` and of `retrorecomp.hostkit`; the
adapter `rrhk_gb.inc` is a host file owned by the Game Boy alone. The Game Boy compiles the kit inside the runtime library of its
project: `gameboy_host.adapt_shell` stages it (`hostkit.stage(project, "gb")`, adapter included but not listed as a source: the patched
`platform_sdl.cpp` includes it) and `gameboy_runtime` lists the shell in its CMake file, both game role (the stamp of the Game Boy
moves once). `gb_menu.inc`, `gb_audio_output.inc`, `gb_input_refresh.inc` and `gameboy_timing.py` are gone from the stamps. See
[UPGRADES.md](UPGRADES.md#game-boy-exports-in-163-host-kit-phase-5).

Status after phase 1: the stamp inputs are explicit lists, so every kit file is
listed in `retrorecomp/stamp_inputs.py` (host role, owned by Mega Drive, SNES,
Neo Geo and CPS-1; each adapter by its own console) and `retrorecomp/hostkit.py`
is a host module. The kit files live in `native/hostkit/{shell,adapters}/` with
unique `rrhk_` names (several engines own files called `audio.c` or `menu.c`
and a project builds one object per name). The staging code that copies host
files into a project belongs to the game-role modules `console16.py`,
`cps1_build.py` and `neogeo_build.py`; calling `hostkit.stage()` changed those
three modules once, which moves the game stamp of the four consoles once, and
every later kit edit is host-only (`tests/test_compilation_inputs.py`). Phase 3 (1.6.3) adds the X68000 to the owners
of the shell files and of `console16_video.h`; its adapter `rrhk_x68k.inc` is a host file owned by the X68000 alone and
replaces `player_ui.inc`; the X68000 compiles the kit from the tree and has no staging call, but `reference_host.c` and
its CMake file (game role) change, which moves the X68000 game stamp, the SDK stamp and the quick-state key once
([UPGRADES.md](UPGRADES.md#x68000-exports-in-163-host-kit-phase-3)). Phase 2 (1.6.2)
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
| 3 | X68000 | Already MIT, already on the shared headers, libretro-shaped; resolves divergences 2, 3, 5 and 7. **Done in 1.6.3**, see "Phase 3" below |
| 4 | Master System / Game Gear | Largest single shell; French ini legacy table, guest-driven input refresh, reset unwinding, window rect, the Windows hint set. **Done in 1.6.3**, see "Phase 4" below |
| 5 | Game Boy | Kit functions called from the patched upstream code, never the loop owner. **Done in 1.6.3**, see "Phase 5" below |
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
`audio_model` / `audio_rate` / `audio_enable` (ring output), `pointer_section` and
`pointer_max` (the `[NES.Zapper]` section and its 1..8 size range, divergence 13), `pointer_keeps_player2` (the Zapper
game still reads the second pad), `save_failed_*` (the F8 failure wording). A `capture_any_pad` setting existed in phase 2
for divergence 3; it was removed on 28 October 2026 when the rule was decided (see below).

Divergences, for this family:

| # | Status for the NES |
| --- | --- |
| 1 stick 16000 | decided (D1); the NES already used it, nothing changed |
| 2 autofire | decided (D4); the NES already used `rr_autofire` on A and B per guest frame; nothing changed |
| 3 F2 pad capture | decided 28 October 2026 (D9), applied after phase 2: the NES takes the selected player's pad only, like the 16-bit consoles (it took any connected pad in phase 2); the `capture_any_pad` setting is removed |
| 4 audio open flags and period | **pending** with the unified output: the NES keeps its flags (format change allowed with retry) and its 256-sample request |
| 5 callback ring | decided (D5); the NES already had it, and the kit now owns it (`rrhk_ring.c`); the 16-bit queue model is not moved in this phase |
| 6, 7, 8, 9 Windows set, vsync, window rectangle, integer scaling | decided (D2, D3) but they needed the SMS/GG mechanism: **applied in phase 4** (see below), not in phase 2. The NES keeps its fit/integer rule, except that Pixel mode in a window smaller than 256 x 240 now fits the picture instead of cropping it (the kit's rectangle function) |
| 10 pad slots | decided 28 October 2026 (D11), applied after phase 2: Automatic (first free slot, as in phase 2) stays the default; the F2 gamepad pages gain the Gamepad row and the `device` / `name` keys. The Zapper keeps reading the second pad (`pointer_keeps_player2`) |
| 11 autofire notice | decided 28 October 2026 (D10), applied after phase 2: F6 is no longer handled by the adapter's `key_event`, so the shell's own F6 runs on the NES (same toggle, same memory reset, same `[Manettes] autofire` write) and shows the shared notice "Autofire ON" / "Autofire OFF" (the NES was silent in phase 2) |
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

Divergences 3 and 11 (28 October 2026), measured the same way (`tools/hostkit_ab.py`, Windows, MSVC, offscreen SDL, the
kit of 1.6.2 before the change against after it, same generated project): Donkey Kong (NES) and Blockout (Mega Drive).
The standard battery on the NES (3,707 iterations): the 36 captures, the state file, the preferences, the audio log and
both controller words are identical; the only differing pictures are the 144 consecutive frames of the two F6 presses
(429-572), which now carry the notice. A short script with two virtual pads (rebinding from the other player's pad, F6 in
each language, F6 with the help open, 2,373 iterations): on the NES the old host bound a press of the other player's pad
and the new one keeps "Press a control..." until the selected player's own pad is pressed (both preferences files differ
by exactly that binding); the notice reads "Autofire ON / OFF", "Fuoco automatico ON", "Dauerfeuer AUS", and so on. On the
Mega Drive both scripts are **identical** (pictures, states, preferences, logs): its guard and its notice text were
already these. Not run: the consoles of the kit other than these two (same shell code), Linux.

Not covered by this battery (as for phase 1): menus driven by a pad, hot unplug, mouse clicks on option rows, F9 with no
state or a failed save, audio open failures, a NES game with PAL timing or an expansion-audio mapper, Linux.

### Phase 3: the X68000 (1.6.3)

`player_ui.inc` (383 lines) and the window, picture, sound and pad code of `reference_host.c` are gone. The X68000 runs
the shell of the other consoles with `native/hostkit/adapters/rrhk_x68k.inc`, an adapter that `reference_host.c`
includes (one translation unit, like the old `player_ui.inc`: the frontend owns the libretro core, the disks and the
quick-state envelope, and a separate file would have needed a dozen of its statics exported). The kit's loop calls the
adapter's `run_frame`, which hands the pad words to the core's input callback and runs `host_frame()`, the body of the old
loop moved into a function that the headless loop calls too: the checks, reports, traces, disk events and `--state-*`
options are the same code as before (a 600-frame headless trace of the old and the new executable is byte identical).
The kit's files are compiled from the tree (`native/x68000_reference/CMakeLists.txt` lists the shell), not staged: the
X68000 export is built from the repository, so `hostkit.stage` is not used and `retrorecomp.hostkit` is not an X68000
input.

What the X68000 keeps as its own, behind hooks of `RrhkMachine` (HOST_KIT.md section 5): the guest keyboard and its
Ctrl+Alt chords (`event`, `keyboard_pad`), the function keys that the options hand to the guest (`machine_fkeys`), the
captured mouse and the mouse-game profile (`event`, `action_held`), the floppy drives (Ctrl+Alt+Page Up/Down/Backspace,
disk events, automatic changes: unchanged in `host_frame`), the fast-loading key (`fast_forward`), the variable picture
size read from the core and its 4:3 placement (`game_rect`), the second help page (`help_page`), F5 and F11 in the help,
the window size of `player.cfg`, and the F11 pause, which became a kit state (`paused`: the machine does not run, the
picture stays, "Paused" is drawn, Esc still quits).

Settings the kit gained for this family (each one a named per-machine field, none an `if` on the machine):
`video_section`, `autofire_section` and `indexed_bindings` (the preferences keep the layout of the first host, divergences
14 and 15 being "later": `[X68000] filter`, `display_mode`, `autofire`, `guest_keyboard`, `p<player>_key<n>`,
`p<player>_pad<n>`, `[X68000.Options] fkeys_machine`), `bindings_clearable` (Delete clears a binding: the old page had
it; the other consoles are not given it by this phase), `audio_rate` for the queue model (44,100 Hz stereo), `audio_chunked`
(more than one buffer of sound per frame), `machine_fkeys`, and the hooks `event`, `keyboard_pad`, `action_held`,
`fast_forward`, `game_rect`, `help_page`.

Divergences, for this family:

| # | Status for the X68000 |
| --- | --- |
| 1 stick 16000 | decided (D1), applied: it was 12000 (the stick of the pointer emulation of a mouse game included) |
| 2 autofire | decided (D4) and settled for this machine on 28 October 2026 ("same rules on every machine", maintainer; open question 5): `rr_autofire` per button on both game buttons (they are FACE actions; the old pulse touched Button A only), each new press starts on, guest frames; the key bound to a button is that button (the key the guest reads is released with it), a mouse button of a mouse game is Button A / Button B (it is held into the same autofire state); the unconditional parity pulse, the global clears and the separate mouse pulse are gone; Ctrl+Alt+F is the same toggle as F6 |
| 3 F2 pad capture | decided (D9), applied: it took any connected pad |
| 4 audio open flags and period | **pending**: opened as before (44,100 Hz, stereo, 512 samples, no format change); the start reserve is the kit's queue model's (one frame plus one period plus the adaptive cushion; the old host added 10 ms and counted the frame at 55 Hz): 5,740 bytes queued when the device starts instead of 8,608 on the Columns script |
| 5 callback ring | decided (D5) but not applied to any 16-bit console either: the X68000 shares the kit's queue output (audio filter, cushion, wait for room) |
| 6, 8 Windows set, window rectangle | decided (D3), **applied in phase 4** (the SMS/GG mechanism); the X68000 also keeps the width and height it keeps in `player.cfg` across runs |
| 7 vsync | decided, applied by the kit's renderer: not requested on Windows (it was always requested), POSIX hint kept. Not measured on a real display: the A/B runs use a virtual clock |
| 9 integer scaling | decided (D2), **applied in phase 4**: the placement is still the X68000's own (aspect-correct fit in Fit mode); the window and Pixel mode are the largest whole multiple of the picture's pixel grid (the window was the aspect-correct fit in phase 3, where the four display modes were measured identical) |
| 10 pad slots | decided (D11), applied: Automatic by default, a Gamepad row on each player's gamepad page, `device` and `name` in `[X68000.Gamepad.PlayerN]`; the old host dealt pads in plug order with no choice |
| 11 autofire notice | decided (D10), applied: "Autofire ON" / "Autofire OFF" for F6 and Ctrl+Alt+F; "Rapid fire" retires |
| 12 F8/F9 deferred | decided (D6), applied: the kit saves and loads at the top of the loop, before the next guest frame; the old host did it after the frame that read the key. A state is therefore taken one guest frame earlier (measured: the machine repeats frame 101 after a load that followed a save at 101, where the old host repeated 102). Its messages are the kit's ("Quick state saved" ...) |
| 13 gun page | not applicable (the mouse is the computer's, captured with Ctrl+Alt+M or a click) |
| 14, 15 preference layout, autofire key | decided (D7), **later** with the preferences phase: the X68000 keeps its layout and `[X68000] autofire` (see above); the files of the old and the new host are identical on the Columns script |
| 16 title texts | decided (D8), applied: "Native code" or "Interpreter fallback" after the title, counted from the CPU's own interpreter counters; the states "Starting" and "Native code + Interpreter fallback" are gone, and the reference prototype (no native CPU) always says "Interpreter fallback" |
| 17 latency line | the kit prints its closing line only when the audio reserve was raised; the old host printed it always. Tag `[host]` instead of `[player]`; the tag decision (18) stays pending |
| 18 diagnostic tags | **pending**: `[host]` through the kit |
| 19 ini writers | decided: the shared ini layer, as before |
| 20 dead renderer block | removed (zero behaviour change: it was unreachable) |
| 21 help language lookup | decided: the kit's lines come from the catalogue; the X68000's own lines had no translation before and have none now (English in every language) |

Also differing from the old X68000 host, with no decision on file: opposite directions cancel (the kit's pad word, on
every console), F2 has five pages (a keyboard and a gamepad page per player, then the options) instead of three, F3 shows
the name of the filter for 1.8 s and F4 shows nothing (the old host showed the display mode for 3.5 s and nothing for F3),
every notice is the kit's status line (1.8 s) instead of the old box (3.5 s), the options page, help page, pause word and
binding pages are the kit's drawing, and the picture is converted into a fixed 800 x 600 buffer that the kit uploads whole.

Measurements (Windows, MSVC, offscreen SDL, virtual clock and modelled audio device, `tools/hostkit_ab.py build-x68`:
the same kept build of Columns (Gyagon), Sharp X68000, 2 MiB, compiled once from the tree of the tag `v1.6.2` and once from
this tree, both against the harness; the second script is shifted by one iteration because the old host presents nothing
for its first frame):

* Script `play` (every key of both players, every button, the sticks around and beyond the dead zone, two buttons at once,
  a few thousand iterations of play, the four filters and four display modes with a picture each after the notices are
  gone; 3,280 frames): the per-frame trace (video, sound and RAM hashes, 18 CPU registers, the hardware counters) is
  **identical**; the 506 answers the core received are **identical**; the stream sent to the audio device is **identical**
  (10,336,324 bytes, one hash); the preferences file is **identical**; of the 3,280 pictures 2,099 are identical and 1,181
  differ in eight runs that are exactly the notice windows after each F3 (the kit's notice) and F4 (the old notice).
* Script `keyboard` (Ctrl+Alt+K, keys, F2, F5, F8-F10, Escape and Tab to the guest, back to game mode): all 68 answers
  identical; the trace identical until the F8 and F9 of the game mode, which act one frame apart (divergence 12).
* Script `mouse` (click to capture, motion with and without buttons, Ctrl+Alt+M release and capture again): trace and the 16
  mouse answers identical; the relative mode is set at the same iterations (the kit applies it at the start of the next one).
* Script `autofire` (F6, held keys and buttons, the bound key, both players, Ctrl+Alt+F): the pulses differ from the old
  host exactly as decided (a new press starts on; Button B pulses; the old host pulsed Button A by the parity of the frame).
* Script `states` (F9 with nothing saved, F8, F9 without input): a load returns the machine to the saved frame in both
  hosts; the state of the kit host is one frame earlier (divergence 12). The quick-state key of the X68000 hashes
  `reference_host.c`, so it moves (see [UPGRADES.md](UPGRADES.md#x68000-exports-in-163-host-kit-phase-3)); a state written by
  the old host is refused, as between any two releases of the X68000.
* Pad slots on the kit host (`tools/hostkit_ab.py pads` scenarios `one`, `two`, `twin`, `twin-unplug`, `next-missing`,
  `replug`, `persist`, `capture`): all probes on the right player; the F2 binding of a player without a pad says "No
  gamepad for player N"; the preferences hold `device` and `name` and a second run on them keeps the pinned pad.
* Mega Drive (Blockout), regression of the shared shell: the shell of 1.6.2 against this one, same project, the standard
  battery of 3,694 iterations: **identical** pictures, window log, state file and 35 captures.
* The headless harness of the converter is unchanged: a 600-frame headless run of the old and the new executable gives the
  same trace file, and a fresh conversion of the same game with this tree builds, runs and passes the converter's own
  comparison of the export with a fresh reference.
* ROM-free: `tests/test_x68000_controls.py` rebuilt on the kit (60 checks of the input callbacks with virtual controllers,
  40 of the computer's events and menus on a real software renderer, 7 of a fresh process).

Not rerun for this phase: the other consoles of the kit than the Mega Drive (same shell code; the NES ring output and the
Zapper page are untouched), and the NES in particular. Not covered, as for the other phases: a mouse game (the mouse profile is the same code; Columns does not read the mouse), a
two-disk game, fast loading held during a real load, audio open failures, Linux (the same sources, not built there in this
phase), and a timing measurement on a real display (vsync and the audio start reserve changed).

### Phase 4: the Master System and the Game Gear (1.6.3)

`native/host.c` (759 lines), `controls.c` (422) and `ui.c` (215) are gone. The two consoles run the shell of the others with
`native/hostkit/adapters/rrhk_sms.c`, one adapter for both (the Game Gear is the `RETRO_GAME_GEAR` build: one player, a Pause/Menu
row and a cartridge Start row). Their guest owns the loop: the recompiled Z80 code calls `host_present` once per frame, so the
kit gained a *driven* mode (`RrhkMachine.driven`, `rrhk_open`, `rrhk_frame_done`, `rrhk_stop`, `rrhk_close`). `rrhk_main` and the
guest-driven entry share the same two halves of an iteration (`begin_frame`: events, quit and restart, state requests, pads;
`end_frame`: sound, picture, title, menus, notices, pacing); a menu is a loop inside `rrhk_frame_done`, the guest does not run
meanwhile, and a reset unwinds the generated call stack as before (`reset` sets the launcher's request and calls `rrhk_stop`;
the launcher starts the runtime again and the window is made again at its remembered position and size).

What stays the adapter's own: the action table and the French preference keys it still reads (`settings_loaded`), the guest's
mid-frame refresh of the pads (`host_refresh_input`, at most once a millisecond, now through `rrhk_pad_word` and
`rrhk_pointer_poll`), the Light Phaser (mouse to picture with the crop, the P2 trigger alias, the trigger held while a menu closed does not
shoot), the sprite-flicker option (F5, Master System only; the Game Gear keeps its "Config unavailable"), the Pause menu text, the
crop of the picture (the Game Gear window inside the 256 x 192 frame, the Master System left column the VDP blanks) and its placement rule,
the quick-state requests (`smsrecomp_request_state`, serviced by the guest at a banked-instruction boundary, reported by its callback),
and the sound: `native/audio_output.inc` (the stereo callback ring with its FIR source conversion) is included by the adapter
unchanged. D5 holds for it (a callback ring), but the kit's own mono ring (`rrhk_ring.c`, the NES) and this stereo one are still
two implementations; merging them is a later step with its own measurement.

New per-machine fields and hooks of `RrhkMachine` (all optional, none an `if` on the machine): `driven`, `host_pause` (a row that
is the host's own, no pad bit), `pause_page` (the body of the Pause menu, `RRHK_MENU_PAUSE`), `minimum_window`, `state_deferred`
(with `rrhk_state_done`), `legacy_ini` (the former preferences file, read while `Retro-Recomp.ini` does not exist and copied to it
before the first write, as the Master System host did), `window_icon`, and `RRHK_POINTER_PHASER` (the Light Phaser page; the
`[MasterSystem.Pointer]` keys). Shell behaviour added for everyone, from the SMS/GG host: a menu opened from the Pause menu returns to it
(`parent_menu`), `rrhk_write_ready` (the one place a preference write starts), the window rectangle and the hint set (below).

Divergences, for this family:

| # | Status for the Master System and the Game Gear |
| --- | --- |
| 1 stick 16000 | decided (D1), applied: it was 12000 |
| 2 autofire | decided (D4): the same `rr_autofire` rule per button on the two face buttons; opposite directions now cancel in the pad word (they were both sent to the guest) |
| 3 F2 pad capture | decided (D9), applied to the Quit and Restart combinations (the button bindings already took the selected player's pad only) |
| 4 audio open flags and period | **pending**: the stereo ring opens as before (48,000 Hz, 256 samples, format and frequency change allowed) |
| 5 callback ring | decided (D5): it was one; see above for the two implementations |
| 6, 7, 8 Windows set, vsync, window rectangle | decided (D3), **applied to every kit console** in this phase: the hints of the Master System host (render scale, XInput, per-monitor DPI — on a Windows display scaled above 100 % a kit window is no longer enlarged by Windows, so it opens physically smaller than in 1.6.2 at the same integer scale, a visible change on every kit console, Direct3D 11 and the joystick thread on Windows, the vsync hint elsewhere) before `SDL_Init`, the renderer line on stderr, the window position and size kept when going fullscreen and back and across a restart of the guest. F4 from Pixel to Fit no longer calls `SDL_SetWindowFullscreen` (it was a no-op). Not persisted across runs (open question 7). Not measured on a real display |
| 9 integer scaling | decided (D2), **applied to every kit console** in this phase: whole pixels, centred, in the window and in Pixel mode; only Fit stretches (to the largest size that keeps the aspect). The Master System and the Game Gear already did it (their own `game_rect` keeps its scale from the full picture when a game blanks the left column). The X68000's own placement follows the rule in the window too. **Opening size:** so that a game does not open smaller with borders (the Mega Drive engine reports 256 until its first frame, most games are 320 wide: 768 x 672 would show them at 2x), the window opens at the largest integer multiple of the machine's native picture that fits comfortably in the display's usable area (`opening_size` in `rrhk_main.c`; a machine states its usual picture with `open_width`/`open_height`, the Mega Drive 320 x 240; one whose size is already an exact multiple of the picture it reports keeps it, as every other console, the Master System and the Game Gear do). A remembered window rectangle wins, and resizing keeps the whole-pixel rule |
| 10 pad slots | decided (D11), applied: Automatic by default and a Gamepad row per player; the first-player preference (`[Manettes] premier_joueur`) is ignored and the C swap is gone |
| 11 autofire notice | decided (D10), applied: "Autofire ON" / "Autofire OFF" from the catalogue; the "Tir auto" toast retires |
| 12 F8/F9 deferred | decided (D6): the Master System already asked the guest for a state at a safe boundary; the kit now owns the request and its notices (they say "Quick state saved / loaded", and one message for a state that cannot be loaded) |
| 13 gun page, mapping, reticle | decided, applied: the kit's pointer page (title "Light Phaser", `[MasterSystem.Pointer]`: `shape` 0/1, `size` 1..5, `color` 0..2), mapping and reticle (thin cross, dot in picture pixels); the Phaser games are not in the A/B battery (no gun game was run) |
| 14, 15 preference layout, autofire key | decided (D7), applied for these two consoles: `[MasterSystem.Keyboard.PlayerN]` and `.Gamepad.PlayerN` (numeric values, English action names `Up`, `Down`, `Left`, `Right`, `Button1`, `Button2`, `Pause`, and `Start` on the Game Gear), `[<Console>.Video]` (`filter`, `display_mode`, `reduce_sprite_flicker`), `[Manettes] autofire` as before. The French keys (`[Clavier]`, `[ClavierJ2]`, `[Manette]`, `[ManetteJ2]` and their Game Gear sections, `[Video] filtre`, `[LightPhaser]`, the 0.8 layout of player 2 ignored) are read where the new key is absent, never deleted; a change writes the new key only. A file written by 1.6.2 therefore keeps its meaning, and one written by 1.6.3 is not read by a 1.6.2 export for the bindings changed since |
| 16 title texts | decided (D8), applied: "Native code" or "Interpreter fallback" counted from the guest's interpreter cycles (once it ran, for the rest of the session); "Fallback interpreter ACTIVE", "Native code \| fallback used earlier" and "Reference interpreter" are gone (the reference interpreter reports as a fallback). The window is first titled "<game> \| Native code" instead of the bare title |
| 17 latency line | decided (D8): the renderer line and the audio line end with "physical latency unmeasured" |
| 18 diagnostic tags | **pending**: `[host]` kept; the `[host] player N controller` line is gone |
| 19 ini writers | decided: the shared ini layer, as before; `controls_load` on every F2 is gone (the kit reads once) |
| 21 help language lookup | decided: the catalogue; the inline `TR(en,fr)` pairs are the kit's `rrhk_tr` |

Also differing from the old host, with no decision on file (the A/B pictures below show each of them): F2 pages are the kit's drawing
("Name: value" rows with the SDL key names, "Player 1" heading on the Game Gear too, no "D: defaults" row, Enter binds any action and
a key can serve two actions); the help page has no "F1 / Esc: close" footer; the F4 notices ("Windowed", "Fullscreen - integer scale") and
the F7 notice wording are the kit's; every notice is the kit's status line (the start hint keeps its 2.4 s); the Pause menu opens with
the key or button bound to Start/Menu of any player (Enter always paused the Master System before: only the bound key does now);
the mouse no longer selects rows of the F2 pages (the kit has no such click: not carried); gamepads are read while the window has no
focus (the old host read nothing then); a Game Gear help line and the pause page still list F5 although the option does not exist on that console.

Measurements (Windows, MSVC, offscreen SDL, `tools/hostkit_ab.py build-sms`, virtual clock and modelled audio device; both sides
compiled from the same kept conversion, the host sources of the tree before this phase (`git archive`, `host.c`, `controls.c`, `ui.c`) against this tree;
the former host built with one harness patch: it handled one event per pass of its menu loop and drew between them, the harness
drains the pending events there so that the iteration numbers of the two sides agree):

* Master System, Bank Panic (Europe) (PAL, one 32 KiB bank), script `play` (every key and button of both players, the sticks at and around the two thresholds,
  opposite directions, 60 timed keys, the four filters and four display modes; 3,614 iterations): **identical**: 2,534 of the
  3,614 pictures and the 9 captures taken after the notices; every audio callback block and the device calls (13,634 lines); the title and
  window log. **Different, as decided**: the 1,080 pictures of nine 120-frame runs that show a notice (the start hint and the eight notices
  of F3 and F4: the kit draws them as its status line, the old host as a box); the 218 pad-byte lines against 194 (the sticks at +-15,999 and +-12,001 are no longer
  directions, left and right held together send neither); the first title line (the old host set it on the first picture); stderr.
* `autofire` (F6, held buttons, both players, 740 iterations): pad bytes (122 lines), audio and every picture outside the notices identical.
* `states` (F9 with nothing saved, F8, F9, F8; 904 iterations): the pad bytes and audio identical, the state file **byte for byte equal**; a state
  written by one host loads in the other (checked both ways: the quick-state format, path and ROM binding are untouched).
* `ui` (help, every F2 page and the Pause menu in five languages, rebinding, the sprite option, Shift+F1): read by eye (see the differences
  above); Shift+F1 restarts the guest, the window comes back and the start hint shows again in both; the preference files differ as listed
  (`[Clavier] bas=J` against `[MasterSystem.Keyboard.Player1] Down=13`).
* Game Gear, Pac-Attack (USA, Europe) (NTSC, 3,496 iterations): the same results: pictures identical outside nine 144-frame notice runs,
  audio identical but two silent callback blocks one iteration apart, state file equal, autofire pad bytes identical.
* Pad slots (`tools/hostkit_ab.py pads` on the kit build, Master System): `one`, `two`, `twin`, `twin-unplug`, `next-missing`, `replug`, `persist`
  all correct (every probe on the right player), `capture` says "No gamepad for player N", `combo` ignores player 2's pad and writes `quit_pad`
  from player 1's. Game Gear (one player): `one` is right for player 1 and nothing reaches a second player, as it should.
* Mega Drive (Blockout), regression of the shared shell: the shell of before this phase against this one with the placement rule of D2 held back
  (same project, 3,694 iterations): **identical** pictures, 35 captures, state file, preferences, pad words; only two `SetWindowFullscreen` calls
  of the log (Pixel to Fit, a no-op) and the renderer line of stderr differ. With D2 and the opening size of row 9 (the harness states a 1920 x 1040 usable
  display area, `RRAB_DISPLAY`), the window opens at 960 x 720 instead of 768 x 672 and the 320-wide picture is shown at 3x (the logo of the title
  measures 235 game pixels in both: 564 screen pixels at 2.4x before, 705 at 3x now, never smaller); the 2,916 pictures presented in the window differ
  by that and by nothing else (the 778 presented in fullscreen, where the placement is the same, are identical, as are the pad words, the audio,
  the state file and the preferences).
* ROM-free: `tools/autofire_selftest.py` and `tools/start_select_selftest.py` (the Master System and Game Gear fixtures are now the kit's
  input module with the adapter's own table), `tools/lazy_data_selftest.py` (read-only startup, the former `SMSRecomp.ini` read in place and
  copied only on the first write), `tools/presentation_selftest.py`, `tools/host_selftest.py` (the kit's adapter driven with synthetic events through
  the generated game: the former French keys, the Pause menu, menus from it, Shift+F1, Esc, a pause leaves the guest untouched, the placement
  rule), `tools/game_options_selftest.py`, `language`, `display_settings`, `audio`, `lightphaser`, `nes_audio`: all passing. `tools/icon_selftest.py`
  needs a converted Alex Kidd (not available here).

Not covered: a Light Phaser game (the page, the reticle and the P2 trigger alias are the kit's and the adapter's code, unrun), a PAL Game Gear, menus driven by a
pad, hot unplug during a menu, audio open failures, a real display (vsync, window position), a Master System game that blanks the left column
in the A/B pictures (the placement is checked by arithmetic only), Linux (the same sources; the adapter defines `rr_resource` for the kit's icon routine
there, and nothing was built on Linux in this phase).

### Phase 5: the Game Boy (1.6.3)

`gb_menu.inc` (345 lines), `gb_audio_output.inc` (73), `gb_input_refresh.inc` (45) and `gameboy_timing.py` are gone, and the
patched `platform_sdl.cpp` of the pinned runtime (4,209 lines upstream, with some eighty text patches on top of it in 1.6.2) is now about 1,100 lines: its
window, ImGui settings panel, bindings, controller handling, preferences file, sound device and pacing are cut out
(`gameboy_host.kit_platform`: named cuts, each failing if the pinned file moved) and the Game Boy runs the shell of the other consoles
with `native/hostkit/adapters/rrhk_gb.inc`, which the patched platform file includes (one translation unit, like the X68000: the adapter
sees the runtime's statics and types). What stays upstream's, and is not the player's business: the input scripts and their recording,
the screenshots of selected frames, the battery, clock and state files (atomic writes, injected faults), the display palette of a
frame and the benchmark/headless mode; `gb_platform_*` of `platform_sdl.h` is unchanged for the generated main, which keeps its loop.

The loop is driven like the Master System's: the generated main calls `gb_platform_poll_events` once per slice (what it does is the
scripted input and a live sample of the pads), `gb_platform_render_frame` (or the partial-slice presents) to hand the picture over,
and `gb_platform_vsync(cycles)` at the end of each frame or paced slice: that is the kit's `rrhk_frame_done()`, with the machine's
`frame_seconds` set to the cycles just run (`cycles / 4,194,304`, as upstream paced them). It presents the picture with the chosen
filter, plays the sound of the frame, reads the events, runs a menu as a loop of its own (the guest does not run meanwhile), services
F8/F9 and the restart combinations at the frame boundary and waits for the deadline. A quit asked there ends the loop at the next
slice (`gb_platform_poll_events` and `gb_platform_wait_while_menu` say so). A cartridge's JOYP read asks the host for fresh input, at
most once a millisecond, as before (`refresh_input`, the guest side is unchanged).

New per-machine fields of `RrhkMachine`: `audio_channels` (the ring takes interleaved stereo; the NES stays mono), `audio_margin_ms`
(the start margin of the ring: 10 ms for the Game Boy as before, 30 ms for the NES) and `even_scale2x` (Scale2x shows the picture at an even whole
multiple from 2x up, the rule the Master System, Game Gear and Game Boy had; the Master System and Game Gear keep their own
`game_rect`). `rrhk_ring.c` is the Game Boy's callback ring too (its own `gb_audio_output.inc` is gone); a driven machine that does not
open its own sound device now starts SDL's audio subsystem. `rrhk_input.c` reads the language and the autofire from the machine's
former preferences when the kit's keys are absent (`settings_loaded` sets the values they start from).

What stays the adapter's own: the action table (up, down, left, right, A, B, Start, Select, and the host's own Pause/Menu row, key P and
the Guide button, as the Game Boy had them), the F5 palette (monochrome or classic green; a Game Boy Color game keeps its own colours),
the Pause menu text, the pad word to the JOYP registers and the joypad interrupt, the former preferences, the state functions (slot 1 of
the runtime's own state file, between two frames) and the sound of the APU (44.1 kHz stereo).

Divergences, for this family:

| # | Status for the Game Boy |
| --- | --- |
| 1 stick 16000 | decided (D1): the upstream threshold was already 16000; the stick is now the kit's (left stick as the direction pad), not a per-axis binding |
| 2 autofire | decided (D4): the Game Boy already used `rr_autofire` on A and B by guest frame (cycles / 70,224); the kit's rule is the same (the register sequences of a script with F6, held keys and buttons are identical). **Opposite directions now cancel in the pad word** (they were both sent to the cartridge) |
| 3 F2 pad capture | decided (D9), applied: the Game Boy took any connected pad; it takes the selected player's pad only, in the bindings and in the quit and restart combinations |
| 4 audio open flags and period | **pending**: the ring opens as before (44,100 Hz, 256 samples, format and sample-count change allowed, 10 ms margin); the NES keeps its 30 ms |
| 5 callback ring | decided (D5): it was one, its own; it is now the kit's ring (`rrhk_ring.c`, extended to stereo). Differences: 8,192 frames instead of 16,384, the backlog trimmed at the kit's limit, no volume, mute or output-device choice in this phase (D12 gives them back to every console), no audio statistics. The Master System and Game Gear stereo ring is the one duplicate left |
| 6, 7, 8 Windows set, vsync, window rectangle | decided (D3): the Game Boy already had the Direct3D 11 hint and the joystick thread; the vsync hint, the renderer line and the window position and size kept across fullscreen toggles are new for it |
| 9 integer scaling | decided (D2): the window opens at 5x (800 x 720), an exact multiple, as before; whole pixels, centred, Fit stretches; **below 1x the picture now fits the window instead of being cropped to 1x**; Scale2x keeps its even rule (`even_scale2x`) |
| 10 pad slots | decided (D11), applied: the Game Boy opened the first controller it found; Automatic by default and a Gamepad row (`[GameBoy.Gamepad.Player1] device`, `name`); one player |
| 11 autofire notice | decided (D10), applied: "Autofire ON" / "Autofire OFF" instead of the status line |
| 12 F8/F9 deferred | decided (D6), applied: the Game Boy saved and loaded from the event path after a slice, which could be in the middle of a frame; it now acts after a completed frame (`state_ready` is the frame boundary). The state file, its path (`datas/games/<game>/<game>.state1`) and its format are the runtime's, unchanged: it is **not byte-identical** to the file the former host wrote at the same iteration (7 of 220,784 bytes differ: the frame-done flag and the cycle counter of the frame), and each host loads the other's |
| 13 gun page | not applicable |
| 14, 15 preference layout, autofire key | decided (D7), applied: `[GameBoy.Keyboard.Player1]`, `[GameBoy.Gamepad.Player1]` (numeric values, English action names `Up`, `Down`, `Left`, `Right`, `A`, `B`, `Start`, `Select`, `Pause`), `[GameBoy.Video] filter`, `display_mode` and `palette` (0 classic green, 1 monochrome), `[Manettes] autofire`, `[Interface] language`. The flat `datas/Retro-Recomp-GameBoy.ini` of 1.6.2 and before (`video.*`, `ui.language`, `input.autofire`, `keyboard.<action>.0`, `controller.<action>.0`) is read where the kit's key is absent, never written and never deleted; the second binding of an action, the axis bindings and the `audio.*` and `savestate.slot` keys are not read |
| 16 title texts | decided (D8), applied: the window is first titled "<game> \| Native code" and says "Interpreter fallback" as soon as the guest uses it (the former host looked every 60 frames) |
| 17 latency line | decided (D8), applied: the renderer line and the ring's closing line end with "physical latency unmeasured" (the Game Boy printed none) |
| 18 diagnostic tags | **pending**: the `[SDL]` lines of the former platform layer are gone, `[host]` is the kit's; the `[AUTO]` and `[SDL]` lines of the retained persistence and screenshot code are upstream's and unchanged |
| 19 ini writers | decided: the shared ini layer (the former flat writer is gone) |
| 21 help language lookup | decided: the catalogue; the F2, help and pause pages are the kit's drawing |

**Retired, by "same rules on every machine"** (the upstream shell had them behind default keys that no page or document listed, and no other
console has them): the fast-forward key (Tab, the right trigger) and the maximum-speed toggle (backquote, the left trigger), the mute key
(M) with the volume and the output-device choice of the upstream settings panel, the slots of the upstream state keys (F8/F9 use slot 1
only, as the Game Boy already did), the second keyboard and gamepad binding of each action (the right and left shoulders were also A
and B) and the ImGui overlay and panel. The fast-forward, maximum-speed, mute, volume and output-device features **came back the same day as kit features of every console (D12)**: see D12 in section 3. The second binding of each action stays retired.
ImGui is still compiled into the runtime library of the project, where nothing calls it any more; its notice stays in the game's legal text.

Measurements (Windows, llvm-mingw, offscreen SDL, virtual clock and modelled audio device, `tools/hostkit_ab.py build-gb`): the project of
a conversion made with the tree before this phase (host of 1.6.2) against the same project with the host of this tree (and, for the
second game, against a conversion made with this tree). The harness logs the joypad registers the cartridge is handed at the start of
every slice (`G` lines).

* Kirby's Block Ball (USA, Europe) (MBC1, battery), script `play` (every key and button, the sticks around the threshold, 60 timed keys,
  the four filters and four display modes with a picture each after the notices are gone; 3,386 iterations): the **joypad registers are
  identical** (166 changes), and so are the 9 pictures taken after the notices, the battery file and the fallback record. Of the 3,386
  pictures 2,138 are identical and 1,248 differ in eight runs of 156 pictures: the notice after each F3 and F4 (the kit's status line, the old
  host's box). **Intended differences in this run**: the left and right shoulders no longer press B and A (the script leaves them out, because
  the game would diverge), opposite directions (script `opposite`: `f0` against `ff`), the first title line, the preferences file
  (`[GameBoy.Video] filter=0 display_mode=1` in `Retro-Recomp.ini` against the flat file), the delays of the pacing (`D` lines).
* Sound of the same run: the **non-silent stereo samples are identical, in order, over the whole run** (1,733,700 frames compared; the old
  host handed 216 more at the end) and each side has one recovery of the start reserve (515 silent samples) at a different moment: the
  model's two clocks beat differently with the kit's whole-frame submission, which is not a measurement of a real device. The ring of the
  kit raised its reserve twice (+5 ms) on this run.
* `autofire` (F6, held keys and buttons; 578 iterations): the register sequences are **identical** (72 changes); the pictures differ by the
  two notices only. `states` (F9 with nothing saved, F8, F9, F8; 794 iterations): the pictures after a load and after nothing are identical,
  the state file differs in 7 bytes as said above, and the states cross over (script `load`: a state of either host loaded by either host
  shows the same continuation, except one picture 190 frames after the load of the new host's state by the old one, an animation phase).
* Super Mario Land (MBC1, a conversion with this tree against the former host): the same results (3,385 iterations, registers identical,
  1,248 pictures in the eight notice runs, 2,385,450 non-silent frames identical, one reserve recovery on each side).
* Preferences: a file of 1.6.2 (`video.filter=3`, `display_mode=2`, `palette=green`, `ui.language=fr`, `input.autofire=1`, `keyboard.a.0=key:4`)
  gives scanlines, fit, classic green, French, autofire on and A on the A key; reading writes nothing; once `Retro-Recomp.ini` holds the
  keys they win (`tools/gameboy_display_selftest.py`).
* Pad slots (`tools/hostkit_ab.py pads`, one player: `one`, `capture`, `combo`, and the Game Boy's `gb-replug` and `gb-persist`): every
  probe on the right player (or on nobody: a pad that is not the player's drives nothing), a pinned pad that is unplugged leaves the
  player without a pad and gets it back on hot-plug, a second run on the preferences keeps the pinned pad, the F2 binding says "No gamepad
  for player 1", the quit combination is captured from player 1's pad only.
* Mega Drive (Blockout) and Master System (Bank Panic), regression of the shared shell: the kit of `main` against this one, the full
  battery of 3,694 iterations (Mega Drive) and the scripts `play`, `autofire`, `states` (3,614, 740, 904 iterations, Master System):
  **identical** (pictures, window log, states, preferences, pad words).
* ROM-free: `tools/gameboy_latency_selftest.py` (the adapter against authored pads, clock, scripts, menu and APU samples),
  `tools/gameboy_display_selftest.py` (settings and files), `tools/nes_audio_selftest.py` (the ring, now with a stereo case),
  `tools/autofire_selftest.py` and `tools/start_select_selftest.py` (the Game Boy is now one of the kit consoles there; the second needs
  `RETRO_RECOMP_TOOLCHAIN=msvc`, the llvm-mingw linker not finding the Visual Studio SDL), `tools/gameboy_boundary_selftest.py`,
  `gameboy_hardware_selftest.py` and `gameboy_ram_selftest.py`, all passing; two real conversions (Kirby's Block Ball, Super Mario Land)
  with the tree validate their exports as before. The adapter also builds with the Visual Studio toolchain (`tools/gameboy_latency_selftest.py` under
  `RETRO_RECOMP_TOOLCHAIN=msvc`: it caught a `std::min` that the Windows `min` macro breaks).

Not covered, as for the other phases: a Game Boy Color game (the palette option is hidden for one), a game with an RTC or a rumble
cartridge, menus driven by a pad, hot unplug during a menu, audio open failures, a real display (vsync, window position) and a real
sound device (the reserve and start timing are measured on a virtual clock only), Linux (the same sources, not built there in this phase).

### Sound and speed controls: A/B (1.6.3, decision D12)

Measured on 29 October 2026 (Windows, llvm-mingw, offscreen SDL, `tools/hostkit_ab.py` with its virtual clock and modelled audio
device, which hashes every block the device callback is handed; ROMs read in place and never copied outside the kept builds, which were
deleted). Each game was converted with the tree of `main` (27434da) and with this tree (`tools/ab_conversion.py`, quick scan), and the
two harness executables were built from the same kept project. The two conversions differ only in the host files, the host stamp and the
size of the executable (the Game Boy and Master System traces, reports and generated sources are identical, so no game stamp moves).
For the Mega Drive the engine's own audio callback is built against the harness too (`--also native/audio.c`).

* **With the new keys untouched, nothing changes.** Mega Drive Blockout, the whole battery (3,694 iterations: both players' keys, pads, the
  filters and display modes, every language, every F2 page, states, preferences): the window log, **all 5,477 callback blocks of the
  engine's sound, the pad words, the state file and the preferences are identical**; 3,639 of the 3,694 pictures are identical and the 55
  that differ are the five help pages and the five options pages (ten intervals, one per language), which are meant to differ. Master
  System Bank Panic (scripts `play`, `autofire`, `states`: 3,614, 740 and 904 iterations) and Game Boy Kirby's Block Ball (3,386, 579 and
  794 iterations): **identical** in pictures, pad bytes and joypad registers, callback blocks, states and preferences (the Game Boy `states`
  run differs in one line of stderr, the run folder's name); the `ui` scripts differ only in the help, Pause-help and options pictures.
* **Fast-forward** (Mega Drive, Master System, Game Boy; the same scripts on the three): Tab held for 200 iterations slept 1,010 ms of
  virtual time instead of 3,000 (Mega Drive and Game Boy; 1,412 against 3,800 on the Master System, whose frame is 16.67 ms), the
  maximum speed 213 ms for 100 iterations against 1,500 (316 against 1,900); the harness sleeps whole milliseconds, so the ratios (2.7 to 3.0
  and 6.0 to 7.0) are not the ideal 2.5 and 5. The **right trigger** and **left trigger** of a virtual pad do the same. Every callback block
  inside the windows is silent (the few at the edges are the tail of the ring emptied at the change). **Identical guest state after the same
  guest frame count**: a quick state taken at iteration 780 (Mega Drive) or 1,060 (Master System, Game Boy) after Tab held, mute toggled
  twice and the maximum speed toggled on and off is byte for byte the state of the plain run (206,953, 450,897 and 220,784 bytes), and the
  pictures of the iterations that show no notice are identical.
* **Mute**: the run with M pressed twice has, in the callback blocks, one stretch of zeros (Mega Drive 159,744 samples, Master System
  193,536, Game Boy 147,968) and **every other sample equal to the plain run's**: the machine's sound state (the ring, the bridge) was not
  touched. **Volume** 50% (preferences seeded with `audio_volume=50`): every sample of 1.28 million (Mega Drive), 2.1 million (Master
  System) and 1.6 million (Game Boy) equals the plain run's sample times 50%, rounded toward zero; the pictures are identical.
* ROM-free: `tools/game_options_selftest.py` (volume, mute, hold, F32, persistence, the rows and the device cycle, in C and C++),
  `nes_audio_selftest.py`, `autofire_selftest.py`, `start_select_selftest.py` (msvc), `gameboy_latency_selftest.py` and
  `gameboy_display_selftest.py` (the Game Boy's 1.6.2 `audio.*` keys reach the kit's controls), `tests/test_hostkit.py`.
* **Review fixes** (Mega Drive Blockout, harness; a script commands `audioremove`, which pushes `SDL_AUDIODEVICEREMOVED` for the
  harness's device): a pad whose right trigger is held and that is then unplugged slept 5 ms an iteration while held and 15 ms after the
  unplug (the pace of a normal speed; before, the hold stayed); the removal of the device on the Mega Drive, which owns its device,
  logged the close and the open of the engine's sound again in the same iteration. `game_options_checks.c` checks that a volume, a mute
  and a device choice apply when the preferences file has no path; `audio_checks.c` that the Master System and Game Gear output reopens
  on a new device several times and leaves the audio subsystem started once.
* A Game Boy conversion made at a path of more than about 200 characters cannot write its battery file (`.sav.tmp-v1`, 260-character limit),
  which changes what the discovery plays see: keep the `--work` folder of `ab_conversion.py` short (the first Game Boy comparison of this
  work, in a deep folder, showed 8 more observed ROM entries on the side with the short path; both sides at a short path are identical).

Not covered: a real output device (the harness ignores the device name; the enumeration, the reopen on another device, the fallback to the
default and the replacement of an unplugged device are checked by reading and by the C checks only), Linux, the Super Nintendo, Neo Geo,
CPS-1 and X68000 queue output and the NES ring (they call the same stage; the NES and Game Boy share the ring, checked by
`nes_audio_selftest.py`), a gamepad with its triggers on a real device, and the Game Gear (the Master System adapter, one source).

## 8. Open questions

1. ~~**Game Boy upstream rows**: the exact behaviour of divergences 1, 3, 5, 8
   and 9 needed the upstream `platform_sdl.cpp`, absent from the survey
   checkout (`host-divergences.md:285-286`; `hosts.md:538-540`). **Read in phase 5** (1.6.3): the stick threshold was
   already 16000, the capture took any pad, the sound was already a callback ring, the window rectangle was not kept
   and the placement was integer; see the table of "Phase 5".~~
2. ~~**F2 capture rule** for all families~~ **Settled on 28 October 2026
   (Arthur): the selected player's pad only**, for every console (D9). On the
   kit it is applied, SMS/GG and the X68000 included (phases 3 and 4); Game Boy takes it when it migrates.
3. ~~**Base pad-slot policy** (first free vs slot memory)~~ **Settled on 28
   October 2026 (Arthur)**: Automatic by default plus a Gamepad row per player
   (D11); the SMS swap and first-player preference are replaced by it when
   SMS/GG migrates (`hosts.md:175-178`).
4. **Autofire notice wording and diagnostic tag**: the wording is **settled on
   28 October 2026 (Arthur)**: one short shared pop-up on every console,
   "Autofire ON" / "Autofire OFF" from the catalogue (D10), applied on the kit
   consoles and taken by the X68000 (phase 3) and SMS/GG (phase 4); Game Boy takes it when it migrates. The
   diagnostic tag (one tag for all, or a fixed per-layer set,
   `host-divergences.md:214-225`) is **still pending** (divergence 18).
5. ~~**X68000 autofire aliases**: what guest-keyboard keys and mouse buttons do
   once autofire follows `rr_autofire` semantics (`host-divergences.md:32`).~~
   **Settled on 28 October 2026 (maintainer, "same rules on every machine")**: a
   key or a mouse button bound to a face button is that button, with its
   autofire; no machine-specific pulse (phase 3).
6. **One requested audio period** (256 vs 512 today) and the Mega Drive final
   period, not visible in the checkout (`host-divergences.md:55-67`).
7. **Window rect scope**: session memory (the SMS/GG mechanism, now the kit's) vs
   persisted across runs (`host-divergences.md:95-107`).
8. **Not yet examined**: SMS/GG battery handling (`hosts.md:541-542`: none in the guest today). The X68000
   libretro bridge was examined in phase 3: the frontend keeps the core and calls
   the kit's loop one frame at a time.
9. **Product docs to update when the kit lands**: `docs/UPGRADES.md` (shell
   table), `docs/CONTROLS.md`, `docs/COMPILATION_LIBRARY.md`, and the local
   `PROJECT_STATE.md` (`hosts.md:549-551`).
10. ~~**Fast-forward and mute on every console**~~ **Settled on 29 October 2026 (maintainer, D12)**: the Game Boy's fast-forward (Tab held,
    right trigger), maximum-speed toggle (backquote, left trigger), mute (M), volume and output-device choice are kit features of every
    console, with the Game Boy's former keys and behaviour. The second binding of each action stays retired (it is a contract change).

The kit's own effort estimates stay in the local plan (`hosts.md:513-531`);
they are not part of this public contract.
