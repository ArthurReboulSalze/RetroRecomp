/* EEPROM saves of the CPS-1.5 (QSound) and CPS-2 boards, see cps1_persistence.h. Original work: MIT.
 * One file per exact set, written atomically (temporary file, flush, replace). A file that does not belong to this set,
 * has another size or fails its checksum is never used and never overwritten: the game starts with a blank EEPROM.
 * The write is made off the frame path: a worker thread writes the last contents once the EEPROM has been stable for about
 * a second (a game changes its cells one after another on a coin or at start), and the last contents are written when
 * play ends. A flush to disk can wait for a busy disk for a long while; the picture and the sound never do. */
#define WIN32_LEAN_AND_MEAN
#include "platform_io.h"
#include <errno.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#ifndef _WIN32
#include <pthread.h>
#include <time.h>
#endif
#include "cps1_machine.h"
#include "cps1_persistence.h"
#include "retro16_state_config.h"

enum { HEADER = 96, PAYLOAD_MAX = 128 };
static const uint8_t magic[8] = {'R', 'R', 'C', 'P', 'S', 'E', '0', '1'};
enum { TICK_MS = 50, STABLE_TICKS = 20 };       /* the contents are written after 1 s without a change */
static bool active;
static atomic_bool blocked, stopping;
static wchar_t save_path[32768];
static atomic_flag lock = ATOMIC_FLAG_INIT;
static uint8_t snapshot[PAYLOAD_MAX];
static size_t snapshot_size;
static unsigned generation, written;           /* both under the lock; generation 0 is "nothing changed yet" */
static bool worker_started;
#ifdef _WIN32
static HANDLE worker;
#else
static pthread_t worker;
#endif

static void acquire(void) { while (atomic_flag_test_and_set_explicit(&lock, memory_order_acquire)) { } }
static void release(void) { atomic_flag_clear_explicit(&lock, memory_order_release); }
static void pause_ms(unsigned ms)
{
#ifdef _WIN32
    Sleep(ms);
#else
    struct timespec t = {ms / 1000, (long)(ms % 1000) * 1000000L};
    nanosleep(&t, NULL);
#endif
}

static void put32(uint8_t *p, uint32_t v) { for (unsigned n = 0; n < 4; ++n) p[n] = (uint8_t)(v >> (8 * n)); }
static uint32_t get32(const uint8_t *p) { uint32_t v = 0; for (unsigned n = 0; n < 4; ++n) v |= (uint32_t)p[n] << (8 * n); return v; }
static uint64_t hash(const uint8_t *p, size_t n)
{
    uint64_t h = 14695981039346656037ull;
    for (size_t i = 0; i < n; ++i) h = (h ^ p[i]) * 1099511628211ull;
    return h;
}

bool rr_cps1_save_path(wchar_t *path, size_t capacity)
{
    if (!path || capacity < 32768) return false;
    char tail[128];
    wchar_t wide_tail[128];
    snprintf(tail, sizeof tail, RR_SLASH "datas" RR_SLASH "saves" RR_SLASH "CPS1-%.64s.rrsave", RR16_STATE_ROM);
    return rr_executable_directory(path, capacity) && rr_from_utf8(tail, wide_tail, 128) && rr_wide_append(path, capacity, wide_tail) == 0;
}

/* 1 valid, 0 missing, -1 not usable. */
static int read_saved(uint8_t *data, size_t size)
{
    FILE *file = rr_fopen(save_path, L"rb");
    if (!file) return errno == ENOENT ? 0 : -1;
    uint8_t header[HEADER];
    bool valid = fread(header, 1, HEADER, file) == HEADER && !memcmp(header, magic, 8) && get32(header + 8) == 1 &&
                 get32(header + 12) == size && !memcmp(header + 24, RR16_STATE_ROM, 64);
    for (unsigned n = 88; valid && n < HEADER; ++n) valid = header[n] == 0;
    valid = valid && fread(data, 1, size, file) == size && fgetc(file) == EOF && !ferror(file);
    fclose(file);
    if (valid) {
        const uint64_t checksum = (uint64_t)get32(header + 20) << 32 | get32(header + 16);
        valid = hash(data, size) == checksum;
    }
    return valid ? 1 : -1;
}

static bool write_atomic(const uint8_t *data, size_t size)
{
    uint8_t header[HEADER] = {0};
    memcpy(header, magic, 8);
    put32(header + 8, 1);
    put32(header + 12, (uint32_t)size);
    const uint64_t checksum = hash(data, size);
    put32(header + 16, (uint32_t)checksum);
    put32(header + 20, (uint32_t)(checksum >> 32));
    memcpy(header + 24, RR16_STATE_ROM, 64);
    wchar_t parent[32768], temporary[32768];
    rr_wide_copy(parent, 32768, save_path);
    for (wchar_t *p = parent + 3; *p; ++p)
        if (*p == L'\\' || *p == L'/') {
            const wchar_t separator = *p;
            *p = 0;
            if (!rr_mkdir(parent)) return false;
            *p = separator;
        }
    swprintf(temporary, 32768, L"%ls.%lu.tmp", save_path, rr_process_id());
    FILE *file = rr_fopen(temporary, L"wb");
    if (!file) return false;
    bool okay = fwrite(header, 1, HEADER, file) == HEADER && fwrite(data, 1, size, file) == size;
    if (okay) okay = rr_flush_file(file);
    if (fclose(file)) okay = false;
    if (okay) okay = rr_replace(temporary, save_path);
    if (!okay) rr_remove(temporary);
    return okay;
}

/* Writes the last snapshot when it is newer than the file. Called by the worker only, and by close after the worker ended. */
static bool flush_snapshot(void)
{
    uint8_t data[PAYLOAD_MAX];
    acquire();
    const unsigned wanted = generation;
    const size_t size = snapshot_size;
    memcpy(data, snapshot, sizeof data);
    const bool needed = wanted != written;
    release();
    if (!needed) return true;
    if (!write_atomic(data, size)) { atomic_store(&blocked, true); return false; }   /* a failed write stops further tries, play goes on */
    acquire();
    written = wanted;
    release();
    return true;
}

static void work(void)
{
    unsigned seen = 0, still = 0;
    while (!atomic_load(&stopping)) {
        pause_ms(TICK_MS);
        acquire();
        const unsigned now = generation, done = written;
        release();
        if (now == done || atomic_load(&blocked)) { still = 0; seen = now; continue; }
        if (now != seen) { seen = now; still = 0; continue; }
        if (++still >= STABLE_TICKS) { flush_snapshot(); still = 0; }
    }
}

#ifdef _WIN32
static DWORD WINAPI worker_main(LPVOID unused) { (void)unused; work(); return 0; }
static bool start_worker(void) { worker = CreateThread(NULL, 0, worker_main, NULL, 0, NULL); return worker != NULL; }
static void join_worker(void) { WaitForSingleObject(worker, INFINITE); CloseHandle(worker); }
#else
static void *worker_main(void *unused) { (void)unused; work(); return NULL; }
static bool start_worker(void) { return pthread_create(&worker, NULL, worker_main, NULL) == 0; }
static void join_worker(void) { pthread_join(worker, NULL); }
#endif

bool rr_cps1_save_begin(void)
{
    active = false;
    atomic_store(&blocked, false);
    atomic_store(&stopping, false);
    worker_started = false;
    generation = written = 0;
    const size_t size = cps1_eeprom_size();
    if (!size || size > PAYLOAD_MAX) return true;           /* a board without an EEPROM keeps nothing */
    if (!rr_cps1_save_path(save_path, 32768)) { atomic_store(&blocked, true); return false; }
    uint8_t data[PAYLOAD_MAX];
    const int result = read_saved(data, size);
    if (result == 1 && !cps1_eeprom_load(data, size)) atomic_store(&blocked, true);
    else if (result < 0) atomic_store(&blocked, true);
    active = true;
    snapshot_size = size;
    return !atomic_load(&blocked);
}

void rr_cps1_save_frame(void)
{
    if (!active || atomic_load(&blocked) || !cps1_eeprom_changed()) return;
    acquire();
    memcpy(snapshot, cps1_eeprom_data(), snapshot_size);
    ++generation;
    release();
    if (!worker_started) worker_started = start_worker();
}

bool rr_cps1_save_close(void)
{
    if (!active) return true;
    if (atomic_load(&blocked)) {
        if (worker_started) { atomic_store(&stopping, true); join_worker(); worker_started = false; }
        return false;
    }
    rr_cps1_save_frame();                                  /* a change of the last frame */
    if (worker_started) { atomic_store(&stopping, true); join_worker(); worker_started = false; }
    active = false;
    return flush_snapshot() && !atomic_load(&blocked);
}
