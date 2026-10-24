"""Quick states written by one NES EXE must continue identically in another build.

    python tools/nes_state_cross.py A.exe B.exe [--frames N] [--save-after N] [--input FILE]

Used to compare the Visual Studio and portable-toolchain builds of one game:
A saves a state mid-run, B resumes it in a fresh process, and B's per-frame
hashes and audio must equal A's own continuation (and the other way round).
"""
import argparse
from pathlib import Path
import shutil
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run
from tools.nes_state_selftest import resume_input


def pcm(path: Path) -> bytes:
    with wave.open(str(path)) as stream:
        return stream.readframes(stream.getnframes())


def cross(writer: Path, reader: Path, frames: int, save_after: int, script: Path | None) -> None:
    with tempfile.TemporaryDirectory(prefix='retro-nes-cross-') as temp:
        folder = Path(temp)
        first, second = folder / 'writer.exe', folder / 'reader.exe'
        shutil.copy2(writer, first)
        shutil.copy2(reader, second)
        saved = folder / 'datas/states/cross.rrstate'
        full_input = ['--input', script] if script else []
        resumed_input = ['--input', resume_input(script, save_after, folder / 'resume.input')] if script else []
        run([first, '--frames', str(save_after + frames), '--hash-out', folder / 'full.hash',
             '--wav-out', folder / 'full.wav', '--quick-save', saved,
             '--quick-save-frame', str(save_after - 1), *full_input])
        run([second, '--frames', str(frames), '--hash-out', folder / 'resume.hash',
             '--wav-out', folder / 'resume.wav', '--quick-load', saved, *resumed_input])
        full = (folder / 'full.hash').read_text().splitlines()[save_after:]
        resumed = (folder / 'resume.hash').read_text().splitlines()
        assert len(full) == len(resumed) == frames, (len(full), len(resumed))
        assert all(a[a.index('mem='):] == b[b.index('mem='):] for a, b in zip(full, resumed)), 'state continuation differs'
        tail, resumed_pcm = pcm(folder / 'full.wav'), pcm(folder / 'resume.wav')
        assert resumed_pcm and tail[-len(resumed_pcm):] == resumed_pcm, 'audio continuation differs'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first', type=Path)
    parser.add_argument('second', type=Path)
    parser.add_argument('--frames', type=int, default=180)
    parser.add_argument('--save-after', type=int, default=600)
    parser.add_argument('--input', type=Path)
    args = parser.parse_args()
    for writer, reader in ((args.first, args.second), (args.second, args.first)):
        cross(writer, reader, args.frames, args.save_after, args.input)
        print(f'OK: {writer.name} saved, {reader.name} resumed {args.frames} frames after frame {args.save_after}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
