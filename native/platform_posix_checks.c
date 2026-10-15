/* Authored file/UTF-8/settings tests; no console ROM or display. */
#undef NDEBUG
#include <assert.h>
#include "platform_io.h"
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>
int main(int argc,char **argv) {
    assert(argc==2);wchar_t root[32768],ini[32768],key[64],value[128],wide[128];char utf8[512];
    assert(rr_from_utf8("caf\xc3\xa9 \xf0\x9f\x8e\xae",wide,128));
    assert(rr_to_utf8(wide,utf8,sizeof utf8)&&!strcmp(utf8,"caf\xc3\xa9 \xf0\x9f\x8e\xae"));
    assert(!rr_from_utf8("\xc0\xaf",wide,128));assert(!rr_from_utf8("\xed\xa0\x80",wide,128));
    assert(!rr_from_utf8("\xf4\x90\x80\x80",wide,128));assert(!rr_from_utf8("\xe2",wide,128));
    assert(!rr_from_utf8("long",wide,2));
    assert(rr_from_utf8(argv[1],root,32768));swprintf(ini,32768,L"%ls/settings.ini",root);
    assert(!rr_exists(ini));assert(rr_ini_int(L"Video",L"filter",7,ini)==7);assert(!rr_exists(ini));
    assert(rr_mkdir(root));
    for(unsigned n=0;n<12;++n){pid_t child=fork();assert(child>=0);if(!child){swprintf(key,64,L"key%u",n);_exit(rr_ini_set(L"Video",key,L"3",ini)?0:1);}}
    for(unsigned n=0;n<12;++n){int status;assert(wait(&status)>0&&WIFEXITED(status)&&WEXITSTATUS(status)==0);}
    for(unsigned n=0;n<12;++n){swprintf(key,64,L"key%u",n);assert(rr_ini_int(L"video",key,0,ini)==3);}
    assert(rr_ini_set(L"Interface",L"language",L"fr",ini));
    assert(rr_ini_set(L"Video",L"display_mode",L"2",ini));
    assert(rr_ini_int(L"Video",L"key0",0,ini)==3&&rr_ini_int(L"Video",L"display_mode",0,ini)==2);
    rr_ini_get(L"interface",L"language",L"",value,128,ini);assert(!wcscmp(value,L"fr"));
    assert(!rr_ini_set(L"Video",L"filter",L"1\n[Other]",ini));
    puts("PASS: strict UTF-8, lazy reads, atomic settings, 12 concurrent writers, section preservation.");return 0;
}
