/* The Game Boy machine's state for multiplayer rollback and the host's F8 / F9 for everyone: an in-memory snapshot of the whole
 * state that decides the future frames, and a digest of it. Included at the END of the runtime's gbrt.c (retrorecomp/gameboy_runtime.py),
 * because it needs the runtime's own static core-state capture and restore. Original RetroRecomp code: MIT.
 *
 * What the snapshot holds: the CPU, the timers and counters of the context (the same core state as the quick-state file, which also
 * carries the cartridge mapper registers, the clock of the MBC3 in cycles, DMA, HDMA, serial and the LCD-off bookkeeping), the sound unit's
 * and the video unit's own structs, the five memory blocks and the cartridge RAM, and the five fields of the sound unit's lazy
 * scheduling (audio_pending_*). The quick-state file synchronises the sound unit before it writes; this does not, so that taking a
 * snapshot never changes the future (a seat that saved at a frame and a seat that did not must stay equal). Nothing host-side:
 * not the window, the audio ring, the filters, the performance counters, the pad registers of the shell (the adapter adds those).
 *
 * Memory only: no file, no allocation. The bytes are for this process and this build (raw structs): never sent, never kept. */
#ifndef RR_GB_MACHINE_STATE_H
#define RR_GB_MACHINE_STATE_H
#include "gb_digest.h"

/* The sound unit's digest, in audio.c (named fields of its private structs). */
void rr_gb_audio_digest(const void* audio, RrGbDigest* digest);

#define RR_GB_SNAP_MAGIC 0x53474252u   /* "RBGS" */
#define RR_GB_SNAP_VERSION 1u

typedef struct RrGbSnapHeader {
    uint32_t magic;
    uint32_t version;
    uint64_t rom_hash;
    uint32_t rom_size;
    uint32_t eram_size;
    uint32_t core_size;
    uint32_t ppu_size;
    uint32_t apu_size;
    uint32_t total;
    uint8_t reserved[24];   /* the header is 64 bytes: what follows stays 8-aligned */
} RrGbSnapHeader;

typedef struct RrGbSnapAudioPending {
    uint32_t cpu_cycles;
    uint32_t cycles_until_event;
    uint16_t old_div;
    uint8_t system_cycle_remainder;
    uint8_t double_speed;
    uint32_t reserved;
} RrGbSnapAudioPending;

#define RR_GB_SNAP_ALIGN(n) (((n) + 15u) & ~(size_t)15u)

/* The most cartridge RAM a Game Boy cartridge has: 128 KiB (sixteen banks of 8 KiB, MBC5). */
#define RR_GB_ERAM_MAX 0x20000u

static size_t rr_gb_snap_payload(void) {
    return sizeof(GBSavestateCoreState) + sizeof(RrGbSnapAudioPending) + RR_GB_ERAM_MAX + WRAM_BANK_SIZE * 8u + VRAM_SIZE * 2u +
           OAM_SIZE + HRAM_SIZE + (IO_SIZE + 1u) + sizeof(GBPPU) + gb_audio_state_size();
}

/* The size of every snapshot: the same for every game and every call, whatever the cartridge RAM (a smaller one is padded with zeros), so that
 * it is known before the game's context exists (the host kit asks it when the session opens, before the guest registers its context). */
size_t rr_gb_snap_bound(const GBContext* ctx) {
    (void)ctx;
    return RR_GB_SNAP_ALIGN(sizeof(RrGbSnapHeader) + rr_gb_snap_payload());
}

static bool rr_gb_snap_ready(const GBContext* ctx) {
    return ctx && ctx->rom && ctx->rom_size != 0 && ctx->wram && ctx->vram && ctx->oam && ctx->hram && ctx->io && ctx->eram_size <= RR_GB_ERAM_MAX;
}

/* The bytes written, 0 on a failure (a buffer that is too small, a context that is not ready). Valid after any frame. */
size_t rr_gb_snap_save(GBContext* ctx, void* out, size_t capacity) {
    const size_t bound = rr_gb_snap_bound(ctx);
    if (!rr_gb_snap_ready(ctx) || !out || capacity < bound) return 0;
    uint8_t* cursor = (uint8_t*)out;
    RrGbSnapHeader* header = (RrGbSnapHeader*)cursor;
    memset(header, 0, sizeof *header);
    header->magic = RR_GB_SNAP_MAGIC;
    header->version = RR_GB_SNAP_VERSION;
    header->rom_hash = gb_context_compute_rom_hash(ctx);
    header->rom_size = (uint32_t)ctx->rom_size;
    header->eram_size = (uint32_t)ctx->eram_size;
    header->core_size = (uint32_t)sizeof(GBSavestateCoreState);
    header->ppu_size = ctx->ppu ? (uint32_t)sizeof(GBPPU) : 0u;
    header->apu_size = ctx->apu ? (uint32_t)gb_audio_state_size() : 0u;
    header->total = (uint32_t)bound;
    cursor += sizeof *header;
    gbrt_capture_core_state(ctx, (GBSavestateCoreState*)cursor);
    cursor += sizeof(GBSavestateCoreState);
    RrGbSnapAudioPending pending;
    memset(&pending, 0, sizeof pending);
    pending.cpu_cycles = ctx->audio_pending_cpu_cycles;
    pending.cycles_until_event = ctx->audio_cycles_until_event;
    pending.old_div = ctx->audio_pending_old_div;
    pending.system_cycle_remainder = ctx->audio_pending_system_cycle_remainder;
    pending.double_speed = ctx->audio_pending_double_speed;
    memcpy(cursor, &pending, sizeof pending); cursor += sizeof pending;
    if (ctx->eram_size) { memcpy(cursor, ctx->eram, ctx->eram_size); cursor += ctx->eram_size; }
    memcpy(cursor, ctx->wram, WRAM_BANK_SIZE * 8u); cursor += WRAM_BANK_SIZE * 8u;
    memcpy(cursor, ctx->vram, VRAM_SIZE * 2u); cursor += VRAM_SIZE * 2u;
    memcpy(cursor, ctx->oam, OAM_SIZE); cursor += OAM_SIZE;
    memcpy(cursor, ctx->hram, HRAM_SIZE); cursor += HRAM_SIZE;
    memcpy(cursor, ctx->io, IO_SIZE + 1u); cursor += IO_SIZE + 1u;
    if (ctx->ppu) { memcpy(cursor, ctx->ppu, sizeof(GBPPU)); cursor += sizeof(GBPPU); }
    if (ctx->apu && !gb_audio_save_state(ctx->apu, cursor, gb_audio_state_size())) return 0;
    if (ctx->apu) cursor += gb_audio_state_size();
    /* The padding to the bound is cleared, so two snapshots of the same state are equal byte for byte. */
    memset(cursor, 0, bound - (size_t)(cursor - (uint8_t*)out));
    return bound;
}

/* false, with the context untouched, for a buffer that is not a snapshot of this very game (other size, other ROM, other layout). */
bool rr_gb_snap_load(GBContext* ctx, const void* data, size_t size) {
    const size_t bound = rr_gb_snap_bound(ctx);
    if (!rr_gb_snap_ready(ctx) || !data || size != bound) return false;
    const uint8_t* cursor = (const uint8_t*)data;
    RrGbSnapHeader header;
    memcpy(&header, cursor, sizeof header);
    if (header.magic != RR_GB_SNAP_MAGIC || header.version != RR_GB_SNAP_VERSION || header.total != bound ||
        header.rom_size != ctx->rom_size || header.rom_hash != gb_context_compute_rom_hash(ctx) || header.eram_size != ctx->eram_size ||
        header.core_size != sizeof(GBSavestateCoreState) || header.ppu_size != (ctx->ppu ? sizeof(GBPPU) : 0u) ||
        header.apu_size != (ctx->apu ? gb_audio_state_size() : 0u))
        return false;
    cursor += sizeof header;
    const GBSavestateCoreState* core = (const GBSavestateCoreState*)cursor;
    cursor += sizeof(GBSavestateCoreState);
    RrGbSnapAudioPending pending;
    memcpy(&pending, cursor, sizeof pending); cursor += sizeof pending;
    const uint8_t* eram = cursor; cursor += ctx->eram_size;
    const uint8_t* wram = cursor; cursor += WRAM_BANK_SIZE * 8u;
    const uint8_t* vram = cursor; cursor += VRAM_SIZE * 2u;
    const uint8_t* oam = cursor; cursor += OAM_SIZE;
    const uint8_t* hram = cursor; cursor += HRAM_SIZE;
    const uint8_t* io = cursor; cursor += IO_SIZE + 1u;
    const uint8_t* ppu = ctx->ppu ? cursor : NULL; if (ctx->ppu) cursor += sizeof(GBPPU);
    const uint8_t* apu = ctx->apu ? cursor : NULL;
    if (apu && !gb_audio_load_state(ctx->apu, apu, gb_audio_state_size())) return false;   /* nothing else has been touched yet */
    if (ctx->eram_size) {
        if (memcmp(ctx->eram, eram, ctx->eram_size) != 0) ctx->eram_dirty = true;
        memcpy(ctx->eram, eram, ctx->eram_size);
    }
    memcpy(ctx->wram, wram, WRAM_BANK_SIZE * 8u);
    memcpy(ctx->vram, vram, VRAM_SIZE * 2u);
    memcpy(ctx->oam, oam, OAM_SIZE);
    memcpy(ctx->hram, hram, HRAM_SIZE);
    memcpy(ctx->io, io, IO_SIZE + 1u);
    if (ppu) memcpy(ctx->ppu, ppu, sizeof(GBPPU));
    gbrt_restore_core_state(ctx, core);
    if (ctx->rom && ctx->rom_size > 0x147u && gb_cart_type_has_rtc(ctx->rom[0x147])) ctx->rtc_dirty = true;
    ctx->audio_pending_cpu_cycles = pending.cpu_cycles;
    ctx->audio_cycles_until_event = pending.cycles_until_event;
    ctx->audio_pending_old_div = pending.old_div;
    ctx->audio_pending_system_cycle_remainder = pending.system_cycle_remainder;
    ctx->audio_pending_double_speed = pending.double_speed;
    return true;
}

static void rr_gb_digest_ppu(RrGbDigest* d, const GBPPU* p) {
    const uint8_t bytes[] = {p->lcdc, p->stat, p->scy, p->scx, p->ly, p->scanline, p->lyc, p->dma, p->bgp, p->obp0, p->obp1, p->wy, p->wx,
                             p->bgpi, p->obpi, p->opri, p->latched_lcdc, p->latched_scy, p->latched_scx, p->latched_bgp,
                             p->latched_obp0, p->latched_obp1, p->latched_wy, p->latched_wx};
    for (size_t i = 0; i < sizeof bytes; ++i) rr_gb_dg_u8(d, bytes[i]);
    rr_gb_dg_bool(d, p->stat_irq_state);
    rr_gb_dg_u8(d, (uint8_t)p->mode);
    rr_gb_dg_u8(d, p->visible_mode);
    rr_gb_dg_u8(d, p->stat_irq_mode);
    rr_gb_dg_bool(d, p->vblank_oam_irq_source);
    rr_gb_dg_u8(d, p->lcd_startup_phase);
    rr_gb_dg_u32(d, p->mode_cycles);
    rr_gb_dg_u16(d, p->mode3_length);
    rr_gb_dg_u16(d, p->hblank_length);
    rr_gb_dg_u16(d, p->draw_x);
    rr_gb_dg_u8(d, p->draw_startup);
    rr_gb_dg_u8(d, p->draw_stall);
    rr_gb_dg_u8(d, p->visible_sprite_count);
    for (unsigned i = 0; i < 10; ++i) { rr_gb_dg_u8(d, p->visible_sprite_indices[i]); rr_gb_dg_u8(d, p->visible_sprite_x[i]); rr_gb_dg_u8(d, p->visible_sprite_y[i]); }
    rr_gb_dg_u8(d, p->line_sprite_height);
    rr_gb_dg_u16(d, p->fetched_sprite_mask);
    rr_gb_dg_u64(d, p->considered_bg_tiles);
    rr_gb_dg_u8(d, p->window_line);
    rr_gb_dg_bool(d, p->window_triggered);
    rr_gb_dg_bool(d, p->window_y_triggered);
    rr_gb_dg_bool(d, p->window_active_line);
    rr_gb_dg_bool(d, p->window_rendered_line);
    rr_gb_dg_u8(d, p->window_pixel_x);
    rr_gb_dg_block(d, 0x51, p->bg_palette_ram, sizeof p->bg_palette_ram);
    rr_gb_dg_block(d, 0x52, p->obj_palette_ram, sizeof p->obj_palette_ram);
    rr_gb_dg_bool(d, p->frame_ready);
    /* The three framebuffers are what the screen shows, not what decides a later frame: they are in the snapshot, not here. */
}

/* The digest of the machine after the last frame: named fields, never a raw struct, never a pointer. Not in it: the counters of the
 * interpreter and of the diagnostics, the performance counters, the scheduling flag `stopped`, the pictures, and everything of the host. */
uint64_t rr_gb_digest(const GBContext* ctx) {
    if (!ctx || !ctx->wram) return 0;
    RrGbDigest d;
    rr_gb_dg_init(&d);
    rr_gb_dg_u8(&d, 0x01);   /* CPU */
    rr_gb_dg_u16(&d, ctx->af); rr_gb_dg_u16(&d, ctx->bc); rr_gb_dg_u16(&d, ctx->de); rr_gb_dg_u16(&d, ctx->hl);
    rr_gb_dg_u16(&d, ctx->sp); rr_gb_dg_u16(&d, ctx->pc);
    rr_gb_dg_u8(&d, ctx->f_z); rr_gb_dg_u8(&d, ctx->f_n); rr_gb_dg_u8(&d, ctx->f_h); rr_gb_dg_u8(&d, ctx->f_c);
    rr_gb_dg_u8(&d, ctx->ime); rr_gb_dg_u8(&d, ctx->ime_pending); rr_gb_dg_u8(&d, ctx->halted); rr_gb_dg_u8(&d, ctx->stop_mode_active);
    rr_gb_dg_u8(&d, ctx->halt_bug); rr_gb_dg_u8(&d, ctx->cgb_double_speed); rr_gb_dg_u8(&d, ctx->cgb_system_cycle_remainder);
    rr_gb_dg_u8(&d, (uint8_t)ctx->config.model);
    rr_gb_dg_u8(&d, 0x02);   /* the cartridge's mapper */
    rr_gb_dg_u16(&d, ctx->rom_bank); rr_gb_dg_u8(&d, ctx->ram_bank); rr_gb_dg_u8(&d, ctx->wram_bank); rr_gb_dg_u8(&d, ctx->vram_bank);
    rr_gb_dg_u8(&d, ctx->mbc_type); rr_gb_dg_u8(&d, ctx->ram_enabled); rr_gb_dg_u8(&d, ctx->mbc_mode); rr_gb_dg_u8(&d, ctx->rom_bank_low);
    rr_gb_dg_u8(&d, ctx->rom_bank_upper); rr_gb_dg_u8(&d, ctx->mbc1_multicart); rr_gb_dg_u8(&d, ctx->rtc_mode); rr_gb_dg_u8(&d, ctx->rtc_reg);
    rr_gb_dg_u8(&d, ctx->rtc.s); rr_gb_dg_u8(&d, ctx->rtc.m); rr_gb_dg_u8(&d, ctx->rtc.h); rr_gb_dg_u8(&d, ctx->rtc.dl); rr_gb_dg_u8(&d, ctx->rtc.dh);
    rr_gb_dg_u8(&d, ctx->rtc.latched_s); rr_gb_dg_u8(&d, ctx->rtc.latched_m); rr_gb_dg_u8(&d, ctx->rtc.latched_h);
    rr_gb_dg_u8(&d, ctx->rtc.latched_dl); rr_gb_dg_u8(&d, ctx->rtc.latched_dh); rr_gb_dg_u8(&d, ctx->rtc.latch_state);
    rr_gb_dg_u64(&d, ctx->rtc.last_time); rr_gb_dg_bool(&d, ctx->rtc.active);
    rr_gb_dg_u8(&d, 0x03);   /* time */
    rr_gb_dg_u32(&d, ctx->cycles); rr_gb_dg_u64(&d, ctx->total_cycles); rr_gb_dg_u32(&d, ctx->frame_cycles);
    rr_gb_dg_u32(&d, ctx->last_sync_cycles); rr_gb_dg_u8(&d, ctx->frame_done);
    rr_gb_dg_u8(&d, ctx->lcd_off_active); rr_gb_dg_u32(&d, ctx->lcd_off_start_cycles); rr_gb_dg_u32(&d, ctx->lcd_off_start_frame_cycles);
    rr_gb_dg_u16(&d, ctx->div_counter); rr_gb_dg_u8(&d, ctx->tima_reload_pending); rr_gb_dg_u8(&d, ctx->last_joypad);
    rr_gb_dg_u8(&d, 0x04);   /* the sound unit's scheduling, kept in the context */
    rr_gb_dg_u32(&d, ctx->audio_pending_cpu_cycles); rr_gb_dg_u32(&d, ctx->audio_cycles_until_event);
    rr_gb_dg_u16(&d, ctx->audio_pending_old_div); rr_gb_dg_u8(&d, ctx->audio_pending_system_cycle_remainder);
    rr_gb_dg_u8(&d, ctx->audio_pending_double_speed);
    rr_gb_dg_u8(&d, 0x05);   /* DMA, HDMA and serial */
    rr_gb_dg_u8(&d, ctx->dma.active); rr_gb_dg_u8(&d, ctx->dma.pending); rr_gb_dg_u8(&d, ctx->dma.source_high);
    rr_gb_dg_u8(&d, ctx->dma.active_source_high); rr_gb_dg_u8(&d, ctx->dma.progress); rr_gb_dg_u16(&d, ctx->dma.cycles_remaining);
    rr_gb_dg_u8(&d, ctx->dma.startup_delay);
    rr_gb_dg_u16(&d, ctx->hdma.source); rr_gb_dg_u16(&d, ctx->hdma.dest); rr_gb_dg_u8(&d, ctx->hdma.blocks_remaining);
    rr_gb_dg_u8(&d, ctx->hdma.active); rr_gb_dg_u8(&d, ctx->hdma.hblank_mode); rr_gb_dg_u16(&d, ctx->hdma.cpu_stall_cycles);
    rr_gb_dg_u8(&d, ctx->hdma.processing_stall);
    rr_gb_dg_u8(&d, ctx->serial_transfer.active); rr_gb_dg_u8(&d, ctx->serial_transfer.fast_clock);
    rr_gb_dg_u32(&d, ctx->serial_transfer.cycles_remaining);
    rr_gb_dg_block(&d, 0x10, ctx->wram, WRAM_BANK_SIZE * 8u);
    rr_gb_dg_block(&d, 0x11, ctx->vram, VRAM_SIZE * 2u);
    rr_gb_dg_block(&d, 0x12, ctx->oam, OAM_SIZE);
    rr_gb_dg_block(&d, 0x13, ctx->hram, HRAM_SIZE);
    rr_gb_dg_block(&d, 0x14, ctx->io, IO_SIZE + 1u);
    if (ctx->eram_size) rr_gb_dg_block(&d, 0x15, ctx->eram, ctx->eram_size);
    if (ctx->ppu) rr_gb_digest_ppu(&d, (const GBPPU*)ctx->ppu);
    if (ctx->apu) rr_gb_audio_digest(ctx->apu, &d);
    return d.hash;
}
#endif
