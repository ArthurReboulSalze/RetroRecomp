"""Compile/check shared xBR contours and measure CPU cost without game images."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from smsrecomp.core import run,toolchain

def main():
    project=ROOT/'.build/xbr-selftest';project.mkdir(parents=True,exist_ok=True)
    (project/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.21)
project(XbrChecks C)
add_executable(checks "{ROOT.as_posix()}/native/xbr_checks.c")
''')
    cmake,generator=toolchain();log=project/'build.log'
    run([cmake,'-S',project,'-B',project/'build','-G',generator,'-A','x64'],log=log)
    run([cmake,'--build',project/'build','--config','Release','--parallel','4'],log=log)
    result=run([project/'build/Release/checks.exe'],timeout=60)
    (project/'checks.log').write_text(result);print(result)
if __name__=='__main__': main()
