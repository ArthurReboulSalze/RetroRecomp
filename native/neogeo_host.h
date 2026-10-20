/* The shared presentation host accesses the initialized Neo Geo machine. */
#ifndef RR_NEOGEO_HOST_H
#define RR_NEOGEO_HOST_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
/* Presentation-only power-on cover. Release on the BIOS's first clean
 * monochrome intro, then never inspect or hide gameplay. Fail open if an
 * unfamiliar/error screen replaces the intro. No guest state is changed. */
typedef struct { unsigned last_frame; bool sampled,released; } RrNgBootCover;
static bool rr_ng_boot_cover(RrNgBootCover *cover,unsigned frame,bool aes,const uint32_t *pixels,size_t count) {
    if(cover->released)return false;
    if(frame>=240 || !pixels || !count) {cover->released=true;return false;}
    /* A hard reset retains VRAM/palettes briefly. Old monochrome logo tiles
     * must not release MVS's cover before its RAM color test even begins. */
    if(!aes && frame<60)return true;
    if(cover->sampled && frame==cover->last_frame)return true;
    cover->sampled=true;cover->last_frame=frame;
    size_t light=0,dark=0,colored=0;
    for(size_t n=0;n<count;++n) {
        uint32_t c=pixels[n];unsigned r=(c>>16)&255,g=(c>>8)&255,b=c&255;
        unsigned high=r>g?r:g,low=r<g?r:g;
        if(b>high)high=b;if(b<low)low=b;
        if(high-low>4 && ++colored>count/100)return true;
        if(low>=224)++light;
        if(high<=32)++dark;
    }
    if(light>count/2 || (light>count/500 && light+dark>=count-count/100)) {
        cover->released=true;return false;
    }
    return true;
}
uint32_t *rr_ng_visible_pixels(void);
bool rr_ng_boot_video_hidden(void);
const int16_t *rr_ng_pcm(size_t *count);
void rr_ng_consume_pcm(void);
void rr_ng_audio_queue_probe(int playing,unsigned bytes,unsigned rate,unsigned period);
void rr_ng_host_timing(double seconds);
bool rr_ng_performance_enabled(void);
void rr_ng_host_cost(double busy_ms,double present_ms);
void rr_ng_host_frame(uint16_t p1,uint16_t p2);
uint32_t rr_ng_frame_index(void);
void rr_ng_restore_frame(uint32_t frame);
unsigned rr_ng_frame_limit(void);
bool rr_ng_enhanced(void);
bool rr_ng_aes(void);
bool rr_ng_aes_available(void);
bool rr_ng_arcade_only(void);
const char *rr_ng_identity(void);
void rr_ng_request_mode_restart(void);
void rr_ng_set_enhanced(bool enabled);
void rr_ng_reset_machine(void);
void rr_ng_ui_test_tick(void *window,void *renderer);
void rr_ng_ui_test_present(void *renderer);
void rr_ng_ui_snapshot(FILE *file,const char *label,void *window);
void rr_ng_test_json(FILE *file,const char *text);
bool rr_ng_core_state_valid(const uint8_t *data,size_t size);
size_t rr_ng_cpu_extra_save(uint8_t *data,size_t capacity);
bool rr_ng_cpu_extra_restore(const uint8_t *data,size_t size);
size_t rr_ng_ym_extra_save(uint8_t *data,size_t capacity);
bool rr_ng_ym_extra_restore(const uint8_t *data,size_t size);
#endif
