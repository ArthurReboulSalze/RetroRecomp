/* Original Retro-Recomp player adapter, MIT. Guest state is never filtered. */
#include "retro_menu.h"
#include "game_options.h"
#include "audio_cushion.h"
#include "display_settings.h"
#include "scale2x.h"
#include "xbr_sdl.h"
#include "scanline_sdl.h"
#ifdef RR_X68000_LINKED
#include "runtime_feedback_sdl.h"
#endif
/* No restart row: Shift+F1 and the held restart combination, as on every console. */
enum {X_UP,X_DOWN,X_LEFT,X_RIGHT,X_A,X_B,X_ENTER,X_PAUSE,X_ACTIONS};
static struct {
   int ready,menu,row,player,capture,filter,display,paused,want_reset,help_page,escape_held;
   int key[2][X_ACTIONS],pad[2][X_ACTIONS];
   wchar_t ini[4096],dir[4096];
   uint32_t *rgb,*scaled;size_t rgb_capacity,scaled_capacity;
   SDL_Texture *scaled_texture;int scaled_w,scaled_h;
   RrXbr xbr;RrScanlineMask scanlines;
   int16_t *audio;size_t audio_capacity;
} player_ui;
static const char *player_actions[X_ACTIONS]={"Up","Down","Left","Right","Button A","Button B","Start","Pause"};
static int player_blocked(void){return player_ui.ready&&(player_ui.menu||player_ui.paused);}
static int player_escape_held(void){return player_ui.ready&&player_ui.escape_held;}
static int player_fast_forward(void){
   return player_ui.ready&&input_focus&&!player_blocked()&&
      keys&&keys[SDL_SCANCODE_F5]&&player_host_fkey(SDL_SCANCODE_F5,SDL_GetModState());
}
static int player_ui_quit(void){return player_ui.ready&&rr_options_quit(player_ui.menu);}
/* A held restart combination queues the same reset as Shift+F1. */
static int player_ui_restart(void){
   if(!player_ui.ready||!rr_options_restart(player_ui.menu))return 0;
   player_ui.want_reset=1;player_ui.menu=0;return 1;
}
/* Output priming: one guest frame, one device period and 10 ms, plus the
 * adaptive reserve. The device stays paused until the queue holds it, and
 * re-primes when a block finds the queue empty (the device ran dry). */
static RrAudioCushion player_cushion;
static Uint32 player_audio_period=512;
static int player_audio_primed;
static Uint32 player_audio_target(void){
   return (44100u/55u+player_audio_period+441u+rr_cushion_frames(&player_cushion,44100u))*4u;
}
static int player_queue_audio(const int16_t *samples,size_t count){
   const void *data=samples;
   if(player_ui.ready&&SDL_AtomicGet(&rr_options.audio_mode)){
      if(count>player_ui.audio_capacity){void *p=realloc(player_ui.audio,count*4);if(!p)return 0;player_ui.audio=p;player_ui.audio_capacity=count;}
      memcpy(player_ui.audio,samples,count*4);rr_options_audio(player_ui.audio,(unsigned)count,2,0,44100);data=player_ui.audio;
   }
   if(player_audio_primed&&!SDL_GetQueuedAudioSize(audio_device)){
      rr_cushion_gap(&player_cushion);SDL_PauseAudioDevice(audio_device,1);player_audio_primed=0;
   }else if(player_audio_primed)rr_cushion_clean(&player_cushion,(Uint32)count,44100u);
   rr_cushion_pushed(&player_cushion);
   if(SDL_QueueAudio(audio_device,data,(Uint32)(count*4))!=0)return 0;
   if(!player_audio_primed&&SDL_GetQueuedAudioSize(audio_device)>=player_audio_target()){
      SDL_PauseAudioDevice(audio_device,0);player_audio_primed=1;
   }
   return 1;
}
static void player_defaults(void){
   for(unsigned p=0;p<2;p++)for(unsigned i=0;i<X_ACTIONS;i++){player_ui.key[p][i]=0;player_ui.pad[p][i]=-1;}
   int defaults[]={SDL_SCANCODE_UP,SDL_SCANCODE_DOWN,SDL_SCANCODE_LEFT,SDL_SCANCODE_RIGHT,
      rr_keyboard_letter(SDLK_w,SDL_SCANCODE_W),rr_keyboard_letter(SDLK_x,SDL_SCANCODE_X),SDL_SCANCODE_RETURN,0};
   memcpy(player_ui.key[0],defaults,sizeof(defaults));
   int buttons[]={SDL_CONTROLLER_BUTTON_DPAD_UP,SDL_CONTROLLER_BUTTON_DPAD_DOWN,SDL_CONTROLLER_BUTTON_DPAD_LEFT,
      SDL_CONTROLLER_BUTTON_DPAD_RIGHT,SDL_CONTROLLER_BUTTON_A,SDL_CONTROLLER_BUTTON_B,SDL_CONTROLLER_BUTTON_START,-1};
   memcpy(player_ui.pad[0],buttons,sizeof(buttons));memcpy(player_ui.pad[1],buttons,sizeof(buttons));
}
static void player_store(const wchar_t *key,int value){
   rr_display_save(player_ui.ini,player_ui.dir,L"X68000",key,value);
}
static void player_pause_audio(void){
   /* Paused either way: the next blocks re-prime before the device plays. */
   if(audio_device){SDL_PauseAudioDevice(audio_device,1);SDL_ClearQueuedAudio(audio_device);player_audio_primed=0;}
   rr_options_audio_reset();
   if(mouse_grab)SDL_SetRelativeMouseMode(player_blocked()?SDL_FALSE:SDL_TRUE);
}
static int player_init(void){
   if(!renderer)return 1;
   if(!rr_menu_init(renderer))return 0;
   player_defaults();player_ui.capture=-1;
   if(!rr_executable_directory(player_ui.dir,4000))return 0;
   rr_wide_append(player_ui.dir,4096,RR_SLASH_W L"datas");rr_wide_copy(player_ui.ini,4096,player_ui.dir);
   rr_wide_append(player_ui.ini,4096,RR_SLASH_W L"Retro-Recomp.ini");
   rr_display_load(player_ui.ini,L"X68000",&player_ui.filter,&player_ui.display);
   wchar_t language[16];rr_ini_get(L"Interface",L"language",L"en",language,16,player_ui.ini);
   rr_language_set(rr_language_from_wide(language));
   guest_keyboard=rr_ini_int(L"X68000",L"guest_keyboard",0,player_ui.ini)!=0;
   autofire=rr_ini_int(L"X68000",L"autofire",0,player_ui.ini)!=0;
   for(unsigned p=0;p<2;p++)for(unsigned a=0;a<X_ACTIONS;a++){
      wchar_t key[48];swprintf(key,48,L"p%u_key%u",p,a);int k=rr_ini_int(L"X68000",key,player_ui.key[p][a],player_ui.ini);
      player_ui.key[p][a]=k>=0&&k<SDL_NUM_SCANCODES?k:player_ui.key[p][a];
      swprintf(key,48,L"p%u_pad%u",p,a);k=rr_ini_int(L"X68000",key,player_ui.pad[p][a],player_ui.ini);
      player_ui.pad[p][a]=k>=-1&&k<SDL_CONTROLLER_BUTTON_MAX?k:player_ui.pad[p][a];
   }
   if(SDL_SetWindowFullscreen(window,player_ui.display?SDL_WINDOW_FULLSCREEN_DESKTOP:0))player_ui.display=0;
   rr_options_init(L"X68000");rr_options_keyboard("X68000",10);player_ui.ready=1;return 1;
}
static int player_action(unsigned port,unsigned action){
   if(!player_ui.ready||port>1||action>=X_ACTIONS)return -1;
   if(player_blocked()||!input_focus)return 0;
   int k=player_ui.key[port][action],b=player_ui.pad[port][action];
   int value=!guest_keyboard&&keys&&k>0&&keys[k]&&!(SDL_GetModState()&KMOD_CTRL&&SDL_GetModState()&KMOD_ALT);
   if(controllers[port]&&b>=0&&SDL_GameControllerGetButton(controllers[port],(SDL_GameControllerButton)b))value=1;
   return value;
}
static unsigned player_fire_scan(void){
   return player_ui.ready?(unsigned)player_ui.key[0][X_A]:(unsigned)SDL_GetScancodeFromKey(SDLK_w);
}
static int player_mouse(unsigned id,int value){
   if(!mouse_game||!player_ui.ready||!input_focus||player_blocked())return value;
   if(id==RETRO_DEVICE_ID_MOUSE_LEFT)return (mouse_buttons&SDL_BUTTON_LMASK)!=0||player_action(0,X_A)>0;
   if(id==RETRO_DEVICE_ID_MOUSE_RIGHT)return (mouse_buttons&SDL_BUTTON_RMASK)!=0||player_action(0,X_B)>0;
   if(id==RETRO_DEVICE_ID_MOUSE_X||id==RETRO_DEVICE_ID_MOUSE_Y){
      int horizontal=id==RETRO_DEVICE_ID_MOUSE_X;
      int step=(player_action(0,horizontal?X_RIGHT:X_DOWN)>0)-(player_action(0,horizontal?X_LEFT:X_UP)>0);
      int axis=controllers[0]?SDL_GameControllerGetAxis(controllers[0],horizontal?SDL_CONTROLLER_AXIS_LEFTX:SDL_CONTROLLER_AXIS_LEFTY):0;
      int delta=step*6;if(axis>12000||axis< -12000)delta=axis/5500;
      return (horizontal?mouse_dx:mouse_dy)+delta;
   }
   return value;
}
static int player_joy(unsigned port){
   if(!player_ui.ready)return -1;
   unsigned mask=0;static const unsigned bits[]={RETRO_DEVICE_ID_JOYPAD_UP,RETRO_DEVICE_ID_JOYPAD_DOWN,
      RETRO_DEVICE_ID_JOYPAD_LEFT,RETRO_DEVICE_ID_JOYPAD_RIGHT,RETRO_DEVICE_ID_JOYPAD_B,RETRO_DEVICE_ID_JOYPAD_A};
   for(unsigned a=0;a<6;a++)if(player_action(port,a)>0)mask|=1u<<bits[a];
   if(controllers[port]&&input_focus&&!player_blocked()){
      int x=SDL_GameControllerGetAxis(controllers[port],SDL_CONTROLLER_AXIS_LEFTX),y=SDL_GameControllerGetAxis(controllers[port],SDL_CONTROLLER_AXIS_LEFTY);
      if(x< -12000)mask|=1u<<RETRO_DEVICE_ID_JOYPAD_LEFT;if(x>12000)mask|=1u<<RETRO_DEVICE_ID_JOYPAD_RIGHT;
      if(y< -12000)mask|=1u<<RETRO_DEVICE_ID_JOYPAD_UP;if(y>12000)mask|=1u<<RETRO_DEVICE_ID_JOYPAD_DOWN;
   }
   return (int)mask;
}
static void player_language(void){
   rr_language_set(rr_language_next(rr_language_get()));rr_mkdir(player_ui.dir);
   rr_ini_set(L"Interface",L"language",rr_language_wide(rr_language_get()),player_ui.ini);
   notify(rr_language_name(rr_language_get()));
}
static void player_display(void){
   if(rr_display_cycle(window,&player_ui.display,player_ui.ini,player_ui.dir,L"X68000"))
      notify(rr_tr(player_ui.display==0?"Windowed":player_ui.display==1?"Pixel perfect":"Fit to screen"));
}
/* Function keys are Retro-Recomp shortcuts unless the options hand F1-F10 to
 * the X68000, or full typing keeps F2-F10 for it as before. Ctrl+F1-F12
 * (not Ctrl+Alt) and any function key inside a menu stay with Retro-Recomp. */
static int player_host_fkey(int key,SDL_Keymod mod){
   if(key<SDL_SCANCODE_F1||key>SDL_SCANCODE_F12)return 0;
   if((player_ui.ready&&player_ui.menu)||((mod&KMOD_CTRL)&&!(mod&KMOD_ALT)))return 1;
   if(guest_keyboard&&key>=SDL_SCANCODE_F2&&key<=SDL_SCANCODE_F10)return 0;
   return rr_options_host_fkey(key,mod,false);
}
/* F2 pages: each player's keys and buttons, then the options with the
 * function-key choice of this computer. Player 1's page ends with the quit
 * and restart combinations, keyboard and controller side by side. */
static RrPages player_pages(void){RrPages pages={2,0};return pages;}
static int player_page(void){return rr_pages_index(player_pages(),player_ui.menu,player_ui.player);}
static int player_rows(void){return X_ACTIONS+(player_ui.player?0:RR_COMBO_ROWS);}
static void player_turn_page(int step){
   int control,before=player_ui.menu;
   player_ui.menu=rr_pages_goto(player_pages(),player_page()+step,&control);
   player_ui.player=control;
   player_ui.row=before==2&&player_ui.menu==2?SDL_min(player_ui.row,player_rows()-1):0;
}
/* Option rows run their function keys exactly as the shortcuts do. */
static RrOptionRows player_option_rows(void){
   RrOptionRows d;d.count=0;
   rr_option_row(&d,SDL_SCANCODE_F3,"F3 Filter: %s",rr_option_filter_name(player_ui.filter));
   rr_option_row(&d,SDL_SCANCODE_F4,"F4 Display: %s",rr_option_mode_name(player_ui.display));
   rr_option_row(&d,SDL_SCANCODE_F6,"F6 Autofire: %s",rr_tr(autofire?"ON":"OFF"));
   rr_option_row(&d,SDL_SCANCODE_F7,"F7 Language: %s",rr_language_name(rr_language_get()));
#ifdef RR_X68000_LINKED
   rr_option_row(&d,SDL_SCANCODE_F12,"%s",rr_tr(rr_feedback_label()));
#endif
   rr_option_shared_rows(&d);
   return d;
}
static bool player_event(const SDL_Event *e){
   if(!player_ui.ready)return false;
   int key=e->type==SDL_KEYDOWN&&!e->key.repeat?e->key.keysym.scancode:0;
   int button=e->type==SDL_CONTROLLERBUTTONDOWN?e->cbutton.button:-1;
   /* A function key handed to the X68000 never reaches the frontend. */
   if(key>=SDL_SCANCODE_F1&&key<=SDL_SCANCODE_F12&&!player_host_fkey(key,(SDL_Keymod)e->key.keysym.mod)){
      rr_options_observe(e);return false;
   }
   /* A menu's Escape belongs entirely to the frontend until key release.
    * Do not let the held key pause the guest or become a second quit action. */
   if(e->type==SDL_KEYUP&&e->key.keysym.scancode==SDL_SCANCODE_ESCAPE)player_ui.escape_held=0;
   if(e->type==SDL_KEYDOWN&&e->key.keysym.scancode==SDL_SCANCODE_ESCAPE&&player_ui.escape_held){
      rr_options_observe(e);return true;
   }
   if(key==SDL_SCANCODE_ESCAPE&&player_ui.menu)player_ui.escape_held=1;
   if(player_ui.capture>=0){
      rr_options_observe(e);
      if(key==SDL_SCANCODE_ESCAPE){player_ui.capture=-1;return true;}
      if(key>=SDL_SCANCODE_F1&&key<=SDL_SCANCODE_F12){notify("Reserved shortcut: use another key");return true;}
      if(key||button>=0){
         wchar_t entry[48];int a=player_ui.capture,p=player_ui.player;
         if(key){player_ui.key[p][a]=key;swprintf(entry,48,L"p%d_key%d",p,a);player_store(entry,key);}
         else {player_ui.pad[p][a]=button;swprintf(entry,48,L"p%d_pad%d",p,a);player_store(entry,button);}
         player_ui.capture=-1;notify(rr_tr("Settings saved"));
      }
      return true;
   }
   /* Full computer typing reserves the ordinary keys for the guest. Guide
    * and explicit Ctrl+Alt shortcuts remain available to regain the frontend. */
   if(!guest_keyboard||player_ui.menu||button>=0){
      int before=player_ui.menu;
      if(rr_options_event(e,&player_ui.menu,false)){
         if(before!=player_ui.menu)player_pause_audio();return true;
      }
   }else rr_options_observe(e);
   if(rr_options_quit(player_ui.menu)){quit_requested=true;return true;}
   if(e->type==SDL_QUIT)return false;
   if(key&&(e->key.keysym.mod&KMOD_CTRL)&&(e->key.keysym.mod&KMOD_ALT)){
      if(e->key.keysym.sym==SDLK_h){player_ui.menu=player_ui.menu?0:1;player_pause_audio();return true;}
      if(e->key.keysym.sym==SDLK_o){player_ui.menu=RR_OPTIONS_MENU;player_pause_audio();return true;}
      if(e->key.keysym.sym==SDLK_RETURN){player_display();return true;}
      /* Other established computer shortcuts stay in input_poll. */
      return false;
   }
   /* An option row behaves as its function key. */
   if(player_ui.menu==RR_OPTIONS_MENU){
      RrOptionRows d=player_option_rows();int chosen=rr_option_page_event(e,&d);
      if(chosen<0)return true;
      if(chosen>0)key=chosen;
   }
   /* Left/Right, Tab, LB/RB or the D-pad turn the F2 pages. */
   if(rr_pages_open(player_ui.menu)&&!(key>=SDL_SCANCODE_F1&&key<=SDL_SCANCODE_F12)){
      int step=rr_pages_step(e);if(step){player_turn_page(step);return true;}
   }
   if(key==SDL_SCANCODE_F1){
      /* F1 toggles help; Shift+F1 restarts at once, as on every console. */
      if(e->key.keysym.mod&KMOD_SHIFT){player_ui.want_reset=1;player_ui.menu=0;}
      else player_ui.menu=player_ui.menu==1?0:1;
      player_pause_audio();return true;
   }
   if(key==SDL_SCANCODE_F11){player_ui.paused=!player_ui.paused;player_pause_audio();return true;}
   if(key==SDL_SCANCODE_F2){
      /* F2 opens on the first page and closes F2 from any page. */
      if(rr_pages_open(player_ui.menu))player_ui.menu=0;
      else{player_ui.menu=2;player_ui.player=0;player_ui.row=0;}
      player_pause_audio();return true;
   }
   if(key==SDL_SCANCODE_F12){
#ifdef RR_X68000_LINKED
      rr_feedback_toggle();notify(rr_feedback_label());
#endif
      return true;
   }
   if(key==SDL_SCANCODE_F3){player_ui.filter=rr_menu_next_filter(player_ui.filter);player_store(L"filter",player_ui.filter);return true;}
   if(key==SDL_SCANCODE_F4){player_display();return true;}
   if(key==SDL_SCANCODE_F6){autofire=!autofire;player_store(L"autofire",autofire);notify(autofire?"Rapid fire: ON":"Rapid fire: OFF");return true;}
   if(key==SDL_SCANCODE_F7){player_language();return true;}
   if(player_ui.menu){
      if(key==SDL_SCANCODE_ESCAPE||button==SDL_CONTROLLER_BUTTON_B){player_ui.menu=0;player_pause_audio();return true;}
      if(player_ui.menu==1&&key==SDL_SCANCODE_TAB)player_ui.help_page^=1;
      else if(player_ui.menu==2){
         if(key==SDL_SCANCODE_UP||button==SDL_CONTROLLER_BUTTON_DPAD_UP)player_ui.row=(player_ui.row+player_rows()-1)%player_rows();
         else if(key==SDL_SCANCODE_DOWN||button==SDL_CONTROLLER_BUTTON_DPAD_DOWN)player_ui.row=(player_ui.row+1)%player_rows();
         else if(player_ui.row>=X_ACTIONS){
            /* Quit and restart: Enter captures the keyboard combination, A
             * the controller one; Delete and X clear them. */
            int combo=player_ui.row-X_ACTIONS;
            if(key==SDL_SCANCODE_RETURN||key==SDL_SCANCODE_KP_ENTER)rr_combo_start(combo,false);
            else if(button==SDL_CONTROLLER_BUTTON_A)rr_combo_start(combo,true);
            else if(key==SDL_SCANCODE_DELETE||key==SDL_SCANCODE_BACKSPACE)rr_combo_clear(combo,false);
            else if(button==SDL_CONTROLLER_BUTTON_X)rr_combo_clear(combo,true);
         }
         else if(key==SDL_SCANCODE_RETURN||key==SDL_SCANCODE_KP_ENTER||button==SDL_CONTROLLER_BUTTON_A)player_ui.capture=player_ui.row;
         else if(key==SDL_SCANCODE_DELETE||button==SDL_CONTROLLER_BUTTON_X){
            wchar_t entry[48];int p=player_ui.player,a=player_ui.row;player_ui.key[p][a]=0;player_ui.pad[p][a]=-1;
            swprintf(entry,48,L"p%d_key%d",p,a);player_store(entry,0);swprintf(entry,48,L"p%d_pad%d",p,a);player_store(entry,-1);
         }
      }
      return true;
   }
   if(guest_keyboard)return false;
   if(key==SDL_SCANCODE_ESCAPE){quit_requested=true;return true;}
   if(key||button>=0){
      for(unsigned p=0;p<2;p++){
         int match=key?player_ui.key[p][X_PAUSE]==key:player_ui.pad[p][X_PAUSE]==button;
         if(button>=0&&(!controllers[p]||SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controllers[p]))!=e->cbutton.which))continue;
         if(match){player_ui.paused=!player_ui.paused;player_pause_audio();return true;}
      }
   }
   return false;
}
static void player_overlay(void){
   if(!player_ui.ready)return;
   int page=player_page(),pages=rr_pages_count(player_pages());
   if(player_ui.menu==RR_OPTIONS_MENU){RrOptionRows d=player_option_rows();rr_option_page_draw(renderer,&d,page,pages);return;}
   int x,y,s;rr_menu_layout(renderer,&x,&y,&s);
   if(player_ui.menu){
      rr_menu_begin(renderer,x,y,s);
#define XT(px,py,text) rr_menu_text(renderer,x,y,s,px,py,rr_tr(text),RR_MENU_GOLD)
      if(player_ui.menu==1){
         XT(12,12,"Retro-Recomp - Help");
         if(!player_ui.help_page){
            const char *lines[]={"F1  Help | Shift+F1 Restart","F2  Controls & options","F3  Next filter","F4  Window / Pixel / Fit",
               "F5  Fast loading (hold)","F6  Rapid fire (keyboard / pad)","F7  Language","F8  Save game state","F9  Load game state","F11 Pause","F12 Record fallbacks","Esc Quit (close menus first)"};
            for(unsigned n=0;n<12;n++)XT(12,RR_MENU_FIRST_LINE+(int)n*RR_MENU_LINE,lines[n]);
         }else{
            const char *lines[]={"Ctrl+Alt+K: full guest keyboard","Ctrl+Alt+M: mouse capture",
               "Ctrl+Alt+F: rapid fire",
               "Ctrl+Alt+Page Up/Down: FDD0",
               "Add Shift: FDD1","Ctrl+Alt+Backspace: eject disk",
               "Ctrl+Alt+H: help","Ctrl+Alt+O: options","Ctrl+Alt+Enter: display mode","Ctrl+Alt+Q: quit",
               "Ctrl+F1-F12: Retro-Recomp shortcuts"};
            for(unsigned n=0;n<11;n++)XT(12,RR_MENU_FIRST_LINE+(int)n*RR_MENU_LINE,lines[n]);
         }
         XT(12,RR_MENU_LAST_LINE,"Tab: game / computer shortcuts");
      }else if(player_ui.menu==2){
         char title[80];snprintf(title,sizeof(title),"%s %d",rr_tr("Player"),player_ui.player+1);
         rr_menu_page_header(renderer,x,y,s,title,page,pages);
         for(int a=0;a<player_rows();a++){
            int line=RR_MENU_FIRST_LINE+a*RR_MENU_LINE;
            if(a==player_ui.row)rr_menu_box(renderer,x,y,s,10,line,236,RR_MENU_LINE,RR_MENU_SELECT,255);
            if(a>=X_ACTIONS){
               char keyboard[80],pad[80];
               rr_combo_value(keyboard,sizeof keyboard,a-X_ACTIONS,false);rr_combo_value(pad,sizeof pad,a-X_ACTIONS,true);
               XT(12,line,rr_combo_label(a-X_ACTIONS));
               rr_menu_text_fit(renderer,x,y,s,110,line,64,keyboard,RR_MENU_GOLD);
               rr_menu_text_fit(renderer,x,y,s,178,line,64,pad,RR_MENU_GOLD);
               continue;
            }
            int k=player_ui.key[player_ui.player][a],b=player_ui.pad[player_ui.player][a];
            const char *pad=b<0?"-":SDL_GameControllerGetStringForButton((SDL_GameControllerButton)b);
            XT(12,line,player_actions[a]);
            XT(110,line,k?rr_keyboard_name((SDL_Scancode)k):"-");
            XT(178,line,pad?pad:"?");
         }
         if(player_ui.row>=X_ACTIONS)XT(12,RR_MENU_HINT_LINE,rr_combo_hint(player_ui.row-X_ACTIONS));
         else XT(12,RR_MENU_HINT_LINE,player_ui.capture>=0?"Press a key or gamepad button":"Enter / A: change | X: clear");
         XT(12,RR_MENU_LAST_LINE,player_ui.capture>=0?"Esc: cancel binding":"Left/Right: page | Esc: close");
      }
      if(player_ui.menu==1)rr_menu_build_footer(renderer,x,y,s);
      rr_menu_end(renderer);
#undef XT
   }else if(player_ui.paused){rr_menu_begin(renderer,x,y,s);rr_menu_text(renderer,x,y,s,100,85,rr_tr("Paused"),RR_MENU_GOLD);rr_menu_end(renderer);}
   if(!player_ui.menu&&status_text[0]&&(int32_t)(status_until-SDL_GetTicks())>0){
      rr_menu_box(renderer,x,y,s,4,144,248,26,RR_MENU_PANEL_RGB,235);rr_menu_text(renderer,x,y,s,8,150,status_text,RR_MENU_ACCENT);
   }
}
static void player_present(const void *data,unsigned w,unsigned h,size_t pitch){
   if(!renderer||!data)return;
   size_t count=(size_t)w*h;
   if(count>player_ui.rgb_capacity){void *p=realloc(player_ui.rgb,count*4);if(!p){fail("Presentation allocation failed");return;}player_ui.rgb=p;player_ui.rgb_capacity=count;}
   for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++){
      uint32_t c;if(pixel_format==RETRO_PIXEL_FORMAT_RGB565){uint16_t v;memcpy(&v,(const uint8_t*)data+y*pitch+x*2,2);unsigned r=(v>>11)&31,g=(v>>5)&63,b=v&31;c=0xff000000u|((r*255/31)<<16)|((g*255/63)<<8)|(b*255/31);}
      else{memcpy(&c,(const uint8_t*)data+y*pitch+x*4,4);c|=0xff000000u;}player_ui.rgb[(size_t)y*w+x]=c;
   }
   SDL_Texture *shown=NULL;
   if(player_ui.filter==1)shown=rr_xbr_update(renderer,&player_ui.xbr,player_ui.rgb,(int)w,(int)h,(int)w);
   if(player_ui.filter==2){
      if(count*4>player_ui.scaled_capacity){void *p=realloc(player_ui.scaled,count*16);if(p){player_ui.scaled=p;player_ui.scaled_capacity=count*4;}}
      if(player_ui.scaled_capacity>=count*4){
         rr_scale2x(player_ui.rgb,(int)w,(int)h,(int)w,player_ui.scaled,(int)w*2);
         if(!player_ui.scaled_texture||player_ui.scaled_w!=(int)w||player_ui.scaled_h!=(int)h){
            if(player_ui.scaled_texture)SDL_DestroyTexture(player_ui.scaled_texture);
            player_ui.scaled_texture=SDL_CreateTexture(renderer,SDL_PIXELFORMAT_ARGB8888,SDL_TEXTUREACCESS_STREAMING,(int)w*2,(int)h*2);player_ui.scaled_w=w;player_ui.scaled_h=h;
         }
         if(player_ui.scaled_texture){SDL_UpdateTexture(player_ui.scaled_texture,NULL,player_ui.scaled,(int)w*8);shown=player_ui.scaled_texture;}
      }
   }
   if(!shown){
      if(!texture||texture_width!=w||texture_height!=h){if(texture)SDL_DestroyTexture(texture);texture=SDL_CreateTexture(renderer,SDL_PIXELFORMAT_ARGB8888,SDL_TEXTUREACCESS_STREAMING,w,h);texture_width=w;texture_height=h;}
      if(!texture){fail(SDL_GetError());return;}SDL_UpdateTexture(texture,NULL,player_ui.rgb,(int)w*4);shown=texture;
   }
   int rw,rh;SDL_GetRendererOutputSize(renderer,&rw,&rh);SDL_Rect dst={0,0,rw,(int)round(rw/aspect_ratio)};
   if(dst.h>rh){dst.h=rh;dst.w=(int)round(rh*aspect_ratio);}
   if(player_ui.display==1){int scale=SDL_min(rw/(int)w,rh/(int)h);if(scale>=1){dst.w=(int)w*scale;dst.h=(int)h*scale;}}
   dst.x=(rw-dst.w)/2;dst.y=(rh-dst.h)/2;
   SDL_SetRenderDrawColor(renderer,0,0,0,255);SDL_RenderClear(renderer);SDL_RenderCopy(renderer,shown,NULL,&dst);
   if(player_ui.filter==3)rr_scanlines_draw(renderer,&player_ui.scanlines,&dst,(int)h);
   player_overlay();SDL_RenderPresent(renderer);
}
static void player_shutdown(void){
   rr_xbr_destroy(&player_ui.xbr);rr_scanlines_destroy(&player_ui.scanlines);
   if(player_ui.scaled_texture)SDL_DestroyTexture(player_ui.scaled_texture);
   free(player_ui.rgb);free(player_ui.scaled);free(player_ui.audio);rr_menu_shutdown();
}
