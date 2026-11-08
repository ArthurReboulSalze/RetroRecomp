/* How a file an Amiga install saves reaches the player's disk. Original Retro-Recomp code, MIT.
 *
 * Header-only and free of the machine, so a small authored program can check it (tests/test_amiga_resload.py):
 *  - a name the game gives is written below the game's save folder only; a name that is absolute, names a volume or a drive
 *    (a colon), uses a backslash, or has an empty, "." or ".." part is refused, never written elsewhere;
 *  - the bytes go to `<name>.tmp` first and replace the file only once every byte reached the disk, flushed and closed: a disk
 *    that refuses the write (or the close) leaves the earlier file as it was and no half-written one. */
#pragma once
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>
#include <system_error>
#include <vector>

namespace rr_amiga_savefile {

/* True when `key` (the guest's name, lower-cased, '/' between folders) stays inside the save folder. */
inline bool inside_folder(const std::string &key) {
    if (key.empty() || key.find_first_of(":\\") != std::string::npos || key.find('\0') != std::string::npos) return false;
    size_t start = 0;
    for (;;) {
        size_t end = key.find('/', start);
        if (end == std::string::npos) end = key.size();
        const std::string part = key.substr(start, end - start);
        if (part.empty() || part == "." || part == "..") return false;
        if (end == key.size()) return true;
        start = end + 1;
    }
}

/* Replaces `target` with `data` through `<target>.tmp`. False (and no temporary left) when anything refused. */
inline bool replace_file(const std::filesystem::path &target, const std::vector<uint8_t> &data) {
    namespace fs = std::filesystem;
    std::error_code ec;
    fs::create_directories(target.parent_path(), ec);
    fs::path temporary = target;
    temporary += ".tmp";
    bool ok;
    {
        std::ofstream out(temporary, std::ios::binary | std::ios::trunc);
        out.write(reinterpret_cast<const char *>(data.data()), static_cast<std::streamsize>(data.size()));
        out.flush();
        ok = out.good();
        out.close();
        ok = ok && !out.fail();
    }
    if (ok) {
        fs::rename(temporary, target, ec);
        ok = !ec;
    }
    if (!ok) fs::remove(temporary, ec);
    return ok;
}

}  // namespace rr_amiga_savefile
