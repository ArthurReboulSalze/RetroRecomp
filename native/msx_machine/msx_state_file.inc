/* Quick states of the MSX game (MIT, Retro-Recomp), included by msx_player.c after msx_glue.inc and msx_game.h.
 *
 * The file is the envelope the Z80 machines share (state_envelope.h: magic RRMSXST, schema 1, machine 1 MSX1 or 2 MSX2, the
 * cartridge's SHA-256), then the body: (1) the build binding, RR_MSX_STATE_ABI, 32 bytes the converter writes in
 * msx_game.h (the state layout, the BIOS, the mapper, the cartridge base, the mirror, the standard, the model, the mapper
 * RAM), compared and never applied; (2) the CPU and the loop's cycle; (3-9) the machine (msx_state.c). A state is
 * checked whole on scratch copies (the CPU in a local, the machine in msx_state.c's scratch) and applied only then. Saved
 * and loaded at the service point (an instruction and the interrupt it may accept complete), the only point where the
 * loop's own locals hold nothing a state would need. */
#include "state_envelope.h"

int msx_machine_state(MsxMachine *m, uint8_t *ram64, RetroStateIO *io);
int msx_machine_state_check_io(const MsxMachine *m, const uint8_t *ram64, RetroStateIO *io, uint64_t *cycles);
void msx_refresh_layout(MsxMachine *m);

#define MSX_STATE_SCHEMA 1u
/* The largest body: 4 MB of mapper RAM, the V9938 (VRAM, picture), the TMS9918A, the slots and the rest. */
#define MSX_STATE_CAPACITY ((size_t)(8u << 20))

static const uint8_t msx_state_binding[32] = RR_MSX_STATE_ABI;

/* (2) The CPU, field for field as the Master System's (gamestate.inc), into `s`. */
static void msx_cpu_state(RetroStateIO *io, Z80State *s)
{
    Z80State v = *s;
    RR_FIELD(v, a, 1, 255); RR_FIELD(v, f, 1, 255); RR_FIELD(v, b, 1, 255); RR_FIELD(v, c, 1, 255);
    RR_FIELD(v, d, 1, 255); RR_FIELD(v, e, 1, 255); RR_FIELD(v, h, 1, 255); RR_FIELD(v, l, 1, 255);
    RR_FIELD(v, a_, 1, 255); RR_FIELD(v, f_, 1, 255); RR_FIELD(v, b_, 1, 255); RR_FIELD(v, c_, 1, 255);
    RR_FIELD(v, d_, 1, 255); RR_FIELD(v, e_, 1, 255); RR_FIELD(v, h_, 1, 255); RR_FIELD(v, l_, 1, 255);
    RR_FIELD(v, pc, 2, 65535); RR_FIELD(v, sp, 2, 65535); RR_FIELD(v, ix, 2, 65535);
    RR_FIELD(v, iy, 2, 65535); RR_FIELD(v, wz, 2, 65535); RR_FIELD(v, i, 1, 255); RR_FIELD(v, r, 1, 255);
    RR_FIELD(v, iff1, 1, 1); RR_FIELD(v, iff2, 1, 1); RR_FIELD(v, im, 1, 2); RR_FIELD(v, halted, 1, 1);
    RR_FIELD(v, q, 1, 255); RR_FIELD(v, p, 1, 1); RR_FIELD(v, ei_block, 1, 1); RR_FIELD(v, cyc, 8, (1ULL << 60));
    *s = v;
}

static void msx_state_body(RetroStateIO *io)
{
    /* (1) the build binding */
    for (int i = 0; i < 32; ++i)
        if (rr_state_word(io, msx_state_binding[i], 1, 255) != msx_state_binding[i])
            io->ok = false;
    /* (2) the CPU: into a candidate, applied last */
    Z80State cpu = g_z80;
    msx_cpu_state(io, &cpu);
    /* (3-9) the machine */
    if (io->mode == RR_STATE_CHECK) {
        uint64_t cycles = 0;
        if (!msx_machine_state_check_io(&machine, ram, io, &cycles) || cycles > cpu.cyc
            || cpu.cyc - cycles > MSX_CYCLES_PER_LINE)
            io->ok = false;
        return;
    }
    msx_machine_state(&machine, ram, io);
    if (io->mode == RR_STATE_APPLY && io->ok) {
        g_z80 = cpu;
        msx_refresh_layout(&machine);
        map_built = UINT32_MAX;                    /* the loop's region map is rebuilt before the next step */
        g_next_line_cyc = msx_next_event(&machine);
        smsrecomp_measured_guest_cycles = g_z80.cyc;
        step_start = g_z80.cyc;
        smsrecomp_interp_depth = 0;                /* the fallback CPU is refilled from g_z80 at each use */
        /* Execution, fallback and learning counters stay cumulative across a load, as on the Master System. */
    }
}

static RetroStateEnvelope msx_state_envelope(void)
{
    RetroStateEnvelope e = {"RRMSXST\0", MSX_STATE_SCHEMA, RR_MSX_MODEL == 2 ? 2u : 1u, RR_MSX_IDENTITY, msx_state_body};
    return e;
}

/* Save to `path`: written beside it, flushed, then put in its place (the old state stays whole if anything fails). */
static int msx_state_save(const wchar_t *path)
{
    uint8_t *data = (uint8_t *)malloc(MSX_STATE_CAPACITY);
    if (!data) return RR_STATE_IO_ERROR;
    RetroStateEnvelope envelope = msx_state_envelope();
    size_t size = 0;
    if (rr_state_envelope_write(&envelope, data, MSX_STATE_CAPACITY, &size) != RR_STATE_OK) { free(data); return RR_STATE_INVALID; }
    wchar_t temporary[32768];
    swprintf(temporary, 32768, L"%ls.%lu.tmp", path, rr_process_id());
    FILE *f = rr_fopen(temporary, L"wb");
    bool ok = f && fwrite(data, size, 1, f) == 1;
    if (ok) ok = rr_flush_file(f) != 0;
    if (f && fclose(f) != 0) ok = false;
    free(data);
    if (ok) ok = rr_replace(temporary, path) != 0;
    if (!ok) rr_remove(temporary);
    return ok ? RR_STATE_OK : RR_STATE_IO_ERROR;
}

/* Load `path`: RR_STATE_OK, or a refusal that leaves the machine and the file as they were. */
static int msx_state_load(const wchar_t *path)
{
    FILE *f = rr_fopen(path, L"rb");
    if (!f) return rr_exists(path) ? RR_STATE_IO_ERROR : RR_STATE_MISSING;
    uint8_t *data = (uint8_t *)malloc(MSX_STATE_CAPACITY);
    if (!data) { fclose(f); return RR_STATE_IO_ERROR; }
    size_t size = fread(data, 1, MSX_STATE_CAPACITY, f);
    int extra = fgetc(f); bool read_ok = !ferror(f); fclose(f);
    int result = RR_STATE_INVALID;
    if (read_ok && extra == EOF) {
        RetroStateEnvelope envelope = msx_state_envelope();
        result = rr_state_envelope_read(&envelope, data, size);
        /* A whole, undamaged state of another build (BIOS, mapper, standard, RAM...): incompatible, not damaged. */
        if (result == RR_STATE_INVALID && size >= RR_STATE_ENVELOPE_HEADER + 32
            && (size_t)(data[80] | data[81] << 8 | (uint32_t)data[82] << 16 | (uint32_t)data[83] << 24) == size - RR_STATE_ENVELOPE_HEADER
            && rr_state_crc(data + RR_STATE_ENVELOPE_HEADER, size - RR_STATE_ENVELOPE_HEADER)
               == (uint32_t)(data[84] | data[85] << 8 | (uint32_t)data[86] << 16 | (uint32_t)data[87] << 24)
            && memcmp(data + RR_STATE_ENVELOPE_HEADER, msx_state_binding, 32))
            result = RR_STATE_INCOMPATIBLE;
    }
    free(data);
    return result;
}
