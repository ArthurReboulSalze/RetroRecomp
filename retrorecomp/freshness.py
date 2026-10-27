"""Conservative export receipts. Unknown/old evidence always regenerates.

A request has a game part (everything that decides which code is discovered,
translated and validated) and a host part (the player shell: menus, text,
artwork, notices; see docs/UPGRADES.md). An export whose game part still
matches, with no new hints, is upgraded without rediscovery.
"""
import hashlib
import json
from . import __version__
from .feedback import ingest
from .library import file_sha256
from .systems import get_profile, unsigned_option_keys


digest = file_sha256


# Request settings that only shape the player shell or the published file.
HOST_SETTINGS = frozenset(('language', 'icon_tags', 'online_cover', 'use_cover', 'prefer_3d',
                           'cover_reference', 'cover', 'title', 'host_inputs', 'build_inputs'))


def _hash(settings):
    return hashlib.sha256(json.dumps(settings, sort_keys=True, default=str).encode()).hexdigest()


def request_parts(item, options):
    """The whole request signature, plus its game and host parts."""
    from .platforms import target_id
    # Options that only size the work or name firmware (the profiles'
    # option_keys with signature=False), plus the generic firmware key.
    unsigned = unsigned_option_keys() | {'bios'}
    settings = {key: value for key, value in options.items() if key not in unsigned}
    settings['target'] = target_id()
    # The console's own identity (X68000 machine, Neo Geo BIOS), if it has one.
    profile = get_profile(item.system)
    profile.request_identity(item, options, settings)
    if options.get('use_cover', True):
        from .cover_settings import load_settings
        from .cover_references import find as cover_reference
        settings['prefer_3d'] = load_settings().get('box_3d', False)
        reference = (cover_reference(item.system, digest(item.path), item.path.stem,
                                    prefer3d=settings['prefer_3d']) if not item.cover else None)
        settings['cover_reference'] = reference['revision'] if reference else None
    from .compilation_inputs import knowledge_stamp, legacy_game_stamps, role_stamps
    stamps = role_stamps(item.system)
    settings['knowledge'] = knowledge_stamp(item.system, profile.knowledge_identity(item, settings))
    settings.update(engine=stamps['game'], host_inputs=stamps['host'], build_inputs=stamps.get('build', ''),
                    title=item.title, system=item.system, rom=item.sha256,
                    cover=digest(item.cover) if item.cover else None)
    game = {k: v for k, v in settings.items() if k not in HOST_SETTINGS}
    return {'request': _hash(settings), 'game': _hash(game),
            'host': _hash({k: v for k, v in settings.items() if k in HOST_SETTINGS}),
            # The game part an earlier release would have written for this same request.
            'legacy_games': [_hash({**game, 'engine': stamp}) for stamp in legacy_game_stamps(item.system)]}


def request(item, options):
    return request_parts(item, options)['request']


def feedback(report):
    return report.get('runtime_feedback') or report.get('runtime_data', {}).get('runtime_feedback', {})


def _no_new_hints(item, report, report_path, emit):
    previous = feedback(report)
    latest = ingest(item.system, previous['identity'], report_path.parent, emit=emit)
    if latest['fingerprint'] != previous['fingerprint']:
        return False
    if previous.get('aes'):
        aes = previous['aes']
        if ingest(item.system, aes['identity'], report_path.parent, emit=emit)['fingerprint'] != aes['fingerprint']:
            return False
    return True


def _own_export(item, target, report, receipt):
    return (report['rom']['sha256'] == item.sha256 and report['executable'] == target.name
            and receipt['sha256'] == digest(target))


def current(item, target, report_path, signature, emit):
    try:
        report = json.loads(report_path.read_text(encoding='utf-8'))
        receipt = report['export_receipt']
        schema = receipt.get('schema', 1)
        if (schema not in (1, 2, 3) or
                (schema == 1 and report['version'] != __version__) or
                receipt['request'] != signature or not _own_export(item, target, report, receipt)):
            return None
        return report if _no_new_hints(item, report, report_path, emit) else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def upgradable(item, target, report_path, parts, emit):
    """The previous report when only host or build inputs changed: same game part
    (code, settings, knowledge), the exact EXE it published, a passed validation
    and no new gameplay hints. Older receipts have no game part: full conversion.

    A receipt carrying a game part listed in LEGACY_GAME_STAMPS is accepted too,
    even if nothing else changed: it is never current, always rebuilt. The
    returned report then names the release that wrote it under 'legacy_release'."""
    try:
        report = json.loads(report_path.read_text(encoding='utf-8'))
        receipt = report['export_receipt']
        legacy = receipt.get('game') in parts.get('legacy_games', ())
        if (receipt.get('schema') != 3 or not (receipt.get('game') == parts['game'] or legacy)
                or (receipt.get('host') == parts['host'] and not legacy)
                or not _own_export(item, target, report, receipt)
                or report.get('native_validation', {}).get('passed') is False):
            return None
        if not _no_new_hints(item, report, report_path, emit):
            return None
        return {**report, 'legacy_release': str(report.get('version'))} if legacy else report
    except (OSError, ValueError, KeyError, TypeError):
        return None


def report_scan_level(report):
    """The scan level a report was converted at, wherever its writer put it: the top-level `scan_level`
    (Master System, Game Gear, Game Boy, CPS-1, X68000, and every writer since 1.5.6), the schema-2 `scan.level`, or
    `advanced_scan.level` (Mega Drive, Super Nintendo and NES reports of 1.5.x had only that). 'standard' when none."""
    scan, advanced = report.get('scan'), report.get('advanced_scan')
    for level in (report.get('scan_level'), scan.get('level') if isinstance(scan, dict) else None,
                  advanced.get('level') if isinstance(advanced, dict) else None):
        if isinstance(level, str) and level:
            return level
    return 'standard'


def upgrade_record(previous):
    """What an upgraded export inherits: the original discovery, kept across
    successive upgrades, with its own checks (and any fallback they met)."""
    legacy = previous.get('legacy_release')
    origin = previous.get('upgrade', {}).get('discovery') or {
        'version': previous.get('version'), 'created_utc': previous.get('created_utc'),
        'scan_level': report_scan_level(previous),
        'final_checks': previous.get('final_checks', [])}
    reason = ('Only player-shell inputs changed and no new paths were found; '
              'the code was rebuilt from the paths already learned and checked on quick routes.')
    if legacy:
        reason = (f'Exported by Retro-Recomp {legacy}, whose game code is listed as equivalent: only how the game is '
                  'built changed. The code was rebuilt from the paths already learned and checked on quick routes.')
    return {'reason': reason, 'check_level': 'quick', 'discovery': origin,
            **({'from_release': legacy} if legacy else {})}
