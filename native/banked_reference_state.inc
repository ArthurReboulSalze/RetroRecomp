/* The copies between the translated register file (g_z80, z80-recomp-core's Z80State) and the reference CPU of the
 * counted fallback (g_hz, the corrected interpreter of runtime_reference.c), for a machine on the banked Z80 chain that
 * does not run the Sega runner. retrorecomp/z80_chain.py pastes this file ahead of the step loop
 * (native/banked_runtime.inc) when the machine asks for it (Z80Machine.reference_state); the machine's glue declares
 * g_z80 and g_hz before the place where it includes the loop. MIT, Retro-Recomp.
 *
 * The Master System and the Game Gear do not get this file: the pinned runner their glue is made from has its own pair,
 * and their generated text must not change. tests/test_z80_chain.py compares the two pairs, statement by statement.
 *
 * The cycle counter and the PC are the caller's: the fallback rebases the interpreter's count to 0 and sets its PC.
 * No interrupt is pending in the interpreter (the loop accepts interrupts itself); EI's one-instruction delay and the
 * Q and P latches (the undocumented flags of SCF/CCF, the parity of LD A,I / LD A,R under an interrupt) are carried. */
static inline uint8_t banked_pack_f(const z80 *z) {
    return (uint8_t)((z->sf << 7) | (z->zf << 6) | (z->yf << 5) | (z->hf << 4) |
                     (z->xf << 3) | (z->pf << 2) | (z->nf << 1) | (z->cf));
}

static inline void banked_unpack_f(z80 *z, uint8_t f) {
    z->sf = (f >> 7) & 1; z->zf = (f >> 6) & 1; z->yf = (f >> 5) & 1; z->hf = (f >> 4) & 1;
    z->xf = (f >> 3) & 1; z->pf = (f >> 2) & 1; z->nf = (f >> 1) & 1; z->cf = f & 1;
}

static void state_to_hz(void) {
    g_hz.q = g_z80.q; g_hz.p = g_z80.p;
    g_hz.a = g_z80.a; g_hz.b = g_z80.b; g_hz.c = g_z80.c; g_hz.d = g_z80.d;
    g_hz.e = g_z80.e; g_hz.h = g_z80.h; g_hz.l = g_z80.l;
    banked_unpack_f(&g_hz, g_z80.f);
    g_hz.a_ = g_z80.a_; g_hz.b_ = g_z80.b_; g_hz.c_ = g_z80.c_; g_hz.d_ = g_z80.d_;
    g_hz.e_ = g_z80.e_; g_hz.h_ = g_z80.h_; g_hz.l_ = g_z80.l_; g_hz.f_ = g_z80.f_;
    g_hz.ix = g_z80.ix; g_hz.iy = g_z80.iy; g_hz.sp = g_z80.sp;
    g_hz.mem_ptr = g_z80.wz; g_hz.i = g_z80.i; g_hz.r = g_z80.r;
    g_hz.iff1 = g_z80.iff1; g_hz.iff2 = g_z80.iff2;
    g_hz.interrupt_mode = g_z80.im; g_hz.halted = g_z80.halted;
    g_hz.int_pending = 0; g_hz.nmi_pending = 0;
    g_hz.iff_delay = g_z80.ei_block;
}

static void state_from_hz(void) {
    g_z80.q = g_hz.q; g_z80.p = g_hz.p;
    g_z80.a = g_hz.a; g_z80.b = g_hz.b; g_z80.c = g_hz.c; g_z80.d = g_hz.d;
    g_z80.e = g_hz.e; g_z80.h = g_hz.h; g_z80.l = g_hz.l;
    g_z80.f = banked_pack_f(&g_hz);
    g_z80.a_ = g_hz.a_; g_z80.b_ = g_hz.b_; g_z80.c_ = g_hz.c_; g_z80.d_ = g_hz.d_;
    g_z80.e_ = g_hz.e_; g_z80.h_ = g_hz.h_; g_z80.l_ = g_hz.l_; g_z80.f_ = g_hz.f_;
    g_z80.ix = g_hz.ix; g_z80.iy = g_hz.iy; g_z80.sp = g_hz.sp;
    g_z80.wz = g_hz.mem_ptr; g_z80.i = g_hz.i; g_z80.r = g_hz.r;
    g_z80.iff1 = g_hz.iff1; g_z80.iff2 = g_hz.iff2;
    g_z80.im = g_hz.interrupt_mode; g_z80.halted = g_hz.halted;
    g_z80.ei_block = g_hz.iff_delay ? 1 : 0;
}
