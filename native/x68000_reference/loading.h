/* Original Retro-Recomp presentation policy, MIT. No guest state is changed. */
#ifndef RR_X68000_LOADING_H
#define RR_X68000_LOADING_H
#include <stdint.h>
typedef struct {uint64_t image;unsigned stable;} RRLoading;
static int rr_loading_update(RRLoading *state,unsigned activity,uint64_t image){
   if(image!=state->image){state->image=image;state->stable=0;}
   else if(state->stable<3)state->stable++;
   /* An active transfer alone can be background I/O. Require an image that
    * waits too; changing gameplay and an idle title do not trigger this. */
   return activity&&state->stable>=2;
}
#endif
