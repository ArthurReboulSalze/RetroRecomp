"""Standard Windows executable information; no Shell extension or sidecar."""
from pathlib import Path
from . import __version__


def game_metadata(title: str, light_phaser: bool, standard: str | None = None,
                  system_id: str = 'sms', *, zapper: bool = False) -> dict[str, str]:
    if system_id not in ('sms', 'gg', 'gb', 'nes', 'md', 'snes'):
        raise ValueError('Unsupported console')
    if system_id != 'sms' and light_phaser:
        raise ValueError('This console has no Light Phaser')
    controls = 'Mouse (Light Phaser); keyboard/gamepad controls' if light_phaser else 'Keyboard or gamepad'
    if zapper:
        if system_id != 'nes':
            raise ValueError('Zapper requires NES')
        controls = 'Mouse (NES Zapper); keyboard/gamepad controls'
    modes = {'sms': ('pal', 'ntsc'), 'gg': ('ntsc',), 'gb': ('dmg',), 'nes': ('ntsc', 'pal'),
             'md': ('ntsc', 'pal'), 'snes': ('ntsc', 'pal')}
    if standard is not None and standard not in modes[system_id]:
        raise ValueError('Unsupported console video standard')
    console_name = {'sms': 'Master System', 'gg': 'Game Gear', 'gb': 'Game Boy',
                    'nes': 'Nintendo NES', 'md': 'Mega Drive', 'snes': 'Super Nintendo'}[system_id]
    console = console_name + (f' {standard.upper()}' if standard and system_id in ('sms', 'nes', 'md', 'snes') else '')
    values = {'CompanyName': 'RetroRecomp', 'ProductName': title,
        'FileDescription': f'{title} | {console} | {controls}',
        'FileVersion': __version__, 'ProductVersion': f'RetroRecomp {__version__}',
        'Comments': f'Console: {console}. Controls: {controls}. Generated with RetroRecomp {__version__}.',
        'Console': console_name, 'Controls': controls, 'RetroRecompVersion': __version__}
    if standard:
        values['VideoStandard'] = standard.upper()
    return values


def _rc_string(value: str) -> str:
    # RC requires doubled quotes, plus backslash escapes for controls. A title
    # cannot close its value and inject another resource statement.
    value = value.replace('\\', '\\\\').replace('"', '""')
    value = value.replace('\r', '\\r').replace('\n', '\\n').replace('\t', '\\t').replace('\0', '')
    return '"' + value + '\\0"'


def write_game_metadata(game: Path, title: str, filename: str, *, light_phaser: bool,
                        icon: bool, standard: str | None = None,
                        system_id: str = 'sms', zapper: bool = False) -> dict[str, str]:
    metadata = game_metadata(title, light_phaser, standard, system_id, zapper=zapper)
    metadata.update(InternalName=Path(filename).stem, OriginalFilename=filename)
    version = [int(p) for p in __version__.split('.')]
    version += [0] * (4 - len(version))
    numbers = ','.join(str(p) for p in version)
    lines = ['#pragma code_page(65001)', '#include <winver.h>']
    if icon: lines.append('101 ICON "game.ico"')
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
