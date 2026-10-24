/* CPS-1 game runner <-> shared 16-bit host. Original RetroRecomp code: MIT. */
#ifndef CPS1_HOST_H
#define CPS1_HOST_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Host pad bits follow the menu's action order: buttons 1-6, Start, Coin,
 * Up, Down, Left, Right. cps1_game.h maps them to this game's ports. */
enum { RR_CPS1_B1, RR_CPS1_B2, RR_CPS1_B3, RR_CPS1_B4, RR_CPS1_B5, RR_CPS1_B6,
       RR_CPS1_START, RR_CPS1_COIN, RR_CPS1_UP, RR_CPS1_DOWN, RR_CPS1_LEFT, RR_CPS1_RIGHT };
typedef struct { uint8_t port; uint16_t mask; uint8_t action, player; } RrCps1Input;

void rr_cps1_apply_pads(uint16_t p1, uint16_t p2);
/* Players 3 and 4 (RR_CPS1_PLAYERS > 2), applied with the next pads; scripted
 * routes never set them, so they stay released there. */
void rr_cps1_set_extra_pads(uint16_t p3, uint16_t p4);
void rr_cps1_host_frame(uint16_t p1, uint16_t p2);

/* DIP switches with MAME's names and settings (cps1_game.h). Port 0-2 is
 * DSWA-DSWC; a switch with a condition shows only while the other port's
 * masked value equals (or differs from) condition_value. */
#define RR_CPS1_DIP_SETTINGS 24
typedef struct {
    uint8_t port; uint16_t mask, fallback; const char *name; uint8_t count;
    uint16_t values[RR_CPS1_DIP_SETTINGS]; const char *labels[RR_CPS1_DIP_SETTINGS];
    int8_t condition_port; uint8_t condition_equals; uint16_t condition_mask, condition_value;
} RrCps1Dip;
int rr_cps1_dip_count(void);
const RrCps1Dip *rr_cps1_dip(int index);
bool rr_cps1_dip_visible(int index);
int rr_cps1_dip_setting(int index);             /* -1 when no setting matches */
void rr_cps1_dip_values(uint16_t values[3]);
/* Interactive play only: validation runs keep the catalogue defaults. The
 * values stay applied across Shift+F1 and F9. */
void rr_cps1_set_dip_values(const uint16_t values[3]);
void rr_cps1_dip_cycle(int index, int step);
uint32_t rr_cps1_frame_index(void);
void rr_cps1_restore_frame(uint32_t frame);
void rr_cps1_reset_machine(void);
const int16_t *rr_cps1_take_audio(size_t *count);
int rr_cps1_display_width(void);
int rr_cps1_rotated(void);
#endif
