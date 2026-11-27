// PC Engine CD: our side of the comparison with MAME (tools/pcecd_mame_compare.py; development only, never in a game).
//
//   pcecd_mame_probe CARD DISC SHA256 SCRIPT FRAMES [--bram-in IN] [--bram OUT] [--dump DIR]
//
// The machine of the game (native/pce_machine.cpp with the disc, every instruction on the interpreter) plays SCRIPT (lines "frame mask", the pad of player 1 held
// from that frame) for FRAMES frames and prints one line per event of the CD interface, in the order the guest made them, the same events tools/pcecd_mame_compare.py
// asks of MAME: every write of a register of $1800-$180F that is not a data byte of the ADPCM port, the reads of the lock and of the System Card's signature, and, at
// selection of the drive, a hash of the CD RAM ($80-$87) and of the Super System Card's RAM ($68-$7F), of the ADPCM RAM, and whether the backup memory is locked: the data the last transfers left in memory.
// The events come from the engine's observer of bus accesses: the tool builds the probe with a copy of the pinned runtime/src/bus_trace.cpp in which
// observe_bus_access first calls `rr_pcecd_probe_access` (nothing of the engine's behaviour changes).
// Original RetroRecomp code: MIT. The engine keeps its own MIT terms (licenses/pcenginerecomp.md).
#include "pce_machine.h"
#include "pce_machine_internal.hpp"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

namespace {
unsigned frame_now = 0;
std::uint64_t adpcm_data_writes = 0, adpcm_data_hash = 14695981039346656037ull, bram_reads_locked = 0, selects = 0;
bool recording = false;
std::uint64_t port_reads[2] = {0, 0}, port_hash[2] = {14695981039346656037ull, 14695981039346656037ull};   // data the guest read at $1801 and $1808
const char *dump_folder = nullptr;

// The Super System Card's RAM ($68-$7F) then the CD RAM ($80-$87), 256 KiB, as MAME dumps them.
void dump_memory(std::uint64_t number) {
    const auto *bus = pce_bridge::bus();
    std::ofstream out(std::string(dump_folder) + "/mem-" + std::to_string(number) + ".bin", std::ios::binary);
    for (unsigned bank = 0x68; bank < 0x88; ++bank)
        out.write(reinterpret_cast<const char *>(bus->bytes->data() + bus->backing_address(std::uint32_t(bank) << 13)), 0x2000);
}

std::uint64_t fnv(std::uint64_t hash, const std::uint8_t *data, std::size_t size) {
    for (std::size_t i = 0; i < size; ++i) hash = (hash ^ data[i]) * 1099511628211ull;
    return hash;
}

std::uint64_t ram_hash(unsigned first_bank, unsigned banks) {
    const auto *bus = pce_bridge::bus();
    std::uint64_t hash = 14695981039346656037ull;
    for (unsigned bank = first_bank; bank < first_bank + banks; ++bank)
        hash = fnv(hash, bus->bytes->data() + bus->backing_address(std::uint32_t(bank) << 13), 0x2000);
    return hash;
}
}  // namespace

// Called by the copy of bus_trace.cpp: direction 0 read, 1 write; the 21-bit physical address and the byte read or written.
extern "C" void rr_pcecd_probe_access(int write, std::uint32_t physical, std::uint8_t value) {
    if (!recording || physical < 0x1FF800 || physical > 0x1FF8FF) return;
    const unsigned reg = physical - 0x1FF800;
    if (write) {
        if (reg == 0x0A) {                      // ADPCM RAM data: counted and hashed, not listed
            ++adpcm_data_writes;
            adpcm_data_hash = (adpcm_data_hash ^ value) * 1099511628211ull;
            return;
        }
        if (reg > 0x0F) return;
        std::printf("W %u %X %02X\n", frame_now, reg, value);
        if (reg == 0) {
            ++selects;
            const auto *bus = pce_bridge::bus();
            std::printf("S %u %llu %016llx %016llx %016llx %d\n", frame_now, static_cast<unsigned long long>(selects), static_cast<unsigned long long>(ram_hash(0x80, 8)),
                        static_cast<unsigned long long>(ram_hash(0x68, 24)), static_cast<unsigned long long>(fnv(14695981039346656037ull, bus->adpcm.ram.data(), bus->adpcm.ram.size())),
                        bus->cd.bram_unlocked ? 0 : 1);
            if (dump_folder) dump_memory(selects);
        }
    } else if (reg == 0x01 || reg == 0x08) {
        const unsigned port = reg == 0x08;
        ++port_reads[port];
        port_hash[port] = (port_hash[port] ^ value) * 1099511628211ull;
    } else if (reg == 0x03) {
        ++bram_reads_locked;
    } else if (reg >= 0xC0 && reg <= 0xC3) {
        std::printf("R %u %X %02X\n", frame_now, reg, value);
    }
}

int main(int argc, char **argv) {
    if (argc < 6) {
        std::fprintf(stderr, "usage: pcecd_mame_probe CARD DISC SHA256 SCRIPT FRAMES [--bram-in IN] [--bram OUT] [--dump DIR]\n");
        return 2;
    }
    std::ifstream card_file(argv[1], std::ios::binary);
    const std::vector<std::uint8_t> card((std::istreambuf_iterator<char>(card_file)), std::istreambuf_iterator<char>());
    std::vector<std::pair<unsigned, unsigned>> script;
    std::ifstream script_file(argv[4]);
    unsigned at = 0;
    std::string mask;
    while (script_file >> at >> mask) script.emplace_back(at, static_cast<unsigned>(std::strtoul(mask.c_str(), nullptr, 16)));
    const unsigned frames = static_cast<unsigned>(std::atoi(argv[5]));
    const char *bram_out = nullptr, *bram_in = nullptr;
    for (int i = 6; i + 1 < argc; i += 2) {
        if (!std::strcmp(argv[i], "--bram")) bram_out = argv[i + 1];
        else if (!std::strcmp(argv[i], "--bram-in")) bram_in = argv[i + 1];
        else if (!std::strcmp(argv[i], "--dump")) dump_folder = argv[i + 1];
    }
    char error[256] = {0};
    const PceDiscRecipe recipe = {card.data(), card.size(), argv[2], 0, 0, argv[3], 1, 1, PCE_UNKNOWN_NEC_INVALID, 2, 0};
    if (!pce_machine_init_disc(&recipe, error, sizeof error)) {
        std::fprintf(stderr, "cannot start: %s\n", error);
        return 3;
    }
    pce_machine_policy(PCE_POLICY_HYBRID);
    if (bram_in) {                              // the same backup memory as the other side starts with (MAME keeps one formatted)
        std::ifstream file(bram_in, std::ios::binary);
        std::vector<std::uint8_t> memory((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
        memory.resize(PCE_BACKUP_BYTES);
        pce_machine_set_backup(memory.data());
    }
    recording = true;
    std::size_t next = 0;
    std::uint16_t pads[PCE_PADS] = {0};
    bool playing = false;
    std::uint32_t first = 0, last = 0;
    for (frame_now = 1; frame_now <= frames; ++frame_now) {
        while (next < script.size() && script[next].first <= frame_now) pads[0] = static_cast<std::uint16_t>(script[next++].second);
        pce_machine_set_pads(pads);
        if (!pce_machine_run_frame(error, sizeof error)) {
            std::printf("FAULT %u %s\n", frame_now, error);
            return 1;
        }
        const auto &audio = pce_bridge::bus()->cd.audio;     // CD audio: playing or not, and the sectors it was asked for
        if ((audio.state == 0) != playing || (audio.state == 0 && (audio.start_lba != first || audio.stop_lba != last))) {
            playing = audio.state == 0;
            first = audio.start_lba;
            last = audio.stop_lba;
            std::printf("D %u %d %u %u\n", frame_now, playing ? 1 : 0, first, last);
        }
    }
    const auto *backup = pce_machine_backup();
    if (bram_out) std::ofstream(bram_out, std::ios::binary).write(reinterpret_cast<const char *>(backup), PCE_BACKUP_BYTES);
    std::printf("A %016llx %d\n", static_cast<unsigned long long>(fnv(14695981039346656037ull, pce_bridge::bus()->adpcm.ram.data(), pce_bridge::bus()->adpcm.ram.size())),
                pce_bridge::bus()->cd.bram_unlocked ? 0 : 1);
    for (unsigned port = 0; port < 2; ++port)
        std::printf("P %u %llu %016llx\n", port ? 8u : 1u, static_cast<unsigned long long>(port_reads[port]), static_cast<unsigned long long>(port_hash[port]));
    std::printf("END %u adpcm_data %llu %016llx lock_reads %llu selects %llu\n", frames, static_cast<unsigned long long>(adpcm_data_writes),
                static_cast<unsigned long long>(adpcm_data_hash), static_cast<unsigned long long>(bram_reads_locked), static_cast<unsigned long long>(selects));
    return 0;
}
