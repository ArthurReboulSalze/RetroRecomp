/* Neo Geo adapter for the exact shared 16-bit menu/presentation host. MIT. */
#include <SDL.h>
#include <string.h>
#include "retro_console16.h"
#include "neogeo_host.h"
#include "neogeo_reference.h"
static SDL_AudioStream *resampler;
static uint32_t pixels[320*224];
bool rr16_init(bool headless) {(void)headless;return true;}
void rr16_reset(void) {
    rr_ng_reset_machine();if(resampler)SDL_AudioStreamClear(resampler);rr16_host_discontinuity();
}
bool rr16_frame(uint16_t p1,uint16_t p2) {rr_ng_host_frame(p1,p2);return true;}
const uint32_t *rr16_pixels(void) {
    const uint32_t *src=rr_ng_visible_pixels();
    for(unsigned n=0;n<320*224;++n)pixels[n]=src[n]|0xff000000u;
    return pixels;
}
uint64_t rr16_interpreted(void) {return rr_m68000_stats()->interpreted_instructions;}
uint64_t rr16_native_entries(void) {return rr_m68000_stats()->native_instructions;}
uint64_t rr16_audio_interpreted(void) {return rr_ng_z80_instructions;}
const char *rr16_audio_cpu(void) {return "Z80";}
uint64_t rr16_audio_fingerprint(void) {return rr_ng_z80_state_hash();}
uint64_t rr16_audio_frame_fingerprint(void) {return rr_ng_z80_state_hash();}
size_t rr16_audio(int16_t *out,size_t capacity) {
    size_t count=0;const int16_t *input=rr_ng_pcm(&count);
    if(!resampler)resampler=SDL_NewAudioStream(AUDIO_S16SYS,2,55556,AUDIO_S16SYS,2,48000);
    if(!resampler)return 0;
    if(count && SDL_AudioStreamPut(resampler,input,(int)(count*2)))return 0;
    rr_ng_consume_pcm();int n=SDL_AudioStreamGet(resampler,out,(int)(capacity*2));
    return n>0?(size_t)n/2:0;
}
void rr16_pause(bool paused) {if(paused && resampler)SDL_AudioStreamClear(resampler);}
void rr16_shutdown(void) {if(resampler)SDL_FreeAudioStream(resampler);resampler=NULL;}
void rr16_gun_input(Rr16GunInput input) {(void)input;}
int rr16_visible_width(void) {return 320;}
int rr16_visible_height(void) {return 224;}
int rr16_raster_height(void) {return 224;}
uint64_t rr16_input_frame(void) {return rr_ng_frame_index();}
unsigned rr16_host_frame_limit(void) {return rr_ng_frame_limit();}
void rr16_host_test_tick(void *w,void *r) {rr_ng_ui_test_tick(w,r);}
void rr16_report_details(FILE *file) {(void)file;}
void rr_ng_audio_discontinuity(void) {if(resampler)SDL_AudioStreamClear(resampler);rr_ng_consume_pcm();}
