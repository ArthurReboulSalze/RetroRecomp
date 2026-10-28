"""The shared base around one batch, the same for the window and the command line.

Before a batch, the ROMs are named as the base names them (`rom_keys`) and `online.prepare_batch` applies the
local base to them: the qualified paths of this converter's engines fill the qualified bank, so a known game takes
the quick check instead of a discovery (batch.py). A Neo Geo game is named by its prepared cartridge and the BIOS
its conversion uses, so one whose cartridge is not prepared yet is asked for by its conversion (`start_source`).
After the batch, the paths that broke a conversion stop allowing a quick check for that ROM (`rejected_keys`).
Nothing here stops a batch: a failure leaves the conversions as they would be offline.
"""
from __future__ import annotations

from pathlib import Path
import sys
import threading

from .paths import selected_bios_path


def rom_keys(entries, ng_bios=None) -> list[str]:
    """The shared base's names ('system:identity') for the ROMs of a batch,
    from (system, sha256, path) triples. A cartridge console is named by
    its ROM's hash. A Neo Geo game by its prepared cartridge and the BIOS
    its conversion will use (neogeo_knowledge.key); one whose cartridge is
    not prepared yet is not asked for here: its conversion asks once it is
    (start_source)."""
    keys, bios_sha, checked = [], None, False
    for system, sha256, path in entries:
        if system != 'ng':
            keys.append(f'{system}:{sha256}')
            continue
        if not checked:
            checked = True
            try:
                from .neogeo import validate_bios
                firmware = selected_bios_path(ng_bios)
                bios_sha = validate_bios(firmware)['sha256'] if firmware else None
            except (ValueError, OSError):
                bios_sha = None
        try:
            from .neogeo_knowledge import shared_identity
            identity = shared_identity(Path(path), sha256, bios_sha)
        except (OSError, ValueError, TypeError):
            identity = None
        if identity:
            keys.append(f'ng:{identity}')
    return keys


def prepare(keys, enabled: bool) -> dict:
    """`online.prepare_batch` for these keys, whatever happens: an error
    lands in 'error' and the batch goes on with no shared paths."""
    from . import online
    try:
        return online.prepare_batch(keys, bool(enabled))
    except Exception as exc:   # the batch goes on whatever happens here
        return {'paths': {}, 'summary': None, 'error': exc, 'base': None}


def byte_size(count) -> str:
    """A download size in words: '312 KiB', '4.7 MiB'."""
    return f'{count / 1048576:.1f} MiB' if count >= 1048576 else f'{max(1, round(count / 1024))} KiB'


def base_lines(base, summary, error, tr, problem, quiet=False) -> list[tuple[str, str]]:
    """The shared base's outcome for this batch as ('log' | 'notice', text) lines: an update that came in, no base
    and no connection (also a 'notice': every game is discovered in full), the local base used because there was
    no connection, its number and the games received, nothing new (left to the signed-in sync's own line when
    there is one), a format this version cannot read, and the problem that stopped it, if any. Nothing when there
    is no base and nothing was asked of it. `tr(key, **values)` translates, `problem(error)` names an error;
    `quiet` leaves out the lines that say nothing came."""
    lines = []
    if not base:
        return lines
    update = base.get('update') or {}
    if update.get('source'):
        lines.append(('log', tr('base_updated', version=update['version'],
                                size=byte_size(update.get('downloaded_bytes', 0)))))
    if base.get('offline') and not quiet:
        if base.get('version') is None:
            lines += [('log', tr('base_none')), ('notice', tr('base_none'))]
        else:
            lines.append(('log', tr('base_local_offline', version=base['version'])))
    if base.get('note') == 'format':
        lines.append(('log', tr('shared_base_format', format=base.get('format'))))
    elif base.get('version') is not None and base.get('games'):
        lines.append(('log', tr('shared_base_received', version=base['version'], games=base['games'])))
    elif (base.get('version') is not None and base.get('error') is None and summary is None and base.get('asked')
            and not quiet):
        lines.append(('log', tr('shared_base_nothing', version=base['version'])))
    if base.get('error') is not None and not (base.get('offline') or base.get('note') == 'format'):
        named = problem(base['error'])
        # Offline, the signed-in sync reports the same problem right after.
        if error is None or named != problem(error):
            lines.append(('log', tr('shared_base_unavailable', error=named)))
    return lines


def start_source(ask, keys, systems) -> None:
    """For the length of a batch with Neo Geo games: a conversion that has
    just prepared its cartridge asks the shared base for it, once, through
    `ask([key])`, unless `keys` (the batch's first request) already covered it."""
    if 'ng' not in systems:
        return
    from . import neogeo_knowledge
    asked, lock = set(keys), threading.Lock()
    def source(identity):
        key = f'ng:{identity}'
        with lock:   # one request at a time: they all write the same files
            if key in asked:
                return
            asked.add(key)
            ask([key])
    neogeo_knowledge.SHARED_SOURCE = source


def stop_source() -> None:
    module = sys.modules.get(__package__ + '.neogeo_knowledge')
    if module is not None:
        module.SHARED_SOURCE = None


def rejected_keys(shared, results) -> list[str]:
    """The keys whose shared paths a batch set aside after they broke a
    conversion (`online.forget_shared` takes them)."""
    rejected = [f"{result.get('system')}:{result.get('sha256')}" for result in results
                if result.get('imported_hints_rejected')]
    keys = [key for key in rejected if key in shared]
    for result in results:
        if result.get('system') == 'ng' and result.get('report'):
            # Neo Geo says it in its own report, under the cartridge and BIOS identity (a
            # game asked for once its cartridge was prepared is not in `shared`).
            from .knowledge_exchange import report_game_key
            identity, flagged = report_game_key(result['report'])
            if identity and flagged:
                keys.append(f'ng:{identity}')
    return keys


def forget_rejected(shared, results) -> None:
    keys = rejected_keys(shared, results)
    if keys:
        from . import online
        try:
            online.forget_shared(keys)
        except OSError:
            pass
