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
void rr_cps1_host_frame(uint16_t p1, uint16_t p2);
uint32_t rr_cps1_frame_index(void);
void rr_cps1_restore_frame(uint32_t frame);
void rr_cps1_reset_machine(void);
const int16_t *rr_cps1_take_audio(size_t *count);
int rr_cps1_display_width(void);
int rr_cps1_rotated(void);
#endif
