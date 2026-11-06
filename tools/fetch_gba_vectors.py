"""Fetch the independent ARM7TDMI vectors (SingleStepTests/ARM7TDMI) for the Game Boy Advance checks of the CPU (gate G10).

    python tools/fetch_gba_vectors.py FOLDER            download what FOLDER lacks (about 920 MB), check every file
    python tools/fetch_gba_vectors.py FOLDER --verify   check FOLDER against the pinned digests, no network

The suite is MIT licensed and generated from NanoBoyAdvance's model of the ARM7TDMI: it says what that model does, not what hardware
does. One `.json.bin` file per encoding family (45 files of 50,000 vectors: the state before and after one instruction, with the
data transactions it made), read from the pinned revision of the repository. FOLDER is chosen by the player or the maintainer and
is never in the repository or in a release; nothing from the suite is ever copied into either.

Every file has a pinned size and SHA-256 below, and the corpus digest (the SHA-256 of the lines "<name> <SHA-256 of the file>" in
name order) is pinned too: a file that does not match is refused, and what was checked is recorded in FOLDER/vectors.sha256.
A clone of the repository works as FOLDER when pointed at its `v1` directory.
"""
import argparse
import hashlib
import json
import os
import urllib.request
from pathlib import Path

REVISION = 'e3097d88d428752736b949d94c094d5da50f0db6'
CORPUS_SHA256 = '3918e09dc4a6b5293aecb9409434174fb832608f359013e34e3c1a5412b8d77b'
BASE_URL = f'https://raw.githubusercontent.com/SingleStepTests/ARM7TDMI/{REVISION}'
SUFFIX = '.json.bin'
RECORD = 'vectors.sha256'
CHUNK = 1 << 20

# (file, size in bytes, SHA-256) of the files of v1/ at the pinned revision, in name order.
FILES = (
    ('arm_b_bl', 20807256, '08a34cf3cce61e88110fafa110a609ec20d1426f6779ac01c052341ffaf59e4a'),
    ('arm_bx', 20799576, '8b75a2f6166d0fcb4f17ecee0bff0601b59488803a3ef6c87574e36039b1084a'),
    ('arm_cdp', 20807496, '7d4b9c685b71ca1bd0f824511024e407590be2f150d2aa631a1b4dfdc30597ff'),
    ('arm_data_proc_immediate', 19655736, '1cc79b425f7dd483ca5c3afaed5665922fbbaa17653200465af708564ff5086e'),
    ('arm_data_proc_immediate_shift', 19655112, 'afadd0d0f1c4a9926b1e5418e76bff5e1056706aff452c1ba5e4c1622c3f7c4b'),
    ('arm_data_proc_register_shift', 19654632, '542b831c90f93bd739857fd48448806c0e880a8b965e19b0979b6efe26f432ac'),
    ('arm_ldm_stm', 24741624, 'a8e6d88b18f37cfdbba214a034e8a89760f58fbdf1a7b7c7bf45d76e3599745f'),
    ('arm_ldr_str_immediate_offset', 20292888, '799154dc74202ef821b5fdf617b4f8057ea97c1ed216509507fbcb99b8cadab2'),
    ('arm_ldr_str_register_offset', 20296920, 'e4f5b4dafd708bb256c6620afe6e611d232eb896bc64c2e1c74fc4c9ec2e0b43'),
    ('arm_ldrh_strh', 20294544, '6a8c7b909de59e0687097caa9d39fffa6d674af95c534f76fe34e55b48961ee4'),
    ('arm_ldrsb_ldrsh', 20336904, '8cd920d3b933deecc70c9988871ee58346448201547d685379066e21c3f64eb6'),
    ('arm_mcr_mrc', 20804520, '86ac57f74c9bfec7200421e3778412ba4319434d6c93a3abf9998223dc1c4a71'),
    ('arm_mrs', 19600008, '8f2389f06cd794b6c7085b1b87c8df7fa0187791aeba9c5c21b8c934079a10f2'),
    ('arm_msr_imm', 19600008, '77459c806fbc7dbeea2bc165c4b59e7d22e8a6365cfdd9b43a748df8572dc89f'),
    ('arm_msr_reg', 19600008, '402131447d908a2eeed5f7bf3315793b963fb3a76b343537de7343914b5ba31c'),
    ('arm_mul_mla', 19676808, '40fd66bd248e7a54cbe4637b8d10f36558f1a78e1b7a689ed31f568f3ee09aa7'),
    ('arm_mull_mlal', 19741992, '24bbfd810f5d2f833cda25c40577154c8c603a03b0c57b466eaad4f8fe93add5'),
    ('arm_stc_ldc', 20812776, '8eac2385c05c7a60aa436af89fdeb20346611fcb8ee078311ee100a71c8015fe'),
    ('arm_swi', 20806776, 'b2d54cccd1cc04b42eae7490a23ed80242cd199c58420d020fe687b9005ef821'),
    ('arm_swp', 20871192, 'ce9dc62b94fd5f8ff893c056cc6d24b831869cd1518030395658dcd23566675c'),
    ('thumb_add_cmp_mov_hi', 19700712, 'e9fd8c961548a11a155c957140f442c5c8c559ca34ef19b1c1df1412f3157dfb'),
    ('thumb_add_sp_or_pc', 19600008, 'cf75feb7b2483e3f679091dd0fc851ef6b4772c7dc5109025eff0c546d5beea9'),
    ('thumb_add_sub', 19600008, 'c5aab8bfd9187c7e6a0194024a603cbaf63cf678508e623780188f733155b386'),
    ('thumb_add_sub_sp', 19600008, '297b8ffa8cdc768612e823b0b60b15dea1ac1f8633adb47dd750289a09d8ac1a'),
    ('thumb_b', 22000008, 'c9dad33ec000901b147e8d11bd6cba48d0f2e7053404f110ffc9c49ecca430ea'),
    ('thumb_bcc', 20799240, '0163f7f6558da679896993d62dbf81b73e1fa8b783acba9485c8d3d10c366114'),
    ('thumb_bl_blx_prefix', 19600008, '51cef2e4c2f24e26db87d9e41b3f3c00e530c45f7e47eb3e0cd6e8e2061f0937'),
    ('thumb_bl_suffix', 22000008, '201f027814ee6d0a378d780c34b77a7797bf9f3e830f9da6b044930b3871c166'),
    ('thumb_bx', 22000008, 'b322617160e7249c1a6d4fe3bc91913a22d0882298b46cf5ff28171f5f1e967b'),
    ('thumb_data_proc', 19600008, '65b91a6abcf5e916c938f34cdeb700061ac198268d15b6564de45b7ba691c581'),
    ('thumb_ldm_stm', 24405888, 'b8032580bbb3c689e1f61de7811780b70d5bb1ba2fde3125c28193f9a8e617a3'),
    ('thumb_ldr_pc_rel', 20800008, '2ab87b83cdba0d3eb47114ad8aca002eb75c77592483294ee6fd277cfcb0c2be'),
    ('thumb_ldr_str_imm_offset', 20800008, 'fcd15247b7846586cc556d72195a92732066bf604b5c35219145ba9690d9f522'),
    ('thumb_ldr_str_reg_offset', 20800008, '41343ac100577130240251d285c4bdd4c5e123cd1d36f7d02feb5b34d179ad06'),
    ('thumb_ldr_str_sp_rel', 20800008, '6157c583329b23c74620a1440194ed479a91ee4ea45617786e4e926838b496c2'),
    ('thumb_ldrb_strb_imm_offset', 20800008, 'ec12a5926407add41b7efbfc99cdf06252eed6e631c3bf3d0c576e5da9ea2e64'),
    ('thumb_ldrh_strh_imm_offset', 20800008, 'c37ed68dd94483d150a45c34d5944e6b2eb6bc1afc7f8591ee65e264967bd13e'),
    ('thumb_ldrh_strh_reg_offset', 20800008, 'd574e2531549741129cfbb16e1572b8d6c32ef2ddbee37b4c283e27363fc7085'),
    ('thumb_ldrsb_strb_reg_offset', 20800008, 'e1bc905052d2b21dc6ac10cb0310d0e9ee46a7de1186d77d46473a4b32bfd2da'),
    ('thumb_ldrsh_ldrsb_reg_offset', 20800008, 'b150a820c4778b95105b58ed431da81c08ba66b0939ab4be2a2128ef62440ea7'),
    ('thumb_lsl_lsr_asr', 19600008, 'ee06a2b0ad0567e2a0c6b3be9fe6dbe5a59437a5f8562c64793f7642381cea7e'),
    ('thumb_mov_cmp_add_sub', 19600008, '3fad2efb2e3a8b3e083f3265a1e65d5eadbab816956d03ae6553832915092407'),
    ('thumb_push_pop', 25598712, '877d3a7e6613ffa96a268d82ece29c65501ffdc3a89049f33facdcddf4bb9535'),
    ('thumb_swi', 22000008, 'b90f9b4425d5bd872c7b047646103b0701c61d4929bfb8b51b23e3644d01a273'),
    ('thumb_undefined_bcc', 22000008, 'c2f9901dd0624bf03b324df8a5eafd34b5dd4a537ff8d5a25cb84affcfb03e8c'),
)


def file_name(name):
    return name + SUFFIX


def file_url(name):
    return f'{BASE_URL}/v1/{file_name(name)}'


def corpus_digest(hashes):
    """The digest of the corpus from {name: SHA-256 of the file}: it does not depend on where or how the files are stored."""
    return hashlib.sha256('\n'.join(f'{name} {hashes[name]}' for name in sorted(hashes)).encode('ascii')).hexdigest()


def pinned_digest():
    return corpus_digest({name: digest for name, _size, digest in FILES})


def vector_dir(folder):
    """FOLDER itself, or its `v1` directory when that is where the files are (a clone of the repository)."""
    folder = Path(folder)
    return folder / 'v1' if (folder / 'v1').is_dir() and not (folder / file_name(FILES[0][0])).is_file() else folder


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(CHUNK), b''):
            digest.update(block)
    return digest.hexdigest()


def inspect(folder, check_hashes=True):
    """What FOLDER holds: (names of the files that are there and match, names that are missing, names that differ).
    A file whose size differs from the pin is not hashed."""
    folder = vector_dir(folder)
    good, missing, wrong = [], [], []
    for name, size, digest in FILES:
        path = folder / file_name(name)
        if not path.is_file():
            missing.append(name)
        elif path.stat().st_size != size or (check_hashes and sha256_file(path) != digest):
            wrong.append(name)
        else:
            good.append(name)
    return good, missing, wrong


def record(folder):
    """Write what FOLDER was checked against: one SHA-256 line per file, and the revision, source and corpus digest."""
    folder = vector_dir(folder)
    lines = [f'{digest}  {file_name(name)}' for name, _size, digest in FILES]
    (folder / RECORD).write_text('\n'.join(lines) + '\n', encoding='ascii', newline='\n')
    (folder / (RECORD + '.json')).write_text(json.dumps({'revision': REVISION, 'source': BASE_URL, 'corpus_sha256': pinned_digest(),
                                                         'files': len(FILES)}, indent=1) + '\n', encoding='ascii', newline='\n')


def download(name, size, digest, folder, opener=urllib.request.urlopen):
    """One file from the pinned revision, into FOLDER, kept only when its size and SHA-256 are the pinned ones."""
    target = Path(folder) / file_name(name)
    temporary = target.with_name(target.name + '.partial')
    hasher = hashlib.sha256()
    count = 0
    with opener(file_url(name), timeout=300) as response, open(temporary, 'wb') as out:
        for block in iter(lambda: response.read(CHUNK), b''):
            hasher.update(block)
            out.write(block)
            count += len(block)
    if count != size or hasher.hexdigest() != digest:
        temporary.unlink()
        raise SystemExit(f'{file_name(name)} at {REVISION} has {count} bytes and SHA-256 {hasher.hexdigest()}; expected {size} and '
                         f'{digest}. Nothing was kept.')
    os.replace(temporary, target)


def fetch(folder, opener=urllib.request.urlopen, emit=print):
    """Download what FOLDER lacks or holds wrongly, then record the result. Returns the number of files fetched."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    good, _missing, _wrong = inspect(folder)
    wanted = [row for row in FILES if row[0] not in good]
    for number, (name, size, digest) in enumerate(wanted, 1):
        emit(f'[{number}/{len(wanted)}] {file_name(name)} ({size // 1_000_000} MB)')
        download(name, size, digest, folder, opener)
    if not wanted:
        emit('All the vector files are there and match the pinned digests.')
    record(folder)
    return len(wanted)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folder', type=Path, help='where the .json.bin files are kept (outside the repository)')
    parser.add_argument('--verify', action='store_true', help='only check FOLDER against the pinned digests; no network')
    args = parser.parse_args(argv)
    if args.verify:
        good, missing, wrong = inspect(args.folder)
        print(f'{len(good)} of {len(FILES)} files match; missing: {len(missing)}; different: {len(wrong)}')
        for name in missing + wrong:
            print('  ', file_name(name), 'missing' if name in missing else 'different')
        return 0 if len(good) == len(FILES) else 1
    fetch(args.folder)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
