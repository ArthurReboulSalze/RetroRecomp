"""Build and validate the private native Neo Geo prototype from local data."""
from pathlib import Path
import argparse
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.neogeo_build import convert_reference,convert_native

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cartridge',type=Path)
    parser.add_argument('--bios',required=True,type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--set',dest='set_name')
    parser.add_argument('--reference',action='store_true',help='Build the wholly interpreted baseline only.')
    options=parser.parse_args()
    convert=convert_reference if options.reference else convert_native
    executable=convert(options.cartridge,bios=options.bios,output=options.output,set_name=options.set_name)
    print(executable)

if __name__=='__main__':main()
