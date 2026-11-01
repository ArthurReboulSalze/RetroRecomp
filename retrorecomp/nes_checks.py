"""What a NES conversion checks on the file it delivers: how alive a route is, and a quick state in a fresh process.

Both read what the exported game's headless mode writes. `--hash-out` gives one line per frame (the CPU trace, the
memory and hardware hashes, the program counter and registers, and, since 1.6.6, `pic=` the hash of the rendered picture,
`snd=` the hash of the frame's sound and `aud=` 1 when a sample was not zero). The counting of a route is
`delivery_evidence.liveness_summary` (gate G8); the state continuation is the fresh-process check of gate G6.
Nothing here says what the picture shows or how far into the game a route goes.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import shutil
import tempfile
import wave

from .core import ConversionError, run
from .delivery_evidence import FrameRow, liveness_summary, report_fields

# The report keys of a route's liveness, from the common record (the names CPS-1 writes, then the three it does not).
LIVENESS_FIELDS = {'frames': 'frames', 'distinct_pictures': 'distinct_pictures', 'picture_changes': 'picture_changes',
                   'last_picture_change_frame': 'last_picture_change_frame', 'audible_frames': 'audible_frames',
                   'last_audible_frame': 'last_audible_frame', 'distinct_sound_blocks': 'distinct_sound_blocks',
                   'distinct_ram_states': 'distinct_ram_states', 'distinct_program_counters': 'distinct_program_counters'}
HASH_LINE = re.compile(r'^(\d+) .*?\bmem=([0-9A-F]+) PC=([0-9A-F]{4}) .*\bpic=([0-9A-F]+) snd=([0-9A-F]+) aud=([01])$')


def hash_rows(trace: Path):
    """The per-frame rows of a `--hash-out` trace. A line without the picture and sound fields is a trace from an
    older player: it has no rows, so the record counts nothing (`frames`, `distinct_pictures`, `picture_changes` and
    `last_picture_change_frame` are 0) and says nothing of sound, RAM or counters (those keys, and the audible ones, are None)."""
    for line in Path(trace).read_text(encoding='ascii').splitlines():
        match = HASH_LINE.match(line)
        if match:
            frame, memory, counter, picture, sound, audible = match.groups()
            yield FrameRow(int(frame), picture, sound=sound, audible=audible == '1', ram=memory, pc=counter)


def route_liveness(trace: Path) -> dict:
    """Picture and sound activity of one route (gate G8), read from its trace."""
    return report_fields(liveness_summary(hash_rows(trace)), LIVENESS_FIELDS)


def resume_input(source: Path, start: int, target: Path) -> Path:
    """The input schedule to replay after a quick load at frame `start`: the keys held then, and the later events."""
    held = {1: '-', 2: '-'}
    events = []
    previous = -1
    for line in source.read_text(encoding='ascii').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        fields = line.split(maxsplit=1)
        frame = int(fields[0])
        if frame < previous or frame < 0:
            raise ValueError('Input events must be sorted and nonnegative')
        previous = frame
        keys = fields[1] if len(fields) > 1 else '-'
        port = 2 if keys.startswith('2:') else 1
        if keys.startswith(('1:', '2:')):
            keys = keys[2:]
        if frame < start:
            held[port] = keys
        else:
            events.append((frame - start, port, keys))
    target.write_text(''.join(f'{frame} {port}:{keys}\n'
                              for frame, port, keys in [(0, p, k) for p, k in held.items()] + events), encoding='ascii')
    return target


def _must(condition: bool, message: str) -> None:
    if not condition:
        raise ConversionError('NES quick state: ' + message)


def _created(folder: Path, exe: Path) -> list[str]:
    """What a run left beside the game, other than the cartridge's battery file: a game whose first frames change its
    battery RAM saves it at exit (datas/games/*.sav), which is the one file a start may create."""
    found = sorted(path.relative_to(folder).as_posix() for path in folder.rglob('*') if path.is_file() and path != exe)
    return [name for name in found if not (name.startswith('datas/games/') and name.endswith('.sav'))]


def _fresh_cartridge(folder: Path) -> None:
    """Every process of the check starts with the cartridge as new: the battery file an earlier process saved is removed,
    as the probes of a conversion do by running on private copies."""
    for path in (folder / 'datas' / 'games').glob('*.sav'):
        path.unlink()


def _refused(exe: Path, *arguments) -> bool:
    """Whether the game exits with an error on these arguments (a state it will not load)."""
    try:
        run([exe, *arguments])
    except ConversionError:
        return True
    return False


def check_states(executable: Path, frames: int = 180, *, save_after: int | None = None,
                 script: Path | None = None) -> dict:
    """F8/F9 in a fresh process on the delivered file.

    Starting and closing the game, and loading a missing state, create no file. A run saves its state at frame
    `save_after`; a second process saves the same run again and the two files are identical (every byte of a state is
    defined); a third process loads the state and its next `frames` frames equal, field by field, the first run's own
    timeline after the save, with the same sound. A state with a damaged header field, a damaged payload or a truncated
    file is refused, and neither the refused file nor the good one is touched. (Starting the game may write its
    battery file when its first frames change the cartridge's RAM; that is the only file a start may leave.)"""
    save_after = frames if save_after is None else save_after
    if frames < 1 or save_after < 1:
        raise ValueError('Save and continuation frame counts must be positive')
    with tempfile.TemporaryDirectory(prefix='retro-nes-state-') as temporary:
        folder = Path(temporary)
        exe = folder / 'game.exe'
        shutil.copy2(executable, exe)
        run([exe, '--frames', '1'])
        _must(not _created(folder, exe), 'starting the game created files')
        _must(_refused(exe, '--frames', '1', '--quick-load', folder / 'datas/states/missing.rrstate'),
              'a missing state was accepted')
        _must(not _created(folder, exe), 'loading a missing state created files')
        saved = folder / 'datas/states/fixture.rrstate'
        full_input = ['--input', script] if script else []
        resumed_input = ['--input', resume_input(script, save_after, folder / 'resume.input')] if script else []
        _fresh_cartridge(folder)
        run([exe, '--frames', str(save_after + frames), '--hash-out', folder / 'full.hash', '--wav-out', folder / 'full.wav',
             '--quick-save', saved, '--quick-save-frame', str(save_after - 1), *full_input])
        again = folder / 'datas/states/again.rrstate'
        _fresh_cartridge(folder)
        run([exe, '--frames', str(save_after + frames), '--hash-out', folder / 'again.hash', '--wav-out',
             folder / 'again.wav', '--quick-save', again, '--quick-save-frame', str(save_after - 1), *full_input])
        _must(again.read_bytes() == saved.read_bytes(), 'two saves of one run differ')
        _fresh_cartridge(folder)
        run([exe, '--frames', str(frames), '--hash-out', folder / 'resume.hash', '--wav-out', folder / 'resume.wav',
             '--quick-load', saved, *resumed_input])
        full = (folder / 'full.hash').read_text().splitlines()[save_after:]
        resumed = (folder / 'resume.hash').read_text().splitlines()
        _must(len(full) == len(resumed) == frames, 'the continuation has the wrong length')
        # Trace accounting is cumulative within a process: compare the fields from the memory hash on, which
        # include the cycles, the chip state, and the picture and sound of each frame.
        _must(all(a[a.index('mem='):] == b[b.index('mem='):] for a, b in zip(full, resumed)),
              'the continuation differs from the run it was saved from')
        with wave.open(str(folder / 'full.wav')) as stream:
            pcm = stream.readframes(stream.getnframes())
        with wave.open(str(folder / 'resume.wav')) as stream:
            resumed_pcm = stream.readframes(stream.getnframes())
        _must(bool(resumed_pcm) and pcm[-len(resumed_pcm):] == resumed_pcm, 'the sound of the continuation differs')
        original = saved.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        # The header fields are not covered by the payload checksum: each has its own identity gate.
        for name, offset in [('magic', 0), ('abi', 8), ('rom', 73), ('region', 148), ('payload', len(original) - 1),
                             ('truncated', None)]:
            damaged = bytearray(original)
            if offset is None:
                damaged = damaged[:-1]
            else:
                damaged[offset] ^= 0x80
            rejected = folder / f'{name}.rrstate'
            rejected.write_bytes(damaged)
            _must(_refused(exe, '--frames', '1', '--quick-load', rejected), f'a state with a damaged {name} was accepted')
            _must(rejected.read_bytes() == damaged, 'a refused load rewrote the refused file')
            _must(hashlib.sha256(saved.read_bytes()).hexdigest() == digest, 'a refused load rewrote the good state')
        return {'executable': str(executable), 'saved_after_frames': save_after,
                'input_sha256': hashlib.sha256(script.read_bytes()).hexdigest() if script else None,
                'resumed_frames': frames, 'state_bytes': len(original), 'rejected_state_cases': 6,
                'two_saves_identical': True, 'cpu_memory_hardware_match': True, 'pcm_match': True, 'lazy_io': True,
                'corruption_rejected': True}
