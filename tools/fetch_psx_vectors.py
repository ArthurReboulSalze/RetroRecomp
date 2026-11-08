"""The independent vectors of the PlayStation's CPU (gate G10): SingleStepTests/r3000 and the GTE vectors of JaCzekanski/ps1-tests.

    python tools/fetch_psx_vectors.py FOLDER                     download what FOLDER lacks (about 24 MB), check every file
    python tools/fetch_psx_vectors.py FOLDER --verify            check FOLDER against the pinned digests, no network
    python tools/fetch_psx_vectors.py FOLDER --from R3000 TESTS  copy from local clones of the two repositories, no network

Both suites are MIT licensed. SingleStepTests/r3000 is generated from ares's interpreter (a model, not hardware): one `.json.bin`
file per instruction, 1,000 vectors each, no COP0 and no GTE. `gte/test-all/tests.c` of ps1-tests holds 1,150 GTE vectors whose
expected values its author recorded from a console (its `psx.log` says all of them pass there; that is the author's statement). FOLDER
is outside the repository and any release: nothing of either suite is copied into them.

FOLDER/r3000/<name>.json.bin and FOLDER/gte/tests.c; every file has a pinned size and SHA-256, and the corpus digest (the SHA-256 of
the lines "<name> <SHA-256 of the file>" in name order) is pinned too: a file that does not match is refused.
"""
import argparse
import hashlib
import shutil
import sys
import urllib.request
from pathlib import Path

R3000_REVISION = '51e227447d0b93882a8f13c87c6cee72819efdd3'
TESTS_REVISION = 'f727802fead11f1daa7549285548392ef87749cb'
R3000_URL = f'https://raw.githubusercontent.com/SingleStepTests/r3000/{R3000_REVISION}/v1'
GTE_URL = f'https://raw.githubusercontent.com/JaCzekanski/ps1-tests/{TESTS_REVISION}/gte/test-all/tests.c'
CORPUS_SHA256 = '0cc36f7f528ef483bc76d8123d0d4d40763b5470d89214d085c382d84f027b1e'
GTE_SHA256 = 'b44f16500fe9493bf5ff470c68fa3f2002dd0ec40f9da4442ad54e55774d45e6'
SUFFIX = '.json.bin'

# (instruction, size in bytes, SHA-256) of the files of v1/ at the pinned revision, in name order.
FILES = (
    ('ADD', 431004, 'e1e11f8d96e35c11e90503d328c3279772531e644c9352a72accf565738883bb'),
    ('ADDI', 431004, 'ca73e94efc9a69cc650fff3db2ce6fadd9dba053f8e99331ec54c8944314df8c'),
    ('ADDIU', 431004, 'f04c6bc425ffa97cb952653af33c7568264ad37d4d6ecba5fde1beb67248ae69'),
    ('ADDU', 431004, 'f886d27d26f4b89a4de43f005a1d6bfdcd1e752501019329be26e059ff32bbcf'),
    ('AND', 431004, 'cc733a72a0359d6eba41bfcae66ff07752e1fe14a55244b251c457507201b684'),
    ('ANDI', 431004, '7f7ee0117d424deff5254e5d3660448d6634d983f67e5b3e5c39f927d94557e0'),
    ('BCondZ', 431004, 'df5afbefe7514064756bde64f45f84eb8d50ef49ef9590f7dd2cf3bf8cc13554'),
    ('BEQ', 431004, '8d2c47243e5abdf70c9711296b9dd5714f9baf031dc5332656f8f94e1d83e6e9'),
    ('BGTZ', 431004, '0eef68875a743423f3f1d69fa2d09def0253a314686cedb4a10bc41bb59200db'),
    ('BLEZ', 431004, 'd96d2a8d02a5b47c896b04381e2518735044fc8974a64cea5639ae2c4d011d34'),
    ('BNE', 431004, '87db1fd744198957d0460cffcc6042762385a15c649238a7559ebc3a6117c9fb'),
    ('BREAK', 431004, 'a68e542f2aa83b0c91afe84645120c8da6ee85a669ad856d31cae88ef469c7f6'),
    ('DIV', 431004, '74fb72c5141f40ab1f719d8f8d09969122be76449ef22059d8c878e62cfb911a'),
    ('DIVU', 431004, '4a5424058e4b64fa2de6fa535c570b3c592eb18c44282aaf4293c0ef6934e117'),
    ('J', 431004, '383e5017e7cb256a34cb5214ee6f1ff6e3aa6f9321d763ba93126c50350588df'),
    ('JAL', 431004, 'f37ec471892669d97dbfe82f056cb3d84b1618c612a2002868a788a060d54e59'),
    ('JALR', 431004, '083241b8b142fb9a5fd638d7708c221c8f1c68587858e3e0a38db48878321d31'),
    ('JR', 431004, 'fd9cdbe12542a5dd9779489e17ad0c0631c632041cdd7c5f3a78329be75dd086'),
    ('LB', 455004, '799b12786b65a19ac2d1e6894e9da4573fa93e63f9027cbffcba6ac2d36d00f1'),
    ('LBU', 455004, '3cdccffba21f099694529433a8e0b05d4c6e0345bbe0bec2ecc431657822571a'),
    ('LH', 443340, '5ddb427d20694bb2b7dd06e037b84f78e4643abb56aea7837e6a1b2fe76c74a4'),
    ('LHU', 443220, 'a872c0596cb7ca2ada16986314c31b02159bcd55ee3f8502418e5cd94b66d85e'),
    ('LUI', 431004, 'f8581db8f7a0459d76f4bfbec74753bf98adee1c4a0d2c295e463d167e9bf0d8'),
    ('LW', 436572, '08fe23b2d7393473223bde7f603d13b8ccc1b2522c26579af9149e2662d63579'),
    ('LWL', 461244, 'c3aa34313dbf7e7900d76ac584fbd6d5b94a2bd588eb87f28110227be1019c71'),
    ('LWR', 461364, '3dbb3fbc51ad3435d92c0310b5ebe18b5e3b1a845519efd28d18cbd03bf02d7c'),
    ('MFHI', 431004, '2163f6ac7ca87b4495a192351c106402e1ab86a328fef3a8ddce4b0eb1e216b7'),
    ('MFLO', 431004, '99f48e372ad46bb2dc872ad60611a3b463f933442c1dc06de72776cdb5ecee99'),
    ('MTHI', 431004, '13a79e92108bc6ad8f010aa5f0ef9725a9afde110edb14edbfc0d30a46c71b20'),
    ('MTLO', 431004, '6cb89401b3d9092cfe02b68763981ea310e248a582863c3b801b2a6f894c5027'),
    ('MULT', 431004, '1b188cbd0ae6b22e37eea7f51fd03bd3fde9cd278435004c08bcfad31670f9b0'),
    ('MULTU', 431004, '9d0c841477c9055ed6a0d24c67982e3527ca8dcc2d00a0a73ffc84b49aec7422'),
    ('NOR', 431004, '07abaf3f5d131006e728f945cf48143525a43ef811f1fa8cddc9f5bbdfea5d1d'),
    ('OR', 431004, 'f733b46d5da6ca7525dbcd45d8677b8eba2c0f1c2da6653519b8cb4819c3ee4c'),
    ('ORI', 431004, '2f06466bc5a211e825c2a1381c6068a0b003e3e0454fc2538f65ceafee028241'),
    ('SB', 455004, 'f268c90722b9c7a1bb06333fca41843590678b83f65f7ceb5050454349fea431'),
    ('SHL', 442836, '89e0b431af6d26c9a4c7103b5b38e840529c4c616a1e5a78084567c16acce152'),
    ('SLL', 431004, '8dc42ee2733d62ec536c3da97d9617f7dadd375b91a290206b8d38a088afd9f2'),
    ('SLLV', 431004, '519e24dad0ef87cb1c205bb85b6b66c560e6f8599a9d84904c20f248206d1ef7'),
    ('SLT', 431004, 'a1c3a00e4d4abf4c139f6d0c88ebbd202f702de6b657c74844550c772118fc3f'),
    ('SLTI', 431004, '1e6c8d1e6774e69a14698117e746afd93aae497e63fe47970631a2b9d0d57bf7'),
    ('SLTIU', 431004, 'f8a782855b178a9d6e4281d4b9615cfcd28217e32930b29d22b3f1c2505ff521'),
    ('SLTU', 431004, '113b8add0240c945d26394c020e5c3ec523130e6ac43cc14d4c585c8362ccec8'),
    ('SRA', 431004, '2f305bf73dd0fd2bd954f54fd68f7815b67a03d4aab05ef8b73fe7dcc01ad2c0'),
    ('SRAV', 431004, 'b263f5a5a8ac9f6d08df155be6b345274ae152cecc8b0b16bd9763ebedc27bac'),
    ('SRL', 431004, '526ae4c7fbfa4e6c7c5b52181c9cf36852d3c41962fbf44b23012ff8d0c1569d'),
    ('SRLV', 431004, '5f047b35961eab0337b1eb129d12a08891ef35a99f29e6590ad5f9fc1bf46fe7'),
    ('SUB', 431004, '2accef7c8dab34269414b723a448e4d6f277c4f663032d118dfeaad43d1804a8'),
    ('SUBU', 431004, 'e1fb5675b1d96d13e82f45d903b047f796eb35b6a56e9e25989fb2d3075f4ec5'),
    ('SW', 437436, 'a5f5fc771eca8fa04bec8465c2d353b978724c338f0179710bebcf614b8d031d'),
    ('SWL', 460644, 'a25a07362d068417f29f6435f760b3a8e60d4167d423d2aa0bfe32496b7c579d'),
    ('SWR', 461292, '7fac501a86b6e58e087aeb8545c5cd0f3dce4cf97c5d57ad7645fe324bbc213e'),
    ('SYSCALL', 431004, '5807b3ad215cac0787c5fd183d934236c041a01d47d92f25bae3735b2fdedcf2'),
    ('XOR', 431004, 'ca47a3799b7169096e6b1181fb34ae26b6d43ecbcab36ff571565e6c4a625c4b'),
    ('XORI', 431004, '96f05d9ccce7de4123298721f50097e33a6e8d5669a8c6ad8e8c5ab3e33f631c'),
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def corpus_digest(rows) -> str:
    return hashlib.sha256(''.join(f'{name} {digest}\n' for name, digest in rows).encode()).hexdigest()


def r3000_folder(folder: Path) -> Path:
    return Path(folder) / 'r3000'


def gte_file(folder: Path) -> Path:
    return Path(folder) / 'gte' / 'tests.c'


def problems(folder: Path) -> list[str]:
    """What does not match the pins, in words (empty: the folder is the pinned corpus)."""
    out = []
    root = r3000_folder(folder)
    for name, size, digest in FILES:
        path = root / (name + SUFFIX)
        if not path.is_file():
            out.append(f'{path.name}: missing')
        elif path.stat().st_size != size or file_sha256(path) != digest:
            out.append(f'{path.name}: differs from the pinned file')
    if corpus_digest((name, digest) for name, _, digest in FILES) != CORPUS_SHA256:
        out.append('the pinned table does not match its corpus digest')
    gte = gte_file(folder)
    if not gte.is_file():
        out.append('gte/tests.c: missing')
    elif file_sha256(gte) != GTE_SHA256:
        out.append('gte/tests.c: differs from the pinned file')
    return out


def copy_from(folder: Path, r3000_clone: Path, tests_clone: Path) -> None:
    root = r3000_folder(folder)
    root.mkdir(parents=True, exist_ok=True)
    for name, _, _ in FILES:
        shutil.copyfile(Path(r3000_clone) / 'v1' / (name + SUFFIX), root / (name + SUFFIX))
    gte_file(folder).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(tests_clone) / 'gte' / 'test-all' / 'tests.c', gte_file(folder))


def download(folder: Path) -> None:
    root = r3000_folder(folder)
    root.mkdir(parents=True, exist_ok=True)
    wanted = [(f'{R3000_URL}/{name}{SUFFIX}', root / (name + SUFFIX)) for name, _, _ in FILES]
    wanted.append((GTE_URL, gte_file(folder)))
    gte_file(folder).parent.mkdir(parents=True, exist_ok=True)
    for url, path in wanted:
        if not path.is_file():
            with urllib.request.urlopen(url, timeout=120) as response:
                path.write_bytes(response.read())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--from', dest='clones', nargs=2, type=Path, metavar=('R3000', 'PS1_TESTS'))
    args = parser.parse_args()
    if args.clones:
        copy_from(args.folder, *args.clones)
    elif not args.verify:
        download(args.folder)
    wrong = problems(args.folder)
    for line in wrong:
        print(line, file=sys.stderr)
    print(f'{len(FILES)} instruction files and the GTE file ' + ('do not match the pins' if wrong else 'match the pins'))
    return 1 if wrong else 0


if __name__ == '__main__':
    raise SystemExit(main())
