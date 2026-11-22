/* An AUTHORED contention rule for tools/z80_contention_loop_selftest.py: the machine's three functions the chain's evaluator
 * (banked_timed.h, rendered by retrorecomp/z80_timed.py) asks, written so that every kind of cycle is held off by an amount that
 * depends on both the T-state and the address. It is not any real machine's rule (the ZX Spectrum's is its own); it only has to
 * make each delay visible and different, so that a missing or misplaced delay in the chain's step loop (a HALT cycle, the
 * acceptance of /INT in mode 1 or 2, the acceptance of /NMI) changes the count of T-states.
 * MIT, Retro-Recomp. Compiled into the check's two programs only, never into a game. */
#include <stdint.h>

/* The cartridge as the machine sees it (0000h-BFFFh), written by the self-test: the operands of an instruction are read from it. */
extern const unsigned char rr_gate_rom[0xC000];

unsigned rr_contend_memory(uint64_t t, uint16_t address)
{
    const unsigned k = (unsigned)(t % 997u);
    if ((k * 5u + (unsigned)(address >> 3)) % 7u == 0u)
        return 3u;
    return ((k ^ address) & 3u) == 0u ? 1u : 0u;
}

unsigned rr_contend_io(uint64_t t, uint16_t port)
{
    return 1u + (unsigned)((t + port) & 3u);
}

uint8_t rr_contend_peek(uint16_t address)
{
    return address < 0xC000u ? rr_gate_rom[address] : 0xFFu;
}
