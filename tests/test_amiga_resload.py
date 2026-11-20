"""The resload services a WHDLoad slave calls (native/amiga_whdload/rr_resload.c and rr_decrunch.c), checked by an
authored C harness.

The harness runs every provided service on a flat guest memory with authored files: loads, disk images, saves,
CRC-16, Control tags, the whole patch-list language including IF blocks and PL_NEXT, PatchSeg, Relocate (over itself,
into a CHIP area, as a LoadSeg list), RNC1 unpacking (a file packed here by an encoder written from the format, with
literal runs and matches over two sub-chunks), the Kickstart load (resload_LoadKick, and the image a v16+ slave header
asks for, one name or a table of CRC-16 and name pairs, with an authored fake image), Examine, ExNext and ListFiles over
an authored file list, and the refusals of what is not provided. No game, slave, ROM or Kickstart is involved.
"""
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def crc16(data):
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


class RncWriter:
    """RNC method 1 stream: bits least significant first in 16-bit little-endian words; a literal run is stored right
    after the last word that holds bits, and the next bits go on filling that word."""

    def __init__(self):
        self.out = bytearray()
        self.slot = None      # byte position of the word being filled
        self.bits = 0
        self.acc = 0

    def bit(self, b):
        if self.slot is None:
            self.slot = len(self.out)
            self.out += b'\0\0'
            self.bits = self.acc = 0
        self.acc |= (b & 1) << self.bits
        self.bits += 1
        struct.pack_into("<H", self.out, self.slot, self.acc)
        if self.bits == 16:
            self.slot = None

    def number(self, value, n):            # n bits, least significant first
        for k in range(n):
            self.bit(value >> k)

    def code(self, symbol):                # 16 symbols of 4 bits each: canonical code = symbol, sent MSB first
        for k in range(3, -1, -1):
            self.bit(symbol >> k)

    def value(self, x):                    # n < 2 is itself; else 2^(n-1) and n-1 more bits
        if x < 2:
            self.code(x)
        else:
            n = x.bit_length()
            self.code(n)
            self.number(x - (1 << (n - 1)), n - 1)

    def literals(self, data):
        self.out += data


def rnc1(chunks):
    """chunks: a list of sub-chunks (literal bytes, then (distance, length) or None for the last). Returns
    (packed file, unpacked bytes)."""
    w, plain = RncWriter(), bytearray()
    w.number(0, 2)                          # lock and key bits
    for _ in range(3):                      # literal, distance and length tables: 16 codes of 4 bits
        w.number(16, 5)
        for _ in range(16):
            w.number(4, 4)
    w.number(len(chunks), 16)
    for literal, match in chunks:
        w.value(len(literal))
        if literal:
            w.literals(literal)
            plain += literal
        if match:
            distance, length = match
            w.value(distance - 1)
            w.value(length - 2)
            for _ in range(length):
                plain.append(plain[-distance])
    body = bytes(w.out)
    header = b'RNC\x01' + struct.pack('>IIHHBB', len(plain), len(body), crc16(plain), crc16(body), 0, 1)
    return header + body, bytes(plain)


def imploder(plain: bytes) -> bytes:
    """An authored File Imploder ("IMP!") stream of `plain`, made the way the unpacker reads one: literal runs and matches of 2 to 5
    bytes at distances 1 to 16, the stream laid out backward with its first 12 bytes moved into the trailer, then the checksum. Not
    the Imploder's own packer (whose choices are its own): only a stream the format allows, so the unpacker is checked on its reading."""
    n = len(plain)
    reads, bits = [], {'slot': None, 'used': 8}

    def put_bits(value, count):
        for k in range(count - 1, -1, -1):
            if bits['used'] == 8:
                reads.append(0)
                bits['slot'], bits['used'] = len(reads) - 1, 0
            reads[bits['slot']] |= (value >> k & 1) << (7 - bits['used'])
            bits['used'] += 1

    def match_at(pos):        # the longest match of 2 to 5 bytes ending at pos from bytes already written above it
        for count in (5, 4, 3, 2):
            for distance in range(1, 17):
                if pos - count >= 0 and pos + distance <= n and plain[pos - count:pos] == plain[pos - count + distance:pos + distance]:
                    return count, distance
        return None

    def run_from(pos, limit):  # literals until a match is possible (or the start), at most `limit`
        run = 0
        while pos - run > 0 and run < limit and (run == 0 or match_at(pos - run) is None):
            run += 1
        while pos - run > 0 and match_at(pos - run) is None and run < limit:
            run += 1
        return run

    pos, first = n, None
    first = run_from(n, 1 << 30)
    for k in range(first):
        reads.append(plain[pos - 1 - k])
    pos -= first
    run_max = {0: 21, 1: 41, 2: 137, 3: 16401}
    while pos:
        count, distance = match_at(pos)
        selector = count - 2
        put_bits((1 << selector) - 1 << 1, selector + 1)          # the length's code: selector ones, then a zero
        pos -= count
        run = run_from(pos, run_max[selector]) if pos else 0
        if run <= 1:
            put_bits(0, 1); put_bits(run, 1)
        elif run < 2 + (1 << (2, 3, 3, 4)[selector]):
            put_bits(0b10, 2); put_bits(run - 2, (2, 3, 3, 4)[selector])
        else:
            put_bits(0b11, 2); put_bits(run - (6, 10, 10, 18)[selector], (4, 5, 7, 14)[selector])
        put_bits(0, 1); put_bits(distance - 1, 4)                  # the distance: code 0, four bits
        for k in range(run):
            reads.append(plain[pos - 1 - k])
        pos -= run
    end = max(len(reads), 12)
    lower = end & 1                 # an odd stream leaves the top byte of its even length unused, as the packer does, and says so
    end += lower
    data = bytearray(end + 0x32)
    data[0:12] = b'IMP!' + n.to_bytes(4, 'big') + end.to_bytes(4, 'big')
    for k, value in enumerate(reads):
        i = end - 1 - lower - k
        at = i if i >= 12 else end + 8 + i if i < 4 else end + i if i < 8 else end + i - 8
        data[at] = value
    data[end + 12:end + 16] = first.to_bytes(4, 'big')
    data[end + 16] = 0x00 if lower else 0x80                       # the stream starts at its end, or one byte lower
    data[end + 17] = 0                                             # no bits left in a first byte
    for i, value in enumerate((16, 16, 16, 16, 272, 272, 272, 272)):
        data[end + 18 + 2 * i:end + 20 + 2 * i] = value.to_bytes(2, 'big')
    data[end + 34:end + 46] = bytes((4, 4, 4, 4, 8, 8, 8, 8, 12, 12, 12, 12))
    total = (7 + sum(int.from_bytes(data[i:i + 2], 'big') for i in range(0, end + 0x2E, 2))) & 0xFFFFFFFF
    data[end + 0x2E:end + 0x32] = total.to_bytes(4, 'big')
    return bytes(data)


def crunchmania(plain: bytes, lzh: bool = False, sampled: bool = False) -> bytes:
    """An authored Crunch-Mania file of `plain` (no byte of any game), written from the format's rules: tokens made from the end of the
    data backward (the unpacker writes backward), greedy matches, the bits laid out so that the unpacker's first read comes from the
    stream's tail. Standard mode ("CrM!") with its fixed codes, or LZH mode ("CrM2") with one block of single-depth tables; "Crm" when
    the data is delta coded first ("sampled")."""
    data = bytes((plain[i] - (plain[i - 1] if i else 0)) & 0xFF for i in range(len(plain))) if sampled else plain
    rev = data[::-1]
    bits: list[int] = []

    def put(value: int, count: int):                 # read least significant bit first
        bits.extend((value >> i) & 1 for i in range(count))

    def code(pattern: str):                          # a code read most significant bit first
        bits.extend(int(c) for c in pattern)

    def best(j: int, limit: int, longest: int):
        found = (0, 0)
        for d in range(1, min(j, limit) + 1):
            n = 0
            while j + n < len(rev) and n < longest and rev[j + n] == rev[j + n - d]:
                n += 1
            if n > found[0]:
                found = (n, d)
        return found

    tokens, j = [], 0
    while j < len(rev):
        n, d = best(j, 16927 if not lzh else 65536, 278 if not lzh else 258)
        if n >= 3 and d >= 1:
            tokens.append(('match', n, d))
            j += n
        else:
            tokens.append(('literal', rev[j]))
            j += 1
    if not lzh:
        for token in tokens:
            if token[0] == 'literal':
                put(1, 1)
                put(token[1], 8)
                continue
            _, n, d = token
            put(0, 1)
            if n <= 3:
                code('0'); put(n - 2, 1)
            elif n <= 7:
                code('10'); put(n - 4, 2)
            elif n <= 22:
                code('110'); put(n - 8, 4)
            else:
                code('111'); put(n - 23, 8)
            if d < 32:
                code('10'); put(d, 5)
            elif d < 544:
                code('0'); put(d - 32, 9)
            else:
                code('11'); put(d - 544, 14)
    else:
        def distance_bits(d: int) -> tuple[int, int, int]:
            if d <= 2:
                return 0, d - 1, 1
            b = (d - 1).bit_length() - 1
            return b, (d - 1) - (1 << b), b
        lengths = sorted({0x100 | t[1] if t[0] == 'literal' else t[1] - 3 for t in tokens})
        distances = sorted({distance_bits(t[2])[0] for t in tokens if t[0] == 'match'}) or [0]

        def table(values: list[int], code_length: int) -> dict:
            depth = len(values).bit_length()             # the count is written in `depth` bits: it must be below 2**depth
            put(depth, 4)
            for i in range(depth):
                put(len(values) if i + 1 == depth else 0, min(i + 1, code_length))
            for v in values:
                put(v, code_length)
            return {v: format(k, f'0{depth}b') for k, v in enumerate(values)}
        length_codes = table(lengths, 9)
        distance_codes = table(distances, 4)
        put(len(tokens) - 1, 16)
        for token in tokens:
            if token[0] == 'literal':
                code(length_codes[0x100 | token[1]])
                continue
            _, n, d = token
            code(length_codes[n - 3])
            b, extra, width = distance_bits(d)
            code(distance_codes[b])
            put(extra, width)
        put(0, 1)                                    # no further block
    while len(bits) < 16:
        bits.append(0)
    shift = (len(bits) - 16) % 8
    first = 16 + shift
    pending = sum(bit << i for i, bit in enumerate(bits[:first]))
    rest = bits[first:]
    stream = bytes(sum(bit << i for i, bit in enumerate(rest[k:k + 8])) for k in range(0, len(rest), 8))[::-1]
    packed = stream + struct.pack('>IH', (pending << (16 - shift)) & 0xFFFFFFFF, shift)
    ident = (b'Crm' if sampled else b'CrM') + (b'2' if lzh else b'!')
    return ident + b'\0\0' + struct.pack('>II', len(plain), len(packed)) + packed


class ResloadHarnessTest(unittest.TestCase):
    def test_the_authored_harness_passes(self):
        from retrorecomp.core import toolchain
        from retrorecomp.platforms import build_executable, cmake_target_args
        with tempfile.TemporaryDirectory(prefix='rr-amiga-resload-') as temp:
            project = Path(temp)
            native = (ROOT / 'native/amiga_whdload').as_posix()
            (project / 'CMakeLists.txt').write_text(
                'cmake_minimum_required(VERSION 3.20)\n'
                'project(ResloadChecks LANGUAGES C)\n'
                'set(CMAKE_C_STANDARD 11)\n'
                f'add_executable(resload-checks "{ROOT.as_posix()}/tests/amiga_resload_harness.c" "{native}/rr_resload.c"'
                f' "{native}/rr_decrunch.c")\n'
                f'target_include_directories(resload-checks PRIVATE "{native}")\n'
                'if(MSVC)\n'
                'target_compile_options(resload-checks PRIVATE /W4 /WX /utf-8)\n'
                'target_compile_definitions(resload-checks PRIVATE _CRT_SECURE_NO_WARNINGS)\n'
                'else()\n'
                'target_compile_options(resload-checks PRIVATE -Wall -Wextra -Werror)\n'
                'endif()\n', encoding='utf-8')
            packed, plain = rnc1([(b'WHDLoad install data, ', (22, 40)), (b'0123456789', (3, 9)),
                                  (bytes(range(200)), (200, 300)), (b'end of file', None)])
            (project / 'packed.rnc').write_bytes(packed)
            (project / 'plain.bin').write_bytes(plain)
            # Crunch-Mania, the four variants, on authored data: repeats near and far, a long literal stretch, a slow ramp for the delta mode.
            sample = (b'WHDLoad install data, ' * 6 + bytes(range(256)) + b'0123456789' * 40 + bytes((i * 7) & 0xFF for i in range(900))
                      + bytes(range(256)) + b'end of file')
            pairs = []
            for lzh in (False, True):
                for sampled in (False, True):
                    name = f'crm-{int(lzh)}{int(sampled)}'
                    (project / f'{name}.pak').write_bytes(crunchmania(sample, lzh, sampled))
                    (project / f'{name}.bin').write_bytes(sample)
                    pairs += [str(project / f'{name}.pak'), str(project / f'{name}.bin')]
            # Imploder: the same sample (runs of literals, short and long, and matches at distances 1 to 16).
            (project / 'imp.pak').write_bytes(imploder(sample))
            (project / 'imp.bin').write_bytes(sample)
            pairs += [str(project / 'imp.pak'), str(project / 'imp.bin')]
            cmake, generator = toolchain()
            for command in ([str(cmake), '-S', str(project), '-B', str(project / 'build'), '-G', generator,
                             *cmake_target_args()],
                            [str(cmake), '--build', str(project / 'build'), '--config', 'Release']):
                built = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            result = subprocess.run([str(build_executable(project / 'build', 'resload-checks')),
                                     str(project / 'packed.rnc'), str(project / 'plain.bin'), *pairs],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('OK (0 failures)', result.stdout)

    def test_the_rnc1_writer_packs_what_it_says(self):
        packed, plain = rnc1([(b'abc', (3, 6)), (b'', None)])
        self.assertEqual(plain, b'abcabcabc')
        self.assertEqual(packed[:4], b'RNC\x01')
        self.assertEqual(struct.unpack('>I', packed[4:8])[0], 9)


SAVEFILE_HARNESS = r'''// Authored harness for native/amiga_machine/amiga_savefile.h: which names stay inside the save folder, and what a refused write leaves.
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <map>
#include <optional>
#include <string>
#include "amiga_savefile.h"
namespace fs = std::filesystem;
using namespace rr_amiga_savefile;
static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::printf("FAIL line %d: %s\n", __LINE__, #x); failures++; } } while (0)
static std::vector<uint8_t> bytes(const char *text) { std::vector<uint8_t> v; while (*text) v.push_back((uint8_t)*text++); return v; }
static std::string read(const fs::path &p) { std::ifstream in(p, std::ios::binary); return std::string((std::istreambuf_iterator<char>(in)), {}); }
int main(int, char **argv) {
    const char *good[] = {"highs", "dir/file", "a b/c.d", "save.1", "x/y/z"};
    const char *bad[] = {"", "/x", "../x", "a/../x", "a//b", "c:x", "dh0:x", "a\\b", ".", "..", "a/", "a/./b", "x/..", "\\x", "C:/x"};
    for (const char *name : good) CHECK(inside_folder(name));
    for (const char *name : bad) CHECK(!inside_folder(name));
    const fs::path root = fs::path(argv[1]);
    std::error_code ec;
    fs::remove_all(root, ec);
    fs::create_directories(root, ec);
    // A first write creates the folders and the file; a second replaces it; no temporary stays.
    CHECK(replace_file(root / "saves/sub/highs", bytes("first")));
    CHECK(read(root / "saves/sub/highs") == "first");
    CHECK(replace_file(root / "saves/sub/highs", bytes("second, longer")));
    CHECK(read(root / "saves/sub/highs") == "second, longer");
    CHECK(!fs::exists(root / "saves/sub/highs.tmp"));
    CHECK(replace_file(root / "saves/sub/empty", {}));
    CHECK(fs::exists(root / "saves/sub/empty") && fs::file_size(root / "saves/sub/empty") == 0);
    // The target is a folder: refused, the folder stays, no temporary is left.
    fs::create_directories(root / "saves/folder", ec);
    CHECK(!replace_file(root / "saves/folder", bytes("x")));
    CHECK(fs::is_directory(root / "saves/folder"));
    CHECK(!fs::exists(root / "saves/folder.tmp"));
    // A file where the folder should be: refused, the file is untouched.
    CHECK(!replace_file(root / "saves/sub/highs/inside", bytes("x")));
    CHECK(read(root / "saves/sub/highs") == "second, longer");
    // A temporary left by a crash does not stop the next write.
    { std::ofstream(root / "saves/old.tmp", std::ios::binary) << "junk"; }
    CHECK(replace_file(root / "saves/old", bytes("fresh")));
    CHECK(read(root / "saves/old") == "fresh" && !fs::exists(root / "saves/old.tmp"));
    // A match's clean end (commit_folder): only what changed is written, each previous file kept in the backup folder first.
    const fs::path saves = root / "match/saves", backup = root / "match/saves.bak";
    CHECK(replace_file(saves / "a", bytes("old a")) && replace_file(saves / "b", bytes("same")) &&
          replace_file(saves / "dir/c", bytes("to remove")) && replace_file(backup / "a", bytes("older a")));
    std::map<std::string, std::optional<std::vector<uint8_t>>> last = {
        {"a", bytes("new a")}, {"b", bytes("same")}, {"dir/c", std::nullopt}, {"e", bytes("new file")}, {"f", std::nullopt}};
    CHECK(commit_folder(saves, backup, last));
    CHECK(read(saves / "a") == "new a" && read(backup / "a") == "old a");                  // one step: the older backup goes
    CHECK(read(saves / "b") == "same" && !fs::exists(backup / "b"));                       // unchanged: neither written nor kept
    CHECK(!fs::exists(saves / "dir/c") && read(backup / "dir/c") == "to remove");          // removed by the game: kept, then gone
    CHECK(read(saves / "e") == "new file" && !fs::exists(backup / "e"));                   // new: nothing to keep
    CHECK(!fs::exists(saves / "f") && !fs::exists(backup / "f"));
    CHECK(!fs::exists(saves / "a.tmp") && !fs::exists(backup / "a.tmp"));
    CHECK(commit_folder(saves, backup, last));                                             // the same again: nothing moves
    CHECK(read(saves / "a") == "new a" && read(backup / "a") == "old a");
    // A backup that cannot be written leaves its file as it was; a name outside the folder is refused.
    fs::create_directories(backup / "g", ec);
    CHECK(replace_file(saves / "g", bytes("keep")));
    CHECK(!commit_folder(saves, backup, {{"g", bytes("lost")}}));
    CHECK(read(saves / "g") == "keep");
    CHECK(!commit_folder(saves, backup, {{"../out", bytes("x")}}));
    CHECK(!fs::exists(root / "match/out"));
    std::printf(failures ? "FAILED (%d failures)\n" : "OK (%d failures)\n", failures);
    return failures ? 1 : 0;
}
'''


class SaveFileHarnessTest(unittest.TestCase):
    def test_the_save_helper_keeps_names_inside_and_a_refused_write_leaves_nothing(self):
        from retrorecomp.core import toolchain
        from retrorecomp.platforms import build_executable, cmake_target_args
        with tempfile.TemporaryDirectory(prefix='rr-amiga-savefile-') as temp:
            project = Path(temp)
            (project / 'harness.cpp').write_text(SAVEFILE_HARNESS, encoding='utf-8')
            native = (ROOT / 'native/amiga_machine').as_posix()
            (project / 'CMakeLists.txt').write_text(
                'cmake_minimum_required(VERSION 3.20)\n'
                'project(SaveFileChecks LANGUAGES CXX)\n'
                'set(CMAKE_CXX_STANDARD 20)\n'
                f'add_executable(savefile-checks "{(project / "harness.cpp").as_posix()}")\n'
                f'target_include_directories(savefile-checks PRIVATE "{native}")\n'
                'if(MSVC)\n'
                'target_compile_options(savefile-checks PRIVATE /W4 /WX /utf-8)\n'
                'else()\n'
                'target_compile_options(savefile-checks PRIVATE -Wall -Wextra -Werror)\n'
                'endif()\n', encoding='utf-8')
            cmake, generator = toolchain()
            for command in ([str(cmake), '-S', str(project), '-B', str(project / 'build'), '-G', generator,
                             *cmake_target_args()],
                            [str(cmake), '--build', str(project / 'build'), '--config', 'Release']):
                built = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            result = subprocess.run([str(build_executable(project / 'build', 'savefile-checks')), str(project / 'run')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('OK (0 failures)', result.stdout)


class RefusedSaveVerdictTest(unittest.TestCase):
    """tools/amiga_saves_check.py step 4b: what counts as a refused save handled (the tool's verdict, no game involved)."""

    def verdict(self, *args):
        import sys
        sys.path.insert(0, str(ROOT / 'tools'))
        import amiga_saves_check
        return amiga_saves_check.refused_save_handled(*args)

    def test_a_game_may_save_other_files_before_the_refused_one(self):
        message = 'SaveFileOffset failed with DOS error 221 (b/boxer.00A)'
        self.assertTrue(self.verdict(['ok', 'abort'], True, message, 'boxer.00a', False, [], True))
        self.assertTrue(self.verdict(['abort'], True, 'SaveFile failed with DOS error 221 (5thgear.highs)', '5thgear.highs', False, [], True))

    def test_the_stop_must_be_on_the_refused_file_and_leave_nothing_behind(self):
        message = 'SaveFileOffset failed with DOS error 221 (b/boxer.00I)'
        self.assertFalse(self.verdict(['ok', 'abort'], True, message, 'boxer.00a', False, [], True))      # another file was refused
        self.assertFalse(self.verdict(['abort', 'ok'], True, message, 'boxer.00i', False, [], True))      # a save went through after it
        self.assertFalse(self.verdict(['abort'], True, message, 'boxer.00i', False, ['boxer.00i.tmp'], True))
        self.assertFalse(self.verdict(['abort'], True, message, 'boxer.00i', False, [], False))
        self.assertFalse(self.verdict([], False, '', 'boxer.00i', True, [], True))

    def test_a_slave_that_goes_on_must_have_saved_nothing(self):
        self.assertTrue(self.verdict(['abort'], False, '', 'save.dat', True, [], True))
        self.assertFalse(self.verdict(['ok', 'abort'], False, '', 'save.dat', True, [], True))
        self.assertFalse(self.verdict(['abort'], False, '', 'save.dat', False, [], True))


if __name__ == '__main__':
    unittest.main()
