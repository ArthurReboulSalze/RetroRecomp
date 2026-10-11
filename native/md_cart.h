#ifndef RR_MD_CART_H
#define RR_MD_CART_H
#include "retro_md_game.h"
#include "md_timing.h"
#include "md_eeprom.h"
#include "video/genesis_bus.h"
#ifndef RR_MD_SEGA_MAPPER
#define RR_MD_SEGA_MAPPER 0
#endif
typedef struct {
    RrMdEeprom eeprom;
    uint8_t acclaim_rom, mapper, pages[8], reserved[6];
} RrMdCartState;
void rr_md_cart_setup(GenesisBus *bus);
void rr_md_cart_attach_rom(const uint8_t *rom, size_t size);
uint32_t rr_md_cart_rom_offset(uint32_t pc);
uint32_t rr_md_cart_code_offset(uint32_t pc, const uint16_t *words, unsigned count);
extern uint32_t rr_md_rom_fetch_offset;
void rr_md_cart_advance(GenesisBus *bus, uint64_t now);
const RrMdCartState *rr_md_cart_state(void);
int rr_md_cart_valid(const RrMdCartState *state);
int rr_md_cart_restore(const RrMdCartState *state);
int rr_md_cart_legacy_allowed(void);
uint64_t machine_cart_stamp(void);
#endif
