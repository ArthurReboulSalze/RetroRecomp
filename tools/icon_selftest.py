"""Inspect the actual executable's resources, then test a hidden SDL window."""
import argparse
import ctypes
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.artwork import ICON_SIZES
from smsrecomp.core import ROOT, ASSETS, dependencies, run, slug
from smsrecomp.paths import games_directory


def embedded_icons(executable: Path, expected: Path, resource_id: int = 101) -> list[int]:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LoadLibraryExW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint32]
    kernel.LoadLibraryExW.restype = ctypes.c_void_p
    kernel.FindResourceW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    kernel.FindResourceW.restype = ctypes.c_void_p
    kernel.SizeofResource.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel.SizeofResource.restype = ctypes.c_uint32
    kernel.LoadResource.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel.LoadResource.restype = ctypes.c_void_p
    kernel.LockResource.argtypes = [ctypes.c_void_p]
    kernel.LockResource.restype = ctypes.c_void_p
    kernel.FreeLibrary.argtypes = [ctypes.c_void_p]
    module = kernel.LoadLibraryExW(str(executable.resolve()), None, 0x22)  # data only, never run WinMain
    assert module, ctypes.get_last_error()
    def resource(identifier, kind):
        found = kernel.FindResourceW(module, identifier, kind)
        assert found, (executable, identifier, kind)
        size = kernel.SizeofResource(module, found)
        data = kernel.LockResource(kernel.LoadResource(module, found))
        assert data and size
        return ctypes.string_at(data, size)
    try:
        group = resource(resource_id, 14)
        source = expected.read_bytes()
        count = struct.unpack_from("<HHH", group)[2]
        assert count == len(ICON_SIZES) == struct.unpack_from("<HHH", source)[2]
        sizes = []
        for index in range(count):
            width, height, _, _, planes, bits, length, identifier = struct.unpack_from("<BBBBHHIH", group, 6+index*14)
            width, height = width or 256, height or 256
            sw, sh, _, _, sp, sb, sl, offset = struct.unpack_from("<BBBBHHII", source, 6+index*16)
            # RC normalizes PNG icons from Pillow's planes=0 to planes=1.
            assert planes in (0, 1) and sp in (0, 1)
            assert (width, height, bits, length) == (sw or 256, sh or 256, sb, sl)
            assert resource(identifier, 3) == source[offset:offset+length]
            sizes.append(width)
        assert sorted(sizes) == list(ICON_SIZES)
        print(f"PASS {executable.name}: all nine embedded icon images match the compiled ICO.")
        return sizes
    finally:
        kernel.FreeLibrary(module)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=games_directory())
    args = parser.parse_args()
    output = args.output.resolve()
    report_path = output / 'conversion-report.json'
    if not report_path.exists():
        report_path = next((output / 'datas/reports').glob('Alex_Kidd_in_Miracle_World-*/conversion-report.json'))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    output = Path(report.get('published_directory', output))
    assert report["artwork"]["embedded"]
    game = Path(report["build_directory"])
    embedded_icons(output / report["executable"], game / "game.ico")
    engine, sdl, cmake, generator = dependencies()
    source = ROOT / ".build/native-source"
    source.mkdir(parents=True, exist_ok=True)
    import shutil
    for file in (ASSETS / "native").iterdir():
        if file.is_file(): shutil.copy2(file, source / file.name)
    build = ROOT / ".build/icon-checks-build"
    run([cmake, "-S", source, "-B", build, "-G", generator, "-A", "x64",
        f"-DENGINE_DIR={engine.as_posix()}", f"-DGAME_DIR={game.as_posix()}",
        f"-DSMSRECOMP_BANKED_AOT={'ON' if report['backend']=='banked' else 'OFF'}",
        f"-DGAME_NAME={slug(Path(report['executable']).stem)}", f"-DCMAKE_PREFIX_PATH={sdl.as_posix()}",
        "-DSMSRECOMP_ICON_CHECKS=ON"])
    run([cmake, "--build", build, "--config", "Release", "--target", "smsrecomp_icon_checks", "--parallel", "4"])
    print(run([build / "Release/smsrecomp_icon_checks.exe"]).strip())


if __name__ == "__main__":
    main()
