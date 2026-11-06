"""vAmiga Core at its pin, adapted for Retro-Recomp at build time (MIT script; the files it changes stay MPL-2.0 or MIT).

The Amiga machine is vAmiga's Core (Dirk W. Hoffmann, MPL-2.0 per file; its CPU, Moira, is MIT). The converter clones it at the
pinned revision into the workspace's `.deps`, copies `Core/` into a build folder and applies the replacements below. Each one must
find its pinned text exactly once, so an upstream change fails loudly instead of building something else. Our changes to an
MPL-2.0 file are MPL-2.0 too (licenses/vamiga.md); the changed Moira files stay MIT.

What they do: give a host that drives the machine frame by frame (no emulator thread) access to it; let the generated native
steps call Moira's instruction templates and know each opcode's handler; the hook that runs a guarded native step instead of the
jump table; and the fix of an upstream bug in `Texture::clear` that writes past the picture on short PAL lines.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from .paths import ROOT

VAMIGA_REPOSITORY = 'https://github.com/dirkwhoffmann/vAmiga.git'
VAMIGA_REV = 'f51a6bf9e4e19387a27a31b149ef298f6f6807f8'
FORMAT = 1

REPLACEMENTS = [
    ('Infrastructure/Emulator.h',
     'class Emulator : public Thread, public Synchronizable {\n\n    friend class API;\n    friend class VAmiga;\n',
     'class Emulator : public Thread, public Synchronizable {\n\n    friend class API;\n    friend class VAmiga;\n\n'
     'public:\n\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): a host that drives the main instance frame by frame\n'
     '    // itself, without the emulator thread, reaches it here.\n'
     '    class Amiga &rrMain() { return main; }\n'),
    # Upstream bug (vAmiga f51a6bf, Texture.cpp): the cycle offset is added to the row pointer AND used as the column
    # index, so clearing the last cycle of a short PAL line (row 312, cycle 226) writes 3.6 KB past the texture. Unnoticed
    # with glibc/macOS allocators, a crash with MinGW's. Fix: the row pointer only.
    # Native steps (stage 3, option B): our generated steps call Moira's instruction templates directly, so they need
    # access to them (MIT file of Moira; a friend declaration only), and the conversion needs each opcode's handler name.
    ('Components/CPU/Moira/Moira.h',
     'class Moira : public SubComponent {\n',
     'class Moira : public SubComponent {\n\n'
     '    // Retro-Recomp modification (MIT, like this file): the generated native steps call the instruction templates.\n'
     '    friend struct RrAmigaSteps;\n'),
    ('Components/CPU/Moira/MoiraInit_cpp.h',
     '#define CIMS(id,name,I,M,S) { \\\n',
     '// Retro-Recomp modification (MIT, like this file): the handler name of each opcode, for the native-step generator.\n'
     'extern const char *rr_moira_exec_name[65536];\n'
     '#define CIMS(id,name,I,M,S) { \\\n'
     'rr_moira_exec_name[id] = #name; \\\n'),
    ('Components/CPU/Moira/Moira.cpp',
     '#include "MoiraInit_cpp.h"\n',
     '#include "MoiraInit_cpp.h"\n'
     '// Retro-Recomp modification (MIT, like this file): storage of the handler names recorded by CIMS, and the hook the\n'
     '// host sets to observe executed instructions or to run a guarded native step instead of the jump table (true: done).\n'
     'const char *rr_moira_exec_name[65536];\n'
     'bool (*rr_moira_native)(Moira &, u32 pc, u16 opcode) = nullptr;\n'),
    ('Components/CPU/Moira/Moira.cpp',
     '        reg.pc += 2;\n        try {\n            (this->*exec[queue.ird])(queue.ird);\n',
     '        reg.pc += 2;\n        try {\n'
     '            // Retro-Recomp modification (MIT): a guarded native step, else the jump table.\n'
     '            if (!(rr_moira_native && rr_moira_native(*this, reg.pc - 2, queue.ird))) (this->*exec[queue.ird])(queue.ird);\n'),
    ('Components/CPU/Moira/Moira.cpp',
     '            try {\n                (this->*exec[queue.ird])(queue.ird);\n            } catch (const std::exception &exc) {\n                processException(exc);\n            }\n        }\n\n    done:',
     '            try {\n'
     '                // Retro-Recomp modification (MIT): a guarded native step, else the jump table.\n'
     '                if (!(rr_moira_native && rr_moira_native(*this, reg.pc - 2, queue.ird))) (this->*exec[queue.ird])(queue.ird);\n'
     '            } catch (const std::exception &exc) {\n                processException(exc);\n            }\n        }\n\n    done:'),
    ('Components/Denise/Texture.cpp',
     '    auto *ptr = pixels.ptr + row * HPIXELS + 4 * cycle;\n\n    for (isize col = 4 * cycle; col < 4 * cycle + 4; col++) {',
     '    // Retro-Recomp modification (MPL-2.0, like this file): the column index already holds the cycle offset.\n'
     '    auto *ptr = pixels.ptr + row * HPIXELS;\n\n    for (isize col = 4 * cycle; col < 4 * cycle + 4; col++) {'),
]


def adaptation_digest() -> str:
    """What the adapted tree depends on besides the pin: the replacements themselves."""
    value = hashlib.sha256(b'amiga-vamiga-adaptation\0' + str(FORMAT).encode() + b'\0' + VAMIGA_REV.encode())
    for rel, old, new in REPLACEMENTS:
        value.update(b'\0' + rel.encode() + b'\0' + old.encode() + b'\0' + new.encode())
    return value.hexdigest()


def source(emit=print) -> Path:
    """The pinned vAmiga checkout under `.deps` (cloned when missing, refused when moved or edited)."""
    from .conversion_common import pinned_checkout
    from .core import run
    target = ROOT / '.deps' / 'vamiga'

    def git(*arguments, **options):
        return run(['git', '-C', target, *arguments], **options)

    def clone():
        emit('Amiga: fetching vAmiga at its pinned revision.')
        run(['git', 'clone', '--no-hardlinks', VAMIGA_REPOSITORY, target])
        git('checkout', '--detach', VAMIGA_REV)

    def refuse(head):
        raise ValueError('vAmiga revision differs from the pinned one.')
    pinned_checkout(target, VAMIGA_REV, git, present=target.exists(), clone=clone, moved=refuse,
                    dirty=lambda: ValueError('vAmiga sources changed; the converter adapts a copy.'))
    return target


def adapt(checkout: Path, target: Path) -> Path:
    """Copy `Core/` of the checkout to `target/Core` and apply the replacements; returns the adapted Core folder. Done once per
    adaptation digest (a `ready.json` beside it)."""
    ready = target / 'ready.json'
    digest = adaptation_digest()
    core = target / 'Core'
    try:
        if json.loads(ready.read_text(encoding='utf-8')).get('adaptation') == digest and core.is_dir():
            return core
    except (OSError, ValueError):
        pass
    if core.exists():
        shutil.rmtree(core)
    shutil.copytree(checkout / 'Core', core)
    for rel, old, new in REPLACEMENTS:
        path = core / rel
        text = path.read_text(encoding='utf-8')
        if text.count(old) != 1:
            raise ValueError(f'vAmiga {rel}: the pinned text was not found exactly once.')
        path.write_text(text.replace(old, new), encoding='utf-8', newline='\n')
    ready.write_text(json.dumps({'revision': VAMIGA_REV, 'adaptation': digest, 'replacements': len(REPLACEMENTS)}) + '\n',
                     encoding='utf-8')
    return core
