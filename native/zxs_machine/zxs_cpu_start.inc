/* The CPU's registers from the ZX Spectrum's machine image, into the translated register file g_z80 (z80-recomp-core's
 * Z80State), for the native check, the game and the reference runner alike (the reference copies them to its interpreter with
 * banked_reference_state.inc's state_to_hz). MIT, Retro-Recomp. The includer has g_z80 and `machine` in scope. */
/* The CPU's registers from the machine image (zxs_load_image). */
static void zxs_cpu_from_image(const ZxsCpuStart *c)
{
    memset(&g_z80, 0, sizeof g_z80);
    g_z80.a = (uint8_t)(c->af >> 8); g_z80.f = (uint8_t)c->af;
    g_z80.b = (uint8_t)(c->bc >> 8); g_z80.c = (uint8_t)c->bc;
    g_z80.d = (uint8_t)(c->de >> 8); g_z80.e = (uint8_t)c->de;
    g_z80.h = (uint8_t)(c->hl >> 8); g_z80.l = (uint8_t)c->hl;
    g_z80.a_ = (uint8_t)(c->af_ >> 8); g_z80.f_ = (uint8_t)c->af_;
    g_z80.b_ = (uint8_t)(c->bc_ >> 8); g_z80.c_ = (uint8_t)c->bc_;
    g_z80.d_ = (uint8_t)(c->de_ >> 8); g_z80.e_ = (uint8_t)c->de_;
    g_z80.h_ = (uint8_t)(c->hl_ >> 8); g_z80.l_ = (uint8_t)c->hl_;
    g_z80.ix = c->ix; g_z80.iy = c->iy; g_z80.sp = c->sp; g_z80.pc = c->pc;
    g_z80.i = c->i; g_z80.r = c->r; g_z80.im = c->im;
    g_z80.iff1 = c->iff1 != 0; g_z80.iff2 = c->iff2 != 0;
    g_z80.cyc = machine.cycles;
}
