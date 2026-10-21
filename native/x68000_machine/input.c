/* Retro-Recomp X68000 MIT host glue: keyboard, mouse and joystick ports.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * Independently written from docs/X68000_GLUE_SPEC.md sections 3.2-3.4 and
 * 6.4. The key table records X68000 keyboard scan codes (hardware facts).
 * No code from libretro.c or libretro/joystick.c is used.
 */
#include <string.h>

#include "glue.h"
#include "prop.h"
#include "keyboard.h"
#include "mouse.h"
#include "joystick.h"
#include "state/rr_state.h"

extern retro_input_state_t input_state_cb;
extern uint32_t libretro_supports_input_bitmasks;

uint8_t Core_Key_State[512];
uint8_t Core_old_Key_State[512];
bool mbL = false, mbR = false;

/* ---- Keyboard (spec 3.2) ---- */

typedef struct { uint16_t key; uint8_t code; } KeyCode;

/* Host key -> X68000 scan code. Order matters: duplicates (two entries for
 * the 0 key, BREAK/PAUSE, both SHIFT/CTRL/ALT keys) each emit their code. */
static const KeyCode main_keys[] = {
   {RETROK_ESCAPE, 0x01}, {RETROK_1, 0x02}, {RETROK_2, 0x03}, {RETROK_3, 0x04},
   {RETROK_4, 0x05}, {RETROK_5, 0x06}, {RETROK_6, 0x07}, {RETROK_7, 0x08},
   {RETROK_8, 0x09}, {RETROK_9, 0x0a}, {RETROK_0, 0x0b}, {RETROK_MINUS, 0x0c},
   {RETROK_EQUALS, 0x0d}, {RETROK_BACKSLASH, 0x0e}, {RETROK_BACKSPACE, 0x0f},
   {RETROK_TAB, 0x10}, {RETROK_q, 0x11}, {RETROK_w, 0x12}, {RETROK_e, 0x13},
   {RETROK_r, 0x14}, {RETROK_t, 0x15}, {RETROK_y, 0x16}, {RETROK_u, 0x17},
   {RETROK_i, 0x18}, {RETROK_o, 0x19}, {RETROK_p, 0x1a}, {RETROK_BACKQUOTE, 0x1b},
   {RETROK_LEFTBRACKET, 0x1c}, {RETROK_RETURN, 0x1d},
   {RETROK_a, 0x1e}, {RETROK_s, 0x1f}, {RETROK_d, 0x20}, {RETROK_f, 0x21},
   {RETROK_g, 0x22}, {RETROK_h, 0x23}, {RETROK_j, 0x24}, {RETROK_k, 0x25},
   {RETROK_l, 0x26}, {RETROK_SEMICOLON, 0x27}, {RETROK_QUOTE, 0x28},
   {RETROK_RIGHTBRACKET, 0x29},
   {RETROK_z, 0x2a}, {RETROK_x, 0x2b}, {RETROK_c, 0x2c}, {RETROK_v, 0x2d},
   {RETROK_b, 0x2e}, {RETROK_n, 0x2f}, {RETROK_m, 0x30}, {RETROK_COMMA, 0x31},
   {RETROK_PERIOD, 0x32}, {RETROK_SLASH, 0x33}, {RETROK_0, 0x34},
   {RETROK_SPACE, 0x35}, {RETROK_HOME, 0x36}, {RETROK_DELETE, 0x37},
   {RETROK_PAGEDOWN, 0x38}, {RETROK_PAGEUP, 0x39}, {RETROK_END, 0x3a},
   {RETROK_LEFT, 0x3b}, {RETROK_UP, 0x3c}, {RETROK_RIGHT, 0x3d}, {RETROK_DOWN, 0x3e},
   {RETROK_CLEAR, 0x3f}, {RETROK_KP_DIVIDE, 0x40}, {RETROK_KP_MULTIPLY, 0x41},
   {RETROK_KP_MINUS, 0x42}, {RETROK_KP7, 0x43}, {RETROK_KP8, 0x44}, {RETROK_KP9, 0x45},
   {RETROK_KP_PLUS, 0x46}, {RETROK_KP4, 0x47}, {RETROK_KP5, 0x48}, {RETROK_KP6, 0x49},
   {RETROK_KP_EQUALS, 0x4a}, {RETROK_KP1, 0x4b}, {RETROK_KP2, 0x4c}, {RETROK_KP3, 0x4d},
   {RETROK_KP_ENTER, 0x4e}, {RETROK_KP0, 0x4f}, {RETROK_KP_PERIOD, 0x51},
   {RETROK_PRINT, 0x52}, {RETROK_SCROLLOCK, 0x53}, {RETROK_F11, 0x54},
   {RETROK_CAPSLOCK, 0x5d}, {RETROK_INSERT, 0x5e}, {RETROK_BREAK, 0x61},
   {RETROK_PAUSE, 0x61},
   {RETROK_F1, 0x63}, {RETROK_F2, 0x64}, {RETROK_F3, 0x65}, {RETROK_F4, 0x66},
   {RETROK_F5, 0x67}, {RETROK_F6, 0x68}, {RETROK_F7, 0x69}, {RETROK_F8, 0x6a},
   {RETROK_F9, 0x6b}, {RETROK_F10, 0x6c},
   {RETROK_LSHIFT, 0x70}, {RETROK_RSHIFT, 0x70}, {RETROK_LCTRL, 0x71},
   {RETROK_RCTRL, 0x71}, {RETROK_LSUPER, 0x72}, {RETROK_RSUPER, 0x73},
   {RETROK_LALT, 0x72}, {RETROK_RALT, 0x73}
};

/* With COMPOSE held, F1-F10 reach the X68000-specific keys instead. */
static const KeyCode compose_keys[] = {
   {RETROK_F1, 0x55}, {RETROK_F2, 0x56}, {RETROK_F3, 0x57}, {RETROK_F4, 0x58},
   {RETROK_F5, 0x59}, {RETROK_F6, 0x5a}, {RETROK_F7, 0x5b}, {RETROK_F8, 0x5c},
   {RETROK_F9, 0x5f}, {RETROK_F10, 0x60}
};

static void key_edge(unsigned index, uint8_t code)
{
   uint8_t now = Core_Key_State[index];
   if (now == Core_old_Key_State[index])
      return;
   send_keycode(code, now ? 2 : 1);
}

void rr_glue_keyboard_frame(void)
{
   unsigned i;
   bool l2, r2;

   for (i = 0; i < 320; i++)
      Core_Key_State[i] = input_state_cb(0, RETRO_DEVICE_KEYBOARD, 0, i) ? 0x80 : 0;
   Core_Key_State[RETROK_XFX] = 0;
   l2 = input_state_cb(0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_L2) != 0;
   r2 = input_state_cb(0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_R2) != 0;
   if (l2)
      Core_Key_State[RETROK_F12] = 0x80;
   if (r2)
      Core_Key_State[RETROK_SCROLLOCK] = 0x80;
   if (Config.joy1_select_mapping &&
       input_state_cb(0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_SELECT))
      Core_Key_State[RETROK_XFX] = 0x80;

   if (memcmp(Core_Key_State, Core_old_Key_State, sizeof Core_Key_State)) {
      /* The configuration menu (F12) is not part of this frontend. */
      if (Core_Key_State[RETROK_COMPOSE]) {
         for (i = 0; i < sizeof compose_keys / sizeof compose_keys[0]; i++)
            key_edge(compose_keys[i].key, compose_keys[i].code);
      } else {
         for (i = 0; i < sizeof main_keys / sizeof main_keys[0]; i++)
            key_edge(main_keys[i].key, main_keys[i].code);
      }
      if (Config.joy1_select_mapping)
         key_edge(RETROK_XFX, (uint8_t)Config.joy1_select_mapping);
   }
   memcpy(Core_old_Key_State, Core_Key_State, sizeof Core_Key_State);
}

/* ---- Mouse (spec 3.3) ---- */

void rr_glue_mouse_frame(void)
{
   int x = input_state_cb(0, RETRO_DEVICE_MOUSE, 0, RETRO_DEVICE_ID_MOUSE_X);
   int y = input_state_cb(0, RETRO_DEVICE_MOUSE, 0, RETRO_DEVICE_ID_MOUSE_Y);
   bool left, right;

   Mouse_Event(0, (float)x, (float)y);
   left = input_state_cb(0, RETRO_DEVICE_MOUSE, 0, RETRO_DEVICE_ID_MOUSE_LEFT) != 0;
   right = input_state_cb(0, RETRO_DEVICE_MOUSE, 0, RETRO_DEVICE_ID_MOUSE_RIGHT) != 0;
   if (!mbL && left) {
      mbL = true;
      Mouse_Event(1, 1.0f, 0);
   } else if (mbL && !left) {
      mbL = false;
      Mouse_Event(1, 0, 0);
   }
   if (!mbR && right) {
      mbR = true;
      Mouse_Event(2, 1.0f, 0);
   } else if (mbR && !right) {
      mbR = false;
      Mouse_Event(2, 0, 0);
   }
}

void rr_glue_input_reset(void)
{
   memset(Core_Key_State, 0, sizeof Core_Key_State);
   memset(Core_old_Key_State, 0, sizeof Core_old_Key_State);
}

/* ---- Joystick ports (spec 3.4) ---- */

uint8_t JoyKeyState = 0;
static uint8_t JoyKeyState0 = 0, JoyKeyState1 = 0;
static uint8_t AnalogState[3];
static uint8_t JoyState[2][2];
static uint8_t JoyPortData[2];
static uint8_t JoyDownState0 = 0;
static int CyberCount = 0;
static int CyberLatency = 3;
static uint8_t pre_ret0 = 0xff;
static int repeat_rate = 0, repeat_delay = 0;
static uint8_t last_inbuf = 0;

#define CYBER_RELOAD 3

void Joystick_Init(void)
{
   JoyKeyState = JoyKeyState0 = JoyKeyState1 = 0;
   memset(JoyState, 0xff, sizeof JoyState);
   JoyPortData[0] = JoyPortData[1] = 0;
   AnalogState[0] = 0x97;
   AnalogState[1] = 0xb7;
   AnalogState[2] = 0x97;
   CyberCount = 0;
   CyberLatency = CYBER_RELOAD;
}

void Joystick_Cleanup(void)
{
}

static uint8_t cyber_read(void)
{
   uint8_t result;
   switch (CyberCount) {
   case 0: result = 0xff; break;
   case 1: result = JoyState[0][0]; break;
   case 2: result = JoyState[0][1]; break;
   case 3: result = (uint8_t)(0x90 | (AnalogState[1] >> 4)); break;
   case 4: result = (uint8_t)(0xb0 | (AnalogState[0] >> 4)); break;
   case 5: result = (uint8_t)(0x90 | (AnalogState[2] >> 4)); break;
   case 6: result = 0xb0; break;
   case 7: result = (uint8_t)(0x90 | (AnalogState[1] & 15)); break;
   case 8: result = (uint8_t)(0xb0 | (AnalogState[0] & 15)); break;
   case 9: result = (uint8_t)(0x90 | (AnalogState[2] & 15)); break;
   case 10: result = 0xb0; break;
   case 11: result = (uint8_t)(0x9f & ~(~JoyState[0][0] & 0x0c)); break;
   case 12: result = 0xbf; break;
   default: result = 0xff; break;
   }
   if (--CyberLatency <= 0) {
      if (CyberCount >= 13) {
         result = 0xff;
      } else {
         CyberCount++;
         CyberLatency = CYBER_RELOAD;
      }
   }
   return result;
}

uint8_t FASTCALL Joystick_Read(uint8_t num)
{
   switch (Config.JOY_TYPE[num]) {
   case PAD_CYBERSTICK_A:
      return num == 0 ? cyber_read() : 0xff;
   case PAD_CPSF_MD:
   case PAD_CPSF_SFC:
   case PAD_CYBERSTICK_D:
      return JoyPortData[num] == 0xff ? JoyState[num][1] : JoyState[num][0];
   case PAD_2BUTTON:
      return JoyPortData[num] == 0xff ? 0xff : JoyState[num][0];
   default:
      return 0xff;
   }
}

void FASTCALL Joystick_Write(uint8_t num, uint8_t data)
{
   switch (Config.JOY_TYPE[num]) {
   case PAD_CYBERSTICK_A:
      if (num == 0 && data == 0 && JoyPortData[0] == 0xff) {
         CyberCount = 0;
         CyberLatency = CYBER_RELOAD;
      }
      JoyPortData[num] = data;
      break;
   case PAD_2BUTTON:
   case PAD_CPSF_MD:
   case PAD_CPSF_SFC:
   case PAD_CYBERSTICK_D:
      JoyPortData[num] = data;
      break;
   default:
      break;
   }
}

static bool held(uint32_t buttons, unsigned id)
{
   return (buttons >> id) & 1;
}

void FASTCALL Joystick_Update(int is_menu, int key, int port)
{
   uint32_t buttons = 0;
   uint16_t temp = 0;
   uint8_t ret0, *out = JoyState[port];
   unsigned i;

   if (libretro_supports_input_bitmasks) {
      buttons = (uint32_t)(int32_t)input_state_cb(port, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_MASK);
   } else {
      for (i = 0; i < 16; i++)
         if (input_state_cb(port, RETRO_DEVICE_JOYPAD, 0, i))
            buttons |= 1u << i;
   }

   if (held(buttons, RETRO_DEVICE_ID_JOYPAD_RIGHT)) temp |= JOY_RIGHT;
   if (held(buttons, RETRO_DEVICE_ID_JOYPAD_LEFT)) temp |= JOY_LEFT;
   if (held(buttons, RETRO_DEVICE_ID_JOYPAD_UP)) temp |= JOY_UP;
   if (held(buttons, RETRO_DEVICE_ID_JOYPAD_DOWN)) temp |= JOY_DOWN;
   if ((temp & (JOY_LEFT | JOY_RIGHT)) == (JOY_LEFT | JOY_RIGHT))
      temp &= (uint16_t)~(JOY_LEFT | JOY_RIGHT);
   if ((temp & (JOY_UP | JOY_DOWN)) == (JOY_UP | JOY_DOWN))
      temp &= (uint16_t)~(JOY_UP | JOY_DOWN);
   if (held(buttons, RETRO_DEVICE_ID_JOYPAD_A)) temp |= Config.VbtnSwap ? JOY_TRG1 : JOY_TRG2;
   if (held(buttons, RETRO_DEVICE_ID_JOYPAD_B)) temp |= Config.VbtnSwap ? JOY_TRG2 : JOY_TRG1;
   if (held(buttons, RETRO_DEVICE_ID_JOYPAD_X)) temp |= Config.VbtnSwap ? JOY_TRG2 : JOY_TRG1;
   if (held(buttons, RETRO_DEVICE_ID_JOYPAD_Y)) temp |= Config.VbtnSwap ? JOY_TRG1 : JOY_TRG2;
   if (held(buttons, RETRO_DEVICE_ID_JOYPAD_START)) temp |= 0xfffc;
   if (!Config.joy1_select_mapping && held(buttons, RETRO_DEVICE_ID_JOYPAD_SELECT)) temp |= 0xfff3;
   ret0 = (uint8_t)(0xff ^ (temp & 0xff));

   out[0] = out[1] = 0xff;
   switch (Config.JOY_TYPE[port]) {
   case PAD_2BUTTON:
      out[0] = ret0;
      break;
   case PAD_CPSF_MD:
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_RIGHT)) out[0] &= ~0x08;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_LEFT)) out[0] &= ~0x04;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_UP)) out[0] &= ~0x01;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_DOWN)) out[0] &= ~0x02;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_A)) out[0] &= ~0x40;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_B)) out[0] &= ~0x20;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_X)) out[1] &= ~0x02;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_Y)) out[1] &= ~0x04;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_L)) out[1] &= ~0x01;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_R)) out[1] &= ~0x20;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_START)) out[1] &= ~0x40;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_SELECT)) out[1] &= ~0x08;
      break;
   case PAD_CPSF_SFC:
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_RIGHT)) out[0] &= ~0x08;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_LEFT)) out[0] &= ~0x04;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_UP)) out[0] &= ~0x01;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_DOWN)) out[0] &= ~0x02;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_A)) out[0] &= ~0x20;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_B)) out[0] &= ~0x40;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_X)) out[1] &= ~0x04;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_Y)) out[1] &= ~0x02;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_L)) out[1] &= ~0x20;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_R)) out[1] &= ~0x01;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_START)) out[1] &= ~0x40;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_SELECT)) out[1] &= ~0x08;
      break;
   case PAD_CYBERSTICK_D:
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_RIGHT)) out[0] &= ~0x08;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_LEFT)) out[0] &= ~0x04;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_UP)) out[0] &= ~0x01;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_DOWN)) out[0] &= ~0x02;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_A)) out[0] &= ~0x20;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_B)) out[0] &= ~0x40;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_START)) out[0] &= ~0x0c;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_SELECT)) out[0] &= ~0x03;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_X)) out[1] &= ~0x04;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_Y)) out[1] &= ~0x08;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_L)) out[1] &= ~0x20;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_R)) out[1] &= ~0x40;
      break;
   case PAD_CYBERSTICK_A: {
      int lx = input_state_cb(port, RETRO_DEVICE_ANALOG, RETRO_DEVICE_INDEX_ANALOG_LEFT, RETRO_DEVICE_ID_ANALOG_X);
      int ly = input_state_cb(port, RETRO_DEVICE_ANALOG, RETRO_DEVICE_INDEX_ANALOG_LEFT, RETRO_DEVICE_ID_ANALOG_Y);
      int ry = input_state_cb(port, RETRO_DEVICE_ANALOG, RETRO_DEVICE_INDEX_ANALOG_RIGHT, RETRO_DEVICE_ID_ANALOG_Y);
      AnalogState[0] = (uint8_t)((lx + 0x8000) >> 8);
      AnalogState[1] = (uint8_t)((ly + 0x8000) >> 8);
      AnalogState[2] = (uint8_t)((-ry + 0x8000) >> 8);
      if (AnalogState[1] < 30) ret0 &= ~JOY_UP;
      else if (AnalogState[1] > 225) ret0 &= ~JOY_DOWN;
      if (AnalogState[0] < 30) ret0 &= ~JOY_LEFT;
      else if (AnalogState[0] > 225) ret0 &= ~JOY_RIGHT;
      out[0] = 0x9f;
      out[1] = 0xbf;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_A)) out[0] &= ~0x08;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_B)) out[0] &= ~0x04;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_X)) out[0] &= ~0x02;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_Y)) out[0] &= ~0x01;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_L)) out[1] &= ~0x08;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_R)) out[1] &= ~0x04;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_START)) out[1] &= ~0x02;
      if (held(buttons, RETRO_DEVICE_ID_JOYPAD_SELECT)) out[1] &= ~0x01;
      break;
   }
   default:
      break;
   }

   JoyDownState0 = (uint8_t)((~(ret0 ^ pre_ret0) | ret0) & 0xff);
   pre_ret0 = ret0;

   if (is_menu) {
      /* Repeat handling for the frontend menu only (not reachable here). */
      uint8_t inbuf = (uint8_t)((ret0 ^ 0xff) | key);
      if ((inbuf & (JOY_LEFT | JOY_RIGHT)) == (JOY_LEFT | JOY_RIGHT))
         inbuf &= (uint8_t)~(JOY_LEFT | JOY_RIGHT);
      if ((inbuf & (JOY_UP | JOY_DOWN)) == (JOY_UP | JOY_DOWN))
         inbuf &= (uint8_t)~(JOY_UP | JOY_DOWN);
      if (inbuf != last_inbuf) {
         last_inbuf = inbuf;
         repeat_delay = 30;
         repeat_rate = 0;
         JoyDownState0 = (uint8_t)(inbuf ^ 0xff);
      } else if (repeat_delay) {
         repeat_delay--;
      } else if (repeat_rate) {
         repeat_rate--;
      } else {
         repeat_rate = 3;
         for (i = 0; i < 4; i++)
            if (inbuf & (1u << i))
               JoyDownState0 &= (uint8_t)~(1u << i);
      }
   } else {
      (void)Keyboard_IsSwKeyboard();
   }
}

uint8_t get_joy_downstate(void)
{
   return JoyDownState0;
}

void reset_joy_downstate(void)
{
   JoyDownState0 = 0xff;
}

/* Snapshot section INPT: host key edges, mouse buttons and joystick ports. */
void rr_state_input(RRState *s)
{
   rr_state_bytes(s, Core_Key_State, sizeof Core_Key_State);
   rr_state_bytes(s, Core_old_Key_State, sizeof Core_old_Key_State);
   rr_state_cbool(s, &mbL);
   rr_state_cbool(s, &mbR);
   rr_state_u8(s, &JoyKeyState);
   rr_state_u8(s, &JoyKeyState0);
   rr_state_u8(s, &JoyKeyState1);
   rr_state_bytes(s, AnalogState, sizeof AnalogState);
   rr_state_bytes(s, JoyState, sizeof JoyState);
   rr_state_bytes(s, JoyPortData, sizeof JoyPortData);
   rr_state_u8(s, &JoyDownState0);
   rr_state_int(s, &CyberCount);
   rr_state_int(s, &CyberLatency);
   rr_state_u8(s, &pre_ret0);
   rr_state_int(s, &repeat_rate);
   rr_state_int(s, &repeat_delay);
   rr_state_u8(s, &last_inbuf);
}
