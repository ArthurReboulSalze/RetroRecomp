/* Authored snapshot transaction fixtures, MIT. No guest/game bytes. */
#include "state_store.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif

typedef struct Machine {
    unsigned char core[64], auxiliary[32];
    size_t core_size, auxiliary_size;
    const char *mode;
    unsigned loads, applies, captures, validates;
} Machine;

static bool save_core(void *context, void *data, size_t size) {
    Machine *m = (Machine *)context;
    ++m->captures;
    if (size != m->core_size) return false;
    memcpy(data,m->core,size);
    return strcmp(m->mode,"capture-fail") != 0;
}
static bool load_core(void *context, const void *data, size_t size) {
    Machine *m = (Machine *)context;
    ++m->loads;
    if (!size || size > sizeof(m->core)) return false;
    memcpy(m->core,data,size);
    m->core_size = size;
    if (!strcmp(m->mode,"rollback-fail")) return false;
    return strcmp(m->mode,"core-fail") || m->core[0] != 42;
}
static bool capture_auxiliary(void *context, void *data, size_t size) {
    Machine *m = (Machine *)context;
    if (size != m->auxiliary_size) return false;
    memcpy(data,m->auxiliary,size);
    return true;
}
static bool validate_auxiliary(void *context, const void *data, size_t size) {
    Machine *m = (Machine *)context;
    ++m->validates;
    return size && size <= sizeof(m->auxiliary) &&
        ((const unsigned char *)data)[0] == 12 &&
        strcmp(m->mode,"aux-reject");
}
static bool apply_auxiliary(void *context, const void *data, size_t size) {
    Machine *m = (Machine *)context;
    ++m->applies;
    if (!size || size > sizeof(m->auxiliary)) return false;
    memcpy(m->auxiliary,data,size);
    m->auxiliary_size = size;
    return strcmp(m->mode,"aux-fail") || m->auxiliary[0] != 12;
}

static int run(int argc, char **argv) {
    static const char identity[] = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    static const char compatibility[] = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789";
    static const char other[] = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff";
    Machine m;
    RRStateIO io;
    RRStateResult status;
    char error[160];
    bool writing;
    if (argc < 3 || argc > 4) return 2;
    memset(&m,0,sizeof(m)); memset(&io,0,sizeof(io));
    writing = !strcmp(argv[1],"write");
    m.mode = argc == 4 ? argv[3] : "normal";
    memset(m.core,writing?42:77,sizeof(m.core));
    memset(m.auxiliary,writing?12:66,sizeof(m.auxiliary));
    io.context=&m; io.identity=identity; io.compatibility=compatibility;
    m.core_size=32; m.auxiliary_size=16;
    if (!strcmp(m.mode,"expanded")) { m.core_size=48; m.auxiliary_size=24; }
    if (!strcmp(m.mode,"compact")) { m.core_size=16; m.auxiliary_size=8; }
    io.core_size=m.core_size; io.auxiliary_size=m.auxiliary_size;
    io.save_core=save_core; io.load_core=load_core;
    io.capture_auxiliary=capture_auxiliary;
    io.validate_auxiliary=validate_auxiliary; io.apply_auxiliary=apply_auxiliary;
    if (!strcmp(m.mode,"identity")) io.identity=other;
    if (!strcmp(m.mode,"compatibility")) io.compatibility=other;
    if (!strcmp(m.mode,"oversize")) io.core_size=RR_X68K_STATE_MAX_CORE+1u;
    if (!strcmp(m.mode,"malformed-digest")) io.identity="not-a-digest";
    if (!strcmp(m.mode,"noaux")) io.auxiliary_size=0;
    status=writing?rr_x68k_state_save(argv[2],&io,error,sizeof(error)):
        rr_x68k_state_load(argv[2],&io,error,sizeof(error));
    printf("{\"status\":%d,\"core\":%u,\"auxiliary\":%u,\"loads\":%u,"
           "\"applies\":%u,\"captures\":%u,\"validates\":%u,"
           "\"core_size\":%u,\"auxiliary_size\":%u,\"message\":\"%s\"}\n",
           (int)status,(unsigned)m.core[0],(unsigned)m.auxiliary[0],m.loads,
           m.applies,m.captures,m.validates,(unsigned)m.core_size,(unsigned)m.auxiliary_size,error);
    return 0;
}

#ifdef _WIN32
int wmain(int argc, wchar_t **argv) {
    char **utf8=(char **)calloc((size_t)argc,sizeof(*utf8));
    int i,code;
    if (!utf8) return 2;
    for (i=0;i<argc;++i) {
        int count=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,argv[i],-1,NULL,0,NULL,NULL);
        utf8[i]=(char *)malloc((size_t)count);
        if (!utf8[i] || !WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,argv[i],-1,utf8[i],count,NULL,NULL))
            return 2;
    }
    code=run(argc,utf8);
    for (i=0;i<argc;++i) free(utf8[i]);
    free(utf8);
    return code;
}
#else
int main(int argc,char **argv) { return run(argc,argv); }
#endif
