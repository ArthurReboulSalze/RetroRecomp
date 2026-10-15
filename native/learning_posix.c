/* Converter-only observation journal. Gameplay feedback is buffered separately. */
#include "learning.h"
#include "embedded_rom.h"
#include "paths.h"
#include "platform_io.h"
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/file.h>

static wchar_t journal[RETRO_PATH_CAP],code_journal[RETRO_PATH_CAP],directory[RETRO_PATH_CAP];
static char lock_path[RETRO_PATH_CAP];
static int initialized,available,warned;
int smsrecomp_learning_enabled(void) {const char *v=getenv("RETRO_RECOMP_LEARNING");return v&&!strcmp(v,"1");}
static int initialize(void) {
    if(!smsrecomp_learning_enabled())return 0;if(initialized)return available;initialized=1;
    char root[RETRO_PATH_CAP],entry[256];wchar_t wide[RETRO_PATH_CAP];
    const char *custom=getenv("RETRO_RECOMP_LIBRARY_DIR");if(!custom||!*custom)custom=getenv("SMSRECOMP_LIBRARY_DIR");
    if(custom&&*custom){if(strlen(custom)>sizeof root-512)return 0;snprintf(root,sizeof root,"%s",custom);}
    else {if(!retro_data_directory(wide)||!rr_to_utf8(wide,root,sizeof root))return 0;strcat(root,"/library");}
    snprintf(entry,sizeof entry,"%s-%s",sms_game_slug,sms_rom_sha256);
    DIR *d=opendir(root);struct dirent *e;
    if(d){while((e=readdir(d))){size_t n=strlen(e->d_name);if((n==64&&!strcmp(e->d_name,sms_rom_sha256))||(n>65&&e->d_name[n-65]=='-'&&!strcmp(e->d_name+n-64,sms_rom_sha256))){snprintf(entry,sizeof entry,"%s",e->d_name);break;}}closedir(d);}
    char full[RETRO_PATH_CAP];if(snprintf(full,sizeof full,"%s/%s",root,entry)>=(int)sizeof full)return 0;
    if(!rr_from_utf8(full,directory,RETRO_PATH_CAP))return 0;
    swprintf(journal,RETRO_PATH_CAP,L"%ls/observations.log",directory);
    swprintf(code_journal,RETRO_PATH_CAP,L"%ls/native.patterns",directory);
    if(snprintf(lock_path,sizeof lock_path,"%s/entry.lock",full)>=(int)sizeof lock_path)return 0;
    return available=1;
}
FILE *smsrecomp_observations_read(void) {return initialize()?rr_fopen(journal,L"rb"):NULL;}
static int append_record(const wchar_t *path,const char *line) {
    if(!initialize())return 0;int ok=0;
    if(retro_make_directories(directory)) {
        int lock=open(lock_path,O_RDWR|O_CREAT,0600);
        if(lock>=0){if(!flock(lock,LOCK_EX)){FILE *f=rr_fopen(path,L"ab");if(f){ok=fputs(line,f)>=0;if(fflush(f))ok=0;if(fclose(f))ok=0;}flock(lock,LOCK_UN);}close(lock);}
    }
    if(!ok&&!warned){fprintf(stderr,"[learning] library unavailable: observation not saved\n");warned=1;}return ok;
}

int smsrecomp_observe(uint16_t address, uint8_t b0, uint8_t b1, uint8_t b2, uint32_t hash) {
    char line[80];
    snprintf(line, sizeof line, "%04X %02X %02X %02X %08X\n", address, b0, b1, b2, hash);
    return append_record(journal, line);
}

int smsrecomp_observe_code(const uint8_t bytes[4]) {
    /* Small data-only windows, independent of unrelated neighbouring RAM. */
    static uint32_t seen[4096];
    static unsigned count;
    static int loaded, full_warning;
    if (!initialize()) return 0;
    if (!loaded) {
        loaded = 1;
        FILE *file = rr_fopen(code_journal, L"rb");
        if (file) {
            char line[80], extra; unsigned raw;
            while (count < 4096 && fgets(line, sizeof line, file)) {
                if (strlen(line) != 9 || sscanf(line, "%8x %c", &raw, &extra) != 1) continue;
                unsigned i; for (i = 0; i < count && seen[i] != raw; ++i) {}
                if (i == count) seen[count++] = raw;
            }
            fclose(file);
        }
    }
    uint32_t raw = ((uint32_t)bytes[0]<<24) | ((uint32_t)bytes[1]<<16) | ((uint32_t)bytes[2]<<8) | bytes[3];
    for (unsigned i = 0; i < count; ++i) if (seen[i] == raw) return 1;
    if (count == 4096) {
        if (!full_warning) { fprintf(stderr, "[learning] native pattern limit reached (4096)\n"); full_warning = 1; }
        return 0;
    }
    char line[16]; snprintf(line, sizeof line, "%08X\n", raw);
    int ok = append_record(code_journal, line);
    if (ok) seen[count++] = raw;
    return ok;
}
