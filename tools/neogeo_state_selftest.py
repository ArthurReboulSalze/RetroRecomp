"""Developer CLI for the same state gates used by the converter."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from smsrecomp.neogeo_state_checks import check, check_invalid, probe, reframe

def main():
    p=argparse.ArgumentParser();p.add_argument('exe',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--warmups',type=int,nargs='+',default=[30,2600,3300]);p.add_argument('--replay',type=int,default=300)
    p.add_argument('--input-script',type=Path,help='Exact cartridge controller route, rather than the historical NAM route.')
    a=p.parse_args();print(json.dumps(check(a.exe.resolve(),a.output.resolve(),a.warmups,a.replay,a.input_script)))
if __name__=='__main__':main()
