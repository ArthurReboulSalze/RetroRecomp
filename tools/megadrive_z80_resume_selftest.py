"""ROM-free code mutations in the actual backend's suspended Z80 fibers."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run
from retrorecomp.megadrive_z80 import generate
from tools.megadrive_bus_selftest import executable


def check(project, output):
    output.mkdir(parents=True, exist_ok=True)
    variants = [{'address': pc, 'bytes': raw} for pc in (0, 0x8000)
                for raw in ('3e9a0000', 'dd219a00', 'fd219a00', 'cb460000',
                            'ed430000', 'ddcbf946', 'ddfd2100', 'dded4300')]
    generate(output, ROOT / '.deps/segagenesisrecomp', variants)
    exe = executable(project, output,
        (ROOT / 'native/md_z80_resume_checks.c').read_text(encoding='utf-8'),
        output / 'md_z80_generated.c')
    result = json.loads(run([exe]).strip().splitlines()[-1])
    (output / 'resume.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('project', type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    print(json.dumps(check(args.project.resolve(), args.output.resolve())))
