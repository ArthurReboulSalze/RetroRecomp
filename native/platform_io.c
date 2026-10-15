#include "platform_io.h"
#ifndef _WIN32
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <stdint.h>
#include <sys/stat.h>
#include <sys/file.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <ctype.h>
unsigned long rr_process_id(void) { return (unsigned long)getpid(); }
int rr_flush_file(FILE *f) { return fflush(f)==0 && fsync(fileno(f))==0; }

int rr_to_utf8(const wchar_t *s,char *out,size_t cap) {
    size_t n=0;
    for(;*s;++s) {
        uint32_t c=(uint32_t)*s;unsigned z=c<0x80?1:c<0x800?2:c<0x10000?3:4;
        if(c>0x10ffff || (c>=0xd800 && c<=0xdfff) || n+z>=cap)return 0;
        if(z==1)out[n++]=(char)c;
        else { out[n++]=(char)((z==2?0xc0:z==3?0xe0:0xf0)|(c>>(6*(z-1))));
            for(unsigned i=z-1;i;--i)out[n++]=(char)(0x80|((c>>(6*(i-1)))&63)); }
    }
    if(!cap)return 0;out[n]=0;return 1;
}
int rr_from_utf8(const char *s,wchar_t *out,size_t cap) {
    size_t n=0;
    while(*s) {
        uint32_t c=(unsigned char)*s++;unsigned z;
        if(c<128)z=0;else if(c>=0xc2 && c<0xe0){c&=31;z=1;}
        else if(c<0xf0 && c>=0xe0){c&=15;z=2;}else if(c>=0xf0 && c<=0xf4){c&=7;z=3;}else return 0;
        unsigned width=z;
        while(z--) {unsigned d=(unsigned char)*s++;if((d&0xc0)!=0x80)return 0;c=(c<<6)|(d&63);}
        if((width==1 && c<128)||(width==2 && c<0x800)||(width==3 && c<0x10000)||c>0x10ffff||(c>=0xd800&&c<=0xdfff)||n+1>=cap)return 0;
        out[n++]=(wchar_t)c;
    }
    if(!cap)return 0;out[n]=0;return 1;
}
static int path(const wchar_t *p,char *out) { return rr_to_utf8(p,out,32768); }
int rr_exists(const wchar_t *p) { char b[32768];struct stat st;return path(p,b)&&stat(b,&st)==0; }
int rr_mkdir(const wchar_t *p) { char b[32768];struct stat st;if(!path(p,b))return 0;return mkdir(b,0700)==0 || (errno==EEXIST && stat(b,&st)==0 && S_ISDIR(st.st_mode)); }
FILE *rr_fopen(const wchar_t *p,const wchar_t *m) { char b[32768],mode[16];return path(p,b)&&rr_to_utf8(m,mode,sizeof mode)?fopen(b,mode):NULL; }
void rr_remove(const wchar_t *p) { char b[32768];if(path(p,b))unlink(b); }
int rr_replace(const wchar_t *a,const wchar_t *b) {
    char x[32768],y[32768];if(!path(a,x)||!path(b,y))return 0;
    int fd=open(x,O_RDONLY);if(fd<0)return 0;int ok=fsync(fd)==0;close(fd);
    if(!ok || rename(x,y))return 0;
    char *slash=strrchr(y,'/');if(slash){*slash=0;fd=open(y,O_RDONLY|O_DIRECTORY);if(fd>=0){ok=fsync(fd)==0;close(fd);}}
    return ok;
}
int rr_copy_new(const wchar_t *a,const wchar_t *b) {
    char x[32768],y[32768];if(!path(a,x)||!path(b,y))return 0;
    FILE *in=fopen(x,"rb");if(!in)return 0;
    int fd=open(y,O_WRONLY|O_CREAT|O_EXCL,0600);if(fd<0){fclose(in);return 0;}
    FILE *out=fdopen(fd,"wb");if(!out){close(fd);fclose(in);unlink(y);return 0;}
    char buf[4096];size_t z;int ok=1;while((z=fread(buf,1,sizeof buf,in)))if(fwrite(buf,1,z,out)!=z){ok=0;break;}
    if(ferror(in)||fflush(out)||fsync(fd))ok=0;fclose(in);if(fclose(out))ok=0;if(!ok)unlink(y);return ok;
}
int rr_executable_directory(wchar_t *out,size_t cap) {
    char b[32768];ssize_t n=readlink("/proc/self/exe",b,sizeof b-1);
    if(n<=0 || (size_t)n>=sizeof b-1)return 0;b[n]=0;char *slash=strrchr(b,'/');if(!slash)return 0;*slash=0;return rr_from_utf8(b,out,cap);
}
static char *trim(char *s) {while(isspace((unsigned char)*s))++s;size_t n=strlen(s);while(n&&isspace((unsigned char)s[n-1]))s[--n]=0;return s;}
int rr_ini_get(const wchar_t *section,const wchar_t *key,const wchar_t *fallback,wchar_t *out,unsigned cap,const wchar_t *p) {
    char sec[256],entry[256],line[4096];int active=0;
    if(!rr_to_utf8(section,sec,sizeof sec)||!rr_to_utf8(key,entry,sizeof entry)||!cap)return 0;
    wcsncpy(out,fallback,cap-1);out[cap-1]=0;
    FILE *f=rr_fopen(p,L"rb");if(!f)return (int)wcslen(out);
    while(fgets(line,sizeof line,f)) {
        char *s=trim(line);if(*s=='['){char *end=strchr(s,']');if(end){*end=0;active=!strcasecmp(s+1,sec);}continue;}
        if(!active||*s==';'||*s=='#')continue;char *eq=strchr(s,'=');if(!eq)continue;*eq=0;
        if(!strcasecmp(trim(s),entry)){wchar_t value[4096];if(rr_from_utf8(trim(eq+1),value,4096)){wcsncpy(out,value,cap-1);out[cap-1]=0;}break;}
    }
    fclose(f);return (int)wcslen(out);
}
int rr_ini_int(const wchar_t *s,const wchar_t *k,int d,const wchar_t *p) {wchar_t v[64],*end;rr_ini_get(s,k,L"",v,64,p);if(!*v)return d;long n=wcstol(v,&end,10);return *end?d:(int)n;}
int rr_ini_set(const wchar_t *section,const wchar_t *key,const wchar_t *value,const wchar_t *p) {
    /* Read/merge/write under a stable sibling flock. Atomic rename never loses
     * another running game's setting and never truncates the previous file. */
    char name[32768],lockname[32768],temp[32768],sec[256],entry[256],v[4096];
    if(!path(p,name)||strlen(name)>32600||!rr_to_utf8(section,sec,sizeof sec)||!rr_to_utf8(key,entry,sizeof entry)||!rr_to_utf8(value,v,sizeof v)||strchr(v,'\n')||strchr(v,'\r'))return 0;
    snprintf(lockname,sizeof lockname,"%s.lock",name);int lock=open(lockname,O_CREAT|O_RDWR,0600);if(lock<0)return 0;if(flock(lock,LOCK_EX)){close(lock);return 0;}
    snprintf(temp,sizeof temp,"%s.XXXXXX",name);int fd=mkstemp(temp);FILE *out=fd<0?NULL:fdopen(fd,"wb");
    int ok=out!=NULL,active=0,found=0;FILE *in=ok?fopen(name,"rb"):NULL;char line[4096];
    while(in&&fgets(line,sizeof line,in)) {
        char copy[4096];snprintf(copy,sizeof copy,"%s",line);char *s=trim(copy);
        if(*s=='['){if(active&&!found){fprintf(out,"%s=%s\n",entry,v);found=1;}char *end=strchr(s,']');if(end)*end=0;active=end&&!strcasecmp(s+1,sec);}
        char *eq=strchr(s,'=');if(active&&eq){*eq=0;if(!strcasecmp(trim(s),entry)){if(!found)fprintf(out,"%s=%s\n",entry,v);found=1;continue;}}
        fputs(line,out);
        if(line[0] && line[strlen(line)-1]!='\n')fputc('\n',out);
    }
    if(in){if(ferror(in))ok=0;fclose(in);}
    if(out){if(!found){if(!active)fprintf(out,"\n[%s]\n",sec);fprintf(out,"%s=%s\n",entry,v);}if(fflush(out)||fsync(fd)||ferror(out))ok=0;if(fclose(out))ok=0;}
    else if(fd>=0)close(fd);
    if(ok)ok=rename(temp,name)==0;if(!ok)unlink(temp);flock(lock,LOCK_UN);close(lock);return ok;
}
#endif
