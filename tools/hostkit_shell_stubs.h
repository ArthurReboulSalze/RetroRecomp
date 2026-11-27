/* The host kit shell around its input module, for the checks that compile rrhk_input.c (and an adapter) without the rest
 * of the shell: tools/autofire_selftest.py and tools/neogeo_controls_selftest.py. No menu is open, no options page is drawn,
 * no multiplayer session runs, no look is chosen. Include it once, after rrhk_input.c. One copy for both checks: when the
 * shell's input module or an adapter calls a new shell function, it is added here. Original RetroRecomp code: MIT. */
#ifndef RRHK_SHELL_STUBS_H
#define RRHK_SHELL_STUBS_H

/* menu and options */
#ifndef RRHK_STUBS_LINK_RETRO_MENU     /* a check that links native/retro_menu.c has the real one */
const char *rr_menu_pad_name(int button) {(void)button;return "";}
#endif
void rrhk_notice(const char *text,Uint64 milliseconds) {(void)text;(void)milliseconds;}
bool rrhk_options_hidden(int button) {(void)button;return false;}
void rrhk_combo_restore(bool gamepad) {(void)gamepad;}
int rrhk_action_row(void) {return -1;}
bool rrhk_trigger_step(bool down,int value) {(void)down;(void)value;return false;}
void rrhk_option_row_run(RrhkOptionRows *rows,int key,int icon,const char *format,const char *value)
    {(void)rows;(void)key;(void)icon;(void)format;(void)value;}
/* the CRT and LCD looks (HOST_KIT D35) */
const char *rrhk_crt_style_name(int style) {(void)style;return "";}
const char *rrhk_lcd_style_name(int style) {(void)style;return "";}
/* multiplayer */
bool rrhk_session_on;
bool rrhk_session_active(void) {return false;}
uint16_t rrhk_session_port(int port) {(void)port;return 0;}
void rrhk_session_axes(int port,int16_t axes[RRHK_AXES]) {(void)port;for(int i=0;i<RRHK_AXES;++i)axes[i]=0;}

#endif
