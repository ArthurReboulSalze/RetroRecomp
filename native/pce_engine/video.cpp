// Retro-Recomp's copy of the pinned pcenginerecomp runtime/src/video.cpp (MIT, licenses/pcenginerecomp.md), made from the file whose SHA-256 is
// retrorecomp/pce_build.PATCHED_ENGINE_FILES. One edit, marked "Retro-Recomp patch": patch 5 (the background of a line fetched once per tile). Nothing else differs
// (docs/UPSTREAMS.md, "Our patches of the PC Engine engine").
#include "pce/video.hpp"
#include "pce/runtime.hpp"
#include <algorithm>
#include <fstream>
#include <filesystem>

namespace pce {
std::uint8_t Vce::read(unsigned port) {
    ++reads;
    switch(port&7) {
    case 4: return static_cast<std::uint8_t>(palette[address]);
    case 5: {
        const auto value=static_cast<std::uint8_t>(0xFE|(palette[address]>>8));
        address=(address+1)&511;
        return value;
    }
    default: return 0xFF;
    }
}
void Vce::write(unsigned port, std::uint8_t value) {
    ++writes;
    switch(port&7) {
    case 0: control=value; break;
    case 2: address=(address&256)|value; break;
    case 3: address=(address&255)|((value&1)<<8); break;
    case 4: palette[address]=(palette[address]&256)|value; break;
    case 5:
        palette[address]=(palette[address]&255)|((value&1)<<8);
        address=(address+1)&511;
        break;
    default: break; // Documented unused ports.
    }
}

std::array<std::uint8_t,3> vce_rgb(std::uint16_t color, std::uint8_t control) {
    const auto red=static_cast<std::uint8_t>(((color>>3)&7)*255/7);
    const auto green=static_cast<std::uint8_t>(((color>>6)&7)*255/7);
    const auto blue=static_cast<std::uint8_t>((color&7)*255/7);
    if(!(control&128)) return {red,green,blue};
    // Explicit full-range digital presentation profile. This does not model
    // the analog VCE colorburst signal. Keep the operation order and floating
    // truncation used by the independently checked Mesen custom-palette path.
    const auto gray=static_cast<std::uint8_t>(std::clamp(
        0.299*red+0.587*green+0.114*blue,0.0,255.0));
    return {gray,gray,gray};
}

namespace {
inline bool two_bit_background(unsigned mode) { return (mode&3)==3; }
std::uint16_t vram_word(const Vdc& vdc, unsigned address) {
    return vdc.peek_vram(static_cast<std::uint16_t>(address));
}
unsigned background_pixel(const Vdc& vdc, unsigned x, unsigned y,
                          unsigned scroll_x, unsigned scroll_y, unsigned mode,
                          Vdc* guest=nullptr) {
    constexpr unsigned columns[]={32,64,128,128};
    const auto map_width=columns[(mode>>4)&3];
    const auto map_height=(mode&64) ? 64u:32u;
    x=(x+scroll_x)%(map_width*8);
    y=(y+scroll_y)%(map_height*8);
    const auto word=[&](unsigned address) {
        return guest ? guest->read_vram(static_cast<std::uint16_t>(address)):vram_word(vdc,address);
    };
    const auto descriptor=word((y/8)*map_width+x/8);
    const bool two_bit=(mode&3)==3;
    const auto pattern=(descriptor&(two_bit ? 4095:2047))*16+(y&7);
    const auto low=word(pattern+(two_bit && (mode&128) ? 8:0));
    const unsigned shift=7-(x&7);
    unsigned color=((low>>shift)&1)|(((low>>(shift+8))&1)<<1);
    if(!two_bit) {
        const auto high=word(pattern+8);
        color|=(((high>>shift)&1)<<2)|(((high>>(shift+8))&1)<<3);
    }
    return color ? ((descriptor>>12)<<4)|color:0;
}
struct SpriteCell { int x; unsigned line, palette; bool flip, front; };
std::vector<SpriteCell> sprite_line(std::span<const std::uint16_t> satb, unsigned y, unsigned mode) {
    std::vector<SpriteCell> cells;
    cells.reserve(16);
    constexpr unsigned heights[]={16,32,64,64};
    constexpr unsigned masks[]={1023,1021,1017,1017};
    const bool two_bit=((mode>>2)&3)==1;
    for(unsigned i=0;i<64 && cells.size()<16;++i) {
        const auto attr=satb[i*4+3];
        const auto height=heights[(attr>>12)&3];
        const int top=static_cast<int>(satb[i*4]&1023)-64;
        if(static_cast<int>(y)<top || static_cast<int>(y)>=top+static_cast<int>(height)) continue;
        auto row=static_cast<unsigned>(static_cast<int>(y)-top);
        if(attr&0x8000) row=height-1-row;
        const bool wide=(attr&256)!=0, flip=(attr&0x800)!=0;
        auto tile=(satb[i*4+2]>>1)&masks[(attr>>12)&3];
        if(wide) tile&=1022;
        const auto line=tile*64+(row/16)*128+(row&15)+
            (two_bit ? (satb[i*4+2]&1)*32:0);
        const int left=static_cast<int>(satb[i*4+1]&1023)-32;
        cells.push_back({left,line+(wide&&flip ? 64u:0u),unsigned(attr&15)*16,flip,(attr&128)!=0});
        if(wide && cells.size()<16)
            cells.push_back({left+16,line+(flip ? 0u:64u),unsigned(attr&15)*16,flip,(attr&128)!=0});
    }
    return cells;
}
}

VideoFrame render_snapshot(const Vdc& vdc, const Vce& vce,
                           std::span<const std::uint16_t> satb) {
    if(!vdc.enabled || !vce.enabled) throw Fault("snapshot requires VDC and VCE profiles");
    if(!satb.empty() && satb.size()!=256) throw Fault("snapshot SATB must contain exactly 256 words");
    VideoFrame frame;
    frame.width=((vdc.reg[11]&127)+1)*8;
    frame.height=(vdc.reg[13]&511)+1;
    frame.rgb.resize(static_cast<std::size_t>(frame.width)*frame.height*3);
    // With both display enables clear the VDC enters burst mode and outputs
    // black, independently of the backdrop palette. Use the current control
    // state here; a snapshot cannot reconstruct its historical latch edge.
    if(!(vdc.reg[5]&192)) return frame;
    const bool two_bit=((vdc.reg[9]>>2)&3)==1;
    for(unsigned y=0;y<frame.height;++y) {
        std::vector<SpriteCell> cells;
        if((vdc.reg[5]&64) && !satb.empty()) cells=sprite_line(satb,y,vdc.reg[9]);
        for(unsigned x=0;x<frame.width;++x) {
            unsigned index=(vdc.reg[5]&128) ? background_pixel(vdc,x,y,vdc.reg[7],vdc.reg[8],vdc.reg[9]):0;
            for(const auto& cell:cells) {
                const int offset=static_cast<int>(x)-cell.x;
                if(offset<0 || offset>=16) continue;
                const unsigned shift=cell.flip ? unsigned(offset):15-unsigned(offset);
                unsigned color=0;
                for(unsigned p=0;p<(two_bit ? 2u:4u);++p)
                    color|=((vram_word(vdc,cell.line+p*16)>>shift)&1)<<p;
                if(!color) continue;
                if(cell.front || !(index&15)) index=256+cell.palette+color;
                break; // Lower SATB index also masks a sprite behind background.
            }
            const auto rgb=vce_rgb(vce.palette[index],vce.control);
            const auto out=(static_cast<std::size_t>(y)*frame.width+x)*3;
            for(unsigned channel=0;channel<3;++channel) frame.rgb[out+channel]=rgb[channel];
        }
    }
    return frame;
}
namespace {
void scanline_indices(const Vdc& vdc, unsigned sprite_y, unsigned scroll_x,
                             unsigned scroll_y, std::uint16_t control,
                             std::uint16_t mode, std::span<std::uint16_t> output,
                             bool cached_sprites, Vdc* guest) {
    if(output.size()>1024) throw Fault("video scanline exceeds 1024 pixels");
    const bool two_bit=((mode>>2)&3)==1;
    const auto cells=(control&64) && !cached_sprites ? sprite_line(vdc.satb,sprite_y,mode):std::vector<SpriteCell>{};
    // Retro-Recomp patch 5: the background of a line, fetched once per tile instead of three VRAM reads for every pixel. The words are the same and
    // read in the same order (descriptor, low, high) at the first pixel of each tile; the VRAM bus latch ends the line as it did (the repeats read the
    // same words again, each one after the descriptor read that sets the latch).
    constexpr unsigned columns[]={32,64,128,128};
    const auto map_width=columns[(mode>>4)&3];
    const auto map_height=(mode&64) ? 64u:32u;
    const unsigned row_y=(0+scroll_y)%(map_height*8);
    unsigned tile=~0u,descriptor=0,pattern=0,low=0,high=0;
    for(unsigned x=0;x<output.size();++x) {
        unsigned index=0;
        if(control&128) {
            const auto column=(x+scroll_x)%(map_width*8);
            if(column/8!=tile) {
                tile=column/8;
                const auto word=[&](unsigned address) {
                    return guest ? guest->read_vram(static_cast<std::uint16_t>(address)):vram_word(vdc,address);
                };
                descriptor=word((row_y/8)*map_width+tile);
                pattern=(descriptor&(two_bit_background(mode) ? 4095:2047))*16+(row_y&7);
                low=word(pattern+(two_bit_background(mode) && (mode&128) ? 8:0));
                high=two_bit_background(mode) ? 0:word(pattern+8);
            }
            const unsigned shift=7-(column&7);
            unsigned color=((low>>shift)&1)|(((low>>(shift+8))&1)<<1);
            if(!two_bit_background(mode)) color|=(((high>>shift)&1)<<2)|(((high>>(shift+8))&1)<<3);
            index=color ? ((descriptor>>12)<<4)|color:0;
        }
        if(cached_sprites && (control&64)) {
            for(unsigned i=0;i<vdc.sprite_count;++i) {
                const auto& cell=vdc.sprite_rows[i];
                const int offset=static_cast<int>(x)-cell.x;
                if(offset<0 || offset>=16) continue;
                const unsigned shift=cell.flip ? unsigned(offset):15-unsigned(offset);
                unsigned color=0;
                for(unsigned plane=0;plane<4;++plane)
                    color|=((cell.planes[plane]>>shift)&1)<<plane;
                if(!color) continue;
                if(cell.front || !(index&15)) index=256+cell.palette+color;
                break;
            }
        }
        for(const auto& cell:cells) {
            const int offset=static_cast<int>(x)-cell.x;
            if(offset<0 || offset>=16) continue;
            const unsigned shift=cell.flip ? unsigned(offset):15-unsigned(offset);
            unsigned color=0;
            for(unsigned plane=0;plane<(two_bit ? 2u:4u);++plane)
                color|=((vram_word(vdc,cell.line+plane*16)>>shift)&1)<<plane;
            if(!color) continue;
            if(cell.front || !(index&15)) index=256+cell.palette+color;
            break;
        }
        output[x]=static_cast<std::uint16_t>(index);
    }
}
}
void render_scanline_indices(const Vdc& vdc, unsigned sprite_y, unsigned scroll_x,
                             unsigned scroll_y, std::uint16_t control,
                             std::uint16_t mode, std::span<std::uint16_t> output,
                             bool cached_sprites) {
    scanline_indices(vdc,sprite_y,scroll_x,scroll_y,control,mode,output,cached_sprites,nullptr);
}
void render_guest_scanline_indices(Vdc& vdc, unsigned sprite_y, unsigned scroll_x,
                                  unsigned scroll_y, std::uint16_t control,
                                  std::uint16_t mode, std::span<std::uint16_t> output) {
    scanline_indices(vdc,sprite_y,scroll_x,scroll_y,control,mode,output,true,&vdc);
}
void write_ppm(const VideoFrame& frame, const std::string& path) {
    if(frame.width==0 || frame.width>1024 || frame.height==0 || frame.height>512 ||
       frame.rgb.size()!=static_cast<std::size_t>(frame.width)*frame.height*3)
        throw Fault("invalid snapshot RGB frame");
    std::ofstream out(std::filesystem::path(std::u8string(reinterpret_cast<const char8_t*>(path.c_str()))),std::ios::binary|std::ios::trunc);
    if(!out) throw Fault("cannot open snapshot output");
    out<<"P6\n"<<frame.width<<' '<<frame.height<<"\n255\n";
    out.write(reinterpret_cast<const char*>(frame.rgb.data()),static_cast<std::streamsize>(frame.rgb.size()));
    if(!out) throw Fault("cannot write snapshot output");
}
} // namespace pce
