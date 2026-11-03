"""Cache the independent SM83 vectors (SingleStepTests/sm83) for the Game Boy checks of the CPU.

The corpus is MIT licensed and generated from a reference model, not recorded from hardware: one file per legal opcode
(00-FF and CB 00-FF), 1000 vectors each, the state before and after one instruction on a flat 64 KiB RAM. It is read from the
pinned revision's archive without extracting any path, checked against a pinned digest, and converted to one text line per vector
for the C check (native/gb_sm83_vector_checks.c). It goes to `.deps/sm83-vectors`; it is never in the repository or in a release.

The digest is the SHA-256 of the lines "<file name> <SHA-256 of the file>" for every vector file, in name order: it does not depend
on how the host compresses its archive. A corpus that does not match is refused.
"""
import argparse
import gzip
import hashlib
import json
import os
import urllib.request
import tarfile
from pathlib import Path

REVISION = 'f9c30210245dd691661db39f5ace022c465ecc2f'
CORPUS_SHA256 = 'f9e98c645214a2f5922813f38aa46710852777287ec184e8f0a6a05de9ff4ef7'
ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.deps/sm83-vectors'
URL = f'https://codeload.github.com/SingleStepTests/sm83/tar.gz/{REVISION}'
FILES = 500                      # the files of v1/ at the pinned revision

# A vector touches plain memory when every address its bus uses is ROM that is only read, video RAM, cartridge RAM, work RAM,
# OAM or high RAM: the vector model is a flat RAM, and the runtime's bus is not (echo RAM mirrors, the I/O page and the interrupt
# enable register do things, ROM writes are mapper writes).
PLAIN = ((0x0000, 0x8000), (0x8000, 0xE000), (0xFE00, 0xFEA0), (0xFF80, 0xFFFF))


def plain_address(address, write=False):
    if write and address < 0x8000:
        return False
    return any(low <= address < high for low, high in PLAIN)


def touches_only_plain_memory(vector):
    addresses = {address for address, _ in vector['initial']['ram']} | {address for address, _ in vector['final']['ram']}
    writes = set()
    for address, _value, kind in vector['cycles']:
        if kind != '---':
            addresses.add(address)
        if 'w' in kind:
            writes.add(address)
    return all(plain_address(a) for a in addresses) and all(plain_address(a, True) for a in writes)


def line(family, index, vector):
    """One vector as a text line: family index plain  pc sp a b c d e f h l ime ei ie  NI (addr value)*  a b c d e f h l pc sp ime ei  NF
    (addr value)*  mcycles. `ei` and `ie` that a vector does not give are 0."""
    start, end = vector['initial'], vector['final']
    numbers = [family, index, 1 if touches_only_plain_memory(vector) else 0,
               start['pc'], start['sp'], start['a'], start['b'], start['c'], start['d'], start['e'], start['f'], start['h'],
               start['l'], start['ime'], start.get('ei', 0), start.get('ie', 0), len(start['ram'])]
    for address, value in start['ram']:
        numbers += [address, value]
    numbers += [end['a'], end['b'], end['c'], end['d'], end['e'], end['f'], end['h'], end['l'], end['pc'], end['sp'], end['ime'],
                end.get('ei', 0), len(end['ram'])]
    for address, value in end['ram']:
        numbers += [address, value]
    numbers.append(len(vector['cycles']))
    return ' '.join(map(str, numbers))


def fetch(expected_digest=CORPUS_SHA256):
    target = CACHE / REVISION
    done = target / 'vectors.txt.gz'
    if done.is_file():
        return done
    target.mkdir(parents=True, exist_ok=True)
    temporary = target / 'vectors.txt.gz.partial'
    hashes, names, counts, plain = [], [], [], 0
    with urllib.request.urlopen(URL, timeout=300) as response, tarfile.open(fileobj=response, mode='r|gz') as archive, \
            gzip.open(temporary, 'wt', encoding='ascii', compresslevel=6) as out:
        for member in archive:
            path = Path(member.name)
            if path.name == 'LICENSE' and len(path.parts) == 2:
                (target / 'LICENSE').write_bytes(archive.extractfile(member).read())
            if path.parent.name != 'v1' or path.suffix != '.json':
                continue
            if names and path.stem <= names[-1]:
                raise SystemExit(f'The archive lists {path.stem!r} after {names[-1]!r}: the files are read in name order.')
            raw = archive.extractfile(member).read()
            vectors = json.loads(raw)
            family = len(names)
            names.append(path.stem)
            hashes.append(f'{path.stem} {hashlib.sha256(raw).hexdigest()}')
            counts.append(len(vectors))
            for index, vector in enumerate(vectors):
                text = line(family, index, vector)
                plain += text.split(' ', 3)[2] == '1'
                out.write(text + '\n')
    digest = hashlib.sha256('\n'.join(hashes).encode('ascii')).hexdigest()
    if len(names) != FILES or digest != expected_digest:
        temporary.unlink()
        raise SystemExit(f'The SM83 corpus at {REVISION} has {len(names)} files and digest {digest}; expected {FILES} files '
                         f'and {expected_digest}. Nothing was cached.')
    (target / 'families.json').write_text(json.dumps({'revision': REVISION, 'source': URL, 'corpus_sha256': digest,
                                                       'families': names, 'vectors_per_family': counts, 'plain_memory_vectors': plain},
                                                      indent=1), encoding='utf-8')
    os.replace(temporary, done)
    print(done, f'{sum(counts)} vectors, {plain} on plain memory', flush=True)
    return done


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--print-digest', action='store_true', help='fetch without checking the digest and print it (to pin a revision)')
    args = parser.parse_args()
    if args.print_digest:
        try:
            fetch('(print only)')
        except SystemExit as error:
            print(error)
    else:
        fetch()
