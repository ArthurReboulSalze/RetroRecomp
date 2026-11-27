// PC Engine CD disc: a sector provider for the pinned pcenginerecomp runtime that reads a CHD (version 4 or 5), an ISO or a packed CUE sheet (retrorecomp/pcecd_disc.py)
// from a file, or from the bytes of a larger file (a disc appended to a game executable); a CHD through libchdr linked statically.
// Original RetroRecomp code: MIT. libchdr keeps its own terms (licenses/libchdr.md); the engine its own MIT terms (licenses/pcenginerecomp.md).
#ifndef RR_PCECD_DISC_H
#define RR_PCECD_DISC_H
#include <cstdint>
#include <memory>
#include <string>

#include "pce/sector.hpp"

namespace pcecd {
// The disc held by `length` bytes of `file` from `offset` (length 0: the whole file). `sha256` is the digest of those bytes as the converter computed it
// (64 lower-case hex digits): it is the disc's identity in the engine's checkpoints, and it is not recomputed here (a disc is hundreds of megabytes). A
// file that is not a readable CD image throws pce::Fault with the reason. The provider never writes the file.
std::shared_ptr<pce::SectorProvider> open_disc(const std::string &file, std::uint64_t offset, std::uint64_t length, const std::string &sha256);
}  // namespace pcecd
#endif
