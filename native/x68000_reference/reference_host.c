/* Original RetroRecomp reference frontend, MIT. No game or firmware data.
 * This process loads a separate PX68k reference module. It does not link the
 * PolyForm translation engine and never labels interpreted execution native. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include <libretro.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdarg.h>
#include <string.h>
#include <math.h>
#include <inttypes.h>
#include "probe.h"
#include "hardware_clock.h"
#include "video_checks.h"
#include "audio_checks.h"
#include "timing_checks.h"
#include "session_checks.h"
#include "disk_checks.h"
#include "loading.h"
#include "state_store.h"
#include "media_session.h"
#include "../font6x10.h"
#include "platform_io.h"
#ifdef _WIN32
#include <shellapi.h>
#endif
#ifdef RR_X68000_LINKED
#include "payload.h"
#include "x68000_payload.h"
#include "embedded_resources.h"
#else
#define RR_X68K_GAME_TITLE "Cho Ren Sha 68k"
#endif
#ifdef RR_X68000_DEVCPU
#include "observe.h"
#endif

#define PATH_CAP 2048
#define MAX_OPTIONS 128
#define MAX_EVENTS 4096
#define MAX_FRAMES 36000
#define FNV_START UINT64_C(14695981039346656037)
typedef struct { unsigned begin, end, id,port; int value, keyboard,mouse; } InputEvent;
typedef struct {unsigned frame,drive;int image;} DiskEvent;
typedef struct { uint64_t video, pcm, ram, hardware[8]; uint32_t regs[18]; unsigned samples, width, height; } FrameRecord;
static struct {
   void (*set_environment)(retro_environment_t);
   void (*set_video_refresh)(retro_video_refresh_t);
   void (*set_audio_sample)(retro_audio_sample_t);
   void (*set_audio_sample_batch)(retro_audio_sample_batch_t);
   void (*set_input_poll)(retro_input_poll_t);
   void (*set_input_state)(retro_input_state_t);
   void (*init)(void); void (*deinit)(void); void (*run)(void);
   void (*reset)(void); void (*unload_game)(void);
   bool (*load_game)(const struct retro_game_info *);
   size_t (*serialize_size)(void);
   bool (*serialize)(void *,size_t), (*unserialize)(const void *,size_t);
   const char *(*state_compatibility)(void);
   const void *(*framebuffer)(void);
   void (*get_system_av_info)(struct retro_system_av_info *);
   void *(*get_memory_data)(unsigned); size_t (*get_memory_size)(unsigned);
   void (*set_controller_port_device)(unsigned,unsigned);
   void (*get_cpu)(uint32_t *); void (*set_clock)(uint64_t);
   void (*hardware_snapshot)(uint64_t *);
   uint32_t (*video_checks)(const char *), (*audio_checks)(const char *), (*timing_checks)(const char *);
   uint32_t (*session_checks)(const char *);
   unsigned (*disk_checks)(const char *);
   unsigned (*media_ready)(void),(*media_activity)(void),(*media_interest)(unsigned);
#ifdef RR_X68000_DEVCPU
   int (*cpu_configure)(int,int);int (*cpu_report)(const char*);
   void (*cpu_stats)(uint64_t*);
   int (*trace_configure)(unsigned);int (*trace_report)(const char*);
   unsigned (*guard_checks)(void);
#endif
} core;
static char system_dir[PATH_CAP], saves_dir[PATH_CAP], content_dir[PATH_CAP];
static char options_key[MAX_OPTIONS][128], options_value[MAX_OPTIONS][256];
static unsigned option_count, frame_number, video_frames, nonblack_frames;
static unsigned geometry_changes, width, height, frame_samples;
static int pixel_format = RETRO_PIXEL_FORMAT_RGB565;
static bool headless, mute, quit_requested, core_error;
static double fps = 61.46, sample_rate = 44100.0, aspect_ratio = 4.0/3.0;
static uint64_t video_hash, frame_pcm = FNV_START, total_pcm = FNV_START;
/* Traces and reports hash images and sound; captures and the pause screen
 * reuse the last image. Normal play skips both. A future automatic loading
 * acceleration needs an image signature in play: enable hash_video then. */
static bool hash_video = true, keep_pixels = true;
static uint64_t total_samples, nonzero_samples;
static uint8_t *last_pixels;
static size_t last_pixels_size;
static SDL_Window *window;
static SDL_Renderer *renderer;
static SDL_Texture *texture;
static unsigned texture_width, texture_height;
static SDL_AudioDeviceID audio_device;
static const uint8_t *keys;
static SDL_GameController *controllers[2];
static struct retro_frame_time_callback frame_time;
static InputEvent events[MAX_EVENTS];
static unsigned event_count;
static DiskEvent disk_events[128];
static unsigned disk_event_count;
static bool auto_disk;
static unsigned auto_disk_changes;
static unsigned ram_megabytes = 2;
static struct retro_disk_control_callback disk_callbacks;
static RRMediaSession media;
static bool media_opened,guest_keyboard,mouse_grab,help_open,autofire,input_focus=true;
static bool fast_forward;
static bool automatic_loading;
static unsigned loading_holdoff,loading_candidate_frames,accelerated_frames;
static RRLoading loading_detector;
static bool mouse_game;
static bool want_save,want_load,want_swap,want_eject;
static unsigned disk_drive,swap_drive;
static int swap_direction,mouse_dx,mouse_dy;
static Uint32 mouse_buttons;
static uint64_t input_frame,polled_frame=UINT64_MAX;
static double elapsed_usec;
static char source_identity[65],state_slot[PATH_CAP],player_config[PATH_CAP],media_config[PATH_CAP];
static char status_text[192];
static char last_error[384];
static Uint32 status_until;
static unsigned saved_count,loaded_count,rejected_count,swapped_count;
/* Bounded media timeline for reports. Observation only: presence and blink
 * changes made by the guest during a frame, then those made by the host
 * (menus, automatic changes, disk events, states, restarts). */
#define MEDIA_LOG_MAX 256u
enum { MEDIA_GUEST_EJECT, MEDIA_GUEST_INSERT, MEDIA_BLINK_ON, MEDIA_BLINK_OFF, MEDIA_HOST_EJECT, MEDIA_HOST_INSERT, MEDIA_POLLED };
static const char *const media_log_kinds[]={"guest_eject","guest_insert","blink_on","blink_off","host_eject","host_insert","polled"};
typedef struct { unsigned frame; unsigned char drive,kind; signed char image; } MediaLogEntry;
static MediaLogEntry media_log[MEDIA_LOG_MAX];
static unsigned media_log_count,media_log_dropped,media_log_seen,media_interest_seen[2],media_empty_polls[2];
static bool media_polled_logged[2];
static void media_log_scan(bool host){
   unsigned now=core.media_ready?core.media_ready():0,d;
   for(d=0;d<2;d++){
      unsigned present=1u<<d,blink=1u<<(8+d),interest=core.media_interest?core.media_interest(d):0;int kind=-1;
      /* One entry per empty period: the guest looked at the empty drive. */
      if(!host&&!(now&present)&&!(media_log_seen&present)&&interest!=media_interest_seen[d]){
         media_empty_polls[d]+=interest-media_interest_seen[d];
         if(!media_polled_logged[d]){media_polled_logged[d]=true;
            if(media_log_count<MEDIA_LOG_MAX)media_log[media_log_count++]=(MediaLogEntry){frame_number,(unsigned char)d,MEDIA_POLLED,(signed char)(media_opened?media.selected[d]:-1)};else media_log_dropped++;}
      }
      media_interest_seen[d]=interest;
      if(now&present)media_polled_logged[d]=false;
      if((now^media_log_seen)&present)kind=now&present?(host?MEDIA_HOST_INSERT:MEDIA_GUEST_INSERT):(host?MEDIA_HOST_EJECT:MEDIA_GUEST_EJECT);
      if(kind>=0){if(media_log_count<MEDIA_LOG_MAX)media_log[media_log_count++]=(MediaLogEntry){frame_number,(unsigned char)d,(unsigned char)kind,(signed char)(media_opened?media.selected[d]:-1)};else media_log_dropped++;}
      if((now^media_log_seen)&blink){
         if(media_log_count<MEDIA_LOG_MAX)media_log[media_log_count++]=(MediaLogEntry){frame_number,(unsigned char)d,(unsigned char)(now&blink?MEDIA_BLINK_ON:MEDIA_BLINK_OFF),(signed char)(media_opened?media.selected[d]:-1)};
         else media_log_dropped++;}
   }
   media_log_seen=now;
}
static void player_present(const void *,unsigned,unsigned,size_t);
static int player_init(void),player_blocked(void),player_joy(unsigned),player_action(unsigned,unsigned),player_ui_quit(void),player_ui_restart(void);
static int player_escape_held(void);
static unsigned player_fire_scan(void);
static int player_mouse(unsigned,int);
static int player_fast_forward(void);
static bool player_event(const SDL_Event *);
static void player_shutdown(void),player_pause_audio(void);
static int player_queue_audio(const int16_t *,size_t);
static FILE *player_fopen(const char *path,const char *mode){
   wchar_t p[4096],m[16];return rr_from_utf8(path,p,4096)&&rr_from_utf8(mode,m,16)?rr_fopen(p,m):NULL;
}
#define fopen player_fopen

static void notify(const char *message) {
   snprintf(status_text,sizeof(status_text),"%s",message); status_until=SDL_GetTicks()+3500;
   fprintf(stdout,"Session: %s\n",message);fflush(stdout);
}
static void text_line(int x,int y,const char *s,int scale) {
   for(;*s;s++,x+=6*scale) {
      unsigned c=(unsigned char)*s,row,col;
      if(c<32||c>127)c='?';
      for(row=0;row<10;row++)for(col=0;col<6;col++)if(rr_font6x10[c-32][row]&(1u<<col)){
         SDL_Rect dot={x+(int)col*scale,y+(int)row*scale,scale,scale};SDL_RenderFillRect(renderer,&dot);
      }
   }
}
static void overlay(void) {
   int w,h,scale;SDL_Rect panel;
   if(!renderer)return;SDL_GetRendererOutputSize(renderer,&w,&h);scale=w>=760?2:1;
   if(help_open){
      const char *lines[]={"Retro-Recomp | X68000 controls",
       "Arrows / left stick: move    Z / X: buttons",
       "Gamepad A / B: buttons       Start: Enter",
       "F8: save state              F9: load state",
       "Ctrl+Alt+K: full guest keyboard (F8/F9 pass through)",
       "Ctrl+Alt+M: capture / release mouse",
       "Ctrl+Alt+F: rapid fire while holding button 1",
       "Ctrl+Alt+Page Up/Down: previous / next disk in FDD0",
       "Add Shift for FDD1; Ctrl+Alt+Backspace: eject",
       "Ctrl+Alt+Enter: fullscreen   Ctrl+Alt+Q: quit",
       "Ctrl+Alt+H: close this help"};unsigned i;
      panel=(SDL_Rect){10,10,w-20,(int)(sizeof(lines)/sizeof(lines[0]))*14*scale+20};
      SDL_SetRenderDrawBlendMode(renderer,SDL_BLENDMODE_BLEND);SDL_SetRenderDrawColor(renderer,18,18,18,235);SDL_RenderFillRect(renderer,&panel);
      for(i=0;i<sizeof(lines)/sizeof(lines[0]);i++){SDL_SetRenderDrawColor(renderer,i?235:212,i?235:167,i?235:55,255);text_line(20,20+(int)i*14*scale,lines[i],scale);}
   }
   if(status_text[0]&&(int32_t)(status_until-SDL_GetTicks())>0){
      panel=(SDL_Rect){10,h-16*scale-12,w-20,16*scale+4};
      SDL_SetRenderDrawBlendMode(renderer,SDL_BLENDMODE_BLEND);SDL_SetRenderDrawColor(renderer,18,18,18,235);SDL_RenderFillRect(renderer,&panel);
      SDL_SetRenderDrawColor(renderer,245,205,76,255);text_line(16,panel.y+4,status_text,scale);
   }
}

static uint64_t hash_bytes(uint64_t h, const void *ptr, size_t size) {
   const uint8_t *p = (const uint8_t *)ptr;
   while (size--) { h ^= *p++; h *= UINT64_C(1099511628211); }
   return h;
}
static uint64_t hash_word(uint64_t h, uint16_t value) {
   uint8_t b[2] = { (uint8_t)value, (uint8_t)(value >> 8) };
   return hash_bytes(h,b,2);
}
static void fail(const char *message) { snprintf(last_error,sizeof(last_error),"%s",message);fprintf(stderr,"X68000 reference: %s\n",message); core_error=true; quit_requested=true; }
static void log_message(enum retro_log_level level, const char *fmt, ...) {
   va_list args;
   if (level < RETRO_LOG_WARN) return;
   va_start(args,fmt); vfprintf(stderr,fmt,args); va_end(args);
   if (level == RETRO_LOG_ERROR){va_start(args,fmt);vsnprintf(last_error,sizeof(last_error),fmt,args);va_end(args);core_error=true;}
}
static bool copy_path(char *dst, const char *src) {
   size_t n = strlen(src);
   if (n >= PATH_CAP) return false;
   memcpy(dst,src,n+1); return true;
}
static bool environment(unsigned cmd, void *data) {
   unsigned i;
   switch (cmd) {
   case RETRO_ENVIRONMENT_GET_LOG_INTERFACE:
      ((struct retro_log_callback *)data)->log=log_message; return true;
   case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY: *(const char **)data=system_dir; return true;
   case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY: *(const char **)data=saves_dir; return true;
   case RETRO_ENVIRONMENT_GET_CONTENT_DIRECTORY:
   case RETRO_ENVIRONMENT_GET_FILE_BROWSER_START_DIRECTORY: *(const char **)data=content_dir; return true;
   case RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION: *(unsigned *)data=0; return true;
   case RETRO_ENVIRONMENT_GET_LANGUAGE: *(unsigned *)data=RETRO_LANGUAGE_ENGLISH; return true;
   case RETRO_ENVIRONMENT_GET_CAN_DUPE: *(bool *)data=true; return true;
   case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE: *(bool *)data=false; return true;
   case RETRO_ENVIRONMENT_GET_AUDIO_VIDEO_ENABLE: *(int *)data=3; return true;
   case RETRO_ENVIRONMENT_GET_INPUT_BITMASKS: return true;
   case RETRO_ENVIRONMENT_GET_DISK_CONTROL_INTERFACE_VERSION: *(unsigned *)data=0; return true;
   case RETRO_ENVIRONMENT_SET_DISK_CONTROL_INTERFACE:
      disk_callbacks=*(const struct retro_disk_control_callback *)data;return true;
   case RETRO_ENVIRONMENT_SET_VARIABLES: {
      const struct retro_variable *v=(const struct retro_variable *)data;
      for (;v && v->key;v++) {
         const char *start=strchr(v->value,';'); size_t len;
         if (!start || option_count == MAX_OPTIONS) continue;
         start++; while (*start==' ') start++;
         len=strcspn(start,"|");
         if (strlen(v->key)>=128 || len>=256) { fail("Core option exceeds bounds"); return false; }
         strcpy(options_key[option_count],v->key);
         memcpy(options_value[option_count],start,len); options_value[option_count][len]=0;
         option_count++;
      } return true;
   }
   case RETRO_ENVIRONMENT_GET_VARIABLE: {
      struct retro_variable *v=(struct retro_variable *)data;
      if (!strcmp(v->key,"px68k_cpuspeed")) v->value="10Mhz";
      else if (!strcmp(v->key,"px68k_disk_drive")) v->value=disk_drive?"FDD1":"FDD0";
      else if (!strcmp(v->key,"px68k_ramsize")) v->value=ram_megabytes==2?"2MB":"4MB";
      else if (!strcmp(v->key,"px68k_frameskip")) v->value="Full Frame";
      else if (!strcmp(v->key,"px68k_adjust_frame_rates") ||
               !strcmp(v->key,"px68k_no_wait_mode") ||
               !strcmp(v->key,"px68k_audio_desync_hack") ||
               !strcmp(v->key,"px68k_save_fdd_path") ||
               !strcmp(v->key,"px68k_save_hdd_path") ||
               !strcmp(v->key,"px68k_rumble_on_disk_read")) v->value="disabled";
      else {
         for(i=0;i<option_count;i++) if (!strcmp(v->key,options_key[i])) break;
         if (i==option_count) { v->value=NULL; return false; }
         v->value=options_value[i];
      } return true;
   }
   case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
      pixel_format=*(int *)data;
      return pixel_format==RETRO_PIXEL_FORMAT_RGB565 || pixel_format==RETRO_PIXEL_FORMAT_XRGB8888;
   case RETRO_ENVIRONMENT_SET_FRAME_TIME_CALLBACK: frame_time=*(struct retro_frame_time_callback *)data; return true;
   case RETRO_ENVIRONMENT_SET_GEOMETRY: {
      const struct retro_game_geometry *g=(const struct retro_game_geometry *)data;
      if (!g->base_width || !g->base_height || g->base_width>2048 || g->base_height>2048) return false;
      aspect_ratio=isfinite(g->aspect_ratio) && g->aspect_ratio>0.1 && g->aspect_ratio<10.0?g->aspect_ratio:(double)g->base_width/g->base_height;
      geometry_changes++; return true;
   }
   case RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO: {
      const struct retro_system_av_info *av=(const struct retro_system_av_info *)data;
      if (!isfinite(av->timing.fps) || av->timing.fps < 20 || av->timing.fps>120 || av->timing.sample_rate!=44100) return false;
      fps=av->timing.fps; sample_rate=av->timing.sample_rate;
      if(isfinite(av->geometry.aspect_ratio) && av->geometry.aspect_ratio>0.1 && av->geometry.aspect_ratio<10.0) aspect_ratio=av->geometry.aspect_ratio;
      geometry_changes++; return true;
   }
   case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
   case RETRO_ENVIRONMENT_SET_CONTROLLER_INFO:
   case RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME:
   case RETRO_ENVIRONMENT_SET_PERFORMANCE_LEVEL: return true;
   case RETRO_ENVIRONMENT_SHUTDOWN: quit_requested=true; return true;
   case RETRO_ENVIRONMENT_SET_MESSAGE:
      fprintf(stderr,"Core: %s\n",((const struct retro_message *)data)->msg); return true;
   default: return false;
   }
}
static void video(const void *data, unsigned w, unsigned h, size_t pitch) {
   unsigned x,y,bpp=pixel_format==RETRO_PIXEL_FORMAT_RGB565?2:4;
   bool lit=false; size_t needed;
   if (!data || data==RETRO_HW_FRAME_BUFFER_VALID) return;
   if (!w || !h || w>2048 || h>2048 || pitch < (size_t)w*bpp) { fail("Invalid video geometry"); return; }
   needed=(size_t)w*h*bpp;
   if (last_pixels_size != needed) {
      void *newbuf=realloc(last_pixels,needed);
      if (!newbuf) { fail("Video allocation failed"); return; }
      last_pixels=(uint8_t *)newbuf; last_pixels_size=needed;
   }
   /* A frame is "lit" as soon as one byte is non-zero (reports only). */
   if(hash_video) video_hash=FNV_START;
   if(keep_pixels) for(y=0;y<h;y++) {
      const uint8_t *row=(const uint8_t *)data+y*pitch;
      memcpy(last_pixels+(size_t)y*w*bpp,row,(size_t)w*bpp);
      if(!hash_video) continue;
      video_hash=hash_bytes(video_hash,row,(size_t)w*bpp);
      if(!lit) for(x=0;x<w*bpp;x++) if (row[x]) { lit=true; break; }
   }
   width=w; height=h; video_frames++; nonblack_frames+=lit;
   if(renderer){if(!fast_forward||!(input_frame&7))player_present(data,w,h,pitch);return;}
   if (renderer) {
      if (!texture || w!=texture_width || h!=texture_height) {
         if(texture) SDL_DestroyTexture(texture);
         texture=SDL_CreateTexture(renderer,bpp==2?SDL_PIXELFORMAT_RGB565:SDL_PIXELFORMAT_ARGB8888,
                                  SDL_TEXTUREACCESS_STREAMING,(int)w,(int)h);
         texture_width=w; texture_height=h;
      }
      if(!texture) { fail(SDL_GetError()); return; }
      { int rw,rh; SDL_Rect destination;
        if(SDL_GetRendererOutputSize(renderer,&rw,&rh)!=0 || rw<=0 || rh<=0) { fail(SDL_GetError()); return; }
        destination.w=rw; destination.h=(int)round(rw/aspect_ratio);
        if(destination.h>rh) { destination.h=rh; destination.w=(int)round(rh*aspect_ratio); }
        destination.x=(rw-destination.w)/2; destination.y=(rh-destination.h)/2;
        SDL_UpdateTexture(texture,NULL,data,(int)pitch);
        SDL_SetRenderDrawColor(renderer,0,0,0,255); SDL_RenderClear(renderer);
        SDL_RenderCopy(renderer,texture,NULL,&destination); overlay(); SDL_RenderPresent(renderer);
      }
   }
}
static size_t audio_batch(const int16_t *samples, size_t count) {
   size_t i;
   if (count > 65536) { fail("Invalid audio batch"); return 0; }
   if(hash_video) for(i=0;i<count*2;i++) {
      frame_pcm=hash_word(frame_pcm,(uint16_t)samples[i]);
      total_pcm=hash_word(total_pcm,(uint16_t)samples[i]);
      if(samples[i]) nonzero_samples++;
   }
   total_samples+=count; frame_samples+=(unsigned)count;
   if(audio_device && !fast_forward && !player_queue_audio(samples,count))fail(SDL_GetError());
   return count;
}
static void audio_sample(int16_t left,int16_t right) { int16_t v[2]={left,right}; audio_batch(v,1); }
static unsigned key_scan(unsigned id) {
   switch(id) {
   case RETROK_UP:return SDL_SCANCODE_UP; case RETROK_DOWN:return SDL_SCANCODE_DOWN;
   case RETROK_LEFT:return SDL_SCANCODE_LEFT; case RETROK_RIGHT:return SDL_SCANCODE_RIGHT;
   case RETROK_LSHIFT:return SDL_SCANCODE_LSHIFT; case RETROK_RSHIFT:return SDL_SCANCODE_RSHIFT;
   case RETROK_LCTRL:return SDL_SCANCODE_LCTRL; case RETROK_RCTRL:return SDL_SCANCODE_RCTRL;
   case RETROK_LALT:return SDL_SCANCODE_LALT; case RETROK_RALT:return SDL_SCANCODE_RALT;
   case RETROK_F1:return SDL_SCANCODE_F1; case RETROK_F2:return SDL_SCANCODE_F2;
   case RETROK_F3:return SDL_SCANCODE_F3; case RETROK_F4:return SDL_SCANCODE_F4;
   case RETROK_F5:return SDL_SCANCODE_F5; case RETROK_F6:return SDL_SCANCODE_F6;
   case RETROK_F7:return SDL_SCANCODE_F7; case RETROK_F8:return SDL_SCANCODE_F8;
   case RETROK_F9:return SDL_SCANCODE_F9; case RETROK_F10:return SDL_SCANCODE_F10;
   case RETROK_F11:return SDL_SCANCODE_F11;
   case RETROK_HOME:return SDL_SCANCODE_HOME; case RETROK_END:return SDL_SCANCODE_END;
   case RETROK_INSERT:return SDL_SCANCODE_INSERT; case RETROK_DELETE:return SDL_SCANCODE_DELETE;
   case RETROK_PAGEUP:return SDL_SCANCODE_PAGEUP; case RETROK_PAGEDOWN:return SDL_SCANCODE_PAGEDOWN;
   default: return id<128?SDL_GetScancodeFromKey((SDL_Keycode)id):SDL_SCANCODE_UNKNOWN;
   }
}
static void add_controller(int device_index) {
   unsigned p;
   if(!SDL_IsGameController(device_index))return;
   for(p=0;p<2;p++)if(controllers[p]&&SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controllers[p]))==SDL_JoystickGetDeviceInstanceID(device_index))return;
   for(p=0;p<2;p++)if(!controllers[p]){controllers[p]=SDL_GameControllerOpen(device_index);break;}
}
static void input_poll(void) {
   SDL_Event e;
   if(polled_frame==frame_number)return;
   polled_frame=frame_number;
   if(headless) return;
   while(SDL_PollEvent(&e)) {
      if(e.type==SDL_QUIT) quit_requested=true;
      if(e.type==SDL_CONTROLLERDEVICEADDED)add_controller(e.cdevice.which);
      if(e.type==SDL_CONTROLLERDEVICEREMOVED){unsigned p;for(p=0;p<2;p++)if(controllers[p]&&SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controllers[p]))==e.cdevice.which){SDL_GameControllerClose(controllers[p]);controllers[p]=NULL;}}
      if(e.type==SDL_WINDOWEVENT&&e.window.event==SDL_WINDOWEVENT_FOCUS_LOST){input_focus=false;SDL_SetRelativeMouseMode(SDL_FALSE);}
      if(e.type==SDL_WINDOWEVENT&&e.window.event==SDL_WINDOWEVENT_FOCUS_GAINED){input_focus=true;if(mouse_grab)SDL_SetRelativeMouseMode(SDL_TRUE);}
      if((e.type==SDL_KEYDOWN&&!e.key.repeat&&e.key.keysym.sym!=SDLK_F5)||
         e.type==SDL_MOUSEBUTTONDOWN||e.type==SDL_CONTROLLERBUTTONDOWN||
         (e.type==SDL_MOUSEMOTION&&(e.motion.xrel||e.motion.yrel))||
         (e.type==SDL_CONTROLLERAXISMOTION&&(e.caxis.value>12000||e.caxis.value< -12000)))
         loading_holdoff=16;
      if(player_event(&e))continue;
      /* Mouse-driven computer games can be unknown to the title profiles.
       * Clicking the active game captures it without a hidden key chord.
       * Menus and an unfocused window never capture the pointer. */
      if(e.type==SDL_MOUSEBUTTONDOWN&&e.button.button==SDL_BUTTON_LEFT&&
            input_focus&&!player_blocked()&&!mouse_grab){
         mouse_grab=true;SDL_SetRelativeMouseMode(SDL_TRUE);
         notify("Mouse captured (Ctrl+Alt+M to release)");
      }
      if(e.type==SDL_KEYDOWN && !e.key.repeat && (e.key.keysym.mod & KMOD_CTRL) &&
          (e.key.keysym.mod & KMOD_ALT)) {
         if(e.key.keysym.sym==SDLK_q) quit_requested=true;
         if(e.key.keysym.sym==SDLK_h) help_open=!help_open;
         if(e.key.keysym.sym==SDLK_k){guest_keyboard=!guest_keyboard;notify(guest_keyboard?"Full guest keyboard: ON (F8/F9 sent to X68000)":"Game shortcuts: ON (F8/F9 save and load)");}
         if(e.key.keysym.sym==SDLK_f){autofire=!autofire;notify(autofire?"Rapid fire: ON":"Rapid fire: OFF");}
         if(e.key.keysym.sym==SDLK_m){mouse_grab=!mouse_grab;SDL_SetRelativeMouseMode(mouse_grab?SDL_TRUE:SDL_FALSE);notify(mouse_grab?"Mouse captured (Ctrl+Alt+M to release)":"Mouse released");}
         if(e.key.keysym.sym==SDLK_PAGEUP||e.key.keysym.sym==SDLK_PAGEDOWN){want_swap=true;swap_drive=(e.key.keysym.mod&KMOD_SHIFT)?1:0;swap_direction=e.key.keysym.sym==SDLK_PAGEUP?-1:1;}
         if(e.key.keysym.sym==SDLK_BACKSPACE){want_eject=true;swap_drive=(e.key.keysym.mod&KMOD_SHIFT)?1:0;}
         if(e.key.keysym.sym==SDLK_RETURN) SDL_SetWindowFullscreen(window,
            (SDL_GetWindowFlags(window)&SDL_WINDOW_FULLSCREEN_DESKTOP)?0:SDL_WINDOW_FULLSCREEN_DESKTOP);
      } else if(e.type==SDL_KEYDOWN&&!e.key.repeat&&!guest_keyboard) {
         if(e.key.keysym.sym==SDLK_F8)want_save=true;
         if(e.key.keysym.sym==SDLK_F9)want_load=true;
      }
   }
   keys=SDL_GetKeyboardState(NULL);
   if(player_ui_quit())quit_requested=true;
   else if(player_ui_restart())player_pause_audio();
   mouse_buttons=SDL_GetRelativeMouseState(&mouse_dx,&mouse_dy);
   if(!mouse_grab||!input_focus){mouse_dx=mouse_dy=0;mouse_buttons=0;}
}
static int16_t input_state(unsigned port,unsigned device,unsigned index,unsigned id) {
   unsigned i; int value=0;
   (void)index;
   if(port>1) return 0;
   if(player_blocked())return 0;
   if(device==RETRO_DEVICE_KEYBOARD) {
      /* Keep the upstream configuration menu inaccessible in this frontend. */
      if(port||id==RETROK_F12||id==RETROK_F1||id==RETROK_F11||
            (!guest_keyboard&&(id>=RETROK_F1&&id<=RETROK_F12)))return 0;
      if(id==RETROK_ESCAPE&&(!guest_keyboard||player_escape_held()))return 0;
      if(keys&&input_focus&&!(SDL_GetModState()&KMOD_CTRL&&SDL_GetModState()&KMOD_ALT)&&key_scan(id)!=SDL_SCANCODE_UNKNOWN)value=keys[key_scan(id)]!=0;
      if(id==RETROK_RETURN&&input_focus&&controllers[0]&&SDL_GameControllerGetButton(controllers[0],SDL_CONTROLLER_BUTTON_START))value=1;
      if(id==RETROK_RETURN&&player_action(0,6)>=0&&!guest_keyboard)value=player_action(0,6);
   } else if(device==RETRO_DEVICE_JOYPAD) {
      unsigned mask=0;
      if(keys&&input_focus&&port==0&&!(SDL_GetModState()&KMOD_CTRL&&SDL_GetModState()&KMOD_ALT)) {
         if(keys[SDL_SCANCODE_UP]) mask|=1u<<RETRO_DEVICE_ID_JOYPAD_UP;
         if(keys[SDL_SCANCODE_DOWN]) mask|=1u<<RETRO_DEVICE_ID_JOYPAD_DOWN;
         if(keys[SDL_SCANCODE_LEFT]) mask|=1u<<RETRO_DEVICE_ID_JOYPAD_LEFT;
         if(keys[SDL_SCANCODE_RIGHT]) mask|=1u<<RETRO_DEVICE_ID_JOYPAD_RIGHT;
         if(keys[SDL_GetScancodeFromKey(SDLK_w)]) mask|=1u<<RETRO_DEVICE_ID_JOYPAD_B;
         if(keys[SDL_GetScancodeFromKey(SDLK_x)]) mask|=1u<<RETRO_DEVICE_ID_JOYPAD_A;
      }
      if(controllers[port]&&input_focus) {
         static const unsigned joy[]={ RETRO_DEVICE_ID_JOYPAD_B,RETRO_DEVICE_ID_JOYPAD_A,
            RETRO_DEVICE_ID_JOYPAD_UP,RETRO_DEVICE_ID_JOYPAD_DOWN,RETRO_DEVICE_ID_JOYPAD_LEFT,RETRO_DEVICE_ID_JOYPAD_RIGHT };
         static const SDL_GameControllerButton btn[]={SDL_CONTROLLER_BUTTON_A,SDL_CONTROLLER_BUTTON_B,
            SDL_CONTROLLER_BUTTON_DPAD_UP,SDL_CONTROLLER_BUTTON_DPAD_DOWN,SDL_CONTROLLER_BUTTON_DPAD_LEFT,SDL_CONTROLLER_BUTTON_DPAD_RIGHT};
         int x=SDL_GameControllerGetAxis(controllers[port],SDL_CONTROLLER_AXIS_LEFTX),y=SDL_GameControllerGetAxis(controllers[port],SDL_CONTROLLER_AXIS_LEFTY);
         for(i=0;i<6;i++) if(SDL_GameControllerGetButton(controllers[port],btn[i])) mask|=1u<<joy[i];
         if(x< -12000)mask|=1u<<RETRO_DEVICE_ID_JOYPAD_LEFT;if(x>12000)mask|=1u<<RETRO_DEVICE_ID_JOYPAD_RIGHT;
         if(y< -12000)mask|=1u<<RETRO_DEVICE_ID_JOYPAD_UP;if(y>12000)mask|=1u<<RETRO_DEVICE_ID_JOYPAD_DOWN;
      }
      {int mapped=player_joy(port);if(mapped>=0)mask=(unsigned)mapped;}
      for(i=0;i<event_count;i++) if(!events[i].keyboard&&!events[i].mouse&&port==events[i].port&&input_frame>=events[i].begin&&input_frame<events[i].end&&events[i].value)mask|=1u<<events[i].id;
      if(autofire&&(input_frame&1))mask&=~(1u<<RETRO_DEVICE_ID_JOYPAD_B);
      /* Never send L2/R2/Select/stick clicks to the core's private menus. */
      mask&=~((1u<<RETRO_DEVICE_ID_JOYPAD_L2)|(1u<<RETRO_DEVICE_ID_JOYPAD_R2)|(1u<<RETRO_DEVICE_ID_JOYPAD_SELECT)|(1u<<RETRO_DEVICE_ID_JOYPAD_L3)|(1u<<RETRO_DEVICE_ID_JOYPAD_R3));
      return (int16_t)(id==RETRO_DEVICE_ID_JOYPAD_MASK?mask:(id<16?((mask>>id)&1):0));
   } else if(device==RETRO_DEVICE_MOUSE&&port==0) {
      if(id==RETRO_DEVICE_ID_MOUSE_X)value=mouse_dx;
      if(id==RETRO_DEVICE_ID_MOUSE_Y)value=mouse_dy;
      if(id==RETRO_DEVICE_ID_MOUSE_LEFT)value=(mouse_buttons&SDL_BUTTON_LMASK)!=0;
      if(id==RETRO_DEVICE_ID_MOUSE_RIGHT)value=(mouse_buttons&SDL_BUTTON_RMASK)!=0;
      value=player_mouse(id,value);
   }
   for(i=0;i<event_count;i++)if(id==events[i].id&&input_frame>=events[i].begin&&input_frame<events[i].end&&
      ((events[i].keyboard&&device==RETRO_DEVICE_KEYBOARD)||(events[i].mouse&&device==RETRO_DEVICE_MOUSE)))value=events[i].value;
   /* Some games OR keyboard Z with joystick button 1. Pulsing the joystick
    * alone leaves an unbroken keyboard press and defeats rapid fire. Apply
    * the same release phase to the bound keyboard button, before returning
    * either input interface; full computer typing remains unmodified. */
   if(device==RETRO_DEVICE_KEYBOARD&&!guest_keyboard&&autofire&&(input_frame&1)){
      unsigned fire=player_fire_scan();
      if(fire&&key_scan(id)==fire)value=0;
   }
   if(device==RETRO_DEVICE_MOUSE&&mouse_game&&autofire&&(input_frame&1)&&id==RETRO_DEVICE_ID_MOUSE_LEFT)value=0;
   return (int16_t)value;
}
static bool load_events(const char *path) {
   FILE *f=fopen(path,"rb"); char line[256],kind[16],extra; InputEvent event;
   if(!f) return false;
   while(fgets(line,sizeof(line),f)) {
      if(line[0]=='#' || line[0]=='\r' || line[0]=='\n') continue;
      if(event_count==MAX_EVENTS || sscanf(line,"%u %u %15s %u %d %c",&event.begin,&event.end,kind,&event.id,&event.value,&extra)!=5 ||
         event.end<=event.begin || event.end>MAX_FRAMES || (strcmp(kind,"key")&&strcmp(kind,"joy")&&strcmp(kind,"joy2")&&strcmp(kind,"mouse")) ||
         event.id>=(!strcmp(kind,"key")?320u:!strcmp(kind,"mouse")?4u:16u) ||
         (!strcmp(kind,"mouse")?(event.value< -32768||event.value>32767):(event.value!=0&&event.value!=1))) { fclose(f); return false; }
      event.keyboard=!strcmp(kind,"key");event.mouse=!strcmp(kind,"mouse");event.port=!strcmp(kind,"joy2");events[event_count++]=event;
   }
   fclose(f); return true;
}
static bool load_disk_events(const char *path) {
   FILE *f=fopen(path,"rb");char line[128],extra;DiskEvent e;
   if(!f)return false;
   while(fgets(line,sizeof(line),f)){
      if(line[0]=='#'||line[0]=='\r'||line[0]=='\n')continue;
      if(disk_event_count==128||sscanf(line,"%u %u %d %c",&e.frame,&e.drive,&e.image,&extra)!=3||
         e.frame>=MAX_FRAMES||e.drive>1||e.image< -1||e.image>=RR_MEDIA_MAX){fclose(f);return false;}
      disk_events[disk_event_count++]=e;
   }
   fclose(f);return true;
}
typedef struct {
   uint32_t version,header_size,width,height,pixel_format,autofire;
   uint64_t input_frame,media_size;
   double elapsed_usec,fps,aspect_ratio;
} HostAuxiliary;
static void select_drive(unsigned drive) { disk_drive=drive; }
static bool save_core_state(void *context,void *data,size_t size) {
   (void)context;return core.serialize(data,size);
}
static bool load_core_state(void *context,const void *data,size_t size) {
   (void)context;return core.unserialize(data,size);
}
static bool capture_auxiliary(void *context,void *data,size_t size) {
   HostAuxiliary header;void *disks=NULL;size_t bytes=0;(void)context;
   if(!media_opened||!rr_media_capture(&media,&disks,&bytes)||size!=sizeof(header)+bytes){free(disks);return false;}
   memset(&header,0,sizeof(header));header.version=1;header.header_size=sizeof(header);
   header.width=width;header.height=height;header.pixel_format=(uint32_t)pixel_format;
   header.input_frame=input_frame;header.media_size=bytes;header.elapsed_usec=elapsed_usec;
   header.fps=fps;header.aspect_ratio=aspect_ratio;header.autofire=autofire;
   memcpy(data,&header,sizeof(header));memcpy((uint8_t*)data+sizeof(header),disks,bytes);free(disks);return true;
}
static bool validate_auxiliary(void *context,const void *data,size_t size) {
   HostAuxiliary header;(void)context;
   if(!media_opened||size<sizeof(header))return false;memcpy(&header,data,sizeof(header));
   if(header.version!=1||header.header_size!=sizeof(header)||header.media_size!=size-sizeof(header)||
      header.width>2048||header.height>2048||(!header.width!=!header.height)||header.autofire>1||
      header.input_frame>UINT64_C(9007199254740991)||!isfinite(header.elapsed_usec)||header.elapsed_usec<0||
      !isfinite(header.fps)||header.fps<20||header.fps>120||!isfinite(header.aspect_ratio)||header.aspect_ratio<0.1||header.aspect_ratio>10||
      (header.pixel_format!=RETRO_PIXEL_FORMAT_RGB565&&header.pixel_format!=RETRO_PIXEL_FORMAT_XRGB8888))return false;
   return rr_media_validate(&media,(const uint8_t*)data+sizeof(header),(size_t)header.media_size)!=0;
}
static bool apply_auxiliary(void *context,const void *data,size_t size) {
   HostAuxiliary header;
   if(!validate_auxiliary(context,data,size))return false;memcpy(&header,data,sizeof(header));
   if(!rr_media_apply(&media,(const uint8_t*)data+sizeof(header),(size_t)header.media_size))return false;
   input_frame=header.input_frame;elapsed_usec=header.elapsed_usec;fps=header.fps;
   aspect_ratio=header.aspect_ratio;pixel_format=(int)header.pixel_format;
   width=header.width;height=header.height;autofire=header.autofire!=0;
   return true;
}
static RRStateResult snapshot(bool load) {
   RRStateIO io;void *disks=NULL;size_t bytes=0;char error[192];RRStateResult result;
   if(!media_opened||strlen(source_identity)!=64){notify("Snapshot unavailable: regenerate this prototype folder");return RR_STATE_INVALID;}
   if(!load&&!video_frames){notify("Wait for the first frame before saving");return RR_STATE_INVALID;}
   if(!rr_media_capture(&media,&disks,&bytes)){notify(rr_media_error(&media));return RR_STATE_IO_ERROR;}free(disks);
   memset(&io,0,sizeof(io));io.identity=source_identity;io.compatibility=core.state_compatibility();
   io.core_size=core.serialize_size();io.auxiliary_size=sizeof(HostAuxiliary)+bytes;
   io.save_core=save_core_state;io.load_core=load_core_state;io.capture_auxiliary=capture_auxiliary;
   io.validate_auxiliary=validate_auxiliary;io.apply_auxiliary=apply_auxiliary;
   notify(load?"Loading state...":"Saving state...");
   result=load?rr_x68k_state_load(state_slot,&io,error,sizeof(error)):rr_x68k_state_save(state_slot,&io,error,sizeof(error));
   if(result==RR_STATE_OK){
      if(load){loaded_count++;automatic_loading=false;loading_holdoff=16;memset(&loading_detector,0,sizeof(loading_detector));
         if(audio_device)SDL_ClearQueuedAudio(audio_device);player_pause_audio();
         video(core.framebuffer(),width,height,800*2);}
      else saved_count++;
      notify(load?"State loaded":"State saved");
   }else{rejected_count++;notify(error);if(result==RR_STATE_ROLLBACK_ERROR)fail("Snapshot rollback failed; stopping to preserve state");}
   return result;
}
static void player_load(void) {
   FILE *f=fopen(player_config,"rb");unsigned full=0,keyboard=0,fire=0,w=0,h=0;char extra;
   if(f){int n=fscanf(f,"fullscreen=%u keyboard=%u autofire=%u width=%u height=%u %c",&full,&keyboard,&fire,&w,&h,&extra);fclose(f);
      if(n==5&&full<2&&keyboard<2&&fire<2&&w>=400&&w<=8192&&h>=300&&h<=8192){
         guest_keyboard=keyboard!=0;autofire=fire!=0;if(window){SDL_SetWindowSize(window,(int)w,(int)h);if(full)SDL_SetWindowFullscreen(window,SDL_WINDOW_FULLSCREEN_DESKTOP);}
      }}
}
static void player_save(void) {
   FILE *f;int w=900,h=675;if(!window)return;SDL_GetWindowSize(window,&w,&h);
   f=fopen(player_config,"wb");if(f){fprintf(f,"fullscreen=%u keyboard=%u autofire=%u width=%d height=%d\n",
      (SDL_GetWindowFlags(window)&SDL_WINDOW_FULLSCREEN_DESKTOP)!=0,guest_keyboard,autofire,w,h);fclose(f);}
}
#include "player_ui.inc"
static bool capture(const char *path) {
   unsigned x,y,bpp=pixel_format==RETRO_PIXEL_FORMAT_RGB565?2:4;
   FILE *f;
   if(!last_pixels) return false;
   f=fopen(path,"wb"); if(!f) return false;
   fprintf(f,"P6\n%u %u\n255\n",width,height);
   for(y=0;y<height;y++) for(x=0;x<width;x++) {
      uint8_t rgb[3]; const uint8_t *p=last_pixels+((size_t)y*width+x)*bpp;
      if(bpp==2) {
         uint16_t v; memcpy(&v,p,2);
         rgb[0]=(uint8_t)(((v>>11)&31)*255/31); rgb[1]=(uint8_t)(((v>>5)&63)*255/63); rgb[2]=(uint8_t)((v&31)*255/31);
      } else { rgb[0]=p[2]; rgb[1]=p[1]; rgb[2]=p[0]; }
      if(fwrite(rgb,1,3,f)!=3) { fclose(f); return false; }
   }
   return fclose(f)==0;
}
#ifdef RR_X68000_LINKED
extern const char *rr_x68k_state_compatibility(void);
extern const void *rr_x68k_framebuffer(void);
extern unsigned rr_x68k_guard_checks(void);
static void *linked_symbol(const char *name){
#define BIND(symbol) if(!strcmp(name,#symbol))return (void *)(symbol)
   BIND(retro_set_environment);BIND(retro_set_video_refresh);BIND(retro_set_audio_sample);BIND(retro_set_audio_sample_batch);
   BIND(retro_set_input_poll);BIND(retro_set_input_state);BIND(retro_init);BIND(retro_deinit);BIND(retro_run);BIND(retro_reset);
   BIND(retro_load_game);BIND(retro_unload_game);BIND(retro_serialize_size);BIND(retro_serialize);BIND(retro_unserialize);
   BIND(retro_get_system_av_info);BIND(retro_get_memory_data);BIND(retro_get_memory_size);BIND(retro_set_controller_port_device);
   BIND(rr_x68k_get_cpu);BIND(rr_x68k_set_clock);BIND(rr_x68k_hardware_snapshot);BIND(rr_x68k_video_checks);BIND(rr_x68k_audio_checks);
   BIND(rr_x68k_timing_checks);BIND(rr_x68k_session_checks);BIND(rr_x68k_disk_checks);BIND(rr_x68000_media_ready);BIND(rr_x68000_media_activity);BIND(rr_x68000_media_interest);
   BIND(rr_x68k_state_compatibility);BIND(rr_x68k_framebuffer);BIND(rr_x68k_cpu_configure);BIND(rr_x68k_cpu_report);
   BIND(rr_x68k_cpu_stats);BIND(rr_x68k_trace_configure);BIND(rr_x68k_trace_report);BIND(rr_x68k_guard_checks);
#undef BIND
   return NULL;
}
#define LOAD(member,name) do { *(void **)(&core.member)=linked_symbol(name);if(!core.member){fail(name);goto cleanup;} }while(0)
#else
#define LOAD(member,name) do { *(void **)(&core.member)=SDL_LoadFunction(module,name); if(!core.member) { fail(name); goto cleanup; } } while(0)
#endif
static int player_main(int argc,char **argv) {
   char core_path[PATH_CAP],content[PATH_CAP],report[PATH_CAP],capture_path[PATH_CAP]={0},trace_path[PATH_CAP]={0},config_path[PATH_CAP];
   char *base,base_path[PATH_CAP]; const char *events_path=NULL,*disk_events_path=NULL; unsigned frames=0,i,completed=0;
   bool report_requested=false,state_slot_requested=false;
   const char *video_checks_path=NULL,*audio_checks_path=NULL,*timing_checks_path=NULL;
   const char *session_checks_path=NULL,*disk_checks_path=NULL;
   bool load_start=false;
   unsigned save_at=UINT32_MAX,load_at=UINT32_MAX;
   uint64_t hardware[8]={0};
   void *module=NULL; bool initialized=false,loaded=false; int result=1;
   double wall_start,deadline,frequency;
   FrameRecord *records=NULL;
#ifdef RR_X68000_DEVCPU
   const char *observations_path=NULL;int reference_cpu=0;
   const char *instruction_trace_path=NULL;
   const char *guard_checks_path=NULL;
   uint64_t cpu_stats[8]={0};
#endif
   SDL_SetMainReady();
#ifdef RR_X68000_LINKED
   (void)rr_x68k_export_marker[0];
#endif
   if(SDL_Init(SDL_INIT_TIMER)!=0) { fprintf(stderr,"%s\n",SDL_GetError()); return 1; }
   base=SDL_GetBasePath(); if(!base) { fail("Executable directory unavailable"); goto cleanup; }
   if(!copy_path(base_path,base)){SDL_free(base);fail("Executable path too long");goto cleanup;}
#ifdef _WIN32
   snprintf(core_path,sizeof(core_path),"%srr_px68k_reference.dll",base);
#else
   snprintf(core_path,sizeof(core_path),"%srr_px68k_reference.so",base);
#endif
   snprintf(system_dir,sizeof(system_dir),"%sdatas/system",base);
   snprintf(saves_dir,sizeof(saves_dir),"%sdatas/saves",base);
   snprintf(content,sizeof(content),"%sdatas/media/game.m3u",base);
   snprintf(report,sizeof(report),"%sdatas/reference-report.json",base);
   snprintf(config_path,sizeof(config_path),"%sdatas/reference.cfg",base);
   snprintf(state_slot,sizeof(state_slot),"%sdatas/quick.rrstate",base);
   snprintf(player_config,sizeof(player_config),"%sdatas/player.cfg",base);
   snprintf(media_config,sizeof(media_config),"%sdatas/media-session.bin",base);
   {char identity_path[PATH_CAP],extra;FILE *f;
    snprintf(identity_path,sizeof(identity_path),"%sdatas/source-identity.txt",base);
    f=fopen(identity_path,"rb");if(f){if(fscanf(f,"%64[0-9a-f] %c",source_identity,&extra)!=1 || strlen(source_identity)!=64) source_identity[0]=0;fclose(f);}}
   SDL_free(base);
   { FILE *f=fopen(config_path,"rb");
     if(f) {
        unsigned configured_ram; char extra;
        int fields=fscanf(f,"ram_mib=%u %c",&configured_ram,&extra); fclose(f);
        if(fields!=1 || (configured_ram!=2 && configured_ram!=4)) { fail("Invalid staged machine configuration"); goto cleanup; }
        ram_megabytes=configured_ram;
     }
   }
   for(i=1;i<(unsigned)argc;i++) {
      if(!strcmp(argv[i],"--headless")) headless=true;
      else if(!strcmp(argv[i],"--mute")) mute=true;
      else if(!strcmp(argv[i],"--state-load-start")) load_start=true;
      else if(!strcmp(argv[i],"--auto-disk")) auto_disk=true;
#ifdef RR_X68000_DEVCPU
      else if(!strcmp(argv[i],"--reference-cpu")) reference_cpu=1;
#endif
      else if(!strcmp(argv[i],"--help")) {
#ifdef RR_X68000_DEVCPU
         puts("RetroRecomp X68000 guarded native CPU prototype (private development)\n"
              "--reference-cpu: use the interpreter for an independent replay\n"
              "--observations JSON --instruction-trace FILE --guard-checks JSON");
#endif
#ifndef RR_X68000_DEVCPU
         puts("RetroRecomp X68000 reference prototype (interpreted MC68000)\n"
#else
         puts(
#endif
              "--core MODULE --system DIR --saves DIR --content DISK_OR_M3U\n"
              "--frames N (1..36000) --headless --mute --ram-mb 2|4\n"
              "--report JSON --capture PPM --trace TSV --input-events FILE\n"
              "--disk-events FILE (frame drive image; -1 ejects)\n"
              "--auto-disk (answer guest disk requests automatically)\n"
              "--video-checks JSON --audio-checks JSON --timing-checks JSON\n"
              "--session-checks JSON --disk-checks JSON (diagnostics then quit)\n"
              "--state-slot FILE --state-save-at FRAME --state-load-at FRAME --state-load-start\n"
              "Arrows: direction; Z/X: buttons; Enter: guest Return\n"
              "F8/F9: save/load; Ctrl+Alt+H: all controls\n"
              "Ctrl+Alt+Q: quit; Ctrl+Alt+Enter: fullscreen"); result=0; goto cleanup;
      } else {
         const char *arg=argv[i]; char *end=NULL;
         if(++i>=(unsigned)argc) { fail("Missing argument"); goto cleanup; }
         if(!strcmp(arg,"--frames")) { unsigned long n=strtoul(argv[i],&end,10); if(!*argv[i] || *end || n==0 || n>MAX_FRAMES) { fail("Invalid frame limit"); goto cleanup; } frames=(unsigned)n; }
         else if(!strcmp(arg,"--ram-mb")) { if(strcmp(argv[i],"2") && strcmp(argv[i],"4")) { fail("RAM must be 2 or 4 MiB"); goto cleanup; } ram_megabytes=(unsigned)atoi(argv[i]); }
         else if(!strcmp(arg,"--input-events")) events_path=argv[i];
         else if(!strcmp(arg,"--disk-events")) disk_events_path=argv[i];
         else if(!strcmp(arg,"--video-checks")) video_checks_path=argv[i];
         else if(!strcmp(arg,"--audio-checks")) audio_checks_path=argv[i];
         else if(!strcmp(arg,"--timing-checks")) timing_checks_path=argv[i];
         else if(!strcmp(arg,"--session-checks")) session_checks_path=argv[i];
         else if(!strcmp(arg,"--disk-checks")) disk_checks_path=argv[i];
         else if(!strcmp(arg,"--state-save-at")||!strcmp(arg,"--state-load-at")) {
            unsigned long n=strtoul(argv[i],&end,10);if(!*argv[i]||*end||n>=MAX_FRAMES){fail("Invalid state action frame");goto cleanup;}
            if(!strcmp(arg,"--state-save-at"))save_at=(unsigned)n;else load_at=(unsigned)n;
         }
#ifdef RR_X68000_DEVCPU
         else if(!strcmp(arg,"--observations")) observations_path=argv[i];
         else if(!strcmp(arg,"--instruction-trace")) instruction_trace_path=argv[i];
         else if(!strcmp(arg,"--guard-checks")) guard_checks_path=argv[i];
#endif
         else {
            char *dst=NULL;
#ifdef RR_X68000_LINKED
            if(!strcmp(arg,"--core")||!strcmp(arg,"--content")||!strcmp(arg,"--system")||!strcmp(arg,"--saves")){fail("An embedded game cannot load external firmware or media");goto cleanup;}
#endif
            if(!strcmp(arg,"--core")) dst=core_path; else if(!strcmp(arg,"--system")) dst=system_dir;
            else if(!strcmp(arg,"--saves")) dst=saves_dir; else if(!strcmp(arg,"--content")) dst=content;
            else if(!strcmp(arg,"--report")){dst=report;report_requested=true;} else if(!strcmp(arg,"--capture")) dst=capture_path;
            else if(!strcmp(arg,"--trace")) dst=trace_path;
            else if(!strcmp(arg,"--state-slot")){dst=state_slot;state_slot_requested=true;}
            if(!dst || !copy_path(dst,argv[i])) { fail("Unknown option or overlong path"); goto cleanup; }
         }
      }
   }
   if(headless && !frames) { fail("Headless mode requires a bounded --frames"); goto cleanup; }
#ifdef RR_X68000_LINKED
   {char game_dir[PATH_CAP];
    if(!rr_x68k_payload_prepare(base_path,game_dir,sizeof(game_dir))){fail("Cannot prepare private game data (linked path, changed firmware, or another running copy)");goto cleanup;}
    snprintf(system_dir,sizeof(system_dir),"%s/system",game_dir);snprintf(saves_dir,sizeof(saves_dir),"%s/saves",game_dir);
    snprintf(content,sizeof(content),"%s/media/game.m3u",game_dir);if(!state_slot_requested)snprintf(state_slot,sizeof(state_slot),"%s/quick.rrstate",game_dir);
    snprintf(player_config,sizeof(player_config),"%s/player.cfg",game_dir);snprintf(media_config,sizeof(media_config),"%s/media-session.bin",game_dir);
    if(!report_requested)report[0]=0;
    copy_path(source_identity,RR_X68K_SOURCE_IDENTITY);
    ram_megabytes=RR_X68K_RAM_MIB;
#ifdef RR_X68K_MOUSE_GAME
   mouse_game=RR_X68K_MOUSE_GAME!=0;
#endif
#ifdef RR_X68K_AUTO_DISK
   auto_disk=RR_X68K_AUTO_DISK!=0;
#endif
   }
#endif
   if(events_path && !load_events(events_path)) { fail("Invalid input event file"); goto cleanup; }
   if(disk_events_path&&!load_disk_events(disk_events_path)){fail("Invalid disk event file");goto cleanup;}
   copy_path(content_dir,content);
   { char *a=strrchr(content_dir,'/'),*b=strrchr(content_dir,'\\'); char *p=a?(b && b>a?b:a):b; if(!p) strcpy(content_dir,"."); else *p=0; }
   if(!headless) {
      if(SDL_InitSubSystem(SDL_INIT_VIDEO|SDL_INIT_GAMECONTROLLER|SDL_INIT_AUDIO)!=0) { fail(SDL_GetError()); goto cleanup; }
      SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY,"0");
      window=SDL_CreateWindow(
#ifdef RR_X68000_DEVCPU
          RR_X68K_GAME_TITLE " | Sharp X68000 | Starting",
#else
          "Cho Ren Sha 68k | X68000 reference | Interpreter CPU",
#endif
          SDL_WINDOWPOS_CENTERED,SDL_WINDOWPOS_CENTERED,768,576,SDL_WINDOW_RESIZABLE|SDL_WINDOW_ALLOW_HIGHDPI);
      if(!window) { fail(SDL_GetError()); goto cleanup; }
      renderer=SDL_CreateRenderer(window,-1,SDL_RENDERER_ACCELERATED|SDL_RENDERER_PRESENTVSYNC);
      if(!renderer) renderer=SDL_CreateRenderer(window,-1,SDL_RENDERER_SOFTWARE);
      if(!renderer) { fail(SDL_GetError()); goto cleanup; }
      for(i=0;i<(unsigned)SDL_NumJoysticks();i++) add_controller((int)i);
      SDL_SetWindowMinimumSize(window,400,340);player_load();
      if(!player_init()){fail("Cannot initialize shared player menus");goto cleanup;}
      if(mouse_game){mouse_grab=true;SDL_SetRelativeMouseMode(SDL_TRUE);notify("Mouse controls: Ctrl+Alt+M releases the mouse");}
#ifdef RR_X68000_LINKED
      rr_set_window_icon(window);
#endif
      if(!mute) {
         SDL_AudioSpec want,got; SDL_zero(want); want.freq=44100; want.format=AUDIO_S16SYS; want.channels=2; want.samples=512;
         audio_device=SDL_OpenAudioDevice(NULL,0,&want,&got,0);
         if(!audio_device) { fail(SDL_GetError()); goto cleanup; }
         /* Stays paused until player_queue_audio has primed the queue. */
         player_audio_period=got.samples?got.samples:512u;
      }
   }
#ifndef RR_X68000_LINKED
   module=SDL_LoadObject(core_path); if(!module) { fail(SDL_GetError()); goto cleanup; }
#else
   rr_feedback_start(!headless);
#endif
   LOAD(set_environment,"retro_set_environment"); LOAD(set_video_refresh,"retro_set_video_refresh");
   LOAD(set_audio_sample,"retro_set_audio_sample"); LOAD(set_audio_sample_batch,"retro_set_audio_sample_batch");
   LOAD(set_input_poll,"retro_set_input_poll"); LOAD(set_input_state,"retro_set_input_state");
   LOAD(init,"retro_init"); LOAD(deinit,"retro_deinit"); LOAD(run,"retro_run"); LOAD(reset,"retro_reset");
   LOAD(load_game,"retro_load_game"); LOAD(unload_game,"retro_unload_game");
   LOAD(get_system_av_info,"retro_get_system_av_info"); LOAD(get_memory_data,"retro_get_memory_data"); LOAD(get_memory_size,"retro_get_memory_size");
   LOAD(set_controller_port_device,"retro_set_controller_port_device");
   LOAD(get_cpu,"rr_x68k_get_cpu"); LOAD(set_clock,"rr_x68k_set_clock");
   LOAD(hardware_snapshot,"rr_x68k_hardware_snapshot");
   LOAD(video_checks,"rr_x68k_video_checks"); LOAD(audio_checks,"rr_x68k_audio_checks");
   LOAD(timing_checks,"rr_x68k_timing_checks");
   LOAD(session_checks,"rr_x68k_session_checks");LOAD(disk_checks,"rr_x68k_disk_checks");
   LOAD(serialize_size,"retro_serialize_size");LOAD(serialize,"retro_serialize");LOAD(unserialize,"retro_unserialize");
   LOAD(state_compatibility,"rr_x68k_state_compatibility");LOAD(framebuffer,"rr_x68k_framebuffer");
   LOAD(media_ready,"rr_x68000_media_ready");
   LOAD(media_activity,"rr_x68000_media_activity");
   LOAD(media_interest,"rr_x68000_media_interest");
#ifdef RR_X68000_DEVCPU
   LOAD(cpu_configure,"rr_x68k_cpu_configure");LOAD(cpu_report,"rr_x68k_cpu_report");
   LOAD(cpu_stats,"rr_x68k_cpu_stats");
   LOAD(trace_configure,"rr_x68k_trace_configure");LOAD(trace_report,"rr_x68k_trace_report");
   LOAD(guard_checks,"rr_x68k_guard_checks");
   if(!core.cpu_configure(reference_cpu,observations_path!=NULL)) {fail("CPU configuration rejected");goto cleanup;}
   if(!core.trace_configure(instruction_trace_path?1000000:0)) {fail("CPU trace allocation failed");goto cleanup;}
#endif
   core.set_environment(environment); core.set_video_refresh(video); core.set_audio_sample(audio_sample);
   core.set_audio_sample_batch(audio_batch); core.set_input_poll(input_poll); core.set_input_state(input_state);
   core.set_clock(0); core.init(); initialized=true;
   { struct retro_game_info game={0}; game.path=content; loaded=core.load_game(&game); }
   if(!loaded) { fail("Core rejected the content"); goto cleanup; }
   media_log_seen=core.media_ready();
   core.set_controller_port_device(0,RETRO_DEVICE_JOYPAD);
   core.set_controller_port_device(1,RETRO_DEVICE_JOYPAD);
   { struct retro_system_av_info av; core.get_system_av_info(&av); fps=av.timing.fps; sample_rate=av.timing.sample_rate;
     if(isfinite(av.geometry.aspect_ratio) && av.geometry.aspect_ratio>0.1 && av.geometry.aspect_ratio<10.0) aspect_ratio=av.geometry.aspect_ratio;
   }
   if(!isfinite(fps) || fps<20 || fps>120 || sample_rate!=44100) { fail("Invalid initial AV timing"); goto cleanup; }
   hash_video=trace_path[0] || report[0]; keep_pixels=hash_video || capture_path[0] || renderer;
   if(trace_path[0]) { records=(FrameRecord *)calloc(frames?frames:MAX_FRAMES,sizeof(*records)); if(!records) { fail("Trace allocation failed"); goto cleanup; } }
   frequency=(double)SDL_GetPerformanceFrequency(); wall_start=(double)SDL_GetPerformanceCounter()/frequency; deadline=wall_start;
   for(frame_number=0;!quit_requested && (!frames || frame_number<frames);) {
      bool restored_start=false;
      uint64_t before=(uint64_t)elapsed_usec,ram_hash=0; size_t ram_size;
      input_poll();if(quit_requested)break;
      {bool accelerate=player_fast_forward()!=0;
       if(accelerate!=fast_forward){fast_forward=accelerate;deadline=(double)SDL_GetPerformanceCounter()/frequency;
          if(audio_device){SDL_PauseAudioDevice(audio_device,1);SDL_ClearQueuedAudio(audio_device);player_audio_primed=0;}
          rr_options_audio_reset();}}
      if(player_ui.want_reset){core.reset();player_ui.want_reset=0;
         if(media_opened&&!rr_media_boot(&media)){fail(rr_media_error(&media));break;}
         automatic_loading=false;memset(&loading_detector,0,sizeof(loading_detector));player_pause_audio();}
      if(player_blocked()){
         if(last_pixels&&width&&height)player_present(last_pixels,width,height,(size_t)width*(pixel_format==RETRO_PIXEL_FORMAT_RGB565?2:4));
         else{SDL_SetRenderDrawColor(renderer,0,0,0,255);SDL_RenderClear(renderer);player_overlay();SDL_RenderPresent(renderer);}
         SDL_Delay(10);polled_frame=UINT64_MAX;deadline=(double)SDL_GetPerformanceCounter()/frequency;continue;
      }
      elapsed_usec+=1000000.0/fps;
      /* The peripheral tick ledger owns RTC time. The frontend interval only
       * drives the core's frame callback; never move RTC ahead then back. */
      if(frame_time.callback) frame_time.callback((retro_usec_t)((uint64_t)elapsed_usec-before));
      media_log_scan(true);
      frame_pcm=FNV_START; frame_samples=0; core.run(); completed++;input_frame++;
      media_log_scan(false);
      automatic_loading=rr_loading_update(&loading_detector,core.media_activity(),video_hash)!=0;
      if(automatic_loading)loading_candidate_frames++;
      if(fast_forward)accelerated_frames++;
      if(loading_holdoff)loading_holdoff--;
      core.hardware_snapshot(hardware);
      if(hardware[5]) fail("Guest audio batch exceeded its validated bound; no PCM was discarded");
#ifdef RR_X68000_DEVCPU
      core.cpu_stats(cpu_stats);
      if(window && frame_number%30==0)SDL_SetWindowTitle(window,
         cpu_stats[2]+cpu_stats[3]?RR_X68K_GAME_TITLE " | Sharp X68000 | Native code + Interpreter fallback":
         cpu_stats[0]+cpu_stats[1]?RR_X68K_GAME_TITLE " | Sharp X68000 | Native code":
         RR_X68K_GAME_TITLE " | Sharp X68000 | Starting");
#endif
      if(records && frame_number<MAX_FRAMES) {
         FrameRecord *r=&records[frame_number]; r->video=video_hash; r->pcm=frame_pcm; r->samples=frame_samples; r->width=width; r->height=height;
         memcpy(r->hardware,hardware,sizeof(hardware));
         core.get_cpu(r->regs); ram_size=core.get_memory_size(RETRO_MEMORY_SYSTEM_RAM);
         if(core.get_memory_data(RETRO_MEMORY_SYSTEM_RAM) && ram_size>=ram_megabytes*1024*1024 && ram_size<=12*1024*1024) ram_hash=hash_bytes(FNV_START,core.get_memory_data(RETRO_MEMORY_SYSTEM_RAM),ram_megabytes*1024*1024);
         r->ram=ram_hash;
      }
      if(frame_number%300==0) { uint32_t regs[18]; core.get_cpu(regs); fprintf(stdout,"frame=%u pc=%06x video=%ux%u samples=%" PRIu64 "\n",frame_number,regs[0],width,height,total_samples); fflush(stdout); }
      if(core_error) { quit_requested=true; break; }
      /* pre_main initializes the controllers inside the first retro_run.
       * Restore drive choices only after that initialization has completed. */
      if(!media_opened){
         media_opened=rr_media_open(&media,content,media_config,&disk_callbacks,select_drive,core.media_ready)!=0;
         if(!media_opened){fail(rr_media_error(&media));break;}
         rr_media_set_interest(&media,core.media_interest);
#ifndef RR_X68000_LINKED
         /* Standalone games cold-boot their original pair. Their last data
          * disk belongs to F9, not to the next boot; keep the diagnostic
          * reference host's explicit media-session behaviour separate. */
         if(!rr_media_load_session(&media))notify(rr_media_error(&media));
#endif
         if(load_start){if(snapshot(true)!=RR_STATE_OK&&headless){fail("Requested startup state rejected");break;}load_start=false;restored_start=true;}
      }
      if(want_swap||want_eject){
         int ok=want_eject?rr_media_swap(&media,swap_drive,-1):rr_media_cycle(&media,swap_drive,swap_direction);
         if(ok){char message[128];swapped_count++;snprintf(message,sizeof(message),"FDD%u: %s",swap_drive,media.selected[swap_drive]<0?"empty":media.names[media.selected[swap_drive]]);notify(message);}
         else notify(rr_media_error(&media));
         want_swap=want_eject=false;
      }
      /* The initialization frame ran before the restored snapshot. It must
       * not consume a removal tick belonging to the restored machine. */
      if(auto_disk&&!restored_start){
         int changed=rr_media_auto_advance(&media);
         if(changed<0){fail(rr_media_error(&media));break;}
         if(changed){auto_disk_changes+=(unsigned)changed;notify("Next disk inserted automatically");}
      }
      for(i=0;i<disk_event_count;i++)if(disk_events[i].frame==frame_number){
         if(!rr_media_swap(&media,disk_events[i].drive,disk_events[i].image)){fail(rr_media_error(&media));break;}
         swapped_count++;
      }
      if(core_error)break;
      if(want_save||frame_number==save_at){want_save=false;if(snapshot(false)!=RR_STATE_OK&&headless){fail("Requested save failed");break;}}
      if(want_load||frame_number==load_at){want_load=false;if(snapshot(true)!=RR_STATE_OK&&headless){fail("Requested load failed");break;}deadline=(double)SDL_GetPerformanceCounter()/frequency;}
      if(!headless&&!fast_forward) {
         double now; deadline+=1.0/fps; now=(double)SDL_GetPerformanceCounter()/frequency;
         if(now<deadline) SDL_Delay((Uint32)((deadline-now)*1000));
         else if(now-deadline>0.25) deadline=now;
         /* A display-rate mismatch or a brief stall must not terminate a
          * working game. Retain every PCM pair and drain the queue while
          * continuing to service menus/quit; menus themselves clear it. */
         /* Drain bounds follow the adaptive start target. */
         Uint32 drain_high=SDL_max(44100u*4u*120u/1000u,player_audio_target()+44100u*4u*40u/1000u);
         Uint32 drain_low=SDL_max(44100u*4u*80u/1000u,player_audio_target()+44100u*4u*10u/1000u);
         if(audio_device&&SDL_GetQueuedAudioSize(audio_device)>drain_high){
            do{polled_frame=UINT64_MAX;input_poll();if(quit_requested||player_blocked())break;SDL_Delay(1);}
            while(SDL_GetQueuedAudioSize(audio_device)>drain_low);
            deadline=(double)SDL_GetPerformanceCounter()/frequency;
         }
      }
      media_log_scan(true);
      frame_number++;
   }
   if(report[0]){ uint32_t regs[18]; FILE *f; size_t ram_size=core.get_memory_size(RETRO_MEMORY_SYSTEM_RAM); uint64_t ram_hash=0;
     core.get_cpu(regs);
     if(core.get_memory_data(RETRO_MEMORY_SYSTEM_RAM) && ram_size>=ram_megabytes*1024*1024 && ram_size<=12*1024*1024) ram_hash=hash_bytes(FNV_START,core.get_memory_data(RETRO_MEMORY_SYSTEM_RAM),ram_megabytes*1024*1024);
     f=fopen(report,"wb"); if(!f) { fail("Cannot write report"); goto cleanup; }
#ifdef RR_X68000_DEVCPU
     core.cpu_stats(cpu_stats);
     fprintf(f,"{\n  \"schema\":1,\"mode\":\"%s\",\"native_cpu\":%s,\n",
       reference_cpu?"interpreted-reference":"guarded-native-prototype",cpu_stats[0]+cpu_stats[1]?"true":"false");
     fprintf(f,"  \"native_ram\":%" PRIu64 ",\"native_ipl\":%" PRIu64 ",\"reference_ram\":%" PRIu64 ",\"reference_ipl\":%" PRIu64 ",\n",
       cpu_stats[0],cpu_stats[1],cpu_stats[2],cpu_stats[3]);
     fprintf(f,"  \"cpu_mhz\":10,\"ram_mib\":%u,\"fixed_rtc_epoch\":946684800,\n",ram_megabytes);
#else
     fprintf(f,"{\n  \"schema\": 1, \"mode\": \"interpreted-reference\", \"native_cpu\": false,\n  \"cpu_mhz\": 10, \"ram_mib\": %u, \"fixed_rtc_epoch\": 946684800,\n",ram_megabytes);
#endif
     fprintf(f,"  \"frames\": %u, \"video_frames\": %u, \"nonblack_frames\": %u,\n  \"width\": %u, \"height\": %u, \"fps\": %.9f, \"sample_rate\": %.1f,\n",completed,video_frames,nonblack_frames,width,height,fps,sample_rate);
     fprintf(f,"  \"geometry_changes\": %u, \"audio_samples\": %" PRIu64 ", \"nonzero_samples\": %" PRIu64 ",\n  \"final_video_fnv64\": \"%016" PRIx64 "\", \"pcm_fnv64\": \"%016" PRIx64 "\", \"ram_fnv64\": \"%016" PRIx64 "\",\n",geometry_changes,total_samples,nonzero_samples,video_hash,total_pcm,ram_hash);
     fprintf(f,"  \"hardware\": {\"frames\":%" PRIu64 ",\"cpu_cycles\":%" PRIu64 ",\"peripheral_ticks\":%" PRIu64 ",\"lines\":%" PRIu64 ",\"audio_pairs\":%" PRIu64 ",\"audio_errors\":%" PRIu64 ",\"max_audio_batch\":%" PRIu64 ",\"last_frame_budget\":%" PRIu64 "},\n",
       hardware[0],hardware[1],hardware[2],hardware[3],hardware[4],hardware[5],hardware[6],hardware[7]);
     fprintf(f,"  \"session\": {\"saved\":%u,\"loaded\":%u,\"rejected\":%u,\"disk_changes\":%u},\n",saved_count,loaded_count,rejected_count,swapped_count);
     fprintf(f,"  \"automatic_disk_changes\":%u,\n",auto_disk_changes);
     fprintf(f,"  \"media_empty_polls\":[%u,%u],\"media_events_dropped\":%u,\"media_events\":[",media_empty_polls[0],media_empty_polls[1],media_log_dropped);
     for(i=0;i<media_log_count;i++)fprintf(f,"%s[%u,%u,\"%s\",%d]",i?",":"",media_log[i].frame,media_log[i].drive,media_log_kinds[media_log[i].kind],media_log[i].image);
     fprintf(f,"],\n");
     fprintf(f,"  \"loading\":{\"waiting_transfer_frames\":%u,\"accelerated_frames\":%u},\n",
       loading_candidate_frames,accelerated_frames);
     /* Explicit end-report only: inspect guest eject/blink requests without
      * writing during play or embedding private media paths in diagnostics. */
     fprintf(f,"  \"media\":{\"selected\":[%d,%d],\"ready_mask\":%u},\n",
       media_opened?media.selected[0]:-1,media_opened?media.selected[1]:-1,
       media_opened?core.media_ready():0);
     fprintf(f,"  \"cpu\": ["); for(i=0;i<18;i++) fprintf(f,"%s%u",i?", ":"",regs[i]);
     fprintf(f,"],\n  \"core_error\": %s, \"wall_seconds\": %.6f\n}\n",core_error?"true":"false",(double)SDL_GetPerformanceCounter()/frequency-wall_start); fclose(f);
   }
   if(records) {
      FILE *f=fopen(trace_path,"wb"); if(!f) { fail("Cannot write trace"); goto cleanup; }
      fputs("frame\tvideo\tpcm\tram\tsamples\twidth\theight\tPC\tSR\tD0\tD1\tD2\tD3\tD4\tD5\tD6\tD7\tA0\tA1\tA2\tA3\tA4\tA5\tA6\tA7\tguest_frames\tcpu_cycles\tperipheral_ticks\tlines\taudio_pairs\taudio_errors\tmax_audio_batch\tframe_budget\n",f);
      for(i=0;i<completed && i<MAX_FRAMES;i++) { unsigned j; FrameRecord *r=&records[i];
         fprintf(f,"%u\t%016" PRIx64 "\t%016" PRIx64 "\t%016" PRIx64 "\t%u\t%u\t%u",i,r->video,r->pcm,r->ram,r->samples,r->width,r->height);
         for(j=0;j<18;j++) fprintf(f,"\t%08x",r->regs[j]);
         for(j=0;j<8;j++) fprintf(f,"\t%" PRIu64,r->hardware[j]); fputc('\n',f);
      } fclose(f);
   }
   if(capture_path[0] && !capture(capture_path)) { fail("Capture failed"); goto cleanup; }
#ifdef RR_X68000_DEVCPU
   if(observations_path && !core.cpu_report(observations_path)) {fail("CPU observation write failed");goto cleanup;}
   if(instruction_trace_path && !core.trace_report(instruction_trace_path)) {fail("CPU trace write failed");goto cleanup;}
   if(guard_checks_path) {
      unsigned checks=core.guard_checks();FILE *f=fopen(guard_checks_path,"wb");
      if(!f) {fail("Cannot write guard checks");goto cleanup;}
      fprintf(f,"{\"passed\":%s,\"checks\":%u,\"expected\":1048575}\n",checks==1048575?"true":"false",checks);fclose(f);
      if(checks!=1048575) {fail("CPU/RAM guard check failed");goto cleanup;}
   }
#endif
   if(video_checks_path && core.video_checks(video_checks_path)!=RR_X68K_VIDEO_EXPECTED) fail("Video hardware checks failed");
   if(timing_checks_path && core.timing_checks(timing_checks_path)!=RR_X68K_TIMING_EXPECTED) fail("Timing hardware checks failed");
   if(audio_checks_path && core.audio_checks(audio_checks_path)!=RR_X68K_AUDIO_EXPECTED) fail("Audio hardware checks failed");
   if(session_checks_path && core.session_checks(session_checks_path)!=RR_X68K_SESSION_EXPECTED) fail("Session hardware checks failed");
   if(disk_checks_path && core.disk_checks(disk_checks_path)!=511) fail("Disk hardware checks failed");
   result=core_error || !video_frames?1:0;
cleanup:
   if(media_opened&&!rr_media_save_session(&media)){fprintf(stderr,"X68000 media: %s\n",rr_media_error(&media));result=1;}
   if(player_ui.ready){player_store(L"guest_keyboard",guest_keyboard);player_store(L"autofire",autofire);}
   player_save();
#ifdef RR_X68000_LINKED
   rr_feedback_close_screen(renderer);
#endif
   if(loaded) core.unload_game(); if(initialized) core.deinit(); if(module) SDL_UnloadObject(module);
   if(audio_device)fprintf(stderr,"[player] audio reserve=+%d ms (raised %d times); physical latency unmeasured\n",
      rr_cushion_ms(&player_cushion),SDL_AtomicGet(&player_cushion.raises));
   if(audio_device) SDL_CloseAudioDevice(audio_device);for(i=0;i<2;i++)if(controllers[i])SDL_GameControllerClose(controllers[i]);
   player_shutdown();
#ifdef RR_X68000_LINKED
   rr_x68k_payload_release();
#endif
   if(texture) SDL_DestroyTexture(texture); if(renderer) SDL_DestroyRenderer(renderer); if(window) SDL_DestroyWindow(window);
   if(player_config[0]&&!headless){char name[PATH_CAP];
      int n=snprintf(name,sizeof(name),"%s.last-run.txt",player_config);
      if(n>0&&(size_t)n<sizeof(name)){FILE*f=fopen(name,"wb");if(f){
         fprintf(f,"frames=%u\ncore_error=%d\nexit=%d\nerror=%s\n",completed,core_error?1:0,result,last_error);fclose(f);}}}
   free(last_pixels); free(records); SDL_Quit(); return result;
}
int main(int argc,char **argv) {
#ifdef _WIN32
   /* MSVC's narrow argv uses the ANSI code page. The rest of the frontend,
    * SDL and private path API use UTF-8, including validation output paths. */
   int count=0,result=2;LPWSTR *wide=CommandLineToArgvW(GetCommandLineW(),&count);
   if(!wide||count<1){if(wide)LocalFree(wide);return 2;}
   char **utf8=calloc((size_t)count+1,sizeof(*utf8));if(!utf8){LocalFree(wide);return 2;}
   for(int n=0;n<count;n++){
      int size=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[n],-1,NULL,0,NULL,NULL);
      if(!size||!(utf8[n]=malloc((size_t)size))||!WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[n],-1,utf8[n],size,NULL,NULL))goto arguments_done;
   }
   result=player_main(count,utf8);
arguments_done:
   for(int n=0;n<count;n++)free(utf8[n]);free(utf8);LocalFree(wide);return result;
#else
   return player_main(argc,argv);
#endif
}
