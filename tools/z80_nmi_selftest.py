"""ROM-free check of the banked Z80 chain's NMI acceptance against the reference CPU (native/z80_nmi_checks.c).

Builds the check twice from the pinned interpreter (never a game): with the NMI corrections of `cpu.prepare_reference(nmi=True)`,
where the chain's `banked_accept_nmi` must agree with the interpreter on every register, both flip-flops, HALT, the cycles, the
return address and the memory (every case must pass); and with the interpreter as the pinned engine has it, where the same cases
must FAIL (a positive control: the check can see the difference the corrections make). Nothing is written outside .build/.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def compiler() -> str:
    try:
        from retrorecomp import toolchain
        candidate = toolchain.tools_directory() / 'llvm-mingw' / 'bin' / ('clang.exe' if os.name == 'nt' else 'clang')
        if candidate.is_file():
            return str(candidate)
    except Exception:
        pass
    for name in ('clang', 'gcc', 'cc'):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit('No C compiler found.')


def build_and_run(nmi: bool, folder: Path) -> tuple[int, str]:
    from retrorecomp import z80_chain
    from retrorecomp.cpu import prepare_cpu_headers, prepare_reference
    engine = ROOT / '.deps' / 'smsggrecomp'
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    prepare_cpu_headers(folder, engine)
    prepare_reference(folder, engine, nmi=nmi)
    (folder / 'z80_nmi_accept.inc').write_text(z80_chain._NMI_ACCEPT, encoding='utf-8', newline='\n')
    shutil.copyfile(ROOT / 'native' / 'banked_reference_state.inc', folder / 'banked_reference_state.inc')
    exe = folder / ('z80_nmi_checks.exe' if os.name == 'nt' else 'z80_nmi_checks')
    command = [compiler(), '-std=gnu11', '-Wall', '-O1', '-DSMSRECOMP_BANKED_AOT', '-I', str(folder),
               str(ROOT / 'native' / 'z80_nmi_checks.c'), '-o', str(exe)]
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    built = subprocess.run(command, capture_output=True, encoding='utf-8', errors='replace', creationflags=flags)
    if built.returncode:
        return 2, built.stdout + built.stderr
    ran = subprocess.run([str(exe)] + ([] if nmi else ['--expect-difference']), capture_output=True, encoding='utf-8',
                         errors='replace', timeout=120, creationflags=flags)
    return ran.returncode, ran.stdout.strip()


def main() -> int:
    build = ROOT / '.build' / 'z80-nmi-selftest'
    status = 0
    for nmi, label in ((True, 'corrected interpreter (nmi=True): every case must agree'),
                       (False, 'pinned interpreter (nmi=False): the check must fail (positive control)')):
        code, text = build_and_run(nmi, build / ('nmi' if nmi else 'pinned'))
        print(f'{label}: {text}  ->  {"ok" if code == 0 else "FAILED"}')
        status |= code
    return status


if __name__ == '__main__':
    sys.exit(main())
