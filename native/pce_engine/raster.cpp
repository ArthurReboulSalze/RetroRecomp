// Retro-Recomp's copy of the pinned pcenginerecomp runtime/src/raster.cpp (MIT, licenses/pcenginerecomp.md), made from the file whose SHA-256 is
// retrorecomp/pce_build.PATCHED_ENGINE_FILES. One edit, marked "Retro-Recomp patch": patch 6 (the distance to the next dot without a division by a variable). Nothing else differs
// (docs/UPSTREAMS.md, "Our patches of the PC Engine engine").
#include "pce/runtime.hpp"
#include <algorithm>
#include <limits>

namespace pce {
void Vdc::latch_horizontal() {
    raster.horizontal={unsigned((reg[10]>>8)&127)+1,unsigned(reg[11]&127)+1,
        unsigned((reg[11]>>8)&127)+1,unsigned(reg[10]&31)+1};
    for(auto& length:raster.horizontal) length*=8;
}
void Vdc::latch_vertical() {
    raster.vertical={unsigned(reg[12]>>8)+2,unsigned(reg[13]&511)+1,
        unsigned(reg[14]&255),unsigned(reg[12]&31)+1};
}
void Vdc::enable_raster() {
    const bool reset_output=video.enabled;
    raster=RasterTiming{}; raster.enabled=true;
    pending_vram_read=pending_vram_write=false;
    vram_transfer_delay=0;vram_cpu_cycles=0;
    update_vram_busy();
    load_bg_start_clock=1365;load_bg_end_clock=0;hsync_start_clock=0;
    sprite_rows={};sprite_count=0;sprite_overflow=false;
    sprite_burst=false;sprite_active=false;sprite_control=reg[5];sprite_mode=0;
    latch_horizontal(); latch_vertical(); raster.v_remaining=static_cast<int>(raster.vertical[0]);
    if(reset_output) video.enable(*this);else video.reset_latches(*this);
}
void Vdc::write_vce_control(std::uint8_t value) {
    if(!raster.enabled) throw Fault("VCE timing profile is disabled");
    const auto lines=(value&4) ? 263U:262U;
    // Reducing the frame count behind a live line counter requires separately
    // qualified wrap behavior. Reject it before changing the clock selection.
    if(raster.line>=lines) throw Fault("VCE frame-length change behind the current line is unsupported");
    raster.control=value; raster.total_lines=lines;
    raster.divider=(value&3)==0 ? 4:(value&3)==1 ? 3:2;
}
void Vdc::schedule_line_events() {
    auto& r=raster;
    latch_horizontal();
    hsync_start_clock=r.hclock;
    load_bg_start_clock=1365;load_bg_end_clock=0;
    r.event=0; r.event_remaining=0;
    const auto display_start=static_cast<int>(r.dot)+r.h_remaining+static_cast<int>(r.horizontal[0]);
    if((display_start-24)*static_cast<int>(r.divider)>=1365) return;
    const bool active=r.v_state==1;
    if(active) {
        load_bg_start_clock=(display_start-16)*static_cast<int>(r.divider);
        load_bg_end_clock=std::min(1365,load_bg_start_clock+
            static_cast<int>(r.horizontal[1]+16)*static_cast<int>(r.divider));
    }
    r.event=active ? 1:3;
    r.event_remaining=display_start-(active ? 36:26)-static_cast<int>(r.dot);
    if(r.event_remaining<=0) { r.event_remaining=0; raster_event(); }
}
void Vdc::compare_line() {
    auto& r=raster;
    ++r.raster_line; r.compare_pending=false;
    --r.v_remaining;
    while(r.v_remaining<=0) {
        r.v_state=(r.v_state+1)&3;
        r.v_remaining=static_cast<int>(r.vertical[r.v_state]);
        if(r.v_state==1) { r.raster_line=0; r.blank_consumed=false; }
        if(r.v_state==3) { latch_vertical();video.latch_mode(*this);sprite_mode=reg[9]; }
    }
    video.increment_y();
    if((reg[5]&4) && static_cast<int>(r.raster_line)==static_cast<int>(reg[6])-64) {
        status|=4; irq1=true; ++r.rcr_events;
    }
}
void Vdc::raster_event() {
    auto& r=raster;
    const auto event=r.event; r.event=0; r.event_remaining=0;
    if(event==1) { video.latch_y(*this); r.event=2; r.event_remaining=2; }
    if(event==2) { video.latch_x(*this); r.event=3; r.event_remaining=6; }
    if(event==3 && r.v_state!=1 && !r.blank_consumed) {
        // Consume the source event even with CR disabled: enabling it later
        // cannot manufacture an interrupt for an event that already passed.
        r.blank_consumed=true;
        if(dma_enabled) vblank_dma();
        else if(reg[15]&16) throw Fault("VDC automatic SATB DMA is not implemented");
        if(reg[5]&8) { status|=32; irq1=true; ++r.vblank_events; }
    }
    if(event==3 && sprite_overflow) {
        sprite_overflow=false;
        if(reg[5]&2) { status|=2;irq1=true; }
    }
    if(event==4) {
        compare_line();
        if(r.v_state==1 && !sprite_burst) fetch_sprite_rows();
    }
}
void Vdc::horizontal_edge() {
    auto& r=raster;
    r.h_state=(r.h_state+1)&3;
    r.h_remaining=static_cast<int>(r.horizontal[r.h_state]);
    if(r.h_state==0) {
        video.horizontal_start(*this);
        if(!sprite_burst) sprite_control=reg[5];
    }
    if(r.h_state==1) {
        video.begin_line(*this);
        r.compare_pending=true; r.event=4;
        r.event_remaining=static_cast<int>(r.horizontal[1])-14;
        if(r.event_remaining<=0) { r.event_remaining=0; raster_event(); }
        if(sprite_active && !sprite_burst && (sprite_control&64)) sprite_collision();
    }
    if(r.h_state==3) schedule_line_events();
}
void Vdc::dot_tick() {
    if(dma_enabled) dma_tick();
    auto& r=raster;
    ++r.dot;
    if(--r.h_remaining==0) horizontal_edge();
    // New horizontal events participate in this same dot, as on the VDC.
    if(r.event_remaining>0 && --r.event_remaining==0) raster_event();
}
void Vdc::line_tick() {
    auto& r=raster;
    video.end_line();
    r.hclock=0; r.dot=0;
    ++r.vdc_line;
    if(r.compare_pending) compare_line();
    if(r.vdc_line==r.total_lines) {
        r.vdc_line=0;video.frame_boundary(*this);
        sprite_control=(sprite_control&~192)|(reg[5]&192);
        sprite_burst=(reg[5]&192)==0;
    }
    sprite_active=r.v_state==1 && r.vdc_line>=14 && r.vdc_line<256;
    r.h_state=3; r.h_remaining=r.divider==3 ? 32:24;
    schedule_line_events();
    if(r.line==r.total_lines-4) {
        r.vsync=false; latch_vertical();
        video.latch_mode(*this);sprite_mode=reg[9];
        r.v_state=3; r.v_remaining=static_cast<int>(r.vertical[3]);
    } else if(r.line==r.total_lines-1) r.vsync=true;
    if(++r.line==r.total_lines) { r.line=0; ++r.frames; }
    r.hsync=true;
}
void Vdc::advance_raster(std::uint64_t delta, const Vce* palette) {
    if(!raster.enabled) return;
    if(video.enabled && (!palette || !palette->enabled))
        throw Fault("continuous video requires an enabled palette");
    auto& r=raster;
    if(delta>std::numeric_limits<std::uint64_t>::max()-r.master_ticks) throw Fault("video clock overflow");
    while(delta) {
        // Retro-Recomp patch 6: the divider is 2, 3 or 4: the remainder without a division by a variable.
        const unsigned phase=r.divider==4 ? (r.hclock&3):r.divider==2 ? (r.hclock&1):(r.hclock%3);
        const unsigned to_dot=r.divider-phase;
        const auto chunk=std::min<std::uint64_t>({delta,to_dot,1365-r.hclock});
        r.hclock+=static_cast<unsigned>(chunk); r.master_ticks+=chunk; delta-=chunk;
        if(chunk==to_dot) { dot_tick();if(video.enabled) video.pixel(*this,*palette); }
        if(r.hclock==1365) line_tick();
        else if(r.hclock==1128) r.hsync=false;
    }
}
void Vdc::advance(std::uint64_t delta,const Vce* palette) {
    if(!raster.enabled)return;
    if(video.enabled && (!palette || !palette->enabled))
        throw Fault("continuous video requires an enabled palette");
    if(delta>std::numeric_limits<std::uint64_t>::max()-raster.master_ticks)
        throw Fault("video clock overflow");
    while(delta && has_pending_vram() && queued_cpu_accesses) {
        const auto ticks=static_cast<unsigned>(std::min<std::uint64_t>(delta,3));
        process_cpu_vram_accesses(ticks);
        advance_raster(ticks,palette);
        delta-=ticks;
    }
    if(delta)advance_raster(delta,palette);
}
void Bus::enable_video_timing() {
    enable_vdc(); vce=Vce{};
    // Deterministic reference-emulator reset geometry, not a reconstructed IPL
    // state or a hardware power-on guarantee. Functional-only VDC stays zeroed.
    vdc.reg[11]=31; vdc.reg[13]=239;
    vdc.enable_raster();
}
void Bus::enable_video() {enable_video_timing();vce.enabled=true;vdc.dma_enabled=true;}
void Bus::sync(const Cpu& cpu) {
    if(vdc.raster.enabled) {
        if(cpu.ticks<vdc.raster.master_ticks) throw Fault("CPU/video clock regression");
        vdc.advance(cpu.ticks-vdc.raster.master_ticks,&vce);
    }
    pcm.advance_to(*this,cpu.ticks);
    irq.advance_to(cpu.ticks);
}
void Bus::begin_instruction(Cpu& cpu) {
    sync(cpu);
    if(irq.enabled) { sample_interrupt(cpu); return; }
    if(vdc.raster.enabled && vdc.irq1 && !(cpu.p&I)) throw Fault("unmasked IRQ1 delivery is not implemented");
    if(cd.scsi.enabled && cd.irq2() && !(cpu.p&I)) throw Fault("unmasked IRQ2 delivery is not implemented");
}
void Bus::retire(Cpu& cpu,unsigned cycles,bool native) { cpu.retire(cycles,native); sync(cpu); service_interrupt(cpu); }
void Bus::retire_speed(Cpu& cpu,unsigned divisor,bool native) { cpu.retire_speed(divisor,native); sync(cpu); service_interrupt(cpu); }
} // namespace pce
