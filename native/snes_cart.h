/* Ordinary cartridge RAM decoding; never probe MMIO to recognize code. */
#ifndef RR_SNES_CART_H
#define RR_SNES_CART_H
#include "snes/cart.h"
static inline int32_t rr_snes_cart_ram_offset(const Cart *cart, uint8_t bank, uint16_t address) {
    if (!cart || !cart->ram || !cart->ramSize || (cart->ramSize & (cart->ramSize-1)) ||
        bank==0x7e || bank==0x7f) return -1;
    if (cart->type==CART_DSP1_HIROM && cart_is_dsp1_sram_window(cart,bank,address))
        return (address&0x1fffu)&(cart->ramSize-1);
    if (cart->type==CART_LOROM || cart->type==CART_DSP1) {
        bool full=cart->romImageSize<=0x200000 && cart->ramSize<=0x8000;
        if (((bank>=0x70 && bank<0x7e) || bank>=0xf0) && (address<0x8000 || full))
            return (((bank&15u)<<15) | (address&0x7fffu)) & (cart->ramSize-1);
    } else if (cart->type==CART_HIROM) {
        uint8_t canonical=bank&0x7f;
        if (canonical>=0x20 && canonical<0x40 && address>=0x6000 && address<0x8000)
            return (((canonical&0x1fu)<<13) | (address&0x1fffu)) & (cart->ramSize-1);
    }
    return -1;
}
#endif
