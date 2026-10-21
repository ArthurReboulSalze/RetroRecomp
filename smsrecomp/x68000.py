"""Local X68000 converter inputs; no firmware or game is downloaded."""
from dataclasses import dataclass
import hashlib
import importlib.util
from pathlib import Path
from .paths import ROOT, ASSETS, selected_bios_path
from .x68000_media import identify_disk as read_disk, build_manifest, MachineConfig


def developer_available():
    """True when this installation carries the X68000 converter files.

    The machine sources themselves (hissorii/px68k, Geolith, GenesisRecomp)
    are fetched at their pinned revisions on first conversion, like the other
    profiles' dependencies; firmware and disks always come from the user.
    """
    bundled = all((ASSETS / name).is_file() for name in (
        'native/x68000_native/CMakeLists.txt', 'native/x68000_reference/CMakeLists.txt',
        'native/x68000_machine/base74/musashi/m68kconf.h', 'tools/x68000_base74.py'))
    if not bundled:
        return False
    # The generators run inside the converter's own Python.
    try:
        return importlib.util.find_spec('tools.x68000_native') is not None
    except (ImportError, ValueError):
        return False


@dataclass(frozen=True)
class X68000Input:
    path: Path
    disks: tuple[Path, ...]
    sha256: str
    size: int
    title: str

    def metadata(self):
        return {'name': self.path.name, 'path': str(self.path), 'sha256': self.sha256, 'size': self.size,
                'disks': [str(p) for p in self.disks], 'system': 'x68'}


def read_input(path):
    path = Path(path).resolve(strict=True)
    if path.suffix.casefold() in ('.dim', '.xdf'):
        disk = read_disk(path)
        return X68000Input(path, (path,), disk.sha256, disk.size, path.stem)
    if path.suffix.casefold() != '.m3u':
        raise ValueError('X68000 accepts DIM/XDF or an explicit M3U disk set; command files are never executed.')
    if path.stat().st_size > 32768:
        raise ValueError('X68000 playlist exceeds 32 KiB.')
    disks = []
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'): continue
        if '\x00' in line or '://' in line:
            raise ValueError('Only local disk paths are accepted in an X68000 playlist.')
        value = Path(line)
        disks.append((value if value.is_absolute() else path.parent / value).resolve(strict=True))
    if not 1 <= len(disks) <= 10 or len(set(disks)) != len(disks):
        raise ValueError('An X68000 set requires one to ten distinct disks.')
    records = [read_disk(p) for p in disks]
    # Single disk and one-disk playlist identify the same game.
    identity = records[0].sha256 if len(records) == 1 else hashlib.sha256(
        ('x68000-disk-set-v1\0' + '\0'.join(d.sha256 for d in records)).encode()).hexdigest()
    return X68000Input(path, tuple(disks), identity, sum(d.size for d in records), path.stem)


def machine(path, ipl, cgrom, ram=2):
    source = read_input(path)
    ipl, cgrom = selected_bios_path(ipl), selected_bios_path(cgrom)
    if not ipl or not cgrom:
        raise ValueError('Select your IPL (iplrom.dat) and font ROM (cgrom.dat) in Options → Sharp X68000.')
    if ram not in (2, 4): raise ValueError('This X68000 profile accepts 2 or 4 MiB RAM.')
    manifest = build_manifest(source.disks, ipl, cgrom,
        config=MachineConfig(ram_bytes=ram*1024*1024), initial_drives=(0, 1 if len(source.disks)>1 else None))
    return source, manifest


def automatic_media_rules(source):
    """Private development policy, gated by the complete ordered disk set.

    These are explicit guest-eject transitions, never title/size heuristics.
    Unknown or reordered sets retain manual control. Further transitions are
    added only after the corresponding real request is replayed and checked.
    """
    if source.sha256 == '65a1633e48b34ddfe486c53a96cf0d3460606370972e202b3066458858589b94':
        # A ejects boot disk for disk 2, then B flashes empty for disk 3.
        return ((0, 0, 1), (1, 10, 2))
    if source.sha256 == '39fff56b6a62ea18dbd7f2572261680b436c1b9967ae078a96d9f01168299261':
        # Tricorn Final ejects B from FDD1 and requests C there. D is not
        # inferred: it needs its own observed guest request and validation.
        return ((1, 1, 2),)
    if source.sha256 == '06ae8a805f2826bf049febf54aa2734760ac893f95620ee30dcb6c7a60271215':
        # Power Unit ejects its system image from A before requesting disk 3.
        return ((0, 0, 2),)
    return ()


def mouse_controls(source):
    """Known mouse-driven exact sets; unrelated revisions keep normal controls."""
    return source.sha256 in (
        '24bf876f9d31a622313c4e6fb0f4c8134259c11e1dd0fea28124a44498c797e3',
        '06ae8a805f2826bf049febf54aa2734760ac893f95620ee30dcb6c7a60271215',
    )


