/* How a file an Amiga install saves reaches the player's disk. Original Retro-Recomp code, MIT.
 *
 * Header-only and free of the machine, so a small authored program can check it (tests/test_amiga_resload.py):
 *  - a name the game gives is written below the game's save folder only; a name that is absolute, names a volume or a drive
 *    (a colon), uses a backslash, or has an empty, "." or ".." part is refused, never written elsewhere;
 *  - the bytes go to `<name>.tmp` first and replace the file only once every byte reached the disk, flushed and closed: a disk
 *    that refuses the write (or the close) leaves the earlier file as it was and no half-written one;
 *  - at the clean end of a multiplayer match the host writes the match's saves back once (commit_folder): only the files that
 *    changed, each one's previous bytes first kept at the same name in a backup folder beside the save folder. */
#pragma once
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <map>
#include <optional>
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

/* The bytes of `file`, or nothing when it is not a regular file that could be read whole. */
inline std::optional<std::vector<uint8_t>> read_file(const std::filesystem::path &file) {
    std::error_code ec;
    if (!std::filesystem::is_regular_file(file, ec)) return std::nullopt;
    std::ifstream in(file, std::ios::binary);
    std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(in)), {});
    if (in.bad()) return std::nullopt;
    return bytes;
}

/* The host's saves at the clean end of a match (RrhkMachine.session_save_commit): `last` holds each name the match saved (key as
 * inside_folder takes it) with its final bytes, or nothing for a file the game removed. A name whose file below `folder` already
 * holds those bytes (or, removed, has no file) is left alone. Otherwise the file there now is first kept below `backup` at the same
 * name (replace_file, so a one-step backup: the backup of the match before goes), then the new bytes replace it (replace_file) or it
 * is removed. A backup that could not be written leaves that file as it was. True when every change reached the disk. */
inline bool commit_folder(const std::filesystem::path &folder, const std::filesystem::path &backup,
                          const std::map<std::string, std::optional<std::vector<uint8_t>>> &last) {
    namespace fs = std::filesystem;
    const auto name = [](const std::string &key) { return fs::path(std::u8string(key.begin(), key.end())); };
    bool ok = true;
    for (const auto &entry : last) {
        if (!inside_folder(entry.first)) { ok = false; continue; }
        const fs::path target = folder / name(entry.first);
        const std::optional<std::vector<uint8_t>> now = read_file(target);
        if (now == entry.second) continue;
        if (now && !replace_file(backup / name(entry.first), *now)) { ok = false; continue; }
        if (entry.second) ok = replace_file(target, *entry.second) && ok;
        else {
            std::error_code ec;
            ok = fs::remove(target, ec) && ok;
        }
    }
    return ok;
}

}  // namespace rr_amiga_savefile
