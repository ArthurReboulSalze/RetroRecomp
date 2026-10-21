/* Original Retro-Recomp code, MIT. Private staged floppy sessions only.
 * Snapshot checksums detect accidental corruption, not adversarial signatures. */
#include "media_session.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <errno.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#endif
#define HEADER_BYTES 192u
#define FNV_START UINT64_C(14695981039346656037)
#ifdef _WIN32
static int wide_path(const char*name,wchar_t*out){return MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,name,-1,out,RR_MEDIA_PATH)>0;}
static FILE *open_file(const char*name,const char*mode){wchar_t wname[RR_MEDIA_PATH],wmode[8];
    return wide_path(name,wname)&&MultiByteToWideChar(CP_UTF8,0,mode,-1,wmode,8)?_wfopen(wname,wmode):NULL;}
static int remove_file(const char*name){wchar_t wname[RR_MEDIA_PATH];return wide_path(name,wname)?_wremove(wname):-1;}
#else
static FILE *open_file(const char*name,const char*mode){return fopen(name,mode);}
static int remove_file(const char*name){return remove(name);}
#endif
static uint64_t hash(const void *data,size_t size) {
    uint64_t out=FNV_START; const unsigned char *p=(const unsigned char*)data;
    while(size--){out^=*p++;out*=UINT64_C(1099511628211);}return out;
}
static void put32(unsigned char *p,uint32_t value){unsigned n;for(n=0;n<4;n++)p[n]=(unsigned char)(value>>(n*8));}
static uint32_t get32(const unsigned char *p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static void put64(unsigned char *p,uint64_t value){unsigned n;for(n=0;n<8;n++)p[n]=(unsigned char)(value>>(n*8));}
static uint64_t get64(const unsigned char *p){return (uint64_t)get32(p)|(uint64_t)get32(p+4)<<32;}
static int error(RRMediaSession*s,const char*message){snprintf(s->error,sizeof(s->error),"%s",message);return 0;}
const char *rr_media_error(const RRMediaSession*s){return s->error;}
static int path(RRMediaSession*s,unsigned index,char*out,size_t capacity,const char*suffix){
    int n=snprintf(out,capacity,"%s/%s%s",s->directory,s->names[index],suffix?suffix:"");return n>0&&(size_t)n<capacity;
}
static int safe_file(const char*name,int allow_missing){
    char checked[RR_MEDIA_PATH];size_t n,len=strlen(name);
    if(!len||len>=sizeof(checked))return 0;
    /* Check every existing parent, preventing a media-directory link from
     * redirecting writes to the supplied source collection. */
    memcpy(checked,name,len+1);
    for(n=1;n<=len;n++)if(checked[n]=='/'||checked[n]=='\\'||!checked[n]){
        char c=checked[n];checked[n]=0;
        if(strlen(checked)==2&&checked[1]==':'){checked[n]=c;continue;}
#ifdef _WIN32
        wchar_t wname[RR_MEDIA_PATH];DWORD flags;
        if(!wide_path(checked,wname))return 0;
        flags=GetFileAttributesW(wname);
        if(flags==INVALID_FILE_ATTRIBUTES){checked[n]=c;if(n==len&&allow_missing&&GetLastError()==ERROR_FILE_NOT_FOUND)return 1;return 0;}
        if(flags&FILE_ATTRIBUTE_REPARSE_POINT)return 0;
#else
        struct stat lst;
        if(lstat(checked,&lst)){checked[n]=c;return n==len&&allow_missing&&errno==ENOENT;}
        if(S_ISLNK(lst.st_mode))return 0;
#endif
        checked[n]=c;
    }
#ifdef _WIN32
    {wchar_t wname[RR_MEDIA_PATH];BY_HANDLE_FILE_INFORMATION info;HANDLE h;int okay;
     if(!wide_path(name,wname))return 0;
     h=CreateFileW(wname,0,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
     if(h==INVALID_HANDLE_VALUE)return allow_missing&&GetLastError()==ERROR_FILE_NOT_FOUND;
     okay=GetFileInformationByHandle(h,&info)&&!(info.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT))&&info.nNumberOfLinks==1;
     CloseHandle(h);return okay;}
#else
    {struct stat st;if(stat(name,&st))return allow_missing&&errno==ENOENT;
     return S_ISREG(st.st_mode)&&st.st_nlink==1;}
#endif
}
static int read_file(const char*name,unsigned char**data,size_t*size){
    FILE*f;long end;unsigned char*b;
    if(!safe_file(name,0)||(f=open_file(name,"rb"))==NULL)return 0;
    if(fseek(f,0,SEEK_END)||(end=ftell(f))<1||(unsigned long)end>RR_MEDIA_IMAGE_MAX||fseek(f,0,SEEK_SET)){fclose(f);return 0;}
    b=(unsigned char*)malloc((size_t)end);if(!b){fclose(f);return 0;}
    {int okay=fread(b,1,(size_t)end,f)==(size_t)end;int closed=fclose(f);if(!okay||closed){free(b);return 0;}}
    *data=b;*size=(size_t)end;return 1;
}
static int replace_file(const char*name,const void*data,size_t size){
    char temp[RR_MEDIA_PATH];FILE*f;int n=snprintf(temp,sizeof(temp),"%s.rr-new",name);
    if(n<0||(size_t)n>=sizeof(temp)||!safe_file(name,1)||!safe_file(temp,1))return 0;
    /* Stale temporary files are never silently adopted or truncated. */
    if((f=open_file(temp,"rb"))!=NULL){fclose(f);return 0;}
    f=open_file(temp,"wb");if(!f)return 0;
    if(fwrite(data,1,size,f)!=size){fclose(f);remove_file(temp);return 0;}
    {int flushed=fflush(f);int closed=fclose(f);if(flushed||closed){remove_file(temp);return 0;}}
#ifdef _WIN32
    {wchar_t wtemp[RR_MEDIA_PATH],wname[RR_MEDIA_PATH];
     if(!wide_path(temp,wtemp)||!wide_path(name,wname)||!MoveFileExW(wtemp,wname,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)){remove_file(temp);return 0;}}
#else
    if(rename(temp,name)){remove_file(temp);return 0;}
#endif
    return 1;
}
static int staged_name(const char*name){
    size_t n=strlen(name);
    return n==11&&!memcmp(name,"disk-",5)&&name[5]>='0'&&name[5]<='9'&&name[6]>='0'&&name[6]<='9'&&
           (!strcmp(name+7,".dim")||!strcmp(name+7,".xdf"));
}
static int actual_choice(RRMediaSession*s,unsigned drive){
    return s->ready_mask && !(s->ready_mask()&(1u<<drive))?-1:s->selected[drive];
}
int rr_media_open(RRMediaSession*s,const char*content,const char*session_file,
        const struct retro_disk_control_callback*disk,void(*select_drive)(unsigned),unsigned(*ready_mask)(void)){
    FILE*f;char line[RR_MEDIA_PATH],*slash;unsigned i;uint64_t identity=FNV_START;
    memset(s,0,sizeof(*s));s->selected[0]=s->selected[1]=-1;
    if(!content||!session_file||strlen(content)>=sizeof(s->content)||strlen(session_file)>=sizeof(s->session_file)||
       !disk||!disk->get_num_images||!disk->set_eject_state||!disk->set_image_index||!select_drive||!ready_mask)
        return error(s,"Incomplete private media interface");
    strcpy(s->content,content);strcpy(s->directory,content);strcpy(s->session_file,session_file);
    slash=strrchr(s->directory,'/');{char*b=strrchr(s->directory,'\\');if(b&&(!slash||b>slash))slash=b;}
    if(!slash)return error(s,"Private media path must include its directory");*slash=0;
    if(!safe_file(content,0)||(f=open_file(content,"rb"))==NULL)return error(s,"Private playlist cannot be opened safely");
    while(fgets(line,sizeof(line),f)){
        size_t n=strcspn(line,"\r\n");line[n]=0;
        if(!n||line[0]=='#')continue;
        if(s->count==RR_MEDIA_MAX||!staged_name(line)){fclose(f);return error(s,"Playlist must contain at most ten private disk-NN.dim/xdf files");}
        for(i=0;i<s->count;i++)if(!strcmp(s->names[i],line)){fclose(f);return error(s,"Duplicate private disk path");}
        strcpy(s->names[s->count++],line);
        identity^=hash(line,n);identity*=UINT64_C(1099511628211);
    }
    if(ferror(f)){fclose(f);return error(s,"Private playlist read failed");}fclose(f);
    if(!s->count||disk->get_num_images()!=s->count)return error(s,"Core media count does not match private playlist");
    s->identity=identity;s->disk=*disk;s->select_drive=select_drive;s->ready_mask=ready_mask;
    s->selected[0]=0;s->selected[1]=s->count>1?1:-1;
    for(i=0;i<s->count;i++){unsigned char*b=NULL;size_t size;char name[RR_MEDIA_PATH];
        if(!path(s,i,name,sizeof(name),NULL)||!read_file(name,&b,&size))return error(s,"Unsafe, missing or oversized private disk");free(b);}
    return 1;
}
int rr_media_swap(RRMediaSession*s,unsigned drive,int image){
    int old;
    if(drive>1||image< -1||image>=(int)s->count)return error(s,"Drive or disk index is out of bounds");
    /* A single mutable image cannot be inserted in two buffered drives. */
    if(image>=0&&actual_choice(s,1-drive)==image)return error(s,"Disk is already inserted in the other drive");
    old=actual_choice(s,drive);if(old==image)return 1;
    if(image>=0){char name[RR_MEDIA_PATH];unsigned char*b=NULL;size_t size;
        if(!path(s,(unsigned)image,name,sizeof(name),NULL)||!read_file(name,&b,&size))return error(s,"Requested private disk is unavailable");free(b);}
    s->select_drive(drive);
    if(!s->disk.set_eject_state(true))return error(s,"Core refused disk eject");
    s->selected[drive]=-1;s->empty_frames[drive]=0;
    if(image<0)return 1;
    if(!s->disk.set_image_index((unsigned)image)||!s->disk.set_eject_state(false)||!(s->ready_mask()&(1u<<drive))){
        s->disk.set_eject_state(true);
        if(old>=0&&s->disk.set_image_index((unsigned)old)&&s->disk.set_eject_state(false)&&
           (s->ready_mask()&(1u<<drive)))s->selected[drive]=old;
        return error(s,old>=0&&s->selected[drive]<0?
            "Disk insert failed; the previous disk could not be reinserted":
            "Core could not insert the selected disk");}
    s->selected[drive]=image;return 1;
}
int rr_media_auto_advance(RRMediaSession*s,const RRMediaRule*rules,unsigned count){
    unsigned i;int changes=0;
    for(i=0;i<count;i++){
        if(rules[i].drive>1||(rules[i].previous>=s->count&&rules[i].previous!=RR_MEDIA_MAX)||rules[i].next>=s->count||rules[i].previous==rules[i].next){error(s,"Invalid automatic disk rule");return -1;}
    }
    for(i=0;i<2;i++){
        if(actual_choice(s,i)>=0)s->empty_frames[i]=0;
        else if(s->empty_frames[i]<RR_MEDIA_INSERT_WAIT)s->empty_frames[i]++;
    }
    for(i=0;i<count;i++){
        unsigned d=rules[i].drive;int target=(int)rules[i].next,donor=-1;
        if(actual_choice(s,d)>=0||s->empty_frames[d]<RR_MEDIA_INSERT_WAIT)continue;
        if(rules[i].previous==RR_MEDIA_MAX){
            if(!(s->ready_mask()&(1u<<(8+d)))||!target||actual_choice(s,1-d)!=target-1)continue;
        }else if(s->selected[d]!=(int)rules[i].previous)continue;
        if(actual_choice(s,1-d)==target){donor=(int)(1-d);if(!rr_media_swap(s,(unsigned)donor,-1))return -1;}
        if(!rr_media_swap(s,d,target)){
            if(donor>=0)rr_media_swap(s,(unsigned)donor,target);
            return -1;
        }
        changes++;
    }
    return changes;
}
int rr_media_cycle(RRMediaSession*s,unsigned drive,int direction){
    int n,at;if(drive>1)return error(s,"Invalid drive");at=actual_choice(s,drive);
    for(n=0;n<=(int)s->count;n++){
        at=(at+1+(direction<0?-1:1)+(int)s->count+1)%((int)s->count+1)-1;
        if(at<0||actual_choice(s,1-drive)!=at)return rr_media_swap(s,drive,at);
    }return error(s,"No disk is available for this drive");
}
int rr_media_boot(RRMediaSession*s){
    /* A cold game restart is not a snapshot resume. Restore the original pair
     * even if an automatic transition left a later data disk in drive A. */
    return rr_media_swap(s,0,-1)&&rr_media_swap(s,1,-1)&&rr_media_swap(s,0,0)&&
        rr_media_swap(s,1,s->count>1?1:-1);
}
int rr_media_save_session(RRMediaSession*s){
    unsigned char b[32]={0};memcpy(b,"RRX68DS1",8);put64(b+8,s->identity);put32(b+16,s->count);
    put32(b+20,(uint32_t)(actual_choice(s,0)+1));put32(b+24,(uint32_t)(actual_choice(s,1)+1));put32(b+28,(uint32_t)hash(b,28));
    return replace_file(s->session_file,b,sizeof(b))?1:error(s,"Could not save private disk choices");
}
int rr_media_load_session(RRMediaSession*s){
    unsigned char*b=NULL;size_t size;FILE*f=open_file(s->session_file,"rb");int a,bchoice;
    if(!f)return errno==ENOENT?1:error(s,"Could not read disk choices");fclose(f);
    if(!read_file(s->session_file,&b,&size))return error(s,"Unsafe saved disk choices");
    if(size!=32||memcmp(b,"RRX68DS1",8)||get64(b+8)!=s->identity||get32(b+16)!=s->count||get32(b+28)!=(uint32_t)hash(b,28)||get32(b+20)>s->count||get32(b+24)>s->count){free(b);return error(s,"Saved disk choices do not match this private bundle");}
    a=(int)get32(b+20)-1;bchoice=(int)get32(b+24)-1;free(b);
    if(a>=0&&a==bchoice)return error(s,"Saved disk is inserted twice");
    if(!rr_media_swap(s,0,-1)||!rr_media_swap(s,1,-1))return 0;
    return rr_media_swap(s,0,a)&&rr_media_swap(s,1,bchoice);
}
int rr_media_capture(RRMediaSession*s,void**data,size_t*size){
    unsigned char*files[RR_MEDIA_MAX]={0},*out=NULL;size_t lengths[RR_MEDIA_MAX]={0},total=HEADER_BYTES,at;unsigned i;
    *data=NULL;*size=0;
    for(i=0;i<s->count;i++){char name[RR_MEDIA_PATH];if(!path(s,i,name,sizeof(name),NULL)||!read_file(name,&files[i],&lengths[i]))goto failed;total+=lengths[i];}
    out=(unsigned char*)calloc(1,total);if(!out)goto failed;
    memcpy(out,"RRX68DM1",8);put64(out+8,s->identity);put32(out+16,s->count);
    put32(out+20,(uint32_t)(actual_choice(s,0)+1));put32(out+24,(uint32_t)(actual_choice(s,1)+1));
    /* Previously reserved metadata padding. Keep both the removal interval
     * and the last image identity when F8 lands between eject and insert.
     * Zero identifies an older snapshot, which has no pending transition. */
    put32(out+36,0x1000000u|s->empty_frames[0]|(s->empty_frames[1]<<5)|
        ((unsigned)(s->selected[0]+1)<<12)|((unsigned)(s->selected[1]+1)<<16));
    at=HEADER_BYTES;
    for(i=0;i<s->count;i++){put32(out+32+i*16,(uint32_t)lengths[i]);put64(out+40+i*16,hash(files[i],lengths[i]));memcpy(out+at,files[i],lengths[i]);at+=lengths[i];}
    put32(out+28,(uint32_t)hash(out+32,HEADER_BYTES-32));
    for(i=0;i<s->count;i++)free(files[i]);*data=out;*size=total;return 1;
failed:
    for(i=0;i<s->count;i++)free(files[i]);free(out);return error(s,"Could not capture private disk files");
}
int rr_media_validate(RRMediaSession*s,const void*data,size_t size){
    const unsigned char*b=(const unsigned char*)data;size_t at=HEADER_BYTES;unsigned i,a,c;
    if(!b||size<HEADER_BYTES||size>RR_MEDIA_SNAPSHOT_MAX||memcmp(b,"RRX68DM1",8)||get64(b+8)!=s->identity||get32(b+16)!=s->count||get32(b+28)!=(uint32_t)hash(b+32,HEADER_BYTES-32))return error(s,"Disk snapshot identity or header is invalid");
    a=get32(b+20);c=get32(b+24);if(a>s->count||c>s->count||(a&&a==c))return error(s,"Disk snapshot drive selection is invalid");
    {unsigned pending=get32(b+36),p=(pending>>12)&15u,q=(pending>>16)&15u;
     unsigned x=pending&31u,y=(pending>>5)&31u;
     if(pending&&(pending&~0x10ff3ffu||!(pending&0x1000000u)||p>s->count||q>s->count||
        x>RR_MEDIA_INSERT_WAIT||y>RR_MEDIA_INSERT_WAIT||(a&&(p!=a||x))||(c&&(q!=c||y))))
        return error(s,"Disk snapshot pending insertion is invalid");}
    for(i=0;i<s->count;i++){size_t n=get32(b+32+i*16);char name[RR_MEDIA_PATH];
        if(!n||n>RR_MEDIA_IMAGE_MAX||n>size-at||get64(b+40+i*16)!=hash(b+at,n)||!path(s,i,name,sizeof(name),NULL)||!safe_file(name,0))return error(s,"Disk snapshot data or private destination is invalid");at+=n;}
    return at==size?1:error(s,"Disk snapshot has trailing data");
}
static int apply_files(RRMediaSession*s,const unsigned char*b){
    unsigned i;size_t at=HEADER_BYTES;
    for(i=0;i<s->count;i++){char name[RR_MEDIA_PATH];size_t n=get32(b+32+i*16);
        if(!path(s,i,name,sizeof(name),NULL)||!replace_file(name,b+at,n))return error(s,"Could not restore private disk file");at+=n;}
    return 1;
}
static void apply_pending(RRMediaSession*s,const unsigned char*b){
    unsigned pending=get32(b+36);s->empty_frames[0]=pending&31u;s->empty_frames[1]=(pending>>5)&31u;
    if(pending){s->selected[0]=(int)((pending>>12)&15u)-1;s->selected[1]=(int)((pending>>16)&15u)-1;}
}
int rr_media_apply(RRMediaSession*s,const void*data,size_t size){
    const unsigned char*b=(const unsigned char*)data;void*before=NULL;size_t before_size;int a,c;
    if(!rr_media_validate(s,data,size)||!rr_media_capture(s,&before,&before_size))return 0;
    /* Eject flushes owned dirty buffers before replacing private files. Core
     * unserialize then restores the captured in-memory sectors and cursors. */
    if(!rr_media_swap(s,0,-1)||!rr_media_swap(s,1,-1)||!apply_files(s,b)){
        apply_files(s,(const unsigned char*)before);free(before);return 0;}
    a=(int)get32(b+20)-1;c=(int)get32(b+24)-1;
    if(!rr_media_swap(s,0,a)||!rr_media_swap(s,1,c)){
        rr_media_swap(s,0,-1);rr_media_swap(s,1,-1);apply_files(s,(const unsigned char*)before);
        rr_media_swap(s,0,(int)get32((const unsigned char*)before+20)-1);
        rr_media_swap(s,1,(int)get32((const unsigned char*)before+24)-1);
        apply_pending(s,(const unsigned char*)before);free(before);return 0;}
    apply_pending(s,b);
    free(before);return 1;
}
