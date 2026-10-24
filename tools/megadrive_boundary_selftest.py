"""Compare same-clock checkpoint coalescing against the original arbiter."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from retrorecomp.core import run
from tools.megadrive_bus_selftest import executable


def check(project, output,benchmark=False):
    exe=executable(project,output,(ROOT/'native/md_boundary_checks.c').read_text())
    result=json.loads(run([exe,*(['--benchmark'] if benchmark else [])]).strip().splitlines()[-1])
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('project',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--benchmark',action='store_true')
    args=p.parse_args();print(json.dumps(check(args.project.resolve(),args.output.resolve(),args.benchmark)))
