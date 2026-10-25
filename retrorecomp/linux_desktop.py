"""Local Linux launchers with cover icons; the ELF stays independently runnable."""
from contextlib import contextmanager
import os
from pathlib import Path
import platform
import re
import tempfile
import sys

from .paths import ASSETS


def publish_converter_launcher(executable: Path | None = None) -> Path:
    """Install a local, relocatable-on-request desktop entry beside the converter."""
    executable = (executable or Path(sys.executable)).resolve()
    folder = executable.parent
    icon = folder/'datas/launchers/Retro-Recomp.png'
    launcher = folder/'Retro-Recomp.desktop'
    marker = 'X-RetroRecomp-Converter=true'
    if launcher.exists() and marker not in launcher.read_text(encoding='utf-8').splitlines():
        raise FileExistsError('An unrelated Retro-Recomp.desktop already exists.')
    icon.parent.mkdir(parents=True, exist_ok=True)
    _write(icon, (ASSETS/'assets/Retro-Recomp-icon-256.png').read_bytes())
    text = '\n'.join(('[Desktop Entry]', 'Type=Application', 'Version=1.0',
        'Name=Retro-Recomp', 'Exec='+_argument(executable), 'Path='+_value(folder),
        'Icon='+_value(icon), 'Terminal=false', 'Categories=Game;Utility;',
        'StartupNotify=true', 'StartupWMClass=Retro-Recomp', marker, ''))
    _write(launcher, text.encode('utf-8'), 0o755)
    return launcher


def _value(text):
    return str(text).replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')


def _argument(text):
    # Desktop Entry escaping is followed by Exec argument parsing. No shell.
    text = str(text).replace('%', '%%')
    text = ''.join('\\' + c if c in '\\"$`' else c for c in text)
    return _value('"' + text + '"')


def _write(path, data, mode=None):
    if path.is_file() and path.read_bytes() == data:
        if mode is not None:
            path.chmod(mode)
        return
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def _lock(path):
    if os.name == 'nt':  # Allows pure launcher tests on Windows.
        yield
        return
    import fcntl
    with path.open('ab') as file:
        fcntl.flock(file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(file, fcntl.LOCK_UN)


def publish_launcher(executable: Path, report_path: Path, report: dict) -> Path | None:
    if platform.system() != 'Linux':
        return None
    executable = executable.resolve()
    if not executable.is_file():
        raise OSError('Cannot create a launcher before publishing its game.')
    identity = report.get('rom', {}).get('sha256', '')
    if not re.fullmatch('[0-9a-f]{64}', identity):
        raise ValueError('A Linux launcher requires an exact ROM identity.')
    folder = executable.parent
    icons = folder / 'datas/launchers'
    icons.mkdir(parents=True, exist_ok=True)
    launcher = executable.with_name(executable.name + '.desktop')
    marker = 'X-RetroRecomp-Identity=' + identity
    with _lock(icons / '.lock'):
        if launcher.exists() and marker not in launcher.read_text(encoding='utf-8').splitlines():
            raise FileExistsError('An unrelated launcher already uses ' + str(launcher))
        candidates = sorted((report_path.parent / 'artwork').glob('*-icon.png'))
        icon = icons / (identity + '.png')
        project = Path(report.get('build_directory', report_path.parent))
        candidates += [project / 'game-icon.png', icon]
        source = (next((p for p in candidates if p.is_file()), None)
                  if report.get('artwork', {}).get('embedded') else None)
        source = source or ASSETS / 'assets/Retro-Recomp-icon-256.png'
        _write(icon, source.read_bytes())
        text = '\n'.join((
            '[Desktop Entry]', 'Type=Application', 'Version=1.0',
            'Name=' + _value(executable.name), 'Exec=' + _argument(executable),
            'Path=' + _value(folder), 'Icon=' + _value(icon),
            'Terminal=false', 'Categories=Game;', 'StartupNotify=false', marker, '',
        ))
        _write(launcher, text.encode('utf-8'), 0o755)
        # Dolphin/GIO honor .hidden. Keep other entries and show one cover
        # launcher per game; Show Hidden Files still exposes the original ELF.
        hidden = folder / '.hidden'
        names = hidden.read_text(encoding='utf-8').splitlines() if hidden.exists() else []
        if executable.name not in names:
            names.append(executable.name)
            _write(hidden, ('\n'.join(names) + '\n').encode('utf-8'))
    return launcher


def retire_launcher(executable: Path, identity: str) -> bool:
    """Retire only our matching old starter after a successful game rename."""
    if platform.system() != 'Linux':
        return False
    icons = executable.parent/'datas/launchers'
    if not icons.is_dir():
        return False
    launcher = executable.with_name(executable.name+'.desktop')
    with _lock(icons/'.lock'):
        if not launcher.is_file() or ('X-RetroRecomp-Identity='+identity not in
                launcher.read_text(encoding='utf-8').splitlines()):
            return False
        launcher.unlink()
        hidden = executable.parent/'.hidden'
        if hidden.is_file():
            names=hidden.read_text(encoding='utf-8').splitlines()
            _write(hidden,('\n'.join(name for name in names if name!=executable.name)+'\n').encode('utf-8'))
        return True
