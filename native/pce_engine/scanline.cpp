// Retro-Recomp's copy of the pinned pcenginerecomp runtime/src/scanline.cpp (MIT, licenses/pcenginerecomp.md), made from the file whose SHA-256 is
// retrorecomp/pce_build.PATCHED_ENGINE_FILES. One edit, marked "Retro-Recomp patch": patch 4 (the palette word to RGB for the colour output as a table read). Nothing else differs
// (docs/UPSTREAMS.md, "Our patches of the PC Engine engine").
#include "pce/scanline.hpp"
#include "pce/runtime.hpp"
#include <algorithm>
#include <limits>

namespace pce {
void VideoOutput::prepare_frame(const Vdc& vdc) {
    back_.width=vdc.raster.horizontal[1];
    back_.height=vdc.raster.vertical[1];
    if(!back_.width || back_.width>1024 || !back_.height || back_.height>512)
        throw Fault("continuous video frame geometry exceeds bounded buffers");
    back_.rgb.resize(static_cast<std::size_t>(back_.width)*back_.height*3);
    std::fill(back_.rgb.begin(),back_.rgb.end(),0);
}
void VideoOutput::enable(const Vdc& vdc) {
    if(!vdc.enabled || !vdc.raster.enabled)
        throw Fault("continuous video requires the raster profile");
    if(vdc.raster.master_ticks!=0)
        throw Fault("continuous video must be enabled before guest execution");
    *this=VideoOutput{};
    enabled=true;
    // Reserve once: geometry changes cannot trigger geometric vector growth or
    // unbounded allocation in the guest-clock path.
    constexpr std::size_t max_bytes=1024*512*3;
    front_.rgb.reserve(max_bytes);back_.rgb.reserve(max_bytes);
    reset_latches(vdc);
    prepare_frame(vdc);
}
void VideoOutput::reset_latches(const Vdc& vdc) {
    control_=vdc.reg[5];mode_=vdc.reg[9];
    burst_=(control_&192)==0;
    scroll_x_=vdc.reg[7];scroll_y_=counter_y_=vdc.reg[8];
    y_pending_=increment_=false;
    latch_x_clock_=latch_y_clock_=byr_lsb_write_clock_=-1;
    bxr_written_before_latch_=false;
}
bool VideoOutput::in_latch_window(const Vdc& vdc,int clock) const {
    if(clock<0)return false;
    const auto divider=static_cast<int>(vdc.raster.divider);
    const auto beginning=(clock/divider)*divider;
    const auto current=static_cast<int>(vdc.raster.hclock);
    return current>beginning && current<beginning+(divider+1)/2;
}
void VideoOutput::register_write(const Vdc& vdc,unsigned index,bool high) {
    const auto current=static_cast<int>(vdc.raster.hclock);
    if(index==7) {
        if(latch_x_clock_<0)bxr_written_before_latch_=true;
        if(in_latch_window(vdc,latch_x_clock_))scroll_x_=vdc.reg[7];
    }
    if(index==8) {
        y_pending_=true;
        if(in_latch_window(vdc,latch_y_clock_)) {
            reload_y(vdc);byr_lsb_write_clock_=-1;
        } else if(!high && latch_y_clock_>=0) {
            const auto elapsed=(current-latch_y_clock_+1365)%1365;
            byr_lsb_write_clock_=elapsed<=static_cast<int>(4*vdc.raster.divider)?current:-1;
        } else if(high && byr_lsb_write_clock_>=0) {
            const auto elapsed=(current-byr_lsb_write_clock_+1365)%1365;
            if(!bxr_written_before_latch_ && vdc.raster.h_state==3 &&
               elapsed<=static_cast<int>(6*vdc.raster.divider))
                scroll_y_=static_cast<std::uint16_t>(vdc.reg[8]+(vdc.raster.raster_line?1:0));
            byr_lsb_write_clock_=-1;
        }
    }
}
void VideoOutput::reload_y(const Vdc& vdc) {
    if(vdc.raster.raster_line==0) counter_y_=vdc.reg[8];
    else if(y_pending_) {
        counter_y_=static_cast<std::uint16_t>(vdc.reg[8]+1);
        y_pending_=false;
    } else if(increment_) ++counter_y_;
    scroll_y_=counter_y_;increment_=false;
}
void VideoOutput::latch_y(const Vdc& vdc) {
    latch_y_clock_=static_cast<int>(vdc.raster.hclock);reload_y(vdc);
}
void VideoOutput::latch_x(const Vdc& vdc) {
    latch_x_clock_=static_cast<int>(vdc.raster.hclock);scroll_x_=vdc.reg[7];
}
void VideoOutput::latch_mode(const Vdc& vdc) { mode_=vdc.reg[9]; }
void VideoOutput::increment_y() { increment_=true; }
void VideoOutput::horizontal_start(const Vdc& vdc) {
    if(!burst_) control_=vdc.reg[5];
}
void VideoOutput::begin_line(Vdc& vdc) {
    row_=vdc.raster.raster_line;x_=0;
    line_width_=vdc.raster.horizontal[1];
    if(line_width_>indices_.size()) throw Fault("continuous video line geometry exceeds bound");
    // Device fetches happen independently of framebuffer production. The
    // source profile groups background reads at the active HDW boundary.
    const bool guest_fetch=vdc.sprite_active && vdc.raster.v_state==1 && !vdc.sprite_burst;
    if(guest_fetch) render_guest_scanline_indices(vdc,row_,scroll_x_,scroll_y_,vdc.sprite_control,vdc.sprite_mode,
                                                std::span(indices_).first(line_width_));
    active_=enabled && vdc.raster.v_state==1 && row_<back_.height;
    if(!active_) return;
    ++lines_rendered_;
    if(!burst_ && !guest_fetch) render_scanline_indices(vdc,row_,scroll_x_,scroll_y_,control_,mode_,
                                      std::span(indices_).first(line_width_),true);
}
void VideoOutput::pixel(const Vdc& vdc, const Vce& vce) {
    if(!enabled || !active_ || vdc.raster.h_state!=1 || x_>=line_width_) return;
    const auto x=x_++;
    if(x>=back_.width) return;
    ++pixels_rendered_;
    if(burst_) return;
    // Retro-Recomp patch 4: vce_rgb for the colour output (control bit 7 clear) as a table read; the grey output keeps the call.
    const auto color=vce.palette[indices_[x]];
    const auto offset=(static_cast<std::size_t>(row_)*back_.width+x)*3;
    if(!(vce.control&128)) {
        static constexpr auto level=[] {
            std::array<std::uint8_t,8> value{};
            for(unsigned step=0;step<8;++step) value[step]=static_cast<std::uint8_t>(step*255/7);
            return value;
        }();
        auto* destination=back_.rgb.data()+offset;
        destination[0]=level[(color>>3)&7];destination[1]=level[(color>>6)&7];destination[2]=level[color&7];
        return;
    }
    const auto rgb=vce_rgb(color,vce.control);
    for(unsigned channel=0;channel<3;++channel) back_.rgb[offset+channel]=rgb[channel];
}
void VideoOutput::end_line() {
    active_=false;latch_x_clock_=latch_y_clock_=byr_lsb_write_clock_=-1;
    bxr_written_before_latch_=false;
}
void VideoOutput::frame_boundary(const Vdc& vdc) {
    control_=(control_&~192)|(vdc.reg[5]&192);
    burst_=(vdc.reg[5]&192)==0;
    if(!enabled) return;
    if(sequence_==std::numeric_limits<std::uint64_t>::max())
        throw Fault("continuous video sequence overflow");
    std::swap(front_,back_);
    ++sequence_;completed_ticks_=vdc.raster.master_ticks;
    prepare_frame(vdc);
}
void Bus::enable_continuous_video() {
    enable_video();
    vdc.video.enable(vdc);
}
} // namespace pce
