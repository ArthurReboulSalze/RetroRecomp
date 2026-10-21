/* Original Retro-Recomp disk vectors, MIT. Full machine state is restored.
 * These are authored sector tests against the actual DIM/FDD implementation,
 * not proof of electrical FDC timing or a multi-disk commercial game's prompts. */
#include "disk_checks.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <libretro.h>
#include "fdd.h"
#include "prop.h"
#include "m68000.h"
#include "check_compat.h"
extern unsigned RR_FDD_MediaMask(void);
extern unsigned RR_DIM_BufferMask(void), RR_XDF_BufferMask(void);
typedef struct {const char*name;int passed;} Result;
static int path_for(const char*report,const char*name,char*out,size_t cap){
    const char*slash=strrchr(report,'/'),*back=strrchr(report,'\\');int n;
    if(back&&(!slash||back>slash))slash=back;if(!slash)return 0;
    n=snprintf(out,cap,"%.*s/%s",(int)(slash-report),report,name);return n>0&&(size_t)n<cap;
}
static int authored_dim(const char*name,unsigned char marker){
    unsigned char header[256]={0},block[1024];FILE*f;unsigned t,s;
    /* Type 0, 154 present tracks, 8 x 1024-byte sectors, no overtracks. */
    for(t=0;t<154;t++)header[1+t]=1;
    memcpy(header+194,"Retro-Recomp authored disk fixture",33);
    f=fopen(name,"wb");if(!f)return 0;
    if(fwrite(header,1,sizeof(header),f)!=sizeof(header)){fclose(f);return 0;}
    for(t=0;t<154;t++)for(s=0;s<8;s++){
        memset(block,marker,sizeof(block));
        if(fwrite(block,1,sizeof(block),f)!=sizeof(block)){fclose(f);return 0;}}
    return fclose(f)==0;
}
static int bytes_are(const unsigned char*b,unsigned char value){unsigned i;for(i=0;i<1024;i++)if(b[i]!=value)return 0;return 1;}
static int invalid_image(const char*name){unsigned char header[256];FILE*f=fopen(name,"wb");int okay;
    if(!f)return 0;memset(header,0xff,sizeof(header));okay=fwrite(header,1,sizeof(header),f)==sizeof(header);return fclose(f)==0&&okay;}
static int file_sector(const char*name,unsigned track,unsigned sector,unsigned char value){
    unsigned char b[1024];FILE*f=fopen(name,"rb");int okay;
    if(!f)return 0;okay=!fseek(f,(long)(256+track*8192+(sector-1)*1024),SEEK_SET)&&fread(b,1,sizeof(b),f)==sizeof(b)&&bytes_are(b,value);
    fclose(f);return okay;
}
unsigned rr_x68k_disk_checks(const char*report_path){
    Result results[9]={{"two_authored_images_and_real_drive_presence",0},{"mechanical_ready_delay",0},
        {"separate_drive_sector_markers",0},{"dirty_sector_capture_before_eject",0},
        {"restored_track_and_rotation_cursors",0},{"restored_dirty_sector_bytes",0},
        {"eject_flushes_private_images",0},{"reinsert_reads_saved_private_writes",0},
        {"failed_insert_releases_invalid_format_buffers",0}};
    unsigned mask=0,original_mask=RR_FDD_MediaMask(),i;int restored=0;
    size_t original_size=retro_serialize_size(),fixture_size=0,after_size;
    unsigned cpu_size=m68k_context_size();void*cpu_context=NULL;
    void*original=NULL,*fixture=NULL,*after=NULL;char names[4][512],original_paths[2][sizeof(Config.FDDImage[0])];
    unsigned char sector[1024];FDCID id0={2,0,3,3},id1={3,1,2,3},id;FILE*f;
    memcpy(original_paths,Config.FDDImage,sizeof(original_paths));memset(names,0,sizeof(names));
    if(!original_size||original_size>64u*1024*1024)goto report;
    if(!cpu_size||cpu_size>1024u*1024u)goto report;
    cpu_context=malloc(cpu_size);
    if(!cpu_context||m68k_get_context(cpu_context)!=cpu_size)goto report;
    original=malloc(original_size);if(!original||!retro_serialize(original,original_size))goto report;
    if(!path_for(report_path,"rr-authored-disk-a.dim",names[0],sizeof(names[0]))||
       !path_for(report_path,"rr-authored-disk-b.dim",names[1],sizeof(names[1]))||
       !path_for(report_path,"rr-invalid-disk.dim",names[2],sizeof(names[2]))||
       !path_for(report_path,"rr-invalid-disk.xdf",names[3],sizeof(names[3])))goto restore;
    /* Never overwrite an existing file or accidentally reuse a source path. */
    for(i=0;i<4;i++){f=fopen(names[i],"rb");if(f){fclose(f);goto restore;}}
    if(!authored_dim(names[0],0x41)||!authored_dim(names[1],0x42)||!invalid_image(names[2])||!invalid_image(names[3]))goto restore;
    FDD_EjectFD(0);FDD_EjectFD(1);
    FDD_SetFD(0,names[2],0);FDD_SetFD(1,names[3],0);
    results[8].passed=RR_FDD_MediaMask()==0&&RR_DIM_BufferMask()==0&&RR_XDF_BufferMask()==0;
    FDD_SetFD(0,names[0],0);FDD_SetFD(1,names[1],0);
    results[0].passed=RR_FDD_MediaMask()==3;
    results[1].passed=!FDD_IsReady(0)&&!FDD_IsReady(1);
    FDD_SetFDInt();FDD_SetFDInt();results[1].passed&=!FDD_IsReady(0)&&!FDD_IsReady(1);
    FDD_SetFDInt();results[1].passed&=FDD_IsReady(0)&&FDD_IsReady(1);
    results[2].passed=FDD_Seek(0,4,&id)&&FDD_Read(0,&id0,sector)&&bytes_are(sector,0x41)&&
                      FDD_Seek(1,7,&id)&&FDD_Read(1,&id1,sector)&&bytes_are(sector,0x42);
    memset(sector,0x5a,sizeof(sector));if(!FDD_Write(0,&id0,sector,0))goto restore;
    memset(sector,0x6b,sizeof(sector));if(!FDD_Write(1,&id1,sector,0))goto restore;
    fixture_size=retro_serialize_size();fixture=malloc(fixture_size);
    if(!fixture_size||!fixture||!retro_serialize(fixture,fixture_size))goto restore;
    results[3].passed=file_sector(names[0],4,3,0x41)&&file_sector(names[1],7,2,0x42);
    memset(sector,0xc0,sizeof(sector));FDD_Write(0,&id0,sector,0);FDD_Write(1,&id1,sector,0);
    FDD_Seek(0,12,&id);FDD_Seek(1,16,&id);
    if(!retro_unserialize(fixture,fixture_size))goto restore;
    results[4].passed=FDD_GetCurrentID(0,&id)&&id.c==2&&id.h==0&&id.r==4&&id.n==3;
    results[4].passed&=FDD_GetCurrentID(1,&id)&&id.c==3&&id.h==1&&id.r==3&&id.n==3;
    results[5].passed=FDD_Read(0,&id0,sector)&&bytes_are(sector,0x5a)&&FDD_Read(1,&id1,sector)&&bytes_are(sector,0x6b);
    FDD_EjectFD(0);FDD_EjectFD(1);
    results[6].passed=RR_FDD_MediaMask()==0&&file_sector(names[0],4,3,0x5a)&&file_sector(names[1],7,2,0x6b);
    FDD_SetFD(0,names[0],0);FDD_SetFD(1,names[1],0);
    results[7].passed=FDD_Seek(0,4,&id)&&FDD_Read(0,&id0,sector)&&bytes_are(sector,0x5a)&&
                      FDD_Seek(1,7,&id)&&FDD_Read(1,&id1,sector)&&bytes_are(sector,0x6b);
restore:
    FDD_EjectFD(0);FDD_EjectFD(1);
    for(i=0;i<2;i++)if(original_mask&(1u<<i))FDD_SetFD((int)i,original_paths[i],0);
    if(original&&retro_unserialize(original,original_size)){
        /* Loading SR canonicalizes equivalent Musashi N/Z representations.
         * Preserve the exact pre-diagnostic CPU context before the unchanged
         * whole-state byte comparison, as the video/timing fixtures do.
         * This opaque pointer-bearing context is in-process only: never save
         * it to a file or use it for a player's persisted state. */
        m68k_set_context(cpu_context);
        after_size=retro_serialize_size();after=malloc(after_size);
        restored=after&&after_size==original_size&&retro_serialize(after,after_size)&&!memcmp(original,after,after_size)&&RR_FDD_MediaMask()==original_mask;
    }
    /* Keep authored fixtures for byte inspection; never publish these with a
     * title's supplied media or firmware. Host places this report in .build. */
report:
    free(cpu_context);free(after);free(fixture);free(original);
    for(i=0;i<9;i++)if(results[i].passed)mask|=1u<<i;
    f=fopen(report_path,"wb");if(!f)return 0;
    fprintf(f,"{\"schema\":1,\"suite\":\"authored-disk\",\"mask\":%u,\"expected_mask\":511,\"state_restored\":%s,\"checks\":[",mask,restored?"true":"false");
    for(i=0;i<9;i++)fprintf(f,"%s{\"name\":\"%s\",\"passed\":%s}",i?",":"",results[i].name,results[i].passed?"true":"false");
    fprintf(f,"]}\n");if(fclose(f))return 0;
    return restored?mask:0;
}
