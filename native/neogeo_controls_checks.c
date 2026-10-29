/* ROM-free keyboard/MVS wiring checks through the production host kit: its input
 * module and the Neo Geo adapter, in one translation unit with a mock keyboard. */
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <assert.h>
static Uint8 mock_keys[SDL_NUM_SCANCODES];
static const Uint8 *mock_keyboard(int *size) {if(size)*size=SDL_NUM_SCANCODES;return mock_keys;}
#define SDL_GetKeyboardState mock_keyboard
#include "hostkit/shell/rrhk_input.c"
#include "hostkit/adapters/rrhk_ng.c"
#include "neogeo_input.h"
static uint32_t test_pixels[320*224];
RrNgFixMask rr_ng_fix_mask;   /* the adapter's view reads the detector the engine owns */
bool rr16_init(bool h) {(void)h;return true;}
void rr16_reset(void) {}
bool rr16_frame(uint16_t a,uint16_t b) {(void)a;(void)b;return true;}
const uint32_t *rr16_pixels(void) {return test_pixels;}
uint64_t rr16_interpreted(void) {return 0;}
uint64_t rr16_native_entries(void) {return 0;}
uint64_t rr16_audio_interpreted(void) {return 0;}
const char *rr16_audio_cpu(void) {return "Z80";}
size_t rr16_audio(int16_t *p,size_t n) {(void)p;(void)n;return 0;}
void rr16_pause(bool p) {(void)p;}
bool rr16_state_path(wchar_t *p,size_t n) {(void)p;(void)n;return false;}
bool rr16_state_ready(void) {return true;}
bool rr16_state_file(const wchar_t *p,bool l) {(void)p;(void)l;return false;}
int rr16_visible_width(void) {return 320;}
int rr16_visible_height(void) {return 224;}
int rr16_raster_height(void) {return 224;}
void rr16_gun_input(Rr16GunInput input) {(void)input;}
uint64_t rr16_input_frame(void) {return 0;}
unsigned rr16_host_frame_limit(void) {return 0;}
void rr16_host_test_tick(void *w,void *r) {(void)w;(void)r;}
void rr_ng_ui_test_present(void *r) {(void)r;}
void rr_ng_audio_queue_probe(int playing,unsigned bytes,unsigned rate,unsigned period) {(void)playing;(void)bytes;(void)rate;(void)period;}
void rr_ng_host_timing(double seconds) {(void)seconds;}
bool rr_ng_performance_enabled(void) {return false;}
void rr_ng_host_cost(double busy_ms,double present_ms) {(void)busy_ms;(void)present_ms;}
static bool test_enhanced;
bool rr_ng_enhanced(void) {return test_enhanced;}
bool rr_ng_aes(void) {return false;}
bool rr_ng_aes_available(void) {return true;}
bool rr_ng_arcade_only(void) {return false;}
bool rr_ng_boot_video_hidden(void) {return false;}
void rr_ng_request_mode_restart(void) {}
void rr_ng_set_enhanced(bool enabled) {test_enhanced=enabled;}
uint32_t rr_ng_frame_index(void) {return 0;}
void rr_ng_test_json(FILE *file,const char *text) {fprintf(file,"\"%s\"",text?text:"");}
/* The adapter names these services of the shell; this check never runs the loop or the menus. */
int rrhk_main(const RrhkMachine *machine,const char *title,int scale) {(void)machine;(void)title;(void)scale;return 0;}
void rrhk_option_row(RrhkOptionRows *rows,int key,const char *format,const char *value) {(void)rows;(void)key;(void)format;(void)value;}
void rrhk_notice(const char *text,Uint64 milliseconds) {(void)text;(void)milliseconds;}
void rrhk_menu_line(const RrhkMenuCtx *ctx,int y,const char *text) {(void)ctx;(void)y;(void)text;}
void rrhk_help_sound_line(const RrhkMenuCtx *ctx,int y) {(void)ctx;(void)y;}
const RrhkPage rrhk_pointer_page={0};

int main(void) {
    SDL_SetMainReady();assert(!SDL_Init(SDL_INIT_VIDEO|SDL_INIT_GAMECONTROLLER));rrhk_bind(rrhk_adapter());rrhk_load_bindings();
    const uint16_t expected[10]={16,32,64,128,256,512,1,2,4,8};unsigned checked=0;
    assert(!strcmp(rr_keyboard_name(rrhk.keys[0][A]),"W"));
    assert(!strcmp(rr_keyboard_name(rrhk.keys[0][B]),"X"));
    for(int p=0;p<2;++p)for(int a=0;a<10;++a) {
        memset(mock_keys,0,sizeof mock_keys);mock_keys[rrhk.keys[p][a]]=1;
        assert(rrhk_pad_word(p,0)==expected[a]);assert(rrhk_pad_word(!p,0)==0);++checked;
    }
    /* Enter is Start; either Shift inserts the coin unless the other Shift
     * has a binding of its own, for any player. */
    memset(mock_keys,0,sizeof mock_keys);
    assert(rrhk.keys[0][START]==SDL_SCANCODE_RETURN && rrhk.keys[0][COIN]==SDL_SCANCODE_LSHIFT);++checked;
    mock_keys[SDL_SCANCODE_RSHIFT]=1;assert(rrhk_pad_word(0,0)==512);++checked;
    SDL_Scancode d=rrhk.keys[0][D];rrhk.keys[0][D]=SDL_SCANCODE_RSHIFT;assert(rrhk_pad_word(0,0)==128);rrhk.keys[0][D]=d;++checked;
    SDL_Scancode kp0=rrhk.keys[1][COIN];rrhk.keys[1][COIN]=SDL_SCANCODE_RSHIFT;assert(rrhk_pad_word(0,0)==0 && rrhk_pad_word(1,0)==512);rrhk.keys[1][COIN]=kp0;++checked;
    rrhk.keys[0][COIN]=SDL_SCANCODE_RSHIFT;mock_keys[SDL_SCANCODE_RSHIFT]=0;mock_keys[SDL_SCANCODE_LSHIFT]=1;assert(rrhk_pad_word(0,0)==512);++checked;
    mock_keys[SDL_SCANCODE_LSHIFT]=0;mock_keys[SDL_SCANCODE_RSHIFT]=1;
    rrhk.keys[0][COIN]=SDL_SCANCODE_J;assert(rrhk_pad_word(0,0)==0);++checked;
    for(int p=0;p<2;++p) {
        memset(mock_keys,0,sizeof mock_keys);mock_keys[rrhk.keys[p][UP]]=mock_keys[rrhk.keys[p][DOWN]]=1;
        mock_keys[rrhk.keys[p][LEFT]]=mock_keys[rrhk.keys[p][RIGHT]]=mock_keys[rrhk.keys[p][A]]=1;
        assert(rrhk_pad_word(p,0)==16);++checked;
    }
    assert(rr_ng_start_bits(256,0)==1);assert(rr_ng_start_bits(0,256)==4);
    assert(rr_ng_start_bits(256,256)==5);assert(rr_ng_coin_bits(512,0)==1);
    assert(rr_ng_coin_bits(0,512)==2);assert(rr_ng_coin_bits(512,512)==3);checked+=6;
    assert(!(rr_ng_status_b(0)&0x70));assert(rr_ng_status_b(5)==0x0a);checked+=2;
    assert(rr_ng_host_coin_bits(512,512,0)==3);
    assert(rr_ng_host_coin_bits(512,0,1)==0);
    assert(rr_ng_host_coin_bits(0,512,1)==0);
    assert(rr_ng_status_b(rr_ng_start_bits(256,256))==0x0a);checked+=4;
    RrNgBootCover cover={0};uint32_t image[1000]={0};unsigned boot_checks=0;
    assert(rr_ng_boot_cover(&cover,1,false,image,1000));++boot_checks;
    for(unsigned n=0;n<1000;++n)image[n]=0x00ff00;
    assert(rr_ng_boot_cover(&cover,64,false,image,1000));++boot_checks;
    assert(rr_ng_boot_cover(&cover,64,false,image,1000));++boot_checks;
    for(unsigned n=0;n<1000;++n)image[n]=n<900?0xf7f7f7:0;
    assert(!rr_ng_boot_cover(&cover,175,false,image,1000));++boot_checks;
    for(unsigned n=0;n<1000;++n)image[n]=0x00ff00;
    assert(!rr_ng_boot_cover(&cover,176,false,image,1000));++boot_checks;
    cover=(RrNgBootCover){0};
    assert(rr_ng_boot_cover(&cover,239,false,image,1000));++boot_checks;
    assert(!rr_ng_boot_cover(&cover,240,false,image,1000));++boot_checks;
    cover=(RrNgBootCover){0};
    for(unsigned n=0;n<1000;++n)image[n]=n<995?0:0xffffff;
    assert(rr_ng_boot_cover(&cover,8,false,image,1000));++boot_checks;
    cover=(RrNgBootCover){0};
    assert(!rr_ng_boot_cover(&cover,8,true,image,1000));++boot_checks;
    printf("{\"keyboard_and_mvs_wiring_checks\":%u,\"boot_presentation_checks\":%u,\"rom_free\":true}\n",checked,boot_checks);SDL_Quit();return 0;
}
