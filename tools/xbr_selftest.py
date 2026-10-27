"""Compile/check shared xBR contours and measure CPU cost without game images."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from selftest_build import compile_and_run

def main():
    project=ROOT/'.build/xbr-selftest';project.mkdir(parents=True,exist_ok=True)
    result=compile_and_run(project,ROOT/'native/xbr_checks.c',log=True,timeout=60)
    (project/'checks.log').write_text(result);print(result)
if __name__=='__main__': main()
