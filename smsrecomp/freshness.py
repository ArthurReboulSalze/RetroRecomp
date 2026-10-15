"""Conservative export receipts. Unknown/old evidence always regenerates."""
import hashlib
import json
from pathlib import Path
from functools import lru_cache
from . import __version__
from .feedback import ingest


def digest(path):
    with Path(path).open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


@lru_cache(maxsize=2048)
def _input_hash(path, size, modified):
    return digest(path)


def engine_stamp():
    """Also invalidate development exports when their runtime changes."""
    from .paths import ASSETS
    files = list((ASSETS/'native').rglob('*'))
    files += list(Path(__file__).parent.rglob('*.py'))
    value = hashlib.sha256(__version__.encode())
    for path in sorted(p for p in files if p.is_file()):
        stat = path.stat()
        value.update(path.name.encode())
        value.update(_input_hash(path,stat.st_size,stat.st_mtime_ns).encode())
    return value.hexdigest()


def request(item, options):
    from .platforms import target_id
    settings = {key: value for key, value in options.items()
                if key not in ('gb_parallel_games', 'ng_parallel_games', 'ng_bios', 'bios')}
    settings['target'] = target_id()
    if item.system == 'ng':
        from .neogeo import validate_bios
        from .paths import selected_bios_path
        settings['bios'] = validate_bios(selected_bios_path(options.get('ng_bios') or options.get('bios')))
    if options.get('use_cover', True):
        from .cover_settings import load_settings
        from .cover_references import find as cover_reference
        settings['prefer_3d'] = load_settings().get('box_3d', False)
        reference = (cover_reference(item.system, digest(item.path), item.path.stem,
                                    prefer3d=settings['prefer_3d']) if not item.cover else None)
        settings['cover_reference'] = reference['revision'] if reference else None
    settings.update(engine=engine_stamp(), title=item.title, system=item.system, rom=item.sha256,
                    cover=digest(item.cover) if item.cover else None)
    return hashlib.sha256(json.dumps(settings, sort_keys=True, default=str).encode()).hexdigest()


def feedback(report):
    return report.get('runtime_feedback') or report.get('runtime_data', {}).get('runtime_feedback', {})


def current(item, target, report_path, signature, emit):
    try:
        report = json.loads(report_path.read_text(encoding='utf-8'))
        receipt = report['export_receipt']
        if (report['version'] != __version__ or receipt['request'] != signature or
                report['rom']['sha256'] != item.sha256 or report['executable'] != target.name or
                receipt['sha256'] != digest(target)):
            return None
        previous = feedback(report)
        latest = ingest(item.system, previous['identity'], report_path.parent, emit=emit)
        if latest['fingerprint'] != previous['fingerprint']:
            return None
        if previous.get('aes'):
            aes = previous['aes']
            if ingest(item.system, aes['identity'], report_path.parent, emit=emit)['fingerprint'] != aes['fingerprint']:
                return None
        return report
    except (OSError, ValueError, KeyError, TypeError):
        return None
