/* First Neo Geo cartridge hardware prototype. Reference execution is counted.
 * No user data or diagnostics are written unless explicitly requested by CLI.
 * Original RetroRecomp contributions: MIT; core notices retain their licences. */
#define WIN32_LEAN_AND_MEAN
#include "platform_io.h"
#include "embedded_resources.h"
#ifdef _WIN32
#include <shellapi.h>
#else
#include <unistd.h>
#endif
#include <SDL.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdarg.h>
#include <string.h>
#include <math.h>
#include "geo.h"
#include "geo_neo.h"
#include "geo_lspc.h"
#include "geo_mixer.h"
#include "m68k/m68k.h"
#include "neogeo_reference.h"
#include "runtime_feedback.h"
#include "neogeo_input.h"
#include "console16_video.h"
#include "ng_game.h"
#include "miniz.h"
#include "neogeo_host.h"
#include "console16_state.h"
#include "neogeo_persistence.h"
int rr16_sdl_main(const char *title,int scale);
void rr16_shutdown(void);
#ifdef RR_NG_NATIVE
#include "neogeo_native.h"
#endif

static uint32_t video[320*264];
static int16_t audio[4096];
static uint64_t pcm_hash=14695981039346656037ull, image_hash=14695981039346656037ull;
static uint64_t samples, nonzero, clipped, empty_queue_frames;
static uint64_t pcm_energy;
static unsigned peak, audio_count, frame, nonuniform_frames;
static unsigned audio_device_rate,audio_device_period,audio_queue_peak;
static double loop_wall_seconds;
static uint8_t pad[2]={0xff,0xff};
static unsigned coin, start;
static FILE *pcm;
static const char *report_path, *capture_dir, *pcm_path;
static int performance_only,frame_diagnostics;
static bool enhanced_mode;
static int enhanced_requested;
static int aes_mode, mode_requested=-1, restart_requested;
static unsigned measure_from,measured_frames,over_budget_frames,frame_histogram[1001];
static uint64_t performance_frequency;
static double simulation_ms,simulation_max_ms;
static unsigned host_measured_frames,host_over_budget_frames;
static double host_busy_ms,host_busy_max_ms,host_present_ms,host_present_max_ms;
static int capture_every=600, headless, frames, scripted;
static const char *save_path,*load_path,*trace_path;
static unsigned save_at;
static struct {unsigned frame;const char *path;} checkpoints[8];
static unsigned checkpoint_count;
static int ignore_load_error,state_loaded;
static int save_failed,load_rejected,persistent_memory,persistent_load_failed;
static FILE *trace_file;
static uint64_t pcm_frame_hash;
static size_t pcm_frame_samples;
typedef struct { unsigned frame,p1,p2,coin,start; } Input;
static Input inputs[8192];
static unsigned input_count, input_pos;

static wchar_t *wide(const char *text) {
    size_t n=strlen(text)+1;
    wchar_t *result=calloc(n,sizeof *result);
    if(result && !rr_from_utf8(text,result,n)){free(result);result=NULL;}
    return result;
}
static FILE *file_open(const char *path,const wchar_t *mode) {
    wchar_t *name=wide(path); FILE *f=name?rr_fopen(name,mode):NULL; free(name);return f;
}
static void log_message(int level,const char *format,...) {
    if(level<GEO_LOG_WRN)return;
    va_list ap;va_start(ap,format);vfprintf(stderr,format,ap);va_end(ap);
}
static unsigned input_pad(unsigned port) { return port<2?pad[port]:0xff; }
static unsigned status_a(void) { return (0x07u&~coin)|0x18u; }
static unsigned status_b(void) { return rr_ng_status_b(start | (aes_mode?((coin&1)<<1)|((coin&2)<<2):0)); }
static unsigned system_type(void) { return 0xc0; }
static unsigned dips(void) { return 0xff; }
static unsigned unused(void) { return 0xff; }
static void audio_ready(size_t count) {
    if(count>4096) { fprintf(stderr,"Audio frame exceeds buffer.\n");exit(3); }
    audio_count=(unsigned)count;
    for(size_t n=0;frame_diagnostics && n<count;++n) {
        int sample=audio[n], magnitude=sample<0?-sample:sample;
        pcm_hash=(pcm_hash^(uint16_t)sample)*1099511628211ull;
        pcm_frame_hash=(pcm_frame_hash^(uint16_t)sample)*1099511628211ull;
        ++samples;nonzero+=sample!=0;clipped+=magnitude>=32767;
        pcm_energy+=(uint64_t)((int64_t)sample*sample);
        if((unsigned)magnitude>peak)peak=(unsigned)magnitude;
    }
    pcm_frame_samples+=count;
    if(pcm && fwrite(audio,sizeof *audio,count,pcm)!=count) { fprintf(stderr,"PCM write failed.\n");exit(3); }
}
static void *resource(unsigned id,size_t *size) {
    return (void*)rr_resource(id,size);
}
static int load_script(const char *path) {
    FILE *f=file_open(path,L"rb");if(!f)return 0;
    char line[256];unsigned last=0;
    while(fgets(line,sizeof line,f)) {
        if(line[0]=='#' || line[0]=='\n' || line[0]=='\r')continue;
        if(input_count>=8192) { fclose(f);return 0; }
        Input *row=&inputs[input_count];
        if(sscanf(line,"%u %x %x %x %x",&row->frame,&row->p1,&row->p2,&row->coin,&row->start)!=5 ||
            row->frame<last || row->p1>255 || row->p2>255 || row->coin>3 || row->start>15) { fclose(f);return 0; }
        last=row->frame;++input_count;
    }
    fclose(f);scripted=1;return input_count!=0;
}
static void update_input(void) {
    if(scripted) {
        while(input_pos<input_count && inputs[input_pos].frame<=frame) {
            Input *row=&inputs[input_pos++];pad[0]=(uint8_t)~row->p1;pad[1]=(uint8_t)~row->p2;
            coin=row->coin;start=row->start;
        }
        return;
    }
}
static void capture(void) {
    if(!capture_dir || frame%capture_every)return;
    char path[4096];snprintf(path,sizeof path,"%s/frame-%06u.bmp",capture_dir,frame);
    SDL_Surface *surface=SDL_CreateRGBSurfaceWithFormatFrom(video+320*24,320,224,32,320*4,SDL_PIXELFORMAT_RGB888);
    /* SDL owns its own CRT file handles; no FILE* crosses the static CRTs. */
    SDL_RWops *rw=SDL_RWFromFile(path,"wb");
    if(!surface||!rw) { fprintf(stderr,"Frame capture failed: %s\n",SDL_GetError());exit(3); }
    if(SDL_SaveBMP_RW(surface,rw,1)) { fprintf(stderr,"Frame capture failed: %s\n",SDL_GetError());exit(3); }
    SDL_FreeSurface(surface);
}
static uint64_t extended_hardware_hash(void) {
    uint64_t h=14695981039346656037ull;
    size_t size=geo_state_size();const uint8_t *data=geo_state_save_raw();
    for(size_t n=0;n<size;++n)h=(h^data[n])*1099511628211ull;
    uint8_t ym[16];rr_ng_ym_extra_save(ym,sizeof ym);
    for(unsigned n=0;n<sizeof ym;++n)h=(h^ym[n])*1099511628211ull;
    uint8_t board[16];rr_ng_board_extra_save(board,sizeof board);
    for(unsigned n=0;n<sizeof board;++n)h=(h^board[n])*1099511628211ull;
    uint8_t pipeline[2592];rr_ng_lspc_extra_save(pipeline,sizeof pipeline);
    for(unsigned n=0;n<sizeof pipeline;++n)h=(h^pipeline[n])*1099511628211ull;
    return h;
}
static uint32_t extra_word(const uint8_t *data,unsigned offset) {
    return (uint32_t)data[offset]|((uint32_t)data[offset+1]<<8)|
           ((uint32_t)data[offset+2]<<16)|((uint32_t)data[offset+3]<<24);
}
static uint64_t extended_cpu_hash(void) {
    uint64_t h=14695981039346656037ull;
    for(unsigned n=M68K_REG_D0;n<=M68K_REG_PC;++n)h=(h^m68k_get_reg(NULL,(m68k_register_t)n))*1099511628211ull;
    uint8_t extra[32];rr_ng_cpu_extra_save(extra,sizeof extra);
    /* Only called after geo_exec. The next m68k_execute overwrites both
     * expired slice counters before executing or accepting an interrupt.
     * Bus-read counts can shift them together without changing retired clocks.
     * Compare the elapsed difference here; snapshots still retain both raw
     * values, and the diagnostic report exposes them separately. */
    uint32_t retired=extra_word(extra,20)-extra_word(extra,16);
    memset(extra+16,0,8);
    for(unsigned n=0;n<4;++n)extra[16+n]=(uint8_t)(retired>>(8*n));
    for(unsigned n=0;n<sizeof extra;++n)h=(h^extra[n])*1099511628211ull;
    return h;
}
static int state_file(const char *path,int load) {
    wchar_t *name=wide(path);int ok=name && rr16_state_file(name,load!=0);free(name);return ok;
}
static void step_frame(void) {
    uint64_t begun=performance_only?SDL_GetPerformanceCounter():0;
    rr_ng_persist_activity(pad[0]!=0xff || pad[1]!=0xff || coin || start);
    pcm_frame_hash=14695981039346656037ull;pcm_frame_samples=0;audio_count=0;
    geo_exec();++frame;
    uint64_t hash=0;
    if(frame_diagnostics) {
        hash=rr16_video_hash(video+320*24,320,320,224,224);
        image_hash=(image_hash^hash)*1099511628211ull;
        for(unsigned n=1;n<320*224;++n)if(video[320*24+n]!=video[320*24]) {++nonuniform_frames;break;}
    }
    if(trace_file)fprintf(trace_file,"%u,%016llx,%016llx,%016llx,%016llx,%016llx,%llu\n",
        frame,extended_cpu_hash(),extended_hardware_hash(),rr_ng_z80_state_hash(),hash,pcm_frame_hash,(uint64_t)pcm_frame_samples);
    capture();
    if(save_path && save_at==frame && !state_file(save_path,0))save_failed=1;
    for(unsigned i=0;i<checkpoint_count;++i)
        if(checkpoints[i].frame==frame && !state_file(checkpoints[i].path,0))save_failed=1;
    if(performance_only && frame>measure_from) {
        double ms=1000.0*(SDL_GetPerformanceCounter()-begun)/performance_frequency;
        ++measured_frames;simulation_ms+=ms;if(ms>simulation_max_ms)simulation_max_ms=ms;
        if(ms>1000.0/59.185606)++over_budget_frames;
        unsigned bin=(unsigned)(ms*10);if(bin>1000)bin=1000;++frame_histogram[bin];
    }
}
uint32_t *rr_ng_visible_pixels(void) {return video+320*24;}
const int16_t *rr_ng_pcm(size_t *count) {*count=audio_count;return audio;}
void rr_ng_consume_pcm(void) {audio_count=0;}
void rr_ng_audio_queue_probe(int playing,unsigned bytes,unsigned rate,unsigned period) {
    audio_device_rate=rate;audio_device_period=period;
    if(bytes>audio_queue_peak)audio_queue_peak=bytes;
    if(playing && !bytes)++empty_queue_frames;
}
void rr_ng_host_timing(double seconds) {loop_wall_seconds=seconds;}
bool rr_ng_performance_enabled(void) {return performance_only!=0;}
void rr_ng_host_cost(double busy_ms,double present_ms) {
    if(!performance_only || frame<=measure_from)return;
    ++host_measured_frames;host_busy_ms+=busy_ms;host_present_ms+=present_ms;
    if(busy_ms>host_busy_max_ms)host_busy_max_ms=busy_ms;
    if(present_ms>host_present_max_ms)host_present_max_ms=present_ms;
    if(busy_ms>1000.0/59.185606)++host_over_budget_frames;
}
void rr_ng_host_frame(uint16_t p1,uint16_t p2) {
    if(scripted)update_input();
    else {
        pad[0]=(uint8_t)~p1;pad[1]=(uint8_t)~p2;
        coin=rr_ng_coin_bits(p1,p2);start=rr_ng_start_bits(p1,p2);
    }
    step_frame();
}
uint32_t rr_ng_frame_index(void) {return frame;}
void rr_ng_restore_frame(uint32_t value) {
    frame=value;input_pos=0;audio_count=0;
    pad[0]=pad[1]=0xff;coin=start=0;
}
unsigned rr_ng_frame_limit(void) {return (unsigned)frames;}
bool rr_ng_enhanced(void) {return enhanced_mode;}
bool rr_ng_aes(void) {return aes_mode!=0;}
bool rr_ng_aes_available(void) {return RR_NG_AES_AVAILABLE!=0;}
const char *rr_ng_identity(void) {return aes_mode?RR_NG_AES_IDENTITY:RR_NG_MVS_IDENTITY;}
void rr_ng_request_mode_restart(void) {restart_requested=1;}
void rr_ng_set_enhanced(bool enabled) {
    enhanced_mode=enabled;
    geo_set_div68k(enabled?0:1);
    geo_lspc_set_sprlimit(enabled?381:96);
}
void rr_ng_reset_machine(void) {geo_reset(1);rr_ng_restore_frame(0);memset(video,0,sizeof video);}
/* Test hook is inert in ordinary exports. Its event harness lives separately. */
void rr_ng_ui_test_tick(void *window,void *renderer);
static int report(void) {
    if(!report_path)return 1;
    FILE *f=file_open(report_path,L"wb");if(!f)return 0;
    const RrM68000Stats *s=rr_m68000_stats();
    /* Mode is part of the guest machine, never an interpreter-counter shortcut. */
    uint64_t cpu_hash=14695981039346656037ull,ram_hash=14695981039346656037ull;
    const m68k_register_t registers[]={M68K_REG_D0,M68K_REG_D1,M68K_REG_D2,M68K_REG_D3,
        M68K_REG_D4,M68K_REG_D5,M68K_REG_D6,M68K_REG_D7,M68K_REG_A0,M68K_REG_A1,M68K_REG_A2,M68K_REG_A3,
        M68K_REG_A4,M68K_REG_A5,M68K_REG_A6,M68K_REG_A7,M68K_REG_SR,M68K_REG_PC,M68K_REG_USP,M68K_REG_ISP};
    for(unsigned i=0;i<sizeof registers/sizeof *registers;++i)
        cpu_hash=(cpu_hash^m68k_get_reg(NULL,registers[i]))*1099511628211ull;
    for(unsigned kind=GEO_MEMTYPE_MAINRAM;kind<=GEO_MEMTYPE_PALRAM;++kind) {
        size_t bytes=0;const uint8_t *data=geo_mem_ptr(kind,&bytes);
        if(data)for(size_t i=0;i<bytes;++i)ram_hash=(ram_hash^data[i])*1099511628211ull;
    }
    uint64_t hardware_hash=14695981039346656037ull;
    size_t state_bytes=geo_state_size();const uint8_t *state=geo_state_save_raw();
    for(size_t n=0;n<state_bytes;++n)hardware_hash=(hardware_hash^state[n])*1099511628211ull;
    fprintf(f,"{\"stage\":\"development-prototype\",\"frames\":%u,\"native_68000\":%llu,\"interpreted_68000\":%llu,"
        "\"native_z80\":%llu,\"interpreted_z80\":%llu,\"cpu_clocks\":%llu,\"bus_wait_clocks\":%llu,"
        "\"bios_instructions\":%llu,\"cart_instructions\":%llu,\"ram_instructions\":%llu,\"resets\":%llu,"
        "\"pc\":%u,\"image_hash\":\"%016llx\",\"pcm_hash\":\"%016llx\",\"pcm_samples\":%llu,"
        "\"nonzero_samples\":%llu,\"peak\":%u,\"clipped_samples\":%llu,\"rms\":%.4f,"
        "\"nonuniform_frames\":%u,\"audio_empty_queue_frames\":%llu,\"video_hz\":%.9f,\"pcm_rate\":55556,"
        "\"cpu_hash\":\"%016llx\",\"ram_hash\":\"%016llx\",\"z80_hash\":\"%016llx\",\"hardware_hash\":\"%016llx\",\"state_bytes\":%llu,\"m1_instructions\":%llu,\"sm1_instructions\":%llu,\"loop_wall_seconds\":%.6f,"
        "\"rtc_seeded\":%s,\"rtc_seed\":%lld,\"reached_pc\":[",
        frame,s->native_instructions,s->interpreted_instructions,rr_ng_native_z80,rr_ng_z80_instructions,s->clocks,s->bus_wait_clocks,
        rr_ng_bios_instructions,rr_ng_cart_instructions,rr_ng_ram_instructions,s->resets,m68k_get_reg(NULL,M68K_REG_PC),
        image_hash,pcm_hash,samples,nonzero,peak,clipped,samples?sqrt((double)pcm_energy/samples):0.0,
        nonuniform_frames,empty_queue_frames,FRAMERATE_MVS,cpu_hash,ram_hash,rr_ng_z80_state_hash(),hardware_hash,(uint64_t)state_bytes,rr_ng_m1_instructions,rr_ng_sm1_instructions,loop_wall_seconds,
        rr_ng_test_clock_enabled?"true":"false",rr_ng_test_clock);
    unsigned first=1;
    for(unsigned pc=0;pc<0x1000000;pc+=2)if(rr_ng_reached_pc[pc>>1]) {
        if(!first)fputc(',',f);first=0;fprintf(f,"%u",pc);
    }
    fprintf(f,"],\"reached_physical\":{\"p\":[");first=1;
    for(unsigned offset=0;offset<0x1000000u;offset+=2)if(rr_ng_reached_p[offset>>1]) {
        if(!first)fputc(',',f);first=0;fprintf(f,"%u",offset);
    }
    fprintf(f,"],\"bios\":[");first=1;
    for(unsigned offset=0;offset<0x20000u;offset+=2)if(rr_ng_reached_bios[offset>>1]) {
        if(!first)fputc(',',f);first=0;fprintf(f,"%u",offset);
    }
    fprintf(f,"]},\"m68k_ram_variants\":[");
    for(unsigned n=0;n<rr_ng_ram_variant_count;++n) {
        const RrNgRamVariant *v=&rr_ng_ram_variants[n];
        fprintf(f,"%s{\"offset\":%u,\"words\":\"",n?",":"",v->offset);
        for(unsigned w=0;w<v->count;++w)fprintf(f,"%04x",v->words[w]);
        fprintf(f,"\"}");
    }
    fprintf(f,"],\"m68k_ram_observations_truncated\":%s,\"z80_variants\":[",
        rr_ng_ram_observations_truncated?"true":"false");
    for(unsigned n=0;n<rr_ng_z80_variant_count;++n) {
        const RrNgZ80Variant *v=&rr_ng_z80_variants[n];
        fprintf(f,"%s{\"address\":%u,\"bytes\":\"%02x%02x%02x%02x\"}",n?",":"",v->pc,v->bytes[0],v->bytes[1],v->bytes[2],v->bytes[3]);
    }
    fprintf(f,"],\"state_loaded\":%s,\"load_rejected\":%s,\"save_failed\":%s,\"extended_cpu_hash\":\"%016llx\",\"extended_hardware_hash\":\"%016llx\","
        "\"audio_device_rate\":%u,\"audio_device_period\":%u,\"audio_queue_peak_bytes\":%u",
        state_loaded?"true":"false",load_rejected?"true":"false",save_failed?"true":"false",extended_cpu_hash(),extended_hardware_hash(),
        audio_device_rate,audio_device_period,audio_queue_peak);
    uint8_t extra[32];rr_ng_cpu_extra_save(extra,sizeof extra);
    int32_t remaining=(int32_t)extra_word(extra,16),initial=(int32_t)extra_word(extra,20);
    fprintf(f,",\"cpu_slice_initial\":%d,\"cpu_slice_remaining\":%d,\"cpu_slice_clocks\":%d",
        initial,remaining,initial-remaining);
    unsigned percentile=0,accumulated=0;
    for(;percentile<1000;++percentile) {
        accumulated+=frame_histogram[percentile];
        if(accumulated>=(measured_frames*95u+99u)/100u)break;
    }
    fprintf(f,",\"detailed_observations\":%s,\"performance_only\":%s,\"measured_frames\":%u,"
        "\"simulation_ms_mean\":%.6f,\"simulation_ms_max\":%.6f,\"simulation_ms_p95_upper\":%.3f,"
        "\"simulation_over_budget_frames\":%u",rr_ng_observations?"true":"false",performance_only?"true":"false",
        measured_frames,measured_frames?simulation_ms/measured_frames:0,simulation_max_ms,
        measured_frames?(percentile+1)/10.0:0,over_budget_frames);
    fprintf(f,",\"host_measured_frames\":%u,\"host_busy_ms_mean\":%.6f,\"host_busy_ms_max\":%.6f,"
        "\"host_present_ms_mean\":%.6f,\"host_present_ms_max\":%.6f,\"host_over_budget_frames\":%u",
        host_measured_frames,host_measured_frames?host_busy_ms/host_measured_frames:0,host_busy_max_ms,
        host_measured_frames?host_present_ms/host_measured_frames:0,host_present_max_ms,host_over_budget_frames);
    fprintf(f,",\"enhanced_mode\":%s,\"main_cpu_hz\":%u,\"sprite_limit\":%u",
        enhanced_mode?"true":"false",enhanced_mode?24000000u:12000000u,enhanced_mode?381u:96u);
    fprintf(f,",\"machine_mode\":\"%s\",\"aes_available\":%s",aes_mode?"aes":"mvs",RR_NG_AES_AVAILABLE?"true":"false");
    rr_ng_fallback_report(f);rr_ng_persist_report(f);fprintf(f,"}\n");
    int okay=!ferror(f);return fclose(f)==0 && okay;
}
static int execute(int argc,char **argv) {
    for(int i=1;i<argc;++i) {
        if(!strcmp(argv[i],"--headless"))headless=1;
        else if(!strcmp(argv[i],"--enhanced"))enhanced_requested=1;
        else if(!strcmp(argv[i],"--standard"))enhanced_requested=-1;
        else if(!strcmp(argv[i],"--aes"))mode_requested=1;
        else if(!strcmp(argv[i],"--mvs"))mode_requested=0;
        else if(!strcmp(argv[i],"--persistent-memory"))persistent_memory=1;
        else if(i+1<argc && !strcmp(argv[i],"--frames"))frames=atoi(argv[++i]);
        else if(i+1<argc && !strcmp(argv[i],"--report"))report_path=argv[++i];
        else if(i+1<argc && !strcmp(argv[i],"--performance-report")) {report_path=argv[++i];performance_only=1;}
        else if(i+1<argc && !strcmp(argv[i],"--measure-from"))measure_from=(unsigned)atoi(argv[++i]);
        else if(i+1<argc && !strcmp(argv[i],"--cpu-trace"))rr_ng_cpu_trace=file_open(argv[++i],L"wb");
        else if(i+1<argc && !strcmp(argv[i],"--trace-from"))rr_ng_trace_from=strtoull(argv[++i],NULL,10);
        else if(i+1<argc && !strcmp(argv[i],"--trace-limit"))rr_ng_trace_limit=strtoull(argv[++i],NULL,10);
        else if(i+1<argc && !strcmp(argv[i],"--trace-stride")) {rr_ng_trace_stride=(unsigned)atoi(argv[++i]);if(!rr_ng_trace_stride)return 2;}
#ifdef RR_NG_NATIVE
        else if(!strcmp(argv[i],"--reference"))rr_ng_force_reference=1;
#endif
#ifdef RR_NG_NATIVE_Z80
        else if(!strcmp(argv[i],"--reference-z80")) {extern int rr_ng_force_z80_reference;rr_ng_force_z80_reference=1;}
#endif
        else if(i+1<argc && !strcmp(argv[i],"--pcm"))pcm_path=argv[++i];
        else if(i+1<argc && !strcmp(argv[i],"--save-state"))save_path=argv[++i];
        else if(i+1<argc && !strcmp(argv[i],"--save-at"))save_at=(unsigned)atoi(argv[++i]);
        else if(i+2<argc && !strcmp(argv[i],"--checkpoint") && checkpoint_count<8) {
            unsigned at=(unsigned)atoi(argv[++i]);if(!at || at>1000000)return 2;
            checkpoints[checkpoint_count].frame=at;checkpoints[checkpoint_count++].path=argv[++i];
        }
        else if(i+1<argc && !strcmp(argv[i],"--load-state"))load_path=argv[++i];
        else if(!strcmp(argv[i],"--ignore-load-error"))ignore_load_error=1;
        else if(i+1<argc && !strcmp(argv[i],"--trace"))trace_path=argv[++i];
        else if(i+1<argc && !strcmp(argv[i],"--capture"))capture_dir=argv[++i];
        else if(i+1<argc && !strcmp(argv[i],"--capture-every"))capture_every=atoi(argv[++i]);
        else if(i+1<argc && !strcmp(argv[i],"--rtc-seed")) {
            char *end=NULL;rr_ng_test_clock=strtoll(argv[++i],&end,10);
            if(!end || *end || rr_ng_test_clock<0 || rr_ng_test_clock>4102444800ll)return 2;
            rr_ng_test_clock_enabled=1;
        }
        else if(i+1<argc && !strcmp(argv[i],"--script")) { if(!load_script(argv[++i]))return 2; }
        else return 2;
    }
    if(frames<0||frames>1000000||capture_every<1 || (headless && !frames))return 2;
    /* Normal play keeps honest native/fallback counters but does no coverage
     * discovery or per-pixel/per-sample diagnostic hashing. Qualification
     * reports/traces retain every previous check. */
    if(mode_requested>=0)aes_mode=mode_requested;
    else if(!headless) {
        wchar_t path[32768];
        if(rr_executable_directory(path,32768) && !rr_wide_append(path,32768,RR_SLASH_W L"datas" RR_SLASH_W L"Retro-Recomp.ini"))
            aes_mode=rr_ini_int(L"NeoGeo.Runtime",L"aes",0,path)==1 && RR_NG_AES_AVAILABLE;
    }
    if(aes_mode && !RR_NG_AES_AVAILABLE)return 2;
    rr_feedback_start(!headless);
    rr_ng_observations=(report_path && !performance_only) || trace_path || rr_ng_cpu_trace;
    frame_diagnostics=rr_ng_observations;
    if(SDL_Init(SDL_INIT_TIMER))return 3;
    performance_frequency=SDL_GetPerformanceFrequency();
    size_t packed_size,bios_size;const uint8_t *source=resource(201,&packed_size);
    void *bios=resource(202,&bios_size);
    if(!source || packed_size<8 || memcmp(source,"NGZ1",4) || !bios) { SDL_Quit();return 3; }
    size_t size=rr_ng_le32(source+4);
    if(size<4096 || size>(512u<<20)) { SDL_Quit();return 3; }
    uint8_t *content=malloc(size);if(!content)return 3;
    mz_ulong expanded=(mz_ulong)size;
    if(mz_uncompress(content,&expanded,source+8,(mz_ulong)(packed_size-8))!=MZ_OK ||
        expanded!=size || !rr_ng_container_valid(content,size)) { free(content);SDL_Quit();return 3; }
    geo_log_set_callback(log_message);geo_set_system(aes_mode?SYSTEM_AES:SYSTEM_MVS);geo_set_region(REGION_EU);geo_set_div68k(1);
#ifdef RR_NG_NATIVE
    rr_ng_native_bind();
#else
    rr_ng_reference_bind();
#endif
    geo_lspc_set_buffer(video);geo_lspc_set_palette(0);geo_lspc_set_sprlimit(96);
    geo_mixer_set_buffer(audio);geo_mixer_set_callback(audio_ready);
    for(unsigned p=0;p<2;++p)geo_input_set_callback(p,input_pad);
    geo_input_sys_set_callback(0,status_a);geo_input_sys_set_callback(1,status_b);
    geo_input_sys_set_callback(2,system_type);geo_input_sys_set_callback(3,dips);geo_input_sys_set_callback(4,unused);
    geo_init();rr_ng_reference_observer_enable();geo_mixer_init();geo_mixer_set_raw(1);
    if(!geo_bios_load_mem(bios,bios_size)||!geo_neo_load(content,size)) { free(content);SDL_Quit();return 3; }
    geo_reset(1);
    rr_ng_set_enhanced(enhanced_requested>0 || (!headless && enhanced_requested==0));
    persistent_load_failed=!rr_ng_persist_begin(!headless || persistent_memory);
    if(persistent_load_failed && !headless)SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_WARNING,"Neo Geo saves",
        "Saved scores and memory-card data could not be loaded. The existing file has been kept. Automatic saving is disabled for this session.",NULL);
    if(pcm_path) { pcm=file_open(pcm_path,L"wb");if(!pcm)return 3; }
    if(trace_path) {
        trace_file=file_open(trace_path,L"wb");if(!trace_file)return 3;
        fprintf(trace_file,"frame,cpu,hardware,z80,image,pcm,samples\n");
    }
    if(load_path) {
        state_loaded=state_file(load_path,1);load_rejected=!state_loaded;
        if(!state_loaded && !ignore_load_error)return 4;
    }
    if(enhanced_requested)rr_ng_set_enhanced(enhanced_requested>0);
    uint64_t frequency=SDL_GetPerformanceFrequency(),loop_begin=SDL_GetPerformanceCounter();
    int host_result=0;
    if(headless) {
        for(unsigned n=0;n<(unsigned)frames;++n) {update_input();step_frame();}
    } else {
        host_result=rr16_sdl_main(RR_NG_TITLE,3);rr16_shutdown();
    }
    if(headless)loop_wall_seconds=(double)(SDL_GetPerformanceCounter()-loop_begin)/frequency;
    if(save_path && !save_at && !state_file(save_path,0))save_failed=1;
    if(!rr_ng_persist_close()) {
        if(!headless && !persistent_load_failed)SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_WARNING,"Neo Geo saves",
            "Your scores and memory-card data could not be saved. Check access to the game folder or whether another copy of the game is running.",NULL);
        save_failed=1;
    }
    int okay=report() && !save_failed && !host_result;
    if(pcm && fclose(pcm))okay=0;
    if(trace_file && fclose(trace_file))okay=0;
    if(rr_ng_cpu_trace && fclose(rr_ng_cpu_trace))okay=0;
    geo_mixer_deinit();geo_deinit();geo_bios_unload();free(content);SDL_Quit();return okay?0:3;
}
#ifdef _WIN32
int main(void) {
    int argc=0;wchar_t **wide_argv=CommandLineToArgvW(GetCommandLineW(),&argc);
    char **argv=calloc((size_t)argc,sizeof *argv);if(!wide_argv||!argv)return 3;
    for(int i=0;i<argc;++i) {
        int n=WideCharToMultiByte(CP_UTF8,0,wide_argv[i],-1,NULL,0,NULL,NULL);
        argv[i]=malloc(n);WideCharToMultiByte(CP_UTF8,0,wide_argv[i],-1,argv[i],n,NULL,NULL);
    }
    int result=execute(argc,argv);
    if(!result && restart_requested) {
        wchar_t path[32768];DWORD n=GetModuleFileNameW(NULL,path,32768);
        if(!n || n>=32768 || (INT_PTR)ShellExecuteW(NULL,L"open",path,aes_mode?L"--mvs":L"--aes",NULL,SW_SHOWNORMAL)<=32)result=3;
    }
    if(result && argc==1)SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR,"Neo Geo","Unable to start this Neo Geo game.",NULL);
    for(int i=0;i<argc;++i)free(argv[i]);free(argv);LocalFree(wide_argv);return result;
}

#else
int main(int argc,char **argv) {
    int result=execute(argc,argv);
    if(!result && restart_requested) {
        /* Reopen this exact image even if a new generation has atomically
         * replaced its pathname while the game was running. */
        pid_t child=fork();
        if(child<0)result=3;
        else if(!child){execl("/proc/self/exe",argv[0],aes_mode?"--mvs":"--aes",(char*)NULL);_exit(127);}
    }
    if(result && argc==1)SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR,"Neo Geo","Unable to start this Neo Geo game.",NULL);
    return result;
}
#endif
