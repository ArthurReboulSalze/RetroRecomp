"""Authored numeric/input/resource checks; no video driver or visual testing."""
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.core import ROOT, ASSETS, dependencies, read_rom, default_config, prepare_runtime, run, video_standard
from smsrecomp.metadata import write_game_metadata


def version_strings(executable: Path, expected: dict) -> dict:
    lib = ctypes.WinDLL('version', use_last_error=True)
    lib.GetFileVersionInfoSizeW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
    lib.GetFileVersionInfoSizeW.restype = ctypes.c_uint32
    lib.GetFileVersionInfoW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    lib.GetFileVersionInfoW.restype = ctypes.c_int
    lib.VerQueryValueW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint32)]
    lib.VerQueryValueW.restype = ctypes.c_int
    handle = ctypes.c_uint32()
    size = lib.GetFileVersionInfoSizeW(str(executable.resolve()), ctypes.byref(handle))
    assert size, executable
    buffer = ctypes.create_string_buffer(size)
    assert lib.GetFileVersionInfoW(str(executable.resolve()), 0, size, buffer)
    result = {}
    for key, value in expected.items():
        pointer, length = ctypes.c_void_p(), ctypes.c_uint32()
        assert lib.VerQueryValueW(buffer, '\\StringFileInfo\\040904B0\\' + key, ctypes.byref(pointer), ctypes.byref(length)), key
        result[key] = ctypes.wstring_at(pointer.value)
        assert result[key] == value, (key, result[key], value)
    return result


def main():
    directory = ROOT / '.build/presentation-selftest'
    directory.mkdir(parents=True, exist_ok=True)
    os.environ['SMSRECOMP_LIBRARY_DIR'] = str(directory / 'learning')
    data = bytes(8192)
    rom_path = directory / 'rom.sms'
    rom_path.write_bytes(data)
    rom = read_rom(rom_path)
    (directory / 'game.toml').write_text(default_config(rom), encoding='utf-8')
    (directory / 'dispatch_manifest.txt').write_text('', encoding='utf-8')
    engine, sdl, cmake, generator = dependencies()
    prepare_runtime(directory, rom, 'Authored presentation fixture', engine)
    title = 'Été "test"\\name\nline'
    expected = write_game_metadata(directory, title, 'Authored.exe', light_phaser=True, icon=False)
    log = directory / 'build.log'
    run([ROOT / '.deps/recompiler-build/Release/SmsRecomp.exe', '--game', directory / 'game.toml', '--banked-step'], log=log)
    source = ROOT / '.build/native-source'
    source.mkdir(parents=True, exist_ok=True)
    for file in (ASSETS / 'native').iterdir():
        if file.is_file(): shutil.copy2(file, source / file.name)
    build = directory / 'build'
    run([cmake, '-S', source, '-B', build, '-G', generator, '-A', 'x64',
         f'-DENGINE_DIR={engine.as_posix()}', f'-DGAME_DIR={directory.as_posix()}',
         '-DGAME_NAME=AuthoredPresentation', f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}',
         '-DSMSRECOMP_BANKED_AOT=ON', '-DSMSRECOMP_PRESENTATION_CHECKS=ON',
         '-DSMSRECOMP_VIDEO_CHECKS=ON'], log=log)
    run([cmake, '--build', build, '--config', 'Release', '--target', 'smsrecomp_presentation_checks', '--parallel', '4'], log=log)
    run([cmake, '--build', build, '--config', 'Release', '--target', 'smsrecomp_video_checks', '--parallel', '4'], log=log)
    ntsc_test = subprocess.run([str(build / 'Release/smsrecomp_video_checks.exe')],
        cwd=directory, capture_output=True, text=True, timeout=60,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    assert ntsc_test.returncode == 0, ntsc_test.stdout + ntsc_test.stderr
    print(ntsc_test.stdout)
    executable = build / 'Release/smsrecomp_presentation_checks.exe'
    metadata = version_strings(executable, expected)
    ini = directory / 'test-controls.ini'
    ini.unlink(missing_ok=True)
    result = subprocess.run([str(executable), str(ini)], cwd=directory,
        capture_output=True, text=True, timeout=60,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    (directory / 'checks.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    (directory / 'verification.json').write_text(json.dumps({'exit_code': result.returncode,
        'commercial_rom_used': False, 'visual_review_performed': False, 'video_driver_used': False,
        'windows_version_strings': metadata, 'result': result.stdout}, indent=2), encoding='utf-8')
    print(result.stdout)
    if result.returncode: raise SystemExit(result.returncode)
    pal_path = directory / 'Authored (Europe).sms'
    pal_path.write_bytes(data)
    pal_rom = read_rom(pal_path)
    assert video_standard(pal_rom) == 'pal'
    pal_dir = directory / 'pal'
    pal_dir.mkdir(exist_ok=True)
    prepare_runtime(pal_dir, pal_rom, 'Authored PAL timing fixture', engine, 'pal')
    shutil.copytree(directory / 'generated', pal_dir / 'generated', dirs_exist_ok=True)
    pal_build = pal_dir / 'build'
    run([cmake, '-S', source, '-B', pal_build, '-G', generator, '-A', 'x64',
         f'-DENGINE_DIR={engine.as_posix()}', f'-DGAME_DIR={pal_dir.as_posix()}',
         '-DGAME_NAME=AuthoredPalTiming', f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}',
         '-DSMSRECOMP_BANKED_AOT=ON', '-DSMSRECOMP_VIDEO_CHECKS=ON'], log=log)
    run([cmake, '--build', pal_build, '--config', 'Release', '--target',
         'smsrecomp_video_checks', '--parallel', '4'], log=log)
    pal_test = subprocess.run([str(pal_build / 'Release/smsrecomp_video_checks.exe')],
        cwd=pal_dir, capture_output=True, text=True, timeout=60,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    (pal_dir / 'checks.log').write_text(pal_test.stdout + pal_test.stderr, encoding='utf-8')
    assert pal_test.returncode == 0, pal_test.stdout + pal_test.stderr
    print(pal_test.stdout)

if __name__ == '__main__': main()
