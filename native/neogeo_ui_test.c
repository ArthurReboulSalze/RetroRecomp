/* Explicit opt-in host event tests; no diagnostics in ordinary runs. */
#include <SDL.h>
#include "platform_io.h"
#include <stdlib.h>
#include <string.h>
#include "neogeo_host.h"
static FILE *script,*ui_log;
static unsigned tick,due;
static int initialized,has_line;
static char command[2048],capture[2048];
static SDL_Joystick *joysticks[2];
void rr_ng_test_json(FILE *file,const char *text) {
    fputc('"',file);
    if(text)for(const unsigned char *p=(const unsigned char*)text;*p;++p) {
        if(*p=='"' || *p=='\\')fputc('\\',file);
        if(*p<32)fprintf(file,"\\u%04x",*p);else fputc(*p,file);
    }
    fputc('"',file);
}
static void next_line(void) {
    char line[2200];has_line=0;
    while(fgets(line,sizeof line,script)) {
        if(line[0]=='#' || line[0]=='\n' || line[0]=='\r')continue;
        if(sscanf(line,"%u %2047[^\r\n]",&due,command)!=2)exit(5);
        has_line=1;return;
    }
}
static void key_event(const char *name) {
    SDL_Scancode code=SDL_GetScancodeFromName(name);if(!code)exit(5);
    SDL_Event e={0};e.type=SDL_KEYDOWN;e.key.state=SDL_PRESSED;e.key.keysym.scancode=code;
    e.key.keysym.sym=SDL_GetKeyFromScancode(code);SDL_PushEvent(&e);
}
void rr_ng_ui_test_tick(void *window,void *renderer) {
    (void)renderer;
    if(!initialized) {
        initialized=1;
#ifdef _WIN32
        const wchar_t *path=_wgetenv(L"RETRORECOMP_NG_UI_SCRIPT"),*output=_wgetenv(L"RETRORECOMP_NG_UI_LOG");
        if(!path || !output)return;
        script=rr_fopen(path,L"rb");ui_log=rr_fopen(output,L"wb");
#else
        const char *path=getenv("RETRORECOMP_NG_UI_SCRIPT"),*output=getenv("RETRORECOMP_NG_UI_LOG");
        if(!path || !output)return;
        script=fopen(path,"rb");ui_log=fopen(output,"wb");
#endif
        if(!script || !ui_log)exit(5);next_line();
    }
    if(!script)return;
    while(has_line && due==tick) {
        unsigned p;int value;char name[64];
        if(!strncmp(command,"key ",4))key_event(command+4);
        else if(!strncmp(command,"restart-script ",15))SDL_setenv("RETRORECOMP_NG_UI_SCRIPT",command+15,1);
        else if(!strncmp(command,"restart-log ",12))SDL_setenv("RETRORECOMP_NG_UI_LOG",command+12,1);
        else if(!strncmp(command,"snap ",5))rr_ng_ui_snapshot(ui_log,command+5,window);
        else if(!strncmp(command,"capture ",8))snprintf(capture,sizeof capture,"%s",command+8);
        else if(!strcmp(command,"quit")) {SDL_Event e={0};e.type=SDL_QUIT;SDL_PushEvent(&e);}
        else if(sscanf(command,"attach %u",&p)==1 && p<2 && !joysticks[p]) {
            int index=SDL_JoystickAttachVirtual(SDL_JOYSTICK_TYPE_GAMECONTROLLER,SDL_CONTROLLER_AXIS_MAX,SDL_CONTROLLER_BUTTON_MAX,0);
            if(index<0 || !(joysticks[p]=SDL_JoystickOpen(index)))exit(5);
        }
        else if(sscanf(command,"detach %u",&p)==1 && p<2 && joysticks[p]) {
            SDL_JoystickID id=SDL_JoystickInstanceID(joysticks[p]);SDL_JoystickClose(joysticks[p]);joysticks[p]=NULL;
            for(int i=0;i<SDL_NumJoysticks();++i)if(SDL_JoystickGetDeviceInstanceID(i)==id)SDL_JoystickDetachVirtual(i);
        }
        else if(sscanf(command,"button %u %63s %d",&p,name,&value)==3 && p<2 && joysticks[p]) {
            SDL_GameControllerButton button=SDL_GameControllerGetButtonFromString(name);
            if(button==SDL_CONTROLLER_BUTTON_INVALID || SDL_JoystickSetVirtualButton(joysticks[p],button,(Uint8)value))exit(5);
            SDL_JoystickUpdate();
        }
        else if(sscanf(command,"axis %u %63s %d",&p,name,&value)==3 && p<2 && joysticks[p]) {
            SDL_GameControllerAxis axis=SDL_GameControllerGetAxisFromString(name);
            if(axis==SDL_CONTROLLER_AXIS_INVALID || SDL_JoystickSetVirtualAxis(joysticks[p],axis,(Sint16)value))exit(5);
            SDL_JoystickUpdate();
        }
        else exit(5);
        next_line();
    }
    if(has_line && due<tick)exit(5);
    ++tick;
}
void rr_ng_ui_test_present(void *renderer) {
    if(!capture[0])return;
    int w,h;SDL_Renderer *ren=renderer;SDL_GetRendererOutputSize(ren,&w,&h);
    SDL_Surface *image=SDL_CreateRGBSurfaceWithFormat(0,w,h,32,SDL_PIXELFORMAT_ARGB8888);
    if(!image || SDL_RenderReadPixels(ren,NULL,SDL_PIXELFORMAT_ARGB8888,image->pixels,image->pitch) || SDL_SaveBMP(image,capture))exit(5);
    SDL_FreeSurface(image);capture[0]=0;
}
