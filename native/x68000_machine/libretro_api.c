/* Retro-Recomp X68000 MIT host glue: libretro entry points used by our host.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * Independently written from docs/X68000_GLUE_SPEC.md sections 1-6. The
 * libretro.h API header is MIT. No code from libretro.c is used.
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "glue.h"
#include "winx68k.h"
#include "prop.h"
#include "winui.h"
#include "windraw.h"
#include "dswin.h"
#include "mouse.h"
#include "joystick.h"
#include "timer.h"
#include "dosio.h"
#include "../m68000/m68000.h"
#ifdef RR_X68000_BASE74
#include "memory.h"
#else
#include "../x68k/x68kmemory.h"
#endif
#include "../x68k/adpcm.h"
#include "../x68k/fdd.h"
#include "../x68k/midi.h"
#include "../x68k/sram.h"
#include "../fmgen/fmg_wrap.h"
#include "../x68k/crtc.h"
#include "hardware_clock.h"

#ifdef _WIN32
#define RR_SLASH "\\"
#define RR_SLASH_CHAR '\\'
#else
#define RR_SLASH "/"
#define RR_SLASH_CHAR '/'
#endif

/* ---- Globals named by the machine sources (spec section 7) ---- */
retro_log_printf_t log_cb = NULL;
retro_input_state_t input_state_cb = NULL;
retro_audio_sample_t audio_cb = NULL;
retro_audio_sample_batch_t audio_batch_cb = NULL;
uint32_t libretro_supports_input_bitmasks = 0;
unsigned int total_usec = 0xffffffffu;
struct retro_vfs_interface_info vfs_iface_info;
char base_dir[MAX_PATH];
uint32_t retrow = 800, retroh = 600;

/* The machine renders into an 800x600 buffer (windraw.c ScrBuf) while the
 * CRTC can briefly report larger modes (Metal Sight: 512x1072 for one frame).
 * Present only what exists; the machine's own geometry stays unchanged. */
#define RR_SCREEN_WIDTH 800u
#define RR_SCREEN_HEIGHT 600u
static unsigned presented_width(void) { return retrow < RR_SCREEN_WIDTH ? retrow : RR_SCREEN_WIDTH; }
static unsigned presented_height(void) { return retroh < RR_SCREEN_HEIGHT ? retroh : RR_SCREEN_HEIGHT; }
uint16_t *videoBuffer = NULL;

retro_environment_t rr_glue_environ = NULL;
static retro_video_refresh_t video_cb = NULL;
static retro_input_poll_t input_poll_cb = NULL;

float rr_glue_framerate = 61.46f;
int rr_glue_firstcall = 1;
int rr_glue_cur_drive = 1;
int rr_glue_oldrw = 0, rr_glue_oldrh = 0;
char rr_glue_system_conf[2048];
char rr_glue_browse_conf[2048];

static const float framerates[2][2] = {{61.46f, 55.46f}, {59.94f, 55.5f}};
static int16_t soundbuf[2048];

/* Content: the M3U images and the derived boot arguments. */
static struct {
   unsigned total_images, index;
   bool inserted[2];
   char path[RR_GLUE_MAX_DISKS][MAX_PATH];
} disk;
static bool has_content = false;
static char *boot_argv[3];
static int boot_argc = 0;
static char boot_args[3][MAX_PATH];

/* ---- MIDI output: no frontend MIDI device in this host ---- */
void midi_out_short_msg(size_t msg) { (void)msg; }
void midi_out_long_msg(uint8_t *data, size_t length) { (void)data; (void)length; }
int midi_out_open(void **handle) { (void)handle; return 1; }

/* ---- Core options ---- */

static const char *option(const char *key)
{
   struct retro_variable variable = { key, NULL };
   if (rr_glue_environ && rr_glue_environ(RETRO_ENVIRONMENT_GET_VARIABLE, &variable))
      return variable.value;
   return NULL;
}

static void select_drive_from_option(void)
{
   const char *value = option("px68k_disk_drive");
   if (value)
      rr_glue_cur_drive = strcmp(value, "FDD0") == 0 ? 0 : 1;
}

static int frameskip_value(const char *value)
{
   static const int divisors[] = {2, 3, 4, 5, 6, 8, 16, 32, 60};
   char text[16];
   unsigned i;
   if (!strcmp(value, "Full Frame"))
      return 1;
   if (!strcmp(value, "Auto Frame Skip"))
      return 7;
   for (i = 0; i < sizeof divisors / sizeof divisors[0]; i++) {
      snprintf(text, sizeof text, "1/%d Frame", divisors[i]);
      if (!strcmp(value, text))
         return divisors[i];
   }
   return Config.FrameRate;
}

/* Reads the options in the order the machine expects. Options our host does
 * not provide take the defaults listed in the specification (section 1.3). */
static void update_variables(int running)
{
   const char *value;
   int i;

   if (!running)
      Config.MIDI_SW = 1;
   Config.MIDI_Type = 1;
   for (i = 0; i < 2; i++) {
      if (Config.JOY_TYPE[i] != PAD_2BUTTON) {
         Config.JOY_TYPE[i] = PAD_2BUTTON;
         Joystick_Init();
      }
   }
   if ((value = option("px68k_cpuspeed")) != NULL)
      Config.clockmhz = atoi(value);
   if ((value = option("px68k_ramsize")) != NULL) {
      int megabytes = atoi(value);
      char expected[8];
      snprintf(expected, sizeof expected, "%dMB", megabytes);
      Config.ram_size = (megabytes >= 1 && megabytes <= 12 && !strcmp(value, expected))
         ? megabytes * 1024 * 1024 : 0;
   }
   if (Config.PCM_VOL != 15) {
      Config.PCM_VOL = 15;
      ADPCM_SetVolume((uint8_t)Config.PCM_VOL);
   }
   if (Config.OPM_VOL != 12) {
      Config.OPM_VOL = 12;
      OPM_SetVolume((uint8_t)Config.OPM_VOL);
   }
   select_drive_from_option();
   Config.MenuFontSize = 0;
   Config.joy1_select_mapping = 0;
   if ((value = option("px68k_save_fdd_path")) != NULL)
      Config.save_fdd_path = strcmp(value, "enabled") == 0;
   if ((value = option("px68k_save_hdd_path")) != NULL)
      Config.save_hdd_path = strcmp(value, "enabled") == 0;
   Config.JoyOrMouse = 1;
   Mouse_StartCapture(1);
   Config.VbtnSwap = 0;
   if ((value = option("px68k_no_wait_mode")) != NULL)
      Config.NoWaitMode = strcmp(value, "enabled") == 0;
   if ((value = option("px68k_frameskip")) != NULL)
      Config.FrameRate = (uint8_t)frameskip_value(value);
   if ((value = option("px68k_adjust_frame_rates")) != NULL) {
      int adjusted = strcmp(value, "enabled") == 0;
      if (running)
         CHANGEAV_TIMING |= adjusted != Config.AdjustFrameRates;
      Config.AdjustFrameRates = adjusted;
   }
   if ((value = option("px68k_audio_desync_hack")) != NULL)
      Config.AudioDesyncHack = strcmp(value, "enabled") == 0;
   Debug_Text = Debug_Grp = Debug_Sp = 1;
}

/* ---- Frame time ---- */

static void frame_time(retro_usec_t usec)
{
   total_usec = (unsigned int)((uint64_t)total_usec + (uint64_t)usec);
   if (total_usec == 0xffffffffu)
      total_usec = 0;
}

static void register_frame_time(void)
{
   struct retro_frame_time_callback callback;
   callback.callback = frame_time;
   callback.reference = (retro_usec_t)ceilf(1000000.0f / rr_glue_framerate);
   if (!rr_glue_environ(RETRO_ENVIRONMENT_SET_FRAME_TIME_CALLBACK, &callback))
      total_usec = 0xffffffffu;
   else if (total_usec == 0xffffffffu)
      total_usec = 0;
}

void rr_glue_update_framerate(void)
{
   rr_glue_framerate = framerates[Config.AdjustFrameRates ? 1 : 0][VID_MODE ? 1 : 0];
}

/* ---- Disk control (spec section 4) ---- */

static bool set_eject_state(bool ejected)
{
   select_drive_from_option();
   if (disk.index == disk.total_images)
      return true;
   if (ejected) {
      FDD_EjectFD(rr_glue_cur_drive);
      Config.FDDImage[rr_glue_cur_drive][0] = 0;
   } else {
      strncpy(Config.FDDImage[rr_glue_cur_drive], disk.path[disk.index], MAX_PATH - 1);
      Config.FDDImage[rr_glue_cur_drive][MAX_PATH - 1] = 0;
      FDD_SetFD(rr_glue_cur_drive, Config.FDDImage[rr_glue_cur_drive], 0);
   }
   disk.inserted[rr_glue_cur_drive] = !ejected;
   return true;
}

static bool get_eject_state(void)
{
   select_drive_from_option();
   return !disk.inserted[rr_glue_cur_drive];
}

static unsigned get_image_index(void) { return disk.index; }
static bool set_image_index(unsigned index) { disk.index = index; return true; }
static unsigned get_num_images(void) { return disk.total_images; }

static bool add_image_index(void)
{
   if (disk.total_images >= RR_GLUE_MAX_DISKS)
      return false;
   disk.total_images++;
   return true;
}

static bool replace_image_index(unsigned index, const struct retro_game_info *info)
{
   if (index >= RR_GLUE_MAX_DISKS || !info || !info->path)
      return false;
   strncpy(disk.path[index], info->path, MAX_PATH - 1);
   disk.path[index][MAX_PATH - 1] = 0;
   return true;
}

static void init_disk_control(void)
{
   static struct retro_disk_control_callback callbacks = {
      set_eject_state, get_eject_state, get_image_index, set_image_index,
      get_num_images, replace_image_index, add_image_index
   };
   unsigned version = 0;
   memset(&disk, 0, sizeof disk);
   rr_glue_cur_drive = 1;
   rr_glue_environ(RETRO_ENVIRONMENT_GET_DISK_CONTROL_INTERFACE_VERSION, &version);
   rr_glue_environ(RETRO_ENVIRONMENT_SET_DISK_CONTROL_INTERFACE, &callbacks);
}

/* ---- Content (spec 2.4) ---- */

static bool is_absolute(const char *path)
{
#ifdef _WIN32
   if (((path[0] >= 'A' && path[0] <= 'Z') || (path[0] >= 'a' && path[0] <= 'z')) && path[1] == ':')
      return true;
#endif
   return path[0] == RR_SLASH_CHAR;
}

static bool parse_playlist(const char *path)
{
   char line[MAX_PATH];
   FILE *file = fopen(path, "r");
   if (!file)
      return false;
   disk.total_images = 0;
   while (disk.total_images < RR_GLUE_MAX_DISKS && fgets(line, sizeof line, file)) {
      size_t length;
      char *entry = line, *separator;
      if (line[0] == '#')
         continue;
      line[strcspn(line, "\r")] = 0;
      line[strcspn(line, "\n")] = 0;
      if (entry[0] == '"')
         entry++;
      length = strlen(entry);
      if (length && entry[length - 1] == '"')
         entry[--length] = 0;
      if (!length)
         continue;
      separator = strchr(entry, '|');
      if (separator)
         *separator = 0;
      if (is_absolute(entry))
         snprintf(disk.path[disk.total_images], MAX_PATH, "%s", entry);
      else
         snprintf(disk.path[disk.total_images], MAX_PATH, "%s%s%s", base_dir, RR_SLASH, entry);
      disk.total_images++;
   }
   fclose(file);
   if (!disk.total_images)
      return false;

   /* Boot arguments: the program name and the first one or two images. */
   snprintf(boot_args[0], MAX_PATH, "px68k");
   snprintf(boot_args[1], MAX_PATH, "%s", disk.path[0]);
   boot_argc = 2;
   disk.inserted[0] = true;
   if (disk.total_images >= 2) {
      snprintf(boot_args[2], MAX_PATH, "%s", disk.path[1]);
      boot_argc = 3;
      disk.inserted[1] = true;
   }
   boot_argv[0] = boot_args[0];
   boot_argv[1] = boot_args[1];
   boot_argv[2] = boot_args[2];
   return true;
}

static bool ends_with(const char *text, const char *suffix)
{
   size_t a = strlen(text), b = strlen(suffix);
   return a > 3 && a >= b && !strcmp(text + a - b, suffix);
}

/* ---- Entry points ---- */

void retro_set_environment(retro_environment_t cb)
{
   static const struct retro_controller_description pads[] = {
      { "RetroPad", RETRO_DEVICE_JOYPAD }, { "RetroKeyboard", RETRO_DEVICE_KEYBOARD }
   };
   static const struct retro_controller_info ports[] = {
      { pads, 2 }, { pads, 2 }, { NULL, 0 }
   };
   bool no_game = true;
   unsigned version = 0;
   rr_glue_environ = cb;
   cb(RETRO_ENVIRONMENT_SET_CONTROLLER_INFO, (void *)ports);
   cb(RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME, &no_game);
   cb(RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION, &version);
}

void retro_set_video_refresh(retro_video_refresh_t cb) { video_cb = cb; }
void retro_set_audio_sample(retro_audio_sample_t cb) { audio_cb = cb; }
void retro_set_audio_sample_batch(retro_audio_sample_batch_t cb) { audio_batch_cb = cb; }
void retro_set_input_poll(retro_input_poll_t cb) { input_poll_cb = cb; }
void retro_set_input_state(retro_input_state_t cb) { input_state_cb = cb; }

unsigned retro_api_version(void) { return RETRO_API_VERSION; }
unsigned retro_get_region(void) { return RETRO_REGION_NTSC; }
void retro_cheat_reset(void) {}
void retro_cheat_set(unsigned index, bool enabled, const char *code) { (void)index; (void)enabled; (void)code; }
bool retro_load_game_special(unsigned type, const struct retro_game_info *info, size_t count)
{
   (void)type; (void)info; (void)count;
   return false;
}

void retro_get_system_info(struct retro_system_info *info)
{
   memset(info, 0, sizeof *info);
   info->library_name = "PX68K";
   info->library_version = "0.15+0ad84d7058a1";
   info->need_fullpath = true;
   info->valid_extensions = "dim|img|d88|88d|hdm|dup|2hd|xdf|hdf|cmd|m3u";
   info->block_extract = false;
}

void retro_get_system_av_info(struct retro_system_av_info *info)
{
   memset(info, 0, sizeof *info);
   info->geometry.base_width = presented_width();
   info->geometry.base_height = presented_height();
   info->geometry.max_width = 800;
   info->geometry.max_height = 600;
   info->geometry.aspect_ratio = (float)(4 / 3);
   info->timing.fps = (double)rr_glue_framerate;
   info->timing.sample_rate = RR_GLUE_SAMPLE_RATE;
}

void retro_set_controller_port_device(unsigned port, unsigned device)
{
   (void)port; (void)device;  /* Both joystick ports are always polled. */
}

void retro_init(void)
{
   const char *directory = NULL;
   enum retro_pixel_format format = RETRO_PIXEL_FORMAT_RGB565;
   struct retro_log_callback logging;

   rr_glue_system_conf[0] = 0;
   rr_glue_browse_conf[0] = 0;
   log_cb = rr_glue_environ(RETRO_ENVIRONMENT_GET_LOG_INTERFACE, &logging) ? logging.log : NULL;

   if (!rr_glue_environ(RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY, &directory) || !directory)
      directory = ".";
   snprintf(rr_glue_system_conf, sizeof rr_glue_system_conf, "%s%skeropi", directory, RR_SLASH);
   directory = NULL;
   if (rr_glue_environ(RETRO_ENVIRONMENT_GET_FILE_BROWSER_START_DIRECTORY, &directory) && directory)
      snprintf(rr_glue_browse_conf, sizeof rr_glue_browse_conf, "%s", directory);

   if (!rr_glue_environ(RETRO_ENVIRONMENT_SET_PIXEL_FORMAT, &format))
      return;
   if (rr_glue_environ(RETRO_ENVIRONMENT_GET_INPUT_BITMASKS, NULL))
      libretro_supports_input_bitmasks = 1;
   init_disk_control();

   Config.save_fdd_path = 1;
   Config.clockmhz = 10;
   Config.ram_size = 2 * 1024 * 1024;
   Config.JOY_TYPE[0] = Config.JOY_TYPE[1] = PAD_2BUTTON;
   update_variables(0);
   rr_glue_input_reset();
   rr_glue_update_framerate();
   register_frame_time();
}

bool retro_load_game(const struct retro_game_info *info)
{
   char *slash;

   has_content = false;
   base_dir[0] = 0;
   if (info && info->path) {
      has_content = true;
      snprintf(base_dir, sizeof base_dir, "%s", info->path);
      slash = strrchr(base_dir, '/');
      if (!slash)
         slash = strrchr(base_dir, '\\');
      if (slash)
         *slash = 0;
      else
         base_dir[0] = 0;
      if (!(ends_with(info->path, ".m3u") || ends_with(info->path, ".M3U")) ||
          !parse_playlist(info->path))
         return false;
   }
   if (!has_content)
      return false;

   IPL = (uint8_t *)calloc(1, 0x40000);
   MEM = (uint8_t *)calloc(1, 0xc00000);
   FONT = (uint8_t *)calloc(1, 0xc0000);
   if (!IPL || !MEM || !FONT)
      return false;
#ifdef RR_X68000_BASE74
   if (!OPM_Init(4000000, RR_SOUND_RATE))
#else
   if (!OPM_Init(4000000))
#endif
      return false;
   return true;
}

void retro_unload_game(void)
{
   FDD_Cleanup();
   FDD_Init();
   memset(Config.FDDImage, 0, sizeof Config.FDDImage);
   memset(Config.HDImage, 0, sizeof Config.HDImage);
   rr_glue_firstcall = 1;
   boot_argc = 0;
}

void retro_deinit(void)
{
#ifndef RR_X68000_BASE74
   SRAM_UpdateBoot();
#endif
   OPM_Cleanup();
   Joystick_Cleanup();
   SRAM_Cleanup();
   FDD_Cleanup();
   MIDI_Cleanup();
   free(IPL);
   free(MEM);
   free(FONT);
   IPL = MEM = FONT = NULL;
   WinDraw_Cleanup();
   SaveConfig();
   libretro_supports_input_bitmasks = 0;
}

void retro_reset(void)
{
   WinX68k_Reset();
   if (Config.MIDI_SW && Config.MIDI_Reset)
      MIDI_Reset();
}

static void announce_av_changes(void)
{
   if (!CHANGEAV && !CHANGEAV_TIMING)
      return;
   if (CHANGEAV_TIMING) {
      struct retro_system_av_info av;
      retro_get_system_av_info(&av);
      rr_glue_update_framerate();
      av.timing.fps = (double)rr_glue_framerate;
      rr_glue_environ(RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO, &av);
      register_frame_time();
      CHANGEAV_TIMING = 0;
      CHANGEAV = 0;
   }
   if (CHANGEAV) {
      struct retro_game_geometry geometry;
      memset(&geometry, 0, sizeof geometry);
      geometry.base_width = presented_width();
      geometry.base_height = presented_height();
      geometry.aspect_ratio = (float)(4 / 3);
      rr_glue_environ(RETRO_ENVIRONMENT_SET_GEOMETRY, &geometry);
      CHANGEAV = 0;
   }
}

static void deliver_audio(void)
{
   int pairs = audio_samples_avail();
   if (pairs < 0 || pairs > 1024) {
      rr_x68k_hardware_audio_error();
      pairs = 0;
   }
   if (pairs)
      raudio_callback(soundbuf, NULL, pairs * 4);
   rr_x68k_hardware_audio((unsigned)pairs);
   audio_batch_cb(soundbuf, (size_t)pairs);
}

void retro_run(void)
{
   if (rr_glue_firstcall) {
      if (has_content)
         rr_glue_boot(boot_argc, boot_argv);
      rr_glue_firstcall = 0;
      update_variables(0);
      return;
   }
   announce_av_changes();
   input_poll_cb();
#ifdef RR_X68000_BASE74
   {
      /* The 2014 CRTC does not track the 15/31 kHz mode for the frame rate. */
      int mode = (CRTC_Regs[0x29] & 0x10) ? 1 : 0;
      if (mode != VID_MODE) {
         VID_MODE = mode;
         CHANGEAV_TIMING = 1;
         announce_av_changes();
      }
   }
#else
   FDD_IsReading = 0;
#endif
   if (Config.AudioDesyncHack || Config.NoWaitMode || Timer_GetCount()) {
      Joystick_Update(0, -1, 0);
      Joystick_Update(0, -1, 1);
      rr_glue_exec_frame();
   }
   rr_glue_mouse_frame();
   rr_glue_keyboard_frame();
   deliver_audio();
   video_cb(videoBuffer, presented_width(), presented_height(), RR_SCREEN_WIDTH * 2);
}

void *retro_get_memory_data(unsigned id)
{
   return id == RETRO_MEMORY_SYSTEM_RAM ? MEM : NULL;
}

size_t retro_get_memory_size(unsigned id)
{
   return id == RETRO_MEMORY_SYSTEM_RAM ? 0xc00000 : 0;
}

/* retro_serialize_size/serialize/unserialize: state/snapshot.c (RRX68MS1). */
