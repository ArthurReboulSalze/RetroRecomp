"""Mega Drive games for three and four players: the Sega Team Player, the EA 4 Way Play and the Codemasters J-Cart.

The player plugs nothing and chooses nothing: the converter picks the adapter a game was made for (`detect`), and the game's
private bus copy answers it. Players 3 and 4 are the host kit's third and fourth pads (alone: two more controllers; in a
multiplayer session: the session's port words 3 and 4, set inside `run_frame`).

* **Ports** (`RR_MD_TAP_PORTS`): one adapter on the two control ports that answers both protocols, as later Team Player
  units did. Port A speaks the Team Player's protocol (a game identifies it with TH alone, `3` then `F`, and drives TR for the
  data): TH high resets its counter; each change of the TH or TR the game drives, with TH low, advances it; the reads give the identification nibbles 3, F, 0,
  0, then the four pads' types (0: three buttons, 1: six), then each pad's data nibbles (R L D U, S A C B, and M X Y Z for a
  six-button pad), active low, with TL echoing TR. The 4 Way Play is selected by a write to port B with its two low bits at
  0 (the inputs read high): bits 6-4 latch; latched bit 2 makes port A read `$7C` (the adapter's signature), otherwise port A
  reads the three-button pad bits 1-0 select, with port A's TH; port B then reads `$7F`. Port B carries no pad of its
  own (a fifth Team Player pad is absent).
* **J-Cart** (`RR_MD_TAP_JCART`): two pad ports on the cartridge, answered at `$38FFFE` and at `$3FFFFE` (both above the ROM
  of every J-Cart game: MAME maps Pete Sampras Tennis at the second, the others at the first, and Sampras Tennis 96's code
  uses both): a write's bit 0 drives both pads' TH; a word read gives pad 3 in the low byte and pad 4 in the high byte, each with bit 7 set, bit 6
  the TH level and bits 5-0 the three-button lines, active low.

Facts of the protocols from Genesis Plus GX (`input_hw/teamplayer.c`, `gamepad.c`) and MAME (`bus/megadrive/cart/jcart.cpp`),
read for the hardware only: the code here is written for this runtime. `detect` uses the game's own declaration (a `4` in
the header's I/O support at `$190`: the Team Player; the reviewed table `TEAM_PLAYER_DUMPS` for a game that does not
declare it), the game's own 4 Way Play probe (the instruction that writes `$7C` to
`$A10005`, found in its code) and, for the J-Cart, which no header declares, the reviewed table `JCART_DUMPS` of exact dumps.
"""
from .core import ConversionError

NONE, PORTS, JCART = 0, 1, 2
NAMES = {NONE: None, PORTS: 'team_player_and_4_way_play', JCART: 'j_cart'}

# Codemasters' J-Cart dumps, keyed by SHA-256 (reviewed 17 November 2026 against MAME's jcart.cpp list of J-Cart games; each
# dump's code addresses $38FFFE or $3FFFFE). The value is the title, for the review only.
JCART_DUMPS = {
    '6e21848dd36d9a5843c73875f0a3eb59a23981d3d31a17c824664dc963ed7fa8': 'Pete Sampras Tennis (USA)',
    '533b0fbd59f720d4a8db17fe80887730d2a3d8e32751236dc2953958619b41b9': 'Sampras Tennis 96 (USA)',
    '57fa3662f589929d180648090104f8c802894602a6f660755121cb44918f382c': 'Micro Machines 2 - Turbo Tournament (USA)',
    '43e68f99620bb3dd0ff3b28d232ae43c5b6489716c4cde09725ab4b71704937e': 'Micro Machines Military (USA)',
    '77ff023aa9f88aeb1605d3060b1331b816752b12b64ff2fe95d4a9f3c5dff946': 'Micro Machines Turbo Tournament 96 (USA)',
    '78705e4d3c91c8dc078fb61a08bf37c9c8e2f7ee9e9b13ddfe8279e54e6e9c6b': 'Super Skidmarks (USA)',
}
# Team Player games whose header does not declare it (no '4' at $190), keyed by SHA-256; each entry is checked by a session
# log in which the game reads players 3 and 4 through the Team Player.
TEAM_PLAYER_DUMPS = {
    '473f66ab64bdcf4a3460c583cdc06c473d0a47a47f28091809225852cd9653b2': 'Gauntlet IV (USA)',
}
WAYPLAY_PROBE = (b'\x13\xfc\x00\x7c\x00\xa1\x00\x05',)   # move.b #$7C,($A10005).l


def detect(rom) -> dict:
    """The adapter this cartridge was made for: {'multitap': name or None, 'players': 2 or 4}."""
    data = rom.data
    if rom.sha256 in JCART_DUMPS:
        return {'multitap': NAMES[JCART], 'players': 4}
    team_player = b'4' in data[0x190:0x1a0] or rom.sha256 in TEAM_PLAYER_DUMPS
    way_play = any(probe in data for probe in WAYPLAY_PROBE)
    if team_player or way_play:
        return {'multitap': NAMES[PORTS], 'players': 4}
    return {'multitap': None, 'players': 2}


def header_lines(rom) -> str:
    """The defines of retro_md_game.h."""
    found = detect(rom)
    mode = {NAMES[PORTS]: PORTS, NAMES[JCART]: JCART}.get(found['multitap'], NONE)
    return f'#define RR_MD_MULTITAP {mode}\n#define RR_MD_PLAYERS {found["players"]}\n'


TAP_C = r'''
/* Multitaps (retrorecomp/megadrive_multitap.py): the Team Player and the 4 Way Play on the control ports, the J-Cart on the
 * cartridge. Players 3 and 4 come from rr16_md_extra_pads. The multiplayer rollback snapshot keeps this state
 * (rr_md_tap_live_*); a quick state does not: after its load the adapters start from idle, and the game sets them again on
 * its next read. */
#ifndef RR_MD_MULTITAP
#define RR_MD_MULTITAP 0
#endif
typedef struct {
    uint16_t pad[2];          /* players 3 and 4 (GPAD_* bits) */
    uint8_t tp_state;         /* the Team Player's TH (0x40) and TR (0x20) as the game drives them */
    uint8_t tp_counter;
    uint8_t wp_latch, wp_active;
    uint8_t jcart_th;
    uint8_t reserved[3];
    uint32_t reads[3];        /* the game's reads of players 3/4 through each adapter, for the evidence */
} RrMdTap;
static RrMdTap rr_md_tap = {{0, 0}, 0x60, 0, 0, 0, 1, {0}, {0}};
int rr_md_tap_mode = RR_MD_MULTITAP;
void rr16_md_extra_pads(uint16_t p3, uint16_t p4) { rr_md_tap.pad[0] = p3; rr_md_tap.pad[1] = p4; }
size_t rr_md_tap_live_size(void) { return sizeof rr_md_tap; }
void rr_md_tap_live_save(void *data) { memcpy(data, &rr_md_tap, sizeof rr_md_tap); }
void rr_md_tap_live_load(const void *data) { memcpy(&rr_md_tap, data, sizeof rr_md_tap); }
void rr_md_tap_reads(uint32_t out[3]) { memcpy(out, rr_md_tap.reads, sizeof rr_md_tap.reads); }
/* The first read of players 3/4 through an adapter is said once on stderr (the evidence of a session's log). */
/* Once per run, on stderr: the game reached an adapter's identification (Team Player types, 4 Way Play signature). */
static void rr_md_tap_seen(int kind) {
    static int said[2];
    static const char *const names[2] = {"identifies the Team Player (its pad types)", "asks for the 4 Way Play's signature"};
    if (!said[kind]) { said[kind] = 1; fprintf(stderr, "[multitap] the game %s\n", names[kind]); }
}
static void rr_md_tap_read(int kind) {
    static const char *const names[3] = {"Team Player", "4 Way Play", "J-Cart"};
    if (!rr_md_tap.reads[kind]++) fprintf(stderr, "[multitap] the game reads players 3 and 4 through the %s\n", names[kind]);
}
static uint16_t rr_md_tap_word(const GenesisBus *b, unsigned player) {
    return player < 2 ? b->pad[player] : rr_md_tap.pad[player - 2];
}
/* A three-button pad's six lines for a TH level, active low: TH=1 C B R L D U, TH=0 S A 0 0 D U. */
static uint8_t rr_md_tap_pad3(uint16_t p, int th) {
    if (th) return (uint8_t)(((p & GPAD_C) ? 0 : 0x20) | ((p & GPAD_B) ? 0 : 0x10) | ((p & GPAD_RIGHT) ? 0 : 0x08) |
                             ((p & GPAD_LEFT) ? 0 : 0x04) | ((p & GPAD_DOWN) ? 0 : 0x02) | ((p & GPAD_UP) ? 0 : 0x01));
    return (uint8_t)(((p & GPAD_START) ? 0 : 0x20) | ((p & GPAD_A) ? 0 : 0x10) | ((p & GPAD_DOWN) ? 0 : 0x02) |
                     ((p & GPAD_UP) ? 0 : 0x01));
}
/* The lines a port reads: the bits the game drives as outputs read back what it wrote, the others come from the device. */
static uint8_t rr_md_tap_merge(const GenesisBus *b, int port, uint8_t device) {
    const uint8_t outputs = b->io_ctrl[port] & 0x7f;
    return (uint8_t)(((b->io_data[port] & outputs) | (device & ~outputs)) & 0x7f);
}
static uint8_t rr_md_tap_team_player(const GenesisBus *b) {
    const uint8_t tl = (uint8_t)((rr_md_tap.tp_state & 0x20) >> 1);
    const unsigned i = rr_md_tap.tp_counter;
    uint8_t nibble = 0x0f;
    if (i == 0) nibble = 0x03;
    else if (i == 1) nibble = 0x0f;
    else if (i < 4) nibble = 0x00;
    else if (i < 8) { nibble = RR_MD_SIX_BUTTONS ? 0x01 : 0x00; if (i == 4) rr_md_tap_seen(0); }
    else {
        const unsigned per = RR_MD_SIX_BUTTONS ? 3u : 2u, player = (i - 8u) / per, group = (i - 8u) % per;
        if (player < 4) {
            const uint16_t p = rr_md_tap_word(b, player);
            unsigned pressed;
            if (group == 0) pressed = ((p & GPAD_RIGHT) ? 8u : 0u) | ((p & GPAD_LEFT) ? 4u : 0u) | ((p & GPAD_DOWN) ? 2u : 0u) | ((p & GPAD_UP) ? 1u : 0u);
            else if (group == 1) pressed = ((p & GPAD_START) ? 8u : 0u) | ((p & GPAD_A) ? 4u : 0u) | ((p & GPAD_C) ? 2u : 0u) | ((p & GPAD_B) ? 1u : 0u);
            else pressed = ((p & GPAD_MODE) ? 8u : 0u) | ((p & GPAD_X) ? 4u : 0u) | ((p & GPAD_Y) ? 2u : 0u) | ((p & GPAD_Z) ? 1u : 0u);
            nibble = (uint8_t)(~pressed & 0x0f);
            if (player >= 2) rr_md_tap_read(0);
        }
    }
    return rr_md_tap_merge(b, 0, (uint8_t)(0x60 | tl | nibble));
}
static uint8_t rr_md_tap_port(const GenesisBus *b, int port) {
    if (rr_md_tap_mode != 1) return pad_read(b, port);
    if (port == 1) return rr_md_tap.wp_active ? 0x7f : rr_md_tap_merge(b, 1, 0x7f);   /* no pad of its own */
    if (rr_md_tap.wp_active) {
        if (rr_md_tap.wp_latch & 4) return rr_md_tap_merge(b, 0, 0x7c);
        const unsigned player = rr_md_tap.wp_latch & 3u;
        const int th = (b->io_data[0] & b->io_ctrl[0] & 0x40) != 0 || !(b->io_ctrl[0] & 0x40);
        if (player >= 2) rr_md_tap_read(1);
        return rr_md_tap_merge(b, 0, (uint8_t)((th ? 0x40 : 0) | rr_md_tap_pad3(rr_md_tap_word(b, player), th)));
    }
    return rr_md_tap_team_player(b);
}
/* A write to a data port (before the bus stores it). */
static void rr_md_tap_write(const GenesisBus *b, int port, uint8_t v) {
    if (rr_md_tap_mode != 1) return;
    const uint8_t outputs = b->io_ctrl[port];
    if (port == 0) {
        /* Only the lines the game drives change; TH and TR keep their level otherwise (both high at power-on). */
        const uint8_t old = rr_md_tap.tp_state, state = (uint8_t)(((old & ~outputs) | (v & outputs)) & 0x60);
        if (state & 0x40) rr_md_tap.tp_counter = 0;
        else if ((state ^ old) & 0x60) { if (rr_md_tap.tp_counter < 0xff) ++rr_md_tap.tp_counter; }
        rr_md_tap.tp_state = state;
        return;
    }
    const uint8_t lines = (uint8_t)(((v & outputs) | (~outputs & 0x7f)) & 0x7f);   /* undriven lines read high */
    if (!(lines & 3)) {
        rr_md_tap.wp_latch = (uint8_t)((lines >> 4) & 7); rr_md_tap.wp_active = 1;
        if (rr_md_tap.wp_latch & 4) rr_md_tap_seen(1);
    }
}
/* The J-Cart's ports: `a` already masked to 24 bits. */
static int rr_md_jcart_hit(uint32_t a) { return rr_md_tap_mode == 2 && ((a & ~1u) == 0x38fffeu || (a & ~1u) == 0x3ffffeu); }
static uint16_t rr_md_jcart_read(void) {
    const int th = rr_md_tap.jcart_th;
    rr_md_tap_read(2);
    const uint8_t p3 = (uint8_t)(0x80 | (th ? 0x40 : 0) | rr_md_tap_pad3(rr_md_tap.pad[0], th));
    const uint8_t p4 = (uint8_t)(0x80 | (th ? 0x40 : 0) | rr_md_tap_pad3(rr_md_tap.pad[1], th));
    return (uint16_t)(p4 << 8 | p3);
}
'''


def bus(source: str) -> str:
    """The private bus copy, after megadrive_cart.bus (whose cartridge hooks the J-Cart goes before)."""
    def replace(old, new, count=1):
        nonlocal source
        if source.count(old) != count:
            raise ConversionError('Pinned Mega Drive controller ports changed; multitap adaptation refused.')
        source = source.replace(old, new)
    replace('static uint16_t io_read(const GenesisBus *b, uint32_t a)', TAP_C + 'static uint16_t io_read(const GenesisBus *b, uint32_t a)')
    replace('        case 0x02: return pad_read(b, 0);', '        case 0x02: return rr_md_tap_port(b, 0);')
    replace('        case 0x04: return pad_read(b, 1);', '        case 0x04: return rr_md_tap_port(b, 1);')
    replace('        case 0x02: pad_io_tick(b, 0, v);', '        case 0x02: rr_md_tap_write(b, 0, v); pad_io_tick(b, 0, v);')
    replace('        case 0x04: pad_io_tick(b, 1, v);', '        case 0x04: rr_md_tap_write(b, 1, v); pad_io_tick(b, 1, v);')
    replace('    unsigned cart_value; if(rr_cart_read(b,a,&cart_value,0))return (uint16_t)cart_value;',
            '    if (rr_md_jcart_hit(a)) return rr_md_jcart_read();\n'
            '    unsigned cart_value; if(rr_cart_read(b,a,&cart_value,0))return (uint16_t)cart_value;')
    replace('    unsigned cart_value; if(rr_cart_read(b,a,&cart_value,0))return (uint8_t)cart_value;',
            '    if (rr_md_jcart_hit(a)) { uint16_t w = rr_md_jcart_read(); return (uint8_t)((a & 1u) ? w : w >> 8); }\n'
            '    unsigned cart_value; if(rr_cart_read(b,a,&cart_value,0))return (uint8_t)cart_value;')
    replace('    if(rr_cart_write(b,a,v,2))return;',
            '    if (rr_md_jcart_hit(a)) { rr_md_tap.jcart_th = (uint8_t)(v & 1u); return; }\n    if(rr_cart_write(b,a,v,2))return;')
    replace('    if(rr_cart_write(b,a,v,1))return;',
            '    if (rr_md_jcart_hit(a)) { rr_md_tap.jcart_th = (uint8_t)(v & 1u); return; }\n    if(rr_cart_write(b,a,v,1))return;')
    return source

