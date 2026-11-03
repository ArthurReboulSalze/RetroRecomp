"""Compact validated game builds before they become public exports.

Windows and Linux x86-64 games are packed with the bundled, unmodified UPX
5.3.0 (licenses/UPX.md), then tested by UPX itself. This is how a game is
built, not what it does: a build input (compilation_inputs.BUILD_MODULES).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time

from . import timings
from .paths import ASSETS


UPX_VERSION = "5.3.0"
UPX_LEVEL = "-9"
# The compression method of each OS, one named constant each (1.6.7): 'lzma' (UPX --lzma) or 'nrv' (UPX's default, the
# NRV2 family, no method flag). Windows: LZMA, about 14 % smaller than NRV on average (NES -26 %, SNES -19 %) and packed
# about twice as fast, for a start that decompresses a little longer (tools/startup_cost.py measures it). A size choice,
# not an antivirus measure: nothing shows that it changes a detection. Linux: unchanged until the start-up cost of --lzma
# on a large ELF (see the note on UPX 5.2 below: 2.7 s against 0.17 s on a slow laptop) is measured again.
# `packing_record` reports the method of the file it describes.
WINDOWS_METHOD = 'lzma'
LINUX_METHOD = 'nrv'
METHOD_FLAGS: dict[str, tuple[str, ...]] = {'nrv': (), 'lzma': ('--lzma',)}
UPX_SHA256 = "ff30a651c9e41a2bbb363825fac9e7e23d92871c1ac82813a264e3b8d1cd302b"
# Official upx-5.3.0-amd64_linux.tar.xz (SHA-256 79cea8a5...dc505c1), its upx file.
UPX_LINUX = "assets/tools/upx-amd64_linux"
UPX_LINUX_SHA256 = "39bbf81cb4c56ce3e2e13a1755a31ec4970e33f061db8e214e9fac59354fc9aa"
# Large Mega Drive and Super Nintendo ELFs take longer than PEs to pack at -9.
LINUX_TIMEOUT = 300
# The limit only stops a packer that hangs. A fixed 120 s stopped Dragon Warrior IV (a 512 KiB NES board, a large
# executable) on Windows while other conversions shared the CPUs (1.6.5): the limit now grows with the file, 10 s
# per MB, never below LINUX_TIMEOUT.
SECONDS_PER_MB = 10


def upx_timeout(path: Path) -> int:
    """Seconds allowed to one UPX pass (pack or test) on `path`."""
    try:
        size = Path(path).stat().st_size
    except OSError:
        size = 0
    return max(LINUX_TIMEOUT, SECONDS_PER_MB * -(-size // 1_000_000))
# UPX 5.2.0 and 5.2.1 can reject, with "compressed data violation", their own default (NRV) packing of a
# large ELF at `upx -t` and `upx -d` although the data are valid and the packed program runs (upx/upx
# issue 18937: the test unpacks each block in place with too little slack; fixed in UPX 5.3.0, the bundled
# release since 1.6.2). Seen on Debian with the 78 MB Neo Geo Metal Slug 3 game, in 1.5.6 as in
# 1.6.0. -1, --best, --nrv2b/d/e, --no-filter and a stripped file fail the same way. --lzma passes the test
# and is smaller (40 MB against 45 MB) but a start costs 2.7 s instead of 0.17 s on a Core i7-6600U (the
# unpacked 78 MB file starts in 0.01 s), and the Neo Geo F11 machine switch starts the file again: not
# worth it for the player, so a game UPX cannot pack and test is published unpacked, as built and validated.
# 5.3.0 fixes the known case; the fallback stays as a safety net for any other game UPX rejects.
# The reason is kept for packing_record by the SHA-256 of the unpacked bytes, and handed to the caller's
# `emit` (the conversion log that the interface and the batch command line show); with no `emit` it goes
# to stderr, once.
_UNPACKED_REASONS: dict[str, str] = {}

# A build whose compressed copy was replayed on every route and did not match, or did not even run, on this system (a
# Linux X68000 game: the build runs and `upx -t` passes, the compressed copy stops at start). The conversion then
# replays the build as built; only when the build passes every route and the compressed copy fails again on the route it
# failed on (a failure that is not reproduced is no fault of the compression) does
# delivery_evidence.DeliveredFile.confirm_unpacked register the build here, by the SHA-256 of the unpacked bytes, with
# the notice. A refusal is never registered before that confirmation. The publication packs the same build again (UPX is deterministic), so
# `_compact_executable` looks here first: a build registered here is published unpacked, exactly as it passed every
# route, never as a compressed file nobody replayed successfully. It lives as long as the process, which a conversion
# and its publication share.
_REPLAY_REFUSED: dict[str, str] = {}

# The player's global option "Compress games" (preference `compress_games`, command line `--no-compress`). It exists
# because of Windows Defender: its machine-learning detection (`Program:Win32/Contebrew.A!ml`, a false positive)
# sometimes flags a freshly built, UPX-packed game, and an unpacked game is 3 to 4 times larger but the same program.
# On by default (today's behaviour). The window and the command line set it for the process before a conversion
# starts (`set_compression`); a conversion never reads the preferences file itself, so tests and other tools that call
# `compact_executable` get the default unless they say otherwise. When it is off, the executable is published exactly as
# built and validated, UPX is not run, and the reason is the same kind of notice as a game UPX could not pack.
_COMPRESSION = True
UNCOMPRESSED_NOTICE = ('Published uncompressed: the player turned the "Compress games" option off. '
                       'A larger file, the same program.')


def set_compression(enabled: bool) -> None:
    """Turn the UPX compression of published games on or off for this process (the player's option)."""
    global _COMPRESSION
    _COMPRESSION = bool(enabled)


def compression_enabled() -> bool:
    """Whether published games are compressed (True unless the player turned the option off)."""
    return _COMPRESSION


def refuse_compression(sha256: str, notice: str) -> None:
    """Say that the build with this SHA-256 must not be published compressed: its compressed copy failed its replay.

    `notice` is the reason (the text the log and `packing_record`'s `unpacked_reason` carry). From now on
    `compact_executable` leaves that build as built and returns the notice, and `packing_record` reports it."""
    _REPLAY_REFUSED[sha256] = notice
    _UNPACKED_REASONS[sha256] = notice


def compression_from_preferences(preferences: dict) -> bool:
    """The option as saved in Retro-Recomp.json: on unless `compress_games` is explicitly false."""
    return preferences.get('compress_games', True) is not False


def packing_method() -> str:
    """The compression method ('lzma' or 'nrv') this OS packs games with (WINDOWS_METHOD, LINUX_METHOD)."""
    return WINDOWS_METHOD if os.name == 'nt' else LINUX_METHOD


def file_identity(path: Path) -> dict:
    """Size and SHA-256 of one executable."""
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def packing_record(unpacked: dict, published: Path, packed_replayed: bool = False) -> dict:
    """What a conversion report says about the published executable's packing.

    The conversion compares native and reference runs on the *unpacked* build
    executable; the published one is that file packed by UPX. This records both
    identities and whether the published file really carries the UPX header, so
    a packed validation (tools/snes_packed_check.py) can name the exact file it
    checked. It claims a packed replay only when the conversion says it did one
    (`packed_replayed`: Neo Geo, CPS-1 and X68000 replay a packed copy against the
    reference, `native_validation.packed_reference_match`). A Linux game that UPX
    could not pack and test is published unpacked (`packed` false) and `unpacked_reason`
    says why; so is a game whose compressed copy failed its replay on the system that
    converted it (`refuse_compression`), and the conversion then replayed the unpacked file.
    """
    data = Path(published).read_bytes()
    packed = b'UPX!' in data
    record = {'packer': 'UPX', 'version': UPX_VERSION, 'level': UPX_LEVEL,
              'method': packing_method() if packed else None, 'packed': packed, 'unpacked': unpacked,
              'published': {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()},
              'size_ratio': round(len(data) / max(1, unpacked['bytes']), 4),
              'compared_on': 'unpacked build executable',
              'packed_validation': 'tools/snes_packed_check.py (developer qualification, not run during conversion)'}
    if packed_replayed and not packed:
        record['compared_on'] = 'unpacked build executable and the delivered file, also unpacked, replayed against the reference'
        record['packed_validation'] = 'delivered file replayed during conversion (native_validation.packed_reference_match); it is not compressed'
    elif packed_replayed:
        record['compared_on'] = 'unpacked build executable and a packed copy replayed against the reference'
        record['packed_validation'] = 'packed copy replayed during conversion (native_validation.packed_reference_match)'
    reason = _UNPACKED_REASONS.get(unpacked.get('sha256'))
    if reason and not packed:
        record['unpacked_reason'] = reason
    filtered = _CALL_FILTER_USED.get(unpacked.get('sha256'))
    if filtered and packed:
        # Only when the packing used a shorter filtered length (1.6.7); absent otherwise.
        record['call_filter'] = dict(filtered)
    return record


def compact_executable(path: Path, emit=None) -> dict | None:
    """``_compact_executable``, its time counted as the ``packing`` phase of the conversion (timings.py)."""
    with timings.phase('packing'):
        return _compact_executable(path, emit)


def _compact_executable(path: Path, emit=None) -> dict | None:
    """Pack a disposable staged copy; raise before replacing an existing game.

    On Windows and on Linux alike, a game UPX cannot pack and test is published unpacked, exactly
    as built and validated (compact_windows, compact_linux), rather than failing the conversion;
    only a validated original that is gone too is an error. Returns None when the file was packed as usual or
    left as built on purpose, else {'notice': text}, the reason it stays unpacked. The
    text is passed to `emit` (the conversion log) when given, else printed on stderr:
    never both, so a command line shows it once.

    With the player's option "Compress games" off (`set_compression`), UPX is not run at all: the file stays as built and
    validated and the notice says that the player chose it, which `packing_record` reports as `unpacked_reason`.

    A build registered by `refuse_compression` (its compressed copy failed the replay of the conversion) is left as built
    in the same way, with the notice that registration gave."""
    if not _COMPRESSION:
        _UNPACKED_REASONS[file_identity(path)['sha256']] = UNCOMPRESSED_NOTICE
        return _announce({'notice': UNCOMPRESSED_NOTICE}, emit)
    refused = _REPLAY_REFUSED.get(file_identity(path)['sha256']) if _REPLAY_REFUSED else None
    if refused:
        return _announce({'notice': refused}, emit)
    sha256 = file_identity(path)['sha256']
    outcome = compact_windows(path) if os.name == 'nt' else compact_linux(path)
    kept = _CALL_FILTER_USED.get(sha256)
    if outcome is None and kept and emit is not None:
        emit(f"UPX call filter kept over {round(100 * kept['filtered_bytes'] / kept['code_bytes'])} % of the code "
             f"({kept['filtered_bytes']} of {kept['code_bytes']} bytes): a smaller game.")
    return _announce(outcome, emit)


def _announce(outcome: dict | None, emit=None) -> dict | None:
    """Pass the notice of an unpacked outcome to `emit`, else print it on stderr (once), and return the outcome."""
    if outcome:
        if emit is not None:
            emit(outcome['notice'])
        else:
            print(outcome['notice'], file=sys.stderr, flush=True)
    return outcome


# Windows Defender's machine-learning detection (`Program:Win32/Contebrew.A!ml`, a false positive) has removed UPX's
# temporary output while it packed a freshly built game: UPX then stops with an I/O error ("IOException ... Invalid
# argument") and, until 1.6.6, the whole conversion failed after minutes of work. Seen on Neo Geo and NES games.
_DEFENDER_SIGNS = ('IOException', 'Invalid argument', 'WinError 225', 'virus', 'potentially unwanted')


# UPX shrinks the x86-64 code of a Windows game with a "call trick" filter before it compresses it (relative CALL and JMP
# operands become absolute addresses that repeat, a gain of 1 % to 25 %). The filter (upx/upx src/filter/ctok.h, the one
# win64/pe uses, id 0x49) needs one spare byte value, `cto`: a value that is not the first (low) operand byte of any E8, E9
# or 0F 8x byte of the code whose displacement leaves the code. Every such byte counts, also inside other instructions and
# in tables, so in a few MB of code the 256 values are used up: the Super Mario Land build of 1.6.5 left one spare value
# (162 = 0xa2), 1.6.6 added 1.5 KB of code that used it, UPX then found no filter at all and the packed game grew from
# 1.33 MB to 1.65 MB. `--all-filters`, `--brute` and `--filter` cannot help (the PE packer has this one
# filter and the filter itself fails). UPX bounds the filter by the SizeOfCode field of the PE header it reads (pefile.cpp,
# from BaseOfCode), so a shorter length leaves fewer such bytes in sight and can free a value. The game is packed with the
# longest length for which a value is free (this model is the same scan as UPX's, in Python; UPX stays the judge: the packed
# file must pass `upx -t` and `upx --fileinfo` must show filter 0x49, else the validated build is put back and packed as
# before). The packed file carries UPX's own SizeOfCode (`oh.codesize = osection[1].vsize`): the patched value exists only
# in UPX's input and in the output of `upx -d`. Deterministic: the same build gives the same bytes.
CALL_FILTER_MIN_SHARE = 4    # a shorter filtered part than 1/4 of the code is not worth a different SizeOfCode
CALL_FILTER_ID = '0x49'      # the filter UPX must report for the packed file
CALL_FILTER_MAX_BUF = 0x00FFFFFF      # max_buf_len of filter 0x49 (filter_impl.cpp): UPX does not filter a longer buffer
# The build (SHA-256 of its bytes) whose packing used a shorter filtered length, for packing_record.
_CALL_FILTER_USED: dict[str, dict] = {}
# E8 and E9, and the 8x byte of a 0F 8x conditional jump (COND of filter 0x49, upx/upx src/filter/filter_impl.cpp).
_CALL_CANDIDATE = re.compile(rb'(?<=\x0f)[\x80-\x8f]|[\xe8\xe9]')


def _pe_code(data: bytes) -> tuple[int, int, int, int, int] | None:
    """(offset of SizeOfCode, SizeOfCode, file offset of the code, addvalue, bytes of the code UPX reads) of a 64-bit PE.

    UPX reads min(SizeOfRawData, VirtualSize) bytes of a section and fills the rest with zeros (pefile.cpp): the last
    number is how much of the code is read from the file. None when `data` is not a 64-bit PE this reads."""
    try:
        if data[:2] != b'MZ':
            return None
        pe = struct.unpack_from('<I', data, 0x3C)[0]
        if data[pe:pe + 4] != b'PE\0\0' or struct.unpack_from('<H', data, pe + 24)[0] != 0x20B:
            return None
        sections, optional = struct.unpack_from('<H', data, pe + 6)[0], struct.unpack_from('<H', data, pe + 20)[0]
        field = pe + 24 + 4
        size_of_code, base_of_code = struct.unpack_from('<I', data, field)[0], struct.unpack_from('<I', data, pe + 24 + 20)[0]
        table = pe + 24 + optional
        rvamin = min(struct.unpack_from('<I', data, table + 40 * n + 12)[0] for n in range(sections))
        for n in range(sections):
            virtual_size, rva, raw_size, raw = struct.unpack_from('<IIII', data, table + 40 * n + 8)
            if rva <= base_of_code < rva + max(virtual_size, raw_size):
                start = raw + base_of_code - rva
                if size_of_code and base_of_code + size_of_code <= rva + raw_size and start + size_of_code <= len(data):
                    readable = max(0, min(raw_size, virtual_size) - (base_of_code - rva))
                    return field, size_of_code, start, base_of_code - rvamin, readable
                return None
    except (struct.error, ValueError):
        pass
    return None


def call_filter_length(data: bytes) -> tuple[int, int] | None:
    """(length, cto) UPX's call-trick filter is predicted to accept at the longest, for the PE `data`.

    The scan is UPX's own (src/filter/ctok.h): a candidate is an E8 or E9 byte or the 8x of a 0F 8x jump, its target is
    `rel32 + position + 1`; a target inside the filtered length is a call, a target outside marks the candidate's first
    operand byte as taken, and `cto` is any value left. For each value the lengths where it is taken are intervals (a
    candidate counts from position + 6 up to its target), merged as the scan goes. UPX gives up when a target inside
    the length reaches 2**24 with `addvalue`, and does not filter a buffer over CALL_FILTER_MAX_BUF bytes: the length
    is capped there, so a code over 16 MiB is filtered over at most its first 16 MiB - 1 bytes at best. The code is
    what UPX reads: the section's bytes up to its VirtualSize, zeros after. None when the data is not a 64-bit PE; the
    SizeOfCode itself when a value is free over the whole code (and it is under the cap)."""
    located = _pe_code(data)
    if located is None:
        return None
    _, size_of_code, start, addvalue, readable = located
    limit = min(size_of_code, (1 << 24) - addvalue, CALL_FILTER_MAX_BUF)
    code = data[start:start + min(limit, readable)]
    code += bytes(limit - len(code))
    first = [None] * 256        # start of the last merged interval where each value is taken
    last = [0] * 256            # its end
    unpack = struct.Struct('<I').unpack_from
    for match in _CALL_CANDIDATE.finditer(code):
        position = match.start()
        begin = position + 6
        if begin > limit:
            break
        low = code[position + 1]
        target = (unpack(code, position + 1)[0] + position + 1) & 0xFFFFFFFF
        end = min(target, limit)
        if end < begin:
            continue
        if first[low] is None or begin > last[low] + 1:
            first[low], last[low] = begin, end
        elif end > last[low]:
            last[low] = end
    best = (0, 0)
    for value in range(256):
        length = limit if first[value] is None or last[value] < limit else first[value] - 1
        if length > best[0]:
            best = (length, value)
    return best if best[0] else None


def _call_filter_prefix(path: Path) -> int | None:
    """The SizeOfCode to give a game before UPX when its call filter would otherwise be lost, else None.

    None for a file that is not a 64-bit PE, when the whole code keeps a free value (UPX filters it as it is) and when
    the longest filterable part is under 1/CALL_FILTER_MIN_SHARE of the code (the gain would not pay for it). A code
    over the 16 MiB UPX can filter is given the length it can."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    return _prefix_of(data)


def _prefix_of(data: bytes) -> int | None:
    """`_call_filter_prefix` for the bytes of the build."""
    found = call_filter_length(data)
    located = _pe_code(data)
    if found is None or located is None or found[0] >= located[1] or found[0] * CALL_FILTER_MIN_SHARE < located[1]:
        return None
    return found[0]


def _set_size_of_code(path: Path, length: int) -> None:
    """Write `length` as the SizeOfCode field of the PE header of `path`, the input of UPX (OSError when it cannot)."""
    field = _pe_code(Path(path).read_bytes())[0]
    with Path(path).open('r+b') as stream:
        stream.seek(field)
        stream.write(struct.pack('<I', length))


def _windows_attempt(tool: Path, path: Path) -> str | None:
    """Pack then test `path` in place with the Windows flags: None when both passed, else why not."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    # The exhaustive --best search can spend minutes on large native ROM-PC
    # tables. Level 9 retains the same transparent loader and most of the
    # size reduction with a bounded conversion time.
    for args in (("-9", *METHOD_FLAGS[WINDOWS_METHOD], "--compress-resources=0", "--compress-icons=0", str(path)),
                 ("-t", str(path))):
        try:
            result = subprocess.run((str(tool), *args), capture_output=True, text=True,
                                    timeout=upx_timeout(path), creationflags=flags)
        except subprocess.TimeoutExpired:
            return f"UPX {args[0]} timed out after {upx_timeout(path)} s"
        except OSError as exc:
            return str(exc)
        if result.returncode:
            detail = (result.stderr or result.stdout).strip().splitlines()
            return detail[-1].replace(f"{path}: ", "") if detail else 'unknown error'
    return None


# A pack attempt that fails with one of the signs above is tried once more, with exactly the same command, on the validated
# build put back, after this many seconds (the antivirus's scan of UPX's output is usually over by then). Never another option.
DEFENDER_RETRY_WAIT = 5


def _defender_failure(failure: str | None) -> bool:
    """Whether `failure` carries one of the signs of an antivirus that removed UPX's output."""
    return bool(failure) and any(sign in failure for sign in _DEFENDER_SIGNS)


def _windows_pack(tool: Path, path: Path, original: Path, prepare=None) -> str | None:
    """`_windows_attempt` with one identical retry after a Defender sign: None when packed and tested, else why not.

    On a sign, the validated build is put back, `prepare` (what the first attempt did to the staged copy before UPX, if
    anything) is done again, DEFENDER_RETRY_WAIT seconds pass and the very same command runs once more. The second
    result is final: no third attempt and no other option, flag or file to get past a detection."""
    failure = _windows_attempt(tool, path)
    if not _defender_failure(failure):
        return failure
    try:
        _put_back(original, path, failure)
        if prepare is not None:
            prepare()
    except OSError:
        return failure
    time.sleep(DEFENDER_RETRY_WAIT)
    return _windows_attempt(tool, path)


def _put_back(original: Path, path: Path, failure: str) -> None:
    """Put the validated build back over the game UPX left half-done; an original that cannot be put back is an error."""
    try:
        shutil.copyfile(original, path)
    except OSError as exc:
        raise RuntimeError(f"UPX could not compact or verify {path.name} ({failure}), and the validated "
                           f"executable could not be put back: {exc}") from exc


def _packed_filter(tool: Path, path: Path) -> str | None:
    """The filter id (`0x49`) UPX says the packed `path` carries, from `upx --fileinfo`; None when it says none or fails."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        result = subprocess.run((str(tool), '--fileinfo', str(path)), capture_output=True, text=True,
                                timeout=upx_timeout(path), creationflags=flags)
    except (subprocess.TimeoutExpired, OSError):
        return None
    found = re.search(r'filter (0x[0-9a-f]+)/', result.stdout or '') if result.returncode == 0 else None
    return found.group(1) if found else None


def _pack_with_filter_prefix(tool: Path, path: Path, original: Path) -> tuple[bool, str | None]:
    """Pack the build at `path` with the longest filterable SizeOfCode when UPX would lose its call filter.

    (True, None) when the file was packed, passed `upx -t` and UPX reports filter 0x49 for it (the build is noted for
    `packing_record` and the conversion log, see `_compact_executable`). Otherwise the validated build is put back and
    (False, None) is returned, so the caller packs it as before: nothing to do, a build that keeps its filter, a header
    that cannot be written (the antivirus may have locked the staged copy), a pack or test that fails, or a packed file
    that has no filter. (False, failure) when the antivirus removed UPX's output again after the identical retry: the
    caller does not try another form of the same build."""
    try:
        built = original.read_bytes()
    except OSError:
        return False, None
    identity = hashlib.sha256(built).hexdigest()
    _CALL_FILTER_USED.pop(identity, None)       # a note of an earlier packing of this build is not this one's
    prefix = _prefix_of(built)
    if not prefix:
        return False, None
    try:
        _set_size_of_code(path, prefix)
        failure = _windows_pack(tool, path, original, lambda: _set_size_of_code(path, prefix))
        if failure is None and _packed_filter(tool, path) == CALL_FILTER_ID:
            _CALL_FILTER_USED[identity] = {'filter': CALL_FILTER_ID, 'code_bytes': _pe_code(built)[1],
                                           'filtered_bytes': prefix}
            return True, None
        failure = failure or f"no call filter in the packed file ({CALL_FILTER_ID} expected)"
    except OSError as exc:
        failure = str(exc)
    _put_back(original, path, failure)
    return False, failure if _defender_failure(failure) else None


def compact_windows(path: Path) -> dict | None:
    """Pack a Windows game with the bundled UPX; publish it unpacked when that fails.

    The validated original is kept beside it while UPX works. When UPX cannot pack and test the
    file (or the antivirus removed its temporary output), the original is put back and the game
    is published unpacked, exactly as built and validated, with the reason as {'notice': text};
    None means it was packed and tested. A missing or altered UPX, or an original that cannot be
    put back, is still an error. A build whose call filter UPX would lose is first packed with the longest filterable
    SizeOfCode (see above); `_CALL_FILTER_USED` then says so."""
    tool = ASSETS / "assets/tools/upx.exe"
    if not tool.is_file() or hashlib.sha256(tool.read_bytes()).hexdigest() != UPX_SHA256:
        raise RuntimeError("Bundled UPX 5.3.0 is missing or failed its integrity check.")
    handle, name = tempfile.mkstemp(prefix='.upx-original-', dir=path.parent)
    os.close(handle)
    original = Path(name)
    try:
        shutil.copyfile(path, original)
        packed, blocked = _pack_with_filter_prefix(tool, path, original)
        if packed:
            return None
        # The plain attempt follows a failed filter attempt (a size matter) but not an antivirus removal that the identical
        # retry did not get past: no other form of the same build is tried to get past a detection.
        failure = blocked or _windows_pack(tool, path, original)
        if failure is None:
            return None
        _put_back(original, path, failure)
        defender = _defender_failure(failure)
        notice = (
            f"UPX {UPX_VERSION} could not pack and verify the executable ({failure})"
            f"{'; the antivirus most likely removed its temporary file (a known false positive)' if defender else ''}. "
            "It is published unpacked, exactly as built and validated: a larger file, the same program.")
        _UNPACKED_REASONS[hashlib.sha256(original.read_bytes()).hexdigest()] = notice
        return {'notice': notice}
    finally:
        original.unlink(missing_ok=True)


def _linux_tool(folder: Path) -> tuple[Path, Path | None]:
    """The verified packer, and a private copy to delete when the bundled one
    is not executable (a converter unpacked without file modes)."""
    tool = ASSETS / UPX_LINUX
    data = tool.read_bytes() if tool.is_file() else b''
    if hashlib.sha256(data).hexdigest() != UPX_LINUX_SHA256:
        raise RuntimeError("Bundled UPX 5.3.0 is missing or failed its integrity check.")
    if os.access(tool, os.X_OK):
        return tool, None
    # Beside the game being published: that volume must already allow programs.
    private = Path(tempfile.mkdtemp(prefix='.upx-', dir=folder))
    copy = private / 'upx'
    with copy.open('xb') as stream:
        stream.write(data)
    copy.chmod(0o700)
    return copy, private


def _upx_attempt(tool: Path, path: Path) -> str | None:
    """Pack then test `path` in place: None when both passed, else why not. A packer
    that cannot even start (OSError) is an installation fault and stays an error."""
    for args in (("-9", *METHOD_FLAGS[LINUX_METHOD], "-q", str(path)), ("-t", "-q", str(path))):
        limit = upx_timeout(path)
        try:
            result = subprocess.run((str(tool), *args), capture_output=True, text=True,
                                    timeout=limit)
        except subprocess.TimeoutExpired:
            return f"UPX {args[0]} timed out after {limit} s"
        except OSError as exc:
            raise RuntimeError(f"UPX could not compact or verify {path.name}: {exc}") from exc
        if result.returncode:
            detail = (result.stderr or result.stdout).strip().splitlines()
            # "upx-amd64_linux: /path/packed-game.exe: Exception: compressed data violation"
            return detail[-1].replace(f"{path}: ", "").split(": ", 1)[-1] if detail else 'unknown error'
    return None


def compact_linux(path: Path) -> dict | None:
    """Pack a native Linux x86-64 game; leave other ELFs as built.

    Every console is packed. Players only use /proc/self/exe to find their
    folder; their data, X68000 disks and firmware included, is linked into the
    program (resources.embed_resources) and restored by UPX with the rest.

    The packing is the one every earlier release used, byte for byte. When UPX cannot
    pack the game or rejects its own result (see the note on UPX 5.2.0 and 5.2.1 above), the
    validated original is put back and the game is published unpacked, exactly as built,
    rather than failing the whole conversion. That is returned as {'notice': text};
    None means the game was packed and tested, or is not an x86-64 ELF."""
    with path.open('rb') as stream:
        header = stream.read(20)
    if header[:4] != b'\x7fELF':
        raise RuntimeError('Expected a native Linux ELF executable.')
    # 64-bit little-endian x86-64 only: the bundled UPX is an x86-64 program.
    if (header[4:6] != b'\x02\x01' or int.from_bytes(header[18:20], 'little') != 62
            or platform.machine().lower() not in ('x86_64', 'amd64')):
        return None
    tool, private = _linux_tool(path.parent)
    # UPX rewrites the file in place: keep the validated original beside it.
    handle, name = tempfile.mkstemp(prefix='.upx-original-', dir=path.parent)
    os.close(handle)
    original = Path(name)
    try:
        shutil.copyfile(path, original)
        failure = _upx_attempt(tool, path)
        if failure is None:
            return None
        shutil.copyfile(original, path)
        notice = (
            f"UPX {UPX_VERSION} could not pack and verify the executable ({failure}"
            f"{'; upx/upx issue 18937' if 'violation' in failure else ''}). It is published unpacked, "
            "exactly as built and validated: a larger file, the same program.")
        _UNPACKED_REASONS[hashlib.sha256(original.read_bytes()).hexdigest()] = notice
        return {'notice': notice}
    finally:
        original.unlink(missing_ok=True)
        if private:
            shutil.rmtree(private, ignore_errors=True)
