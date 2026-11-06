// gba_driver.h: the seam between the pinned Game Boy Advance engine's run_game() and the Retro-Recomp player.
// Original Retro-Recomp code (MIT). The engine (mstan/gbarecomp, PolyForm Noncommercial) is staged and patched per conversion
// (retrorecomp/gba_patches.py); this header is copied into the staged copy as src/runtime/rr_driver.h and included by the
// two engine files the patches touch (runtime.cpp, asset_picker.cpp) and by the player's gba_machine.cpp.
//
// The player does not use the engine's window loop. It installs `g_rr_driver` before run_game(); run_game() builds the
// machine as it always does (BIOS, ROM, saves, generated code), then, instead of its own loop, calls the driver once with the
// machine's accessors. The driver (the host kit's loop, through hostkit/adapters/rrhk_gba.c) steps one frame at a time.
#pragma once

#include <cstddef>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

namespace gbarecomp {

struct RrDriverApi {
    // One frame, from VBlank to VBlank. False: the guest stopped (an abort the engine has already reported).
    std::function<bool()> step_frame;
    // KEYINPUT, active low, bit 0 = A ... bit 9 = L. It holds until set again.
    std::function<void(uint16_t)> set_keyinput;
    // The picture of the frame just finished: 240 x 160 RGB888 (3 bytes a pixel), valid until the next step.
    std::function<const uint8_t*(int* width, int* height)> picture;
    // One block of the machine's mono sound; `rate` is that block's rate (32768 << SOUNDBIAS[15:14]). 0: none left.
    std::function<size_t(int16_t* out, size_t capacity, uint32_t* rate)> drain_audio;
    // Quick states: the engine's own container (magic, version, ROM SHA-1). Only between two frames.
    std::function<bool(std::vector<uint8_t>& bytes, std::string& error)> save_state;
    std::function<bool(const std::vector<uint8_t>& bytes, std::string& error)> load_state;
    // Battery: flush the cartridge save (SRAM, Flash or EEPROM) to the save path; false when the write failed.
    std::function<bool()> flush_save;
    std::function<bool()> save_dirty;
    // Honesty counters: guest instructions the engine's interpreter ran, and frames completed.
    std::function<uint64_t()> interpreted_instructions;
    std::function<uint64_t()> frames;
};

struct RrEmbedded {
    const uint8_t* data = nullptr;
    size_t size = 0;
};

// Set by the player before run_game(); null for every other use of the engine (the headless probe host).
extern int (*g_rr_driver)(const RrDriverApi&);
// The player's own copies of the cartridge and the system ROM, linked into the executable: run_game() takes them in place of a
// file of that name, with the same size and hash checks.
extern RrEmbedded g_rr_embedded_bios;
extern RrEmbedded g_rr_embedded_rom;

}  // namespace gbarecomp
