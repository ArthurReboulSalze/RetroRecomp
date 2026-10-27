"""Numeric shared-settings check; no video driver or screen capture."""
from pathlib import Path
import sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tools/, also when imported as tools.<name>
from selftest_build import compile_and_run
def main():
    project=ROOT/'.build/display-settings-selftest'; project.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rr-display-') as temp:
        result=compile_and_run(project,ROOT/'native/display_settings_checks.c',requires_sdl=True,
            sdl_config=None,include_dirs=(ROOT/'native',),link_libraries=('SDL2::SDL2-static',),
            link_options=('$<$<AND:$<C_COMPILER_ID:Clang>,$<PLATFORM_ID:Windows>>:-municode>',),
            compile_options=('$<$<C_COMPILER_ID:MSVC>:/utf-8>',),arguments=(Path(temp)/'Été settings',))
        print(result.strip())
if __name__=='__main__': main()
