"""Cache independent 65816 and SPC700 single-instruction vectors for the Super Nintendo CPU checks (gate G10).

The upstream corpora are MIT licensed (SingleStepTests/65816 and SingleStepTests/spc700) and are not distributed with
Retro-Recomp: they are read from a pinned revision into `.deps/snes-vectors/` and never enter the repository. They were
generated from other emulators' behaviour (not recorded from a console), so they are independent evidence of the
instruction semantics and of the order of bus accesses, not proof of hardware accuracy.

Each family is one file of the corpus (`v1/XX.e.json` / `v1/XX.n.json` for the 65816, emulation and native mode; `v1/XX.json`
for the SPC700). The archive is read as a stream and no path of it is extracted. An evenly spaced sample of each family is
kept (the 65816 corpus holds 20,000 cases per opcode and 489 MB; the SPC700 one 10,000 cases per opcode and 16 MB). Every file
of the archive is hashed whole, and the digest of the list of those hashes is checked against the one pinned here: a corpus
that changed under the same revision (or a damaged download) is refused.

    python tools/fetch_snes_vectors.py --cpu 65816 [--samples 64]
    python tools/fetch_snes_vectors.py --cpu spc700 [--samples 128]
"""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.deps/snes-vectors'
REVISION_65816 = '307c63f5673c8c6b861c52f71ddb89212a227480'
REVISION_SPC700 = '67d15f492b2740964abd4efd1229e0ec9c342228'
CORPORA = {
    '65816': {'repository': 'SingleStepTests/65816', 'revision': REVISION_65816,
              'manifest_sha256': '9187c9021195c5bd80c627222e691cc75afeeb4ab955a1214761d810359694f7', 'families': 512},
    'spc700': {'repository': 'SingleStepTests/spc700', 'revision': REVISION_SPC700,
               'manifest_sha256': '7cddc6a051b9796f923567f33c8e43ea37a4f78a0e7f8f7d87bbacc91cddc905', 'families': 256},
}


def manifest_digest(files):
    """The digest of the sorted list of (family, SHA-256 of the whole file): what is pinned for each corpus."""
    lines = '\n'.join(f"{name} {digest}" for name, digest in sorted(files.items()))
    return hashlib.sha256(lines.encode('ascii')).hexdigest()


def fetch(cpu, samples):
    corpus = CORPORA[cpu]
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / f"{cpu}-{corpus['revision'][:12]}-{samples}.json"
    if target.exists():
        return target
    url = f"https://codeload.github.com/{corpus['repository']}/tar.gz/{corpus['revision']}"
    cases, families, files, licence = [], [], {}, b''
    with urllib.request.urlopen(url, timeout=300) as response:
        with tarfile.open(fileobj=response, mode='r|gz') as archive:
            for member in archive:
                path = Path(member.name)
                if path.name in ('LICENSE', 'LICENCE'):
                    licence = archive.extractfile(member).read()
                if path.parent.name != 'v1' or path.suffix != '.json':
                    continue
                raw = archive.extractfile(member).read()
                files[path.name] = hashlib.sha256(raw).hexdigest()
                vectors = json.loads(raw)
                count = min(samples, len(vectors))
                for i in range(count):
                    case = vectors[i * len(vectors) // count]
                    case['family'] = path.name[:-len('.json')]
                    cases.append(case)
                families.append({'name': path.name[:-len('.json')], 'available': len(vectors), 'selected': count})
                if len(families) % 64 == 0:
                    print(f'{len(families)} families, {len(cases)} vectors', flush=True)
    digest = manifest_digest(files)
    pinned = corpus['manifest_sha256']
    if pinned is None:
        print(f"MANIFEST_SHA256 for {cpu} at {corpus['revision']}: {digest} ({len(files)} files)", flush=True)
    elif digest != pinned:
        raise SystemExit(f'The {cpu} corpus does not match its pinned digest ({digest} instead of {pinned}); nothing cached.')
    if len(files) != corpus['families']:
        raise SystemExit(f"The {cpu} corpus has {len(files)} files, expected {corpus['families']}; nothing cached.")
    if licence:
        (CACHE / f'{cpu}-LICENSE').write_bytes(licence)
    target.write_text(json.dumps({'cpu': cpu, 'revision': corpus['revision'], 'source': url, 'manifest_sha256': digest,
        'families': families, 'cases': cases}, separators=(',', ':')), encoding='utf-8')
    print(target, flush=True)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--cpu', choices=sorted(CORPORA), required=True)
    parser.add_argument('--samples', type=int, default=64)
    args = parser.parse_args()
    if not 1 <= args.samples <= 10000:
        parser.error('--samples must be between 1 and 10000')
    fetch(args.cpu, args.samples)
