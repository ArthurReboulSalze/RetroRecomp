"""Master System cartridge profile; PAL/NTSC defaults are SMS-specific."""
from __future__ import annotations

import json
from pathlib import Path
import re

from . import Capabilities, Cpu, SystemProfile, find_profile
from .specs import (CARTRIDGE_BOUNDS, Catalogues, Identify, InputLayout, LibraryLayout, PathSpec, ReportShape,
                    SharedKnowledge)


def sega_profile(data: bytes, byte_size: int) -> SystemProfile | None:
    """The Master System or the Game Gear, from the region nibble of a 'TMR SEGA' header; None without one.
    The two share a cartridge format: a known header is stronger evidence than a misnamed extension."""
    offset = 512 if byte_size % 16384 == 512 else 0
    sega = data[offset:]
    for header in (0x7ff0, 0x3ff0, 0x1ff0):
        if sega[header:header + 8] == b'TMR SEGA' and len(sega) > header + 15:
            region = sega[header + 15] >> 4
            if region in (3, 4): return find_profile('sms')
            if region in (5, 6, 7): return find_profile('gg')
    return None


def refine_by_header(profile: SystemProfile, path: Path, data: bytes | None) -> SystemProfile:
    """An extension match of either Sega console, settled by the header also inside ZIPs."""
    if data is None and not path.is_file():
        return profile
    if data is None:
        byte_size = path.stat().st_size
        with path.open('rb') as source:
            data = source.read(0x8000 + 512)
    else:
        byte_size = len(data)
    return sega_profile(data, byte_size) or profile


class MasterSystemProfile(SystemProfile):
    id = "sms"
    name = "Master System"
    extensions = (".sms",)
    export_folder = "Master System"
    video_modes = ("ntsc", "pal")
    cpus = (Cpu("z80", "main", "cycles"),)
    quick_state_family = "gamestate"
    capabilities = Capabilities(guns=("light_phaser",))
    feedback_kinds = frozenset({1})
    converter_publishes = True
    options_tab = "options_master_system"
    host_adapter = "adapters/rrhk_sms.c"
    # The Z80 map of the Master System and the Game Gear is declared once, here (the Game Gear lists the section).
    path_spec = PathSpec(order=0, sections=(("z80", "sms"),), source_bounds=(("rom", CARTRIDGE_BOUNDS),),
                         required_sources=("rom",),
                         shapes=(("z80", "sms", dict(roles=("rom",), caps={"sega5": 65536, "window4": 4096},
                                                     pc_below=0xbf01)),))
    report_shape = ReportShape("core", "strict_checks")
    catalogues = Catalogues(libretro="libretro-thumbnails/Sega_-_Master_System_-_Mark_III", screenscraper=2,
                            thegamesdb=35, wikidata=("Q209868",), cover_references=True)
    # The library of the Master System predates the per-console folders.
    library_layout = LibraryLayout(folder="", summary_glob="*/compilation.json", companion="observations.log")
    input_layout = InputLayout(("a", "b"), (), None, 240, start=False, script_format="sega")
    shared_knowledge = SharedKnowledge("stable", site_builder=True)
    # Also asked for the bytes of a headerless dump: the Game Gear is told apart by the same header.
    identify = Identify(content_order=3)

    def refine_match(self, path: Path, data: bytes | None):
        return refine_by_header(self, path, data)

    def identify_content(self, data: bytes):
        return sega_profile(data, len(data))

    def read_rom(self, path: Path):
        from ..core import read_rom
        return read_rom(path)

    def default_video_mode(self, path: Path) -> str:
        # Dump headers identify export markets, not the host console clock.
        groups = re.findall(r"\(([^()]*)\)|\[([^\[\]]*)\]", path.stem)
        markets = {word.casefold() for pair in groups for group in pair
                   for word in re.split(r"\W+", group) if word}
        return "pal" if "europe" in markets and not markets.intersection(
            {"usa", "world", "japan"}) else "ntsc"

    def convert(self, path: Path, **options) -> Path:
        return convert_checked(self, path, **options)


# The banked backend refuses an executable whose run differs from the
# reference CPU. The functions backend compared the same runs but only
# reported a divergence; it now meets the same gate before publication.
REFERENCE_CHECKS = ('reference_vdp_trace_match', 'reference_final_vdp_match',
                    'reference_final_ram_match', 'reference_final_png_match')


def convert_checked(system, path: Path, **options) -> Path:
    """Master System / Game Gear conversion. With the functions backend,
    imported hints from other players are not used (its function entries are
    matched by address, so a wrong-bank entry could replace real code off the
    tested routes), and a divergence from the reference fails the conversion:
    the previous export stays, as with banked."""
    from ..core import ConversionError, convert, executable_name
    if options.get('backend', 'banked') != 'functions' or options.get('output') is None:
        return convert(path, **options)
    from .. import knowledge
    from ..publishing import publish_executable
    identity = (system.id, system.read_rom(path).sha256)
    publish = options.pop('publish_result', True)
    # The batch's retry may already set this cartridge aside: leaving a
    # nested set-aside would end the batch's own while it still converts.
    with knowledge._SET_ASIDE_LOCK:
        already = identity in knowledge._SET_ASIDE
    if already:
        executable = convert(path, publish_result=False, **options)
    else:
        with knowledge.imported_set_aside(*identity):
            executable = convert(path, publish_result=False, **options)
    destination = Path(options['output']).resolve()
    report = json.loads((destination / 'conversion-report.json').read_text(encoding='utf-8'))
    differences = [name[len('reference_'):] for name in REFERENCE_CHECKS if report.get(name) is not True]
    if differences:
        raise ConversionError(f"Native validation failed (functions backend): {', '.join(differences)} "
                              f'differ from the reference CPU. Previous export preserved; the Extended '
                              f'(banked) backend validates these checks. Details: {destination / "validation"}')
    if not publish:
        return executable
    title = options.get('title') or re.sub(r"\s*\([^)]*\)", "", Path(path).stem).strip()
    final = destination / executable_name(title)
    emit = options.get('emit', print)
    if publish_executable(executable, final, compact=True, emit=emit):
        emit(f"Nouvelle version prête ; remplacement à la fermeture du jeu : {final}")
    else:
        emit(f"Exécutable créé : {final}")
    return final


MASTER_SYSTEM = MasterSystemProfile()
