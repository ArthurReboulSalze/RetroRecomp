"""Master System cartridge profile; PAL/NTSC defaults are SMS-specific."""
from __future__ import annotations

import json
from pathlib import Path
import re

from . import Capabilities, Cpu, SystemProfile


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
    if publish_executable(executable, final, compact=True):
        emit(f"Nouvelle version prête ; remplacement à la fermeture du jeu : {final}")
    else:
        emit(f"Exécutable créé : {final}")
    return final


MASTER_SYSTEM = MasterSystemProfile()
