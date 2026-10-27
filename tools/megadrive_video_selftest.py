"""Exercise VDP interlace patterns and the shared presentation geometry, headless."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from selftest_build import compile_and_run


def main():
    project = ROOT / '.build/megadrive-video-selftest'
    project.mkdir(parents=True, exist_ok=True)
    engine = ROOT / '.deps/segagenesisrecomp/runner'
    result = json.loads(compile_and_run(project,(ROOT/'native/md_video_checks.c',
        engine/'video/genesis_vdp.c'),include_dirs=(ROOT/'native',engine),
        compile_options=('$<$<C_COMPILER_ID:MSVC>:/utf-8>',),log=True,parallel=2).strip())
    (project/'results.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
