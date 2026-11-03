"""Standard Windows executable information; no Shell extension or sidecar."""
from pathlib import Path
from . import __version__
from .systems import get_profile, system_ids


def game_metadata(title: str, light_phaser: bool, standard: str | None = None,
                  system_id: str = 'sms', *, zapper: bool = False, gun_device: str | None = None) -> dict[str, str]:
    if system_id not in system_ids():
        raise ValueError('Unsupported console')
    if system_id != 'sms' and light_phaser:
        raise ValueError('This console has no Light Phaser')
    controls = 'Mouse (Light Phaser); keyboard/gamepad controls' if light_phaser else 'Keyboard or gamepad'
    if gun_device:
        from .guns16 import LABELS
        if ((system_id, gun_device) not in (('md', 'menacer'), ('md', 'justifier'), ('snes', 'super_scope'))
                or light_phaser or zapper):
            raise ValueError('Unsupported console gun')
        controls = f'Mouse ({LABELS[gun_device]}); keyboard/gamepad controls'
    if zapper:
        if system_id != 'nes':
            raise ValueError('Zapper requires NES')
        controls = 'Mouse (NES Zapper); keyboard/gamepad controls'
    profile = get_profile(system_id)
    if standard is not None and standard not in profile.video_modes:
        raise ValueError('Unsupported console video standard')
    console_name = profile.name
    # Only the consoles with both a PAL and an NTSC mode carry the standard in their name.
    both_standards = 'ntsc' in profile.video_modes and 'pal' in profile.video_modes
    console = console_name + (f' {standard.upper()}' if standard and both_standards else '')
    values = {'CompanyName': 'RetroRecomp', 'ProductName': title,
        'FileDescription': f'{title} | {console} | {controls}',
        'FileVersion': __version__, 'ProductVersion': f'RetroRecomp {__version__}',
        'Comments': f'Console: {console}. Controls: {controls}. Generated with RetroRecomp {__version__}.',
        'Console': console_name, 'Controls': controls, 'RetroRecompVersion': __version__}
    if standard:
        values['VideoStandard'] = standard.upper()
    return values


# The application manifest of every Windows game (resource 1, type RT_MANIFEST = 24), written inline in the resource script:
# no separate file for the resource compiler to forget. It states standard facts and changes no behaviour of the game:
# it runs as the user who starts it (asInvoker, never an elevation prompt), it names the Windows versions it was written
# for (7, 8, 8.1, 10 and 11 share the last identifier), and its DPI awareness is the one the host asks SDL for at start
# (native/hostkit/shell/rrhk_main.c: SDL_HINT_WINDOWS_DPI_AWARENESS "permonitorv2"), stated before the first window
# instead of after; "true/pm" and the PerMonitor fallback keep Windows 8.1 and older reading it. No other setting (no UTF-8
# code page, no long paths, no common-controls version), so that file names, dialogs and scaling stay what they were.
# A standard practice; its effect on antivirus detections is not demonstrated. Not written for the Visual Studio fallback
# (`_embeds_manifest`).
MANIFEST_XML = (
    "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>\n"
    "<assembly xmlns='urn:schemas-microsoft-com:asm.v1' manifestVersion='1.0'>\n"
    "  <assemblyIdentity type='win32' name='RetroRecomp.Game' version='1.0.0.0'/>\n"
    "  <trustInfo xmlns='urn:schemas-microsoft-com:asm.v3'>\n"
    "    <security><requestedPrivileges>\n"
    "      <requestedExecutionLevel level='asInvoker' uiAccess='false'/>\n"
    "    </requestedPrivileges></security>\n"
    "  </trustInfo>\n"
    "  <compatibility xmlns='urn:schemas-microsoft-com:compatibility.v1'>\n"
    "    <application>\n"
    "      <supportedOS Id='{35138b9a-5d96-4fbd-8e2d-a2440225f93a}'/>\n"
    "      <supportedOS Id='{4a2f28e3-53b9-4441-ba9c-d69d4a4a6e38}'/>\n"
    "      <supportedOS Id='{1f676c76-80e1-4239-95bb-83d0f6d0da78}'/>\n"
    "      <supportedOS Id='{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}'/>\n"
    "    </application>\n"
    "  </compatibility>\n"
    "  <application xmlns='urn:schemas-microsoft-com:asm.v3'>\n"
    "    <windowsSettings>\n"
    "      <dpiAware xmlns='http://schemas.microsoft.com/SMI/2005/WindowsSettings'>true/pm</dpiAware>\n"
    "      <dpiAwareness xmlns='http://schemas.microsoft.com/SMI/2016/WindowsSettings'>PerMonitorV2,PerMonitor</dpiAwareness>\n"
    "    </windowsSettings>\n"
    "  </application>\n"
    "</assembly>\n")


def _embeds_manifest() -> bool:
    """False for the Visual Studio fallback toolchain only: MSBuild merges its own manifest into resource 1 (mt.exe, or LNK1123
    for a duplicate), so a game built there keeps the default manifest of MSBuild and carries none of ours."""
    from . import toolchain
    return toolchain.active() != toolchain.MSVC


def manifest_resource() -> list[str]:
    """The resource-script lines of the application manifest: `1 24` (CREATEPROCESS_MANIFEST_RESOURCE_ID, RT_MANIFEST) with
    the XML as quoted lines (a raw data block gets no terminating NUL; the XML uses single quotes, nothing needs escaping)."""
    pieces = MANIFEST_XML.splitlines()
    lines = ['1 24', 'BEGIN']
    for index, piece in enumerate(pieces):
        lines.append('  "' + piece + '\\n"' + (',' if index + 1 < len(pieces) else ''))
    lines.append('END')
    return lines


def _rc_string(value: str) -> str:
    # RC requires doubled quotes, plus backslash escapes for controls. A title
    # cannot close its value and inject another resource statement.
    value = value.replace('\\', '\\\\').replace('"', '""')
    value = value.replace('\r', '\\r').replace('\n', '\\n').replace('\t', '\\t').replace('\0', '')
    return '"' + value + '\\0"'


def write_game_metadata(game: Path, title: str, filename: str, *, light_phaser: bool,
                        icon: bool, standard: str | None = None,
                        system_id: str = 'sms', zapper: bool = False, gun_device: str | None = None) -> dict[str, str]:
    metadata = game_metadata(title, light_phaser, standard, system_id, zapper=zapper, gun_device=gun_device)
    metadata.update(InternalName=Path(filename).stem, OriginalFilename=filename)
    version = [int(p) for p in __version__.split('.')]
    version += [0] * (4 - len(version))
    numbers = ','.join(str(p) for p in version)
    lines = ['#pragma code_page(65001)', '#include <winver.h>']
    if system_id in ('sms', 'gg'):
        # Other hosts already include this notice in their component resource.
        from .paths import ASSETS
        (game / 'filter_legal.txt').write_bytes((ASSETS / 'licenses/xbr.md').read_bytes() + b'\n\n' + (ASSETS / 'licenses/Noto.md').read_bytes()
                                                + b'\n\n' + (ASSETS / 'licenses/llvm-mingw.md').read_bytes())
        lines.append('104 RCDATA "filter_legal.txt"')
    if icon: lines.append('101 ICON "game.ico"')
    if _embeds_manifest():
        lines += manifest_resource()
    lines += ['1 VERSIONINFO', f'FILEVERSION {numbers}', f'PRODUCTVERSION {numbers}',
        'FILEFLAGSMASK VS_FFI_FILEFLAGSMASK', 'FILEFLAGS 0', 'FILEOS VOS_NT_WINDOWS32',
        'FILETYPE VFT_APP', 'FILESUBTYPE 0', 'BEGIN', '  BLOCK "StringFileInfo"',
        '  BEGIN', '    BLOCK "040904B0"', '    BEGIN']
    lines += [f'      VALUE "{key}", {_rc_string(value)}' for key, value in metadata.items()]
    lines += ['    END', '  END', '  BLOCK "VarFileInfo"', '  BEGIN',
        '    VALUE "Translation", 0x0409, 1200', '  END', 'END', '']
    (game / 'game_resources.rc').write_text('\n'.join(lines), encoding='utf-8')
    return metadata


def write_converter_version(path: Path) -> None:
    """PyInstaller uses its own VERSIONINFO builder instead of a .rc file."""
    from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct
    parts = tuple(int(p) for p in __version__.split('.')) + (0,)
    values = {'CompanyName': 'RetroRecomp', 'ProductName': 'RetroRecomp',
        'FileDescription': 'RetroRecomp | Retro cartridge to native executable converter',
        'FileVersion': __version__, 'ProductVersion': __version__,
        'InternalName': 'Retro-Recomp', 'OriginalFilename': 'Retro-Recomp.exe'}
    data = VSVersionInfo(ffi=FixedFileInfo(filevers=parts, prodvers=parts, mask=0x3F,
        flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)), kids=[
        StringFileInfo([StringTable('040904B0', [StringStruct(k, v) for k, v in values.items()])]),
        VarFileInfo([VarStruct('Translation', [0x0409, 1200])])])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(data), encoding='utf-8')
