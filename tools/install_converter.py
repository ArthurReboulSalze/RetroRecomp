"""Install a completed converter build, preserving a currently open version."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.publishing import publish_executable

if __name__ == '__main__':
    pending = publish_executable(Path(sys.argv[1]), Path(sys.argv[2]))
    print('Converter ready; installation when the current window closes.' if pending else 'Converter installed.')
