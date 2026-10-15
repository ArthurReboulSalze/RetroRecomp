/* Isolated preparation process: lithogen is intentionally not reentrant. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "lithogen_internal.h"
#include "neogeo_path_io.h"
static void json_string(const char *s) {
    putchar('"');
    if (s) for (; *s; ++s) {
        unsigned c = (unsigned char)*s;
        if (c == '"' || c == '\\') putchar('\\');
        if (c < 32) printf("\\u%04x", c); else putchar(c);
    }
    putchar('"');
}
static void catalogue(void) {
    printf("[");
    for (size_t i = 0; i < nc_num_games; ++i) {
        const nc_game *g = &nc_games[i];
        if (i) putchar(',');
        printf("{\"set\":"); json_string(g->name);
        printf(",\"parent\":"); json_string(g->parent);
        printf(",\"title\":"); json_string(g->fullname);
        printf(",\"board\":"); json_string(g->cart);
        printf(",\"files\":[");
        unsigned first = 1;
        for (unsigned r = 0; r < g->nregions; ++r) {
            const nc_region *reg = &g->regions[r];
            for (unsigned n = 0; n < reg->nloads; ++n) {
                const nc_load *l = &g->loads[reg->load0 + n];
                if (l->kind != NC_LOAD || !l->group) continue;
                if (!first) putchar(','); first = 0;
                printf("{\"name\":"); json_string(l->file);
                printf(",\"crc32\":%u,\"region\":%u,\"optional\":%u}",
                       l->crc, reg->kind, l->optional);
            }
        }
        printf("]}");
    }
    printf("]\n");
}
static int execute(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "--catalogue")) { catalogue(); return 0; }
    if (argc < 4) { fprintf(stderr, "Usage: ng_prepare SET INPUT.zip OUTPUT.neo [PARENT.zip...]\n"); return 2; }
    lithogen_options opt; lithogen_report rep;
    lithogen_options_init(&opt);
    opt.set_name = argv[1]; opt.strict_crc = 1; opt.no_auto_parent = 1;
    opt.aux_zips = (const char *const *)(argv + 4); opt.num_aux_zips = argc - 4;
    lithogen_status result = lithogen_convert(argv[2], argv[3], &opt, &rep);
    if (result != LITHOGEN_OK) {
        fprintf(stderr, "%s: %s\n", lithogen_status_str(result), rep.errstr); return 1;
    }
    printf("{\"ngh\":%u,\"crc_mismatches\":%u,\"missing_optional\":%u}\n",
           rep.ngh, rep.crc_mismatches, rep.missing_optional);
    return 0;
}
#ifdef _WIN32
int wmain(int argc,wchar_t **wide) {
    char **argv=calloc((size_t)argc+1,sizeof *argv);if(!argv)return 3;
    int result=3;
    for(int i=0;i<argc;++i) {
        int n=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[i],-1,NULL,0,NULL,NULL);
        if(!n || !(argv[i]=malloc((size_t)n)))goto done;
        if(!WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[i],-1,argv[i],n,NULL,NULL))goto done;
    }
    result=execute(argc,argv);
done:
    for(int i=0;i<argc;++i)free(argv[i]);free(argv);return result;
}

#else
int main(int argc,char **argv){return execute(argc,argv);}
#endif
