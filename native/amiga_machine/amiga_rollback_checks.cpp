// The in-process snapshot of an Amiga multiplayer session (rollback: amiga_session.h, rr_amiga_snap_*), checked without a game.
// Original Retro-Recomp code, MIT. tools/amiga_rollback_selftest.py authors a slave (its own 68000 program: copper, one bitplane,
// blits, audio DMA, VBL / copper / blitter / CIA-A / audio interrupts, a save and two loads through resload) and runs this program
// on it, once per model. A check, never part of a game.
//
//   amiga_rollback_checks SLAVE SCORE MODEL WARM FRAMES     (MODEL 0: the Amiga 500, 1: the Amiga 1200)
//   amiga_rollback_checks SLAVE SCORE MODEL commit FOLDER host|guest     (the saves at a match's clean end: commit_check)
//
// Prints one JSON line; exit status 0 only when every check holds:
//   neutral    a snapshot taken after every frame changes nothing the machine does (registers, RAM, picture, sound of every frame);
//   same_bytes two saves of one state, over buffers of other bytes, are the same bytes;
//   replay     a load at frame k, then the same frames: the same frames as the first time, and the same digests;
//   at_once    right after a load, before any frame: its digest and a new save are those of the saved frame;
//   refused    a load of another size or of foreign bytes is refused and the machine left as it was;
//   saves      the game's save went to the session's memory, and a load before it takes it back (the digest holds the saves);
//   no_alloc   no allocation inside snap_save or snap_load.
#include "amiga_session.h"

#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>
#include <string>
#include <vector>

// Every allocation of the process is counted (the session's and vAmiga's): a snapshot call must make none.
static std::atomic<unsigned long long> allocations{0};
void *operator new(std::size_t n) {
    allocations++;
    if (void *p = std::malloc(n ? n : 1)) return p;
    throw std::bad_alloc();
}
void *operator new[](std::size_t n) { return operator new(n); }
void operator delete(void *p) noexcept { std::free(p); }
void operator delete[](void *p) noexcept { std::free(p); }
void operator delete(void *p, std::size_t) noexcept { std::free(p); }
void operator delete[](void *p, std::size_t) noexcept { std::free(p); }

static std::vector<uint8_t> read_file(const char *path) {
    std::vector<uint8_t> out;
    FILE *f = fopen(path, "rb");
    if (!f) return out;
    uint8_t buffer[65536];
    size_t n;
    while ((n = fread(buffer, 1, sizeof buffer, f)) > 0) out.insert(out.end(), buffer, buffer + n);
    fclose(f);
    return out;
}

// What a frame did, read without touching the machine: registers, RAM, picture and sound.
struct Print {
    uint64_t ram, video, pcm;
    uint32_t pc, sr, d[8], a[8];
    bool operator==(const Print &o) const {
        return ram == o.ram && video == o.video && pcm == o.pcm && pc == o.pc && sr == o.sr && !memcmp(d, o.d, sizeof d) && !memcmp(a, o.a, sizeof a);
    }
};

static Print print_of(const RrAmigaSession *s) {
    RrAmigaFrameInfo info;
    rr_amiga_frame_info(s, &info);
    Print p;
    p.ram = info.ram; p.video = info.video; p.pcm = info.pcm; p.pc = info.pc; p.sr = info.sr;
    memcpy(p.d, info.d, sizeof p.d); memcpy(p.a, info.a, sizeof p.a);
    return p;
}

static std::string failures;
static void fail_check(const char *what, long at) {
    if (!failures.empty()) failures += ",";
    failures += "\"" + std::string(what) + "@" + std::to_string(at) + "\"";
}

static bool exists(const std::string &path) {
    FILE *f = fopen(path.c_str(), "rb");
    if (f) fclose(f);
    return f != nullptr;
}

// The saves at a match's clean end (RrhkMachine.session_save_commit), one seat per run (the process holds one session). FOLDER/saves
// is the seat's save folder, prepared by the tool: "score" (64 bytes of 0x11), "keep" ("keep"), and an older backup
// FOLDER/saves.bak/score ("older"). The program reads "score" at its VBL 40 and saves it at 120 (tools/amiga_rollback_selftest.py).
//   host   plays on its own saves; after 170 frames the commit writes "score" as the session's memory holds it, the previous bytes
//          (0x11) kept in saves.bak/score, "keep" left alone (unchanged: no backup), no temporary left; a second commit moves nothing;
//   guest  plays on the host's image (session_save_put), never commits (the kit calls the hook on the host only): its folder after
//          the match is byte for byte what it was.
static int commit_check(const std::vector<uint8_t> &slave, const std::vector<uint8_t> &score, int model, const std::string &folder, bool host) {
    RrAmigaFile file = {"score", score.data(), (uint32_t)score.size()};
    const std::string saves = folder + "/saves", backup = folder + "/saves.bak";
    RrAmigaGame game;
    memset(&game, 0, sizeof game);
    game.slave = slave.data(); game.slave_size = (uint32_t)slave.size();
    game.files = &file; game.file_count = 1;
    game.model = model;
    game.session = 1;
    game.save_dir = saves.c_str();
    const std::vector<uint8_t> before_score = read_file((saves + "/score").c_str()), before_keep = read_file((saves + "/keep").c_str()),
                               before_backup = read_file((backup + "/score").c_str());
    if (before_score != std::vector<uint8_t>(64, 0x11) || before_keep.size() != 4 || before_backup.size() != 5) fail_check("commit_folder_prepared", 0);
    char error[512] = {0};
    RrAmigaSession *s = rr_amiga_open(&game, error, sizeof error);
    if (!s) { fprintf(stderr, "open: %s\n", error); return 2; }
    if (!host) {
        std::vector<uint8_t> image = {'R', 'R', 'S', 'V', 5, 0, 's', 'c', 'o', 'r', 'e', 0, 64, 0, 0, 0};
        for (int k = 0; k < 64; k++) image.push_back((uint8_t)(0xC0 ^ k));
        if (!rr_amiga_session_save_put(s, image.data(), image.size())) fail_check("commit_guest_put", 0);
    }
    for (long at = 0; at < 170; at++) {
        rr_amiga_side_effects(s, 0);            // as the kit holds every seat from SETUP to the end
        if (rr_amiga_frame(s) != 0) { fprintf(stderr, "frame %ld: %s\n", at, rr_amiga_error(s)); return 2; }
    }
    // Nothing reached a disk during the match, on either seat.
    if (read_file((saves + "/score").c_str()) != before_score || read_file((backup + "/score").c_str()) != before_backup)
        fail_check("commit_quiet_match", 0);
    // The session's memory: the last entry of each name.
    std::vector<uint8_t> image(rr_amiga_session_save(s, nullptr, 0));
    if (image.size() < 4 || rr_amiga_session_save(s, image.data(), image.size()) != image.size()) fail_check("commit_image", 0);
    std::vector<std::pair<std::string, std::vector<uint8_t>>> last;
    for (size_t at = 4; at + 7 <= image.size();) {
        const size_t length = image[at] | image[at + 1] << 8;
        const uint32_t n = image[at + 3 + length] | image[at + 4 + length] << 8 | image[at + 5 + length] << 16 | (uint32_t)image[at + 6 + length] << 24;
        const std::string name((const char *)image.data() + at + 2, length);
        last.erase(std::remove_if(last.begin(), last.end(), [&](auto &e) { return e.first == name; }), last.end());
        if (!image[at + 2 + length]) last.emplace_back(name, std::vector<uint8_t>(image.begin() + at + 7 + length, image.begin() + at + 7 + length + n));
        at += 7 + length + n;
    }
    const auto final_score = std::find_if(last.begin(), last.end(), [](auto &e) { return e.first == "score"; });
    if (final_score == last.end() || final_score->second.size() != 64 || final_score->second == before_score) fail_check("commit_game_saved", 0);
    if (host) {
        if (!rr_amiga_session_save_commit(s)) fail_check("commit_written", 0);
        for (auto &e : last)
            if (read_file((saves + "/" + e.first).c_str()) != e.second) fail_check(("commit_file_" + e.first).c_str(), 0);
        if (read_file((backup + "/score").c_str()) != before_score) fail_check("commit_backup", 0);
        if (read_file((saves + "/keep").c_str()) != before_keep || exists(backup + "/keep")) fail_check("commit_unchanged_left", 0);
        if (exists(saves + "/score.tmp") || exists(backup + "/score.tmp")) fail_check("commit_temporary", 0);
        if (!rr_amiga_session_save_commit(s) || read_file((backup + "/score").c_str()) != before_score) fail_check("commit_again", 0);
    } else {
        if (read_file((saves + "/score").c_str()) != before_score || read_file((saves + "/keep").c_str()) != before_keep ||
            read_file((backup + "/score").c_str()) != before_backup || exists(saves + "/score.tmp"))
            fail_check("commit_guest_untouched", 0);
    }
    printf("{\"model\": %d, \"role\": \"%s\", \"files\": %zu, \"failures\": [%s], \"passed\": %s}\n", model, host ? "host" : "guest",
           last.size(), failures.c_str(), failures.empty() ? "true" : "false");
    fflush(stdout);
    _Exit(failures.empty() ? 0 : 1);
}

int main(int argc, char **argv) {
    if (argc == 7 && !strcmp(argv[4], "commit"))
        return commit_check(read_file(argv[1]), read_file(argv[2]), atoi(argv[3]), argv[5], !strcmp(argv[6], "host"));
    if (argc != 6) { fprintf(stderr, "usage: amiga_rollback_checks SLAVE SCORE MODEL WARM FRAMES\n"); return 2; }
    const std::vector<uint8_t> slave = read_file(argv[1]), score = read_file(argv[2]);
    const int model = atoi(argv[3]), warm = atoi(argv[4]), frames = atoi(argv[5]);
    if (slave.empty() || score.empty() || warm < 1 || frames < 100) { fprintf(stderr, "bad arguments\n"); return 2; }
    RrAmigaFile file = {"score", score.data(), (uint32_t)score.size()};
    RrAmigaGame game;
    memset(&game, 0, sizeof game);
    game.slave = slave.data(); game.slave_size = (uint32_t)slave.size();
    game.files = &file; game.file_count = 1;
    game.model = model;
    game.session = 1;
    char error[512] = {0};
    RrAmigaSession *s = rr_amiga_open(&game, error, sizeof error);
    if (!s) { fprintf(stderr, "open: %s\n", error); return 2; }
    // Each frame's inputs follow its number (the same on every timeline): the two joysticks and the Return key, held for a few frames.
    auto frame = [&](long at) {
        uint8_t held[128] = {0};
        held[0x44] = (at / 7) % 2;
        rr_amiga_joystick(s, (unsigned)((at / 5) * 0x9E37u >> 4) & 0x3Fu);
        rr_amiga_joystick2(s, (unsigned)((at / 3) * 0x7F4Bu >> 5) & 0x3Fu);
        rr_amiga_keys(s, held);
        if (rr_amiga_frame(s) != 0) { fprintf(stderr, "frame %ld: %s\n", at, rr_amiga_error(s)); exit(2); }
    };
    // The host's saves, as a guest receives them before frame 0: "score" of other bytes than the install's (the program's first load,
    // at its VBL 40, reads it). Malformed images are refused and change nothing; the image given back is the one put.
    {
        std::vector<uint8_t> host = {'R', 'R', 'S', 'V', 5, 0, 's', 'c', 'o', 'r', 'e', 0, 64, 0, 0, 0};
        for (int k = 0; k < 64; k++) host.push_back((uint8_t)(0xC0 ^ k));
        std::vector<uint8_t> bad = host;
        bad[0] = 'X';
        std::vector<uint8_t> cut(host.begin(), host.end() - 1);
        std::vector<uint8_t> outside = {'R', 'R', 'S', 'V', 5, 0, '.', '.', '/', 'x', 'y', 0, 0, 0, 0, 0};
        const size_t own = rr_amiga_session_save(s, nullptr, 0);
        if (own != 4) fail_check("own_saves", (long)own);
        if (rr_amiga_session_save_put(s, bad.data(), bad.size()) || rr_amiga_session_save_put(s, cut.data(), cut.size()) ||
            rr_amiga_session_save_put(s, outside.data(), outside.size()))
            fail_check("saves_refused", 0);
        if (rr_amiga_session_save(s, nullptr, 0) != 4) fail_check("saves_untouched", 0);
        if (!rr_amiga_session_save_put(s, host.data(), host.size())) fail_check("saves_put", 0);
        std::vector<uint8_t> back(host.size() + 8, 0);
        if (rr_amiga_session_save(s, back.data(), back.size()) != host.size() || memcmp(back.data(), host.data(), host.size()))
            fail_check("saves_back", 0);
    }
    for (int n = 0; n < warm; n++) frame(n);

    const size_t bound = rr_amiga_snap_bound(s);
    std::vector<uint8_t> a(bound, 0xA5), b(bound, 0x5A), scratch(bound, 0x33);
    const unsigned long long before_save = allocations;
    const size_t size = rr_amiga_snap_save(s, a.data(), a.size());
    const size_t size_b = rr_amiga_snap_save(s, b.data(), b.size());
    unsigned long long snap_allocations = allocations - before_save;
    const unsigned long long snap_allocations_first = snap_allocations;
    if (!size || size != size_b || memcmp(a.data(), b.data(), size)) fail_check("same_bytes", 0);
    const uint64_t digest_a = rr_amiga_digest(s);

    // The first timeline: no snapshot, no digest, only what each frame did.
    std::vector<Print> plain;
    for (int n = 0; n < frames; n++) { frame(warm + n); plain.push_back(print_of(s)); }
    const uint64_t digest_plain = rr_amiga_digest(s);

    // The same frames from the first state, a snapshot after each one (the rollback tier's ring) and a digest of each.
    unsigned long long before_load = allocations;
    if (!rr_amiga_snap_load(s, a.data(), size)) fail_check("load", 0);
    snap_allocations += allocations - before_load;
    const unsigned long long load_allocations = allocations - before_load;
    if (rr_amiga_digest(s) != digest_a) {
        fail_check("at_once", 0);
        // Where a save right after the load differs from the save it loaded: the component (vAmiga's walk order) and the offset in it.
        const size_t again = rr_amiga_snap_save(s, scratch.data(), scratch.size());
        uint32_t parts[4];
        memcpy(parts, a.data(), sizeof parts);
        const size_t machine = size - parts[1] - parts[2] - parts[3];
        {   // the components' sizes, before and after, where they differ
            uint32_t later[4];
            memcpy(later, scratch.data(), sizeof later);
            size_t p = machine, q = again - later[1] - later[2] - later[3];
            for (int index = 0; p < machine + parts[1] && index < 400; index++) {
                uint64_t n = 0, m = 0;
                for (int k = 0; k < 8; k++) { n = n << 8 | a[p + k]; m = m << 8 | scratch[q + k]; }
                if (n != m) fprintf(stderr, "component %d: %llu -> %llu bytes\n", index, (unsigned long long)n, (unsigned long long)m);
                if (!n || !m) break;
                p += (size_t)n; q += (size_t)m;
            }
        }
        for (size_t at = 0; at < std::min(again, size); at++) {
            if (a[at] == scratch[at]) continue;
            long component = -1, inside = (long)at;
            if (at >= machine && at < machine + parts[1]) {
                size_t walk = machine;
                component = 0;
                while (walk < machine + parts[1]) {
                    uint64_t n = 0;
                    for (int k = 0; k < 8; k++) n = n << 8 | a[walk + k];
                    if (at < walk + n) { inside = (long)(at - walk); break; }
                    walk += (size_t)n; component++;
                }
            }
            fprintf(stderr, "first difference at %zu (machine from %zu): component %ld, byte %ld, %02x -> %02x\n", at, machine, component, inside, a[at], scratch[at]);
            break;
        }
    }
    const int marks[3] = {7, 40, frames - 19};
    std::vector<std::vector<uint8_t>> kept(3, std::vector<uint8_t>(bound, 0xC3));
    std::vector<size_t> kept_size(3, 0);
    std::vector<uint64_t> digests;
    for (int n = 0; n < frames; n++) {
        frame(warm + n);
        const unsigned long long before = allocations;
        const size_t written = rr_amiga_snap_save(s, scratch.data(), scratch.size());
        snap_allocations += allocations - before;
        if (!written) fail_check("save", n);
        if (!(print_of(s) == plain[n])) fail_check("neutral", n);
        digests.push_back(rr_amiga_digest(s));
        for (int m = 0; m < 3; m++)
            if (n == marks[m]) kept_size[m] = rr_amiga_snap_save(s, kept[m].data(), kept[m].size());
    }
    if (digests.back() != digest_plain) fail_check("neutral_digest", frames);

    // A load at each mark: at once its digest and its bytes, then the same frames as the first time.
    for (int m = 0; m < 3; m++) {
        before_load = allocations;
        if (!rr_amiga_snap_load(s, kept[m].data(), kept_size[m])) { fail_check("load", marks[m]); continue; }
        snap_allocations += allocations - before_load;
        if (rr_amiga_digest(s) != digests[marks[m]]) fail_check("at_once", marks[m]);
        std::fill(scratch.begin(), scratch.end(), 0x77);
        const size_t again = rr_amiga_snap_save(s, scratch.data(), scratch.size());
        if (again != kept_size[m] || memcmp(scratch.data(), kept[m].data(), again)) fail_check("at_once_bytes", marks[m]);
        for (int n = marks[m] + 1; n < frames; n++) {
            frame(warm + n);
            if (!(print_of(s) == plain[n])) { fail_check("replay", n); break; }
            if (rr_amiga_digest(s) != digests[n]) { fail_check("replay_digest", n); break; }
        }
    }

    // Refused loads: one byte short, one byte more, foreign bytes. The machine stays at the frame it was.
    const uint64_t here = rr_amiga_digest(s);
    std::vector<uint8_t> longer(a.begin(), a.begin() + size);
    longer.push_back(0);
    std::vector<uint8_t> foreign(size, 0xEE);
    if (rr_amiga_snap_load(s, a.data(), size - 1) || rr_amiga_snap_load(s, longer.data(), longer.size()) ||
        rr_amiga_snap_load(s, foreign.data(), foreign.size()))
        fail_check("refused", 0);
    if (rr_amiga_digest(s) != here) fail_check("refused_untouched", 0);

    // The game's save: the program saves once at its VBL 120 and reads the file back at 160 (tools/amiga_rollback_selftest.py), so the
    // first mark is before the save and the others after it. The replay from the first mark saved again: its same digests (which hold
    // the session's saves) show the load took the first save back, and the same RAM after 160 that the saved bytes were read.
    if (!(warm + marks[0] < 120 && warm + marks[1] > 125 && warm + marks[1] < 160 && warm + frames > 170)) fail_check("saves_window", warm);
    printf("{\"model\": %d, \"bound\": %zu, \"size\": %zu, \"frames\": %d, \"save_allocations\": %llu, \"load_allocations\": %llu, \"snap_allocations\": %llu, \"failures\": [%s], \"passed\": %s}\n",
           model, bound, size, frames, snap_allocations_first, load_allocations, snap_allocations, failures.c_str(), failures.empty() && snap_allocations == 0 ? "true" : "false");
    fflush(stdout);
    _Exit(failures.empty() && snap_allocations == 0 ? 0 : 1);
}
