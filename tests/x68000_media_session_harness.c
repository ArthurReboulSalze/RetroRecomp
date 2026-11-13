/* Authored frontend transaction tests; no machine/game/firmware assets. */
#include "media_session.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned drive,index_value,mask=3,images=2,polls[2];
static int fail_insert;
static void select_drive(unsigned d){drive=d;}
static unsigned presence(void){return mask;}
static unsigned count(void){return images;}
static unsigned interest(unsigned d){return polls[d];}
static bool set_index(unsigned i){index_value=i;return i<images;}
static bool eject(bool value){if(value)mask&=~((1u<<drive)|(1u<<(8+drive)));else if(fail_insert)fail_insert--;else{mask|=1u<<drive;mask&=~(1u<<(8+drive));}return true;}
#define CHECK(x) do{if(!(x)){fprintf(stderr,"Failed at line %d: %s (%s)\n",__LINE__,#x,rr_media_error(&s));return 1;}}while(0)
int main(int argc,char**argv){
    RRMediaSession s,again,t;struct retro_disk_control_callback cb={0};
    char content[2048],session[2048],diskfile[2048];void*blob=NULL;size_t size;FILE*f;int ch;
    if(argc!=3)return 2;
    snprintf(content,sizeof(content),"%s/game.m3u",argv[1]);snprintf(session,sizeof(session),"%s/session.bin",argv[1]);
    snprintf(diskfile,sizeof(diskfile),"%s/disk-01.xdf",argv[1]);
    cb.get_num_images=count;cb.set_eject_state=eject;cb.set_image_index=set_index;
    CHECK(rr_media_open(&s,content,session,&cb,select_drive,presence));
    CHECK(!rr_media_swap(&s,0,1)); /* One buffered writable image per drive. */
    CHECK(mask==3);
    CHECK(rr_media_swap(&s,1,-1));CHECK(mask==1);
    CHECK(rr_media_swap(&s,0,1));CHECK(index_value==1&&mask==1);
    CHECK(rr_media_swap(&s,1,0));CHECK(mask==3);
    CHECK(rr_media_save_session(&s));
    CHECK(rr_media_capture(&s,&blob,&size));
    CHECK(rr_media_validate(&s,blob,size));
    CHECK(!rr_media_validate(&s,blob,size-1));
    ((unsigned char*)blob)[size-1]^=1;CHECK(!rr_media_validate(&s,blob,size));((unsigned char*)blob)[size-1]^=1;
    /* Guest-private image rewinds with the core snapshot, including ejected
     * disks. The original authored sources are separate and never opened. */
    f=fopen(diskfile,"wb");CHECK(f!=NULL);fputs("changed guest bytes",f);fclose(f);
    CHECK(rr_media_swap(&s,0,-1));CHECK(rr_media_swap(&s,1,-1));
    CHECK(rr_media_apply(&s,blob,size));CHECK(mask==3&&s.selected[0]==1&&s.selected[1]==0);
    f=fopen(diskfile,"rb");CHECK(f!=NULL);ch=fgetc(f);fclose(f);CHECK(ch=='A');
    free(blob);blob=NULL;
    /* A restart with the core's default disks reattaches the persisted pair. */
    mask=3;CHECK(rr_media_open(&again,content,session,&cb,select_drive,presence));
    CHECK(rr_media_load_session(&again));CHECK(again.selected[0]==1&&again.selected[1]==0&&mask==3);
    CHECK(rr_media_cycle(&again,1,1));CHECK(again.selected[1]==-1&&mask==1);
    CHECK(rr_media_cycle(&again,1,-1));CHECK(again.selected[1]==0&&mask==3);
    CHECK(rr_media_swap(&again,1,-1));fail_insert=1;
    CHECK(!rr_media_swap(&again,1,0));CHECK(!(mask&2));fail_insert=0;
    CHECK(rr_media_swap(&again,1,0));CHECK(rr_media_swap(&again,0,-1));
    fail_insert=1;CHECK(!rr_media_swap(&again,1,1));CHECK(mask==2&&again.selected[1]==0);
    /* A real guest eject leaves our selected identity but removes presence.
     * Once the guest polls the empty drive, the next disk of the set answers,
     * moved from the other drive if needed. */
    rr_media_set_interest(&again,interest);
    CHECK(rr_media_swap(&again,0,1));CHECK(rr_media_swap(&again,1,0));
    mask&=~2u;CHECK(rr_media_auto_advance(&again)==0);polls[1]++;CHECK(rr_media_auto_advance(&again)==0);polls[1]++;
    for(unsigned n=3;n<RR_MEDIA_INSERT_WAIT;n++)CHECK(rr_media_auto_advance(&again)==0);
    CHECK(!(mask&2)); /* Guest must observe removal. */
    CHECK(rr_media_capture(&again,&blob,&size));
    CHECK(rr_media_auto_advance(&again)==1);CHECK(mask==2&&again.selected[1]==1&&again.selected[0]==-1);
    CHECK(rr_media_auto_advance(&again)==0); /* Does not repeat. */
    CHECK(rr_media_apply(&again,blob,size));free(blob);blob=NULL;
    CHECK(mask==1&&again.selected[0]==1&&again.selected[1]==0&&again.empty_frames[1]==RR_MEDIA_INSERT_WAIT-1);
    CHECK(again.request[1].polled==2); /* Polls before F8 still count after F9. */
    CHECK(rr_media_auto_advance(&again)==1);CHECK(mask==2&&again.selected[1]==1);
    CHECK(rr_media_swap(&again,1,0));CHECK(rr_media_swap(&again,1,-1));
    polls[1]++;CHECK(rr_media_auto_advance(&again)==0); /* Manual eject stays empty. */
    CHECK(rr_media_swap(&again,1,0));mask&=~2u;fail_insert=1;CHECK(rr_media_auto_advance(&again)==0);polls[1]++;CHECK(rr_media_auto_advance(&again)==0);polls[1]++;
    for(unsigned n=3;n<RR_MEDIA_INSERT_WAIT;n++)CHECK(rr_media_auto_advance(&again)==0);
    CHECK(rr_media_auto_advance(&again)==-1);CHECK(!(mask&2));fail_insert=0;
    CHECK(rr_media_swap(&again,0,0));CHECK(rr_media_swap(&again,1,-1));
    CHECK(rr_media_auto_advance(&again)==0); /* Empty is not a request. */
    mask|=1u<<9; /* The guest blinks the empty drive. */
    for(unsigned n=2;n<RR_MEDIA_INSERT_WAIT;n++)CHECK(rr_media_auto_advance(&again)==0);
    CHECK(rr_media_auto_advance(&again)==1);
    CHECK(again.selected[0]==0&&again.selected[1]==1);
    CHECK(rr_media_swap(&again,0,-1));CHECK(rr_media_swap(&again,1,0));CHECK(rr_media_swap(&again,0,1));
    CHECK(rr_media_boot(&again));CHECK(mask==3&&again.selected[0]==0&&again.selected[1]==1);
    CHECK(!again.empty_frames[0]&&!again.empty_frames[1]);

    /* Three disks: refusals, a moved disk returning home, acceptance,
     * exhaustion, host changes and F9 inside a request. */
    snprintf(content,sizeof(content),"%s/game.m3u",argv[2]);snprintf(session,sizeof(session),"%s/session.bin",argv[2]);
    images=3;mask=3;polls[0]=polls[1]=0;
    CHECK(rr_media_open(&t,content,session,&cb,select_drive,presence));
    polls[0]=7;rr_media_set_interest(&t,interest); /* Earlier polls are not a request. */
    mask&=~1u;polls[0]++; /* A finished loader ejects A, polling in that frame only. */
    for(unsigned n=0;n<4*RR_MEDIA_INSERT_WAIT;n++)CHECK(rr_media_auto_advance(&t)==0);
    CHECK(!(mask&1)&&t.selected[0]==0&&!t.request[0].active);
    polls[0]++;CHECK(rr_media_auto_advance(&t)==0); /* One poll alone is not a request. */
    for(unsigned n=0;n<4*RR_MEDIA_INSERT_WAIT;n++)CHECK(rr_media_auto_advance(&t)==0);
    polls[0]++; /* Polling again: it waits for media. Disk 2 moves over from B. */
    CHECK(rr_media_auto_advance(&t)==1);CHECK(mask==1&&t.selected[0]==1&&t.selected[1]==-1&&t.request[0].moved);
    for(unsigned n=0;n<20;n++)CHECK(rr_media_auto_advance(&t)==0);
    mask&=~1u; /* Refused: disk 2 returns to B, then disk 3 is offered in A. */
    CHECK(rr_media_auto_advance(&t)==0);CHECK(mask==2&&t.selected[1]==1&&!t.request[0].moved);
    for(unsigned n=2;n<RR_MEDIA_INSERT_WAIT;n++)CHECK(rr_media_auto_advance(&t)==0);
    CHECK(rr_media_capture(&t,&blob,&size));
    CHECK(rr_media_auto_advance(&t)==1);CHECK(mask==3&&t.selected[0]==2&&t.selected[1]==1);
    CHECK(rr_media_apply(&t,blob,size));free(blob);blob=NULL; /* F9 replays the same choice. */
    CHECK(mask==2&&t.request[0].active==1&&t.request[0].refused==2u); /* Disk 1, ejected, is not excluded: it comes last. */
    CHECK(rr_media_auto_advance(&t)==1);CHECK(mask==3&&t.selected[0]==2);
    CHECK(rr_media_capture(&t,&blob,&size));
    for(unsigned n=1;n<RR_MEDIA_REJECT_WINDOW;n++)CHECK(rr_media_auto_advance(&t)==0);
    CHECK(t.request[0].active==1);CHECK(rr_media_auto_advance(&t)==0);
    CHECK(!t.request[0].active&&t.request[0].inserted==-1); /* Accepted. */
    CHECK(rr_media_apply(&t,blob,size));free(blob);blob=NULL;
    CHECK(t.request[0].inserted==2&&t.request[0].window==RR_MEDIA_REJECT_WINDOW);
    for(unsigned n=0;n<RR_MEDIA_REJECT_WINDOW;n++)CHECK(rr_media_auto_advance(&t)==0);
    CHECK(!t.request[0].active);
    /* A later request starts after the accepted disk; every refusal exhausts it. */
    mask&=~1u;CHECK(rr_media_auto_advance(&t)==0);polls[0]++;CHECK(rr_media_auto_advance(&t)==0);polls[0]++;
    for(unsigned n=3;n<RR_MEDIA_INSERT_WAIT;n++)CHECK(rr_media_auto_advance(&t)==0);
    CHECK(rr_media_auto_advance(&t)==1);CHECK(t.selected[0]==0&&t.selected[1]==1);
    mask&=~1u;for(unsigned n=1;n<RR_MEDIA_INSERT_WAIT;n++)CHECK(rr_media_auto_advance(&t)==0);
    CHECK(rr_media_auto_advance(&t)==1);CHECK(t.selected[0]==1&&t.selected[1]==-1&&t.request[0].moved);
    mask&=~1u;CHECK(rr_media_auto_advance(&t)==0);CHECK(mask==2&&t.selected[1]==1);
    /* The disk the game ejected is offered last, after every other was refused (a game that asks for its system disk
     * again gets it back); refused too, the request is exhausted. */
    for(unsigned n=2;n<RR_MEDIA_INSERT_WAIT;n++)CHECK(rr_media_auto_advance(&t)==0);
    CHECK(rr_media_auto_advance(&t)==1);CHECK(mask==3&&t.selected[0]==2&&t.selected[1]==1&&!t.request[0].moved);
    mask&=~1u;
    for(unsigned n=0;n<4*RR_MEDIA_INSERT_WAIT;n++)CHECK(rr_media_auto_advance(&t)==0);
    CHECK(t.request[0].active==2&&!(mask&1)); /* The player decides now. */
    CHECK(rr_media_swap(&t,0,0));CHECK(!t.request[0].active&&mask==3);
    /* A host eject alone never starts a request; a blink on that empty drive
     * does, without taking the other drive's disk. */
    CHECK(rr_media_swap(&t,1,-1));polls[1]++;
    for(unsigned n=0;n<4*RR_MEDIA_INSERT_WAIT;n++)CHECK(rr_media_auto_advance(&t)==0);
    mask|=1u<<9;CHECK(rr_media_auto_advance(&t)==1);CHECK(t.selected[0]==0&&t.selected[1]==1&&!t.request[1].moved);
    puts("media session: swap, duplicate, physical presence, restart, snapshot, corruption, guest requests, refusals and file rewind checks passed");
    return 0;
}
