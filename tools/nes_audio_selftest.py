"""Build the host kit's callback-ring output (the NES host's sound) and check authored PCM timelines, silently."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tools/, also when imported as tools.<name>
from selftest_build import compile_and_run

def main():
    project = ROOT / '.build/nes-audio-selftest'
    project.mkdir(parents=True, exist_ok=True)
    result = compile_and_run(project, ROOT/'native/nes_audio_checks.c',
        include_dirs=(ROOT/'native',), requires_sdl=True, link_libraries=('SDL2::SDL2-static',), log=True, timeout=60)
    (project/'checks.log').write_text(result)
    print(result)

if __name__ == '__main__': main()
