// PC Engine bridge: what the snapshot (pce_snapshot.cpp) needs of the machine that pce_machine.cpp owns. Not part of the C interface of the game.
// Original RetroRecomp code: MIT. The engine keeps its own MIT terms (licenses/pcenginerecomp.md).
#ifndef RR_PCE_MACHINE_INTERNAL_HPP
#define RR_PCE_MACHINE_INTERNAL_HPP
#include <cstdint>

#include "pce/runtime.hpp"

namespace pce {
// Retro-Recomp's patch of the engine's pcm.cpp (native/pce_engine/pcm.cpp): the CD audio fields a HuCard never reads are brought up to date here, not
// after every instruction. Call it before reading the engine's whole state (a checkpoint, the audio side of a snapshot): the state is then what it was
// when every instruction updated them.
void settle_silent_cd_source(Bus &bus);
}  // namespace pce

namespace pce_bridge {
// Null before pce_machine_init and after pce_machine_shutdown.
pce::Bus *bus();
pce::Cpu *cpu();
// The bridge's own counters, which a snapshot holds so that a load leaves the machine as it was.
std::uint64_t &frame_count();
std::uint64_t &cropped_count();
// The picture sequence the bridge last published: a load sets it to the restored machine's, so the next frame is a new one.
void published_sequence_is(std::uint64_t value);
// The PCM the bridge holds for the host: dropped by a load (it belongs to frames that never happened).
void drop_audio();
}  // namespace pce_bridge
#endif
