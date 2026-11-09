"""vAmiga Core at its pin, adapted for Retro-Recomp at build time (MIT script; the files it changes stay MPL-2.0 or MIT).

The Amiga machine is vAmiga's Core (Dirk W. Hoffmann, MPL-2.0 per file; its CPU, Moira, is MIT). The converter clones it at the
pinned revision into the workspace's `.deps`, copies `Core/` into a build folder and applies the replacements below. Each one must
find its pinned text exactly once, so an upstream change fails loudly instead of building something else. Our changes to an
MPL-2.0 file are MPL-2.0 too (licenses/vamiga.md); the changed Moira files stay MIT.

What they do: give a host that drives the machine frame by frame (no emulator thread) access to it; let the generated native
steps call Moira's instruction templates and know each opcode's handler; the hook that runs a guarded native step instead of the
jump table; the specialised routines of the Blitter's copy blits (its own code compiled per shape, `blitter_shape_header`); and the fix
of an upstream bug in `Texture::clear` that writes past the picture on short PAL lines.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from .paths import ROOT

VAMIGA_REPOSITORY = 'https://github.com/dirkwhoffmann/vAmiga.git'
VAMIGA_REV = 'f51a6bf9e4e19387a27a31b149ef298f6f6807f8'
FORMAT = 2       # Raised when what `blitter_shape_header` makes changes.

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
    # The resload traps as one comparison after each instruction, instead of debugger breakpoints: those keep every instruction on Moira's
    # slow path and walk a list. Same place in the loop as the breakpoint test, same stop for the run loop (RL::BREAKPOINT_REACHED).
    ('Components/CPU/Moira/Moira.cpp',
     'bool (*rr_moira_native)(Moira &, u32 pc, u16 opcode) = nullptr;\n',
     'bool (*rr_moira_native)(Moira &, u32 pc, u16 opcode) = nullptr;\n'
     '// Retro-Recomp modification (MIT, like this file): a table of trap addresses, 4 bytes apart, that stops the run loop.\n'
     'u32 rr_moira_trap_base = 0, rr_moira_trap_size = 0;\n'
     'static inline bool rr_moira_trap(u32 pc) { u32 at = pc - rr_moira_trap_base; return at < rr_moira_trap_size && !(at & 3); }\n'),
    ('Components/CPU/Moira/Moira.cpp',
     '        } catch (const std::exception &exc) {\n            processException(exc);\n        }\n\n    } else {\n',
     '        } catch (const std::exception &exc) {\n            processException(exc);\n        }\n'
     '        if (rr_moira_trap(reg.pc0)) didReachBreakpoint(reg.pc0);   // Retro-Recomp modification (MIT)\n\n    } else {\n'),
    ('Components/CPU/Moira/Moira.cpp',
     '    done:\n\n        // Check if a breakpoint has been reached\n',
     '    done:\n\n'
     '        // Retro-Recomp modification (MIT): the trap table, under the condition the breakpoint test has.\n'
     '        if (!(flags & TRACE_EXC) && rr_moira_trap(reg.pc0)) didReachBreakpoint(reg.pc0);\n\n'
     '        // Check if a breakpoint has been reached\n'),
    ('Components/Amiga.cpp',
     '                auto addr = cpu.debugger.breakpoints.hit->addr;\n',
     '                // Retro-Recomp modification (MPL-2.0, like this file): a trap of the table has no breakpoint object.\n'
     '                auto addr = cpu.debugger.breakpoints.hit ? cpu.debugger.breakpoints.hit->addr : (u32)cpu.getPC0();\n'),
    # Native code goes on from instruction to instruction as long as nothing is pending for the Amiga's run loop: it reads the loop's flags.
    ('Components/Amiga.h',
     '    void setFlag(u32 flags);\n',
     '    void setFlag(u32 flags);\n'
     '    const RunLoopFlags *rrRunFlags() const { return &flags; }   // Retro-Recomp modification (MPL-2.0, like this file)\n'),
    # The sound path keeps state a snapshot leaves out (the four samplers' pending samples, the three filters' memory, the
    # sub-sample fraction, the master volume ramps): two public methods save and restore exactly that, so a quick state
    # continues the sound sample for sample. The session appends the bytes to its own state file.
    ('Ports/AudioPort.h',
     '    // Resets the output buffer and the two audio filters\n    void clear();\n',
     r"""    // Retro-Recomp modification (MPL-2.0, like this file): the state of the sound path that a snapshot does not hold.
    void rrSaveAudio(std::vector<u8> &o) const
    {
        auto put = [&](const void *p, size_t n) { o.insert(o.end(), (const u8 *)p, (const u8 *)p + n); };
        for (const auto &s : sampler) {
            i64 n = (i64)s.count(); put(&n, 8);
            for (isize i = 0, k = s.r; i < (isize)n; i++, k = s.next(k)) { put(&s.elements[k], sizeof(i16)); put(&s.keys[k], 8); }
        }
        put(&fraction, 8); put(&sampleRateError, 8);
        double a[6] = { volL.current, volL.maximum, volL.delta, volR.current, volR.maximum, volR.delta }; put(a, sizeof a);
        const OnePoleFilter *one[2] = { &filter.loFilter, &filter.hiFilter };
        for (auto *f : one) { double b[5] = { f->cutoff, f->a1, f->a2, f->tmpL, f->tmpR }; put(b, sizeof b); }
        const TwoPoleFilter &t = filter.ledFilter;
        double c[6] = { t.cutoff, t.qFactor, t.a1, t.a2, t.b1, t.b2 }; put(c, sizeof c);
        put(t.tmpL, sizeof t.tmpL); put(t.tmpR, sizeof t.tmpR);
        u8 m = wasMuted ? 1 : 0; put(&m, 1);
    }
    bool rrLoadAudio(const u8 *p, size_t size)
    {
        const u8 *end = p + size;
        auto get = [&](void *d, size_t n) { if ((size_t)(end - p) < n) return false; memcpy(d, p, n); p += n; return true; };
        for (auto &s : sampler) {
            i64 n; if (!get(&n, 8) || n < 0 || n >= (i64)s.cap()) return false;
            s.clear();
            for (i64 i = 0; i < n; i++) {
                i16 e; i64 k; if (!get(&e, sizeof e) || !get(&k, 8)) return false;
                s.elements[s.w] = e; s.keys[s.w] = k; s.w = s.next(s.w);
            }
        }
        if (!get(&fraction, 8) || !get(&sampleRateError, 8)) return false;
        double a[6]; if (!get(a, sizeof a)) return false;
        volL.current = a[0]; volL.maximum = a[1]; volL.delta = a[2]; volR.current = a[3]; volR.maximum = a[4]; volR.delta = a[5];
        OnePoleFilter *one[2] = { &filter.loFilter, &filter.hiFilter };
        for (auto *f : one) { double b[5]; if (!get(b, sizeof b)) return false; f->cutoff = b[0]; f->a1 = b[1]; f->a2 = b[2]; f->tmpL = b[3]; f->tmpR = b[4]; }
        TwoPoleFilter &t = filter.ledFilter;
        double c[6]; if (!get(c, sizeof c)) return false;
        t.cutoff = c[0]; t.qFactor = c[1]; t.a1 = c[2]; t.a2 = c[3]; t.b1 = c[4]; t.b2 = c[5];
        if (!get(t.tmpL, sizeof t.tmpL) || !get(t.tmpR, sizeof t.tmpR)) return false;
        u8 m; if (!get(&m, 1)) return false;
        wasMuted = m != 0;
        return p == end;
    }

    // Resets the output buffer and the two audio filters
    void clear();
"""),
    # The keyboard's power-up handshake (a second of self test, then the codes $FD and $FE) ended long before a real WHDLoad starts a
    # slave. The machine here enters the slave a frame after its power-on, so the host declares the handshake over: otherwise those
    # two codes arrive about a second into the game, and a slave's keyboard handler that a player's key would reach much later runs
    # during the Kickstart's boot.
    ('Peripherals/Keyboard/Keyboard.h',
     'class Keyboard final : public SubComponent {\n',
     'class Keyboard final : public SubComponent {\n\n'
     'public:\n\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): the keyboard has long been up and is waiting for a key.\n'
     '    void rrHandshakeOver();\n\n'
     'private:\n'),
    ('Peripherals/Keyboard/Keyboard.cpp',
     'void\nKeyboard::wakeUp()\n',
     '// Retro-Recomp modification (MPL-2.0, like this file).\n'
     'void\nKeyboard::rrHandshakeOver()\n{\n    agnus.cancel<SLOT_KBD>();\n    state = KbState::SEND;\n}\n\n'
     'void\nKeyboard::wakeUp()\n'),
    ('Components/Denise/Texture.cpp',
     '    auto *ptr = pixels.ptr + row * HPIXELS + 4 * cycle;\n\n    for (isize col = 4 * cycle; col < 4 * cycle + 4; col++) {',
     '    // Retro-Recomp modification (MPL-2.0, like this file): the column index already holds the cycle offset.\n'
     '    auto *ptr = pixels.ptr + row * HPIXELS;\n\n    for (isize col = 4 * cycle; col < 4 * cycle + 4; col++) {'),
    # The Blitter's copy blits, a specialised routine per shape (`blitter_shape_header` below, generated per game by amiga_codegen): the host looks one up when a blit begins and the
    # slot event runs it instead of the table of the microprogram. A line blit only reports itself. Without a routine, nothing changes.
    ('Components/Agnus/Blitter/Blitter.h',
     'namespace vamiga {\n\n/* The Blitter supports three accuracy levels:\n',
     'namespace vamiga {\n\n'
     '// Retro-Recomp modification (MPL-2.0, like this file): the host is told of each blit (BLTCON0, BLTCON1, words or line steps) and may answer with a routine for its shape.\n'
     'extern void (*(*rr_blit_begin)(u16 con0, u16 con1, u32 size))(void *);\n'
     '// How many blits changed shape under a routine and went on in the microprogram\'s table.\n'
     'extern u64 rr_blit_left_midway;\n\n'
     '/* The Blitter supports three accuracy levels:\n'),
    ('Components/Agnus/Blitter/Blitter.h',
     'class Blitter final : public SubComponent\n{\n    friend class Agnus;\n',
     'class Blitter final : public SubComponent\n{\n    friend class Agnus;\n'
     '    friend struct RrBlitChecks;\n\n'
     'public:\n\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): this blit\'s routine, if any. Not part of a snapshot: every routine checks its shape at each slot.\n'
     '    void (*rrShape)(void *) = nullptr;\n'
     '    template <u16 CON0, u16 CON1> void rrRun();\n\n'
     'private:\n\n'
     '    template <u16 instr, u8 MINTERM, bool DESC, bool EFE> void rrExec();\n'
     '    template <bool EFE> void rrFill(u16 &data, bool &carry) const;\n'),
    ('Components/Agnus/Blitter/Blitter.cpp',
     'void\nBlitter::_initialize()\n',
     '// Retro-Recomp modification (MPL-2.0, like this file).\n'
     'void (*(*rr_blit_begin)(u16 con0, u16 con1, u32 size))(void *) = nullptr;\n'
     'u64 rr_blit_left_midway = 0;\n\n'
     'void\nBlitter::_initialize()\n'),
    ('Components/Agnus/Blitter/SlowBlitter.cpp',
     '    // Schedule the first slow Blitter execution event\n    agnus.scheduleRel<SLOT_BLT>(DMA_CYCLES(1), BLT_COPY_SLOW);\n',
     '    // Retro-Recomp modification (MPL-2.0, like this file): the routine of this shape, if the game has one.\n'
     '    rrShape = rr_blit_begin ? rr_blit_begin(bltcon0, bltcon1, (u32)bltsizeH * bltsizeV) : nullptr;\n\n'
     '    // Schedule the first slow Blitter execution event\n    agnus.scheduleRel<SLOT_BLT>(DMA_CYCLES(1), BLT_COPY_SLOW);\n'),
    ('Components/Agnus/Blitter/SlowBlitter.cpp',
     '    // Schedule the first slow Blitter execution event\n    agnus.scheduleRel<SLOT_BLT>(DMA_CYCLES(1), BLT_LINE_SLOW);\n',
     '    // Retro-Recomp modification (MPL-2.0, like this file): a line blit stays in the microprogram; the host counts it.\n'
     '    if (rr_blit_begin) rr_blit_begin(bltcon0, bltcon1, bltsizeV);\n\n'
     '    // Schedule the first slow Blitter execution event\n    agnus.scheduleRel<SLOT_BLT>(DMA_CYCLES(1), BLT_LINE_SLOW);\n'),
    ('Components/Agnus/Blitter/BlitterEvents.cpp',
     '            (this->*copyBlitInstr[bltconUSE()][0][bltconFE()][bltpc])();\n',
     '            // Retro-Recomp modification (MPL-2.0, like this file): the routine of this blit\'s shape, else the table.\n'
     '            if (rrShape) rrShape(this);\n'
     '            else (this->*copyBlitInstr[bltconUSE()][0][bltconFE()][bltpc])();\n'),
]

# What a routine checks at each slot: the bits of BLTCON0 and BLTCON1 that make a shape, all but the two shift fields, which it reads live. amiga_codegen keys its shapes on these.
SHAPE_CON0_MASK = 0x0fff
SHAPE_CON1_MASK = 0x001f
BLITTER_SHAPE_HEADER = 'Components/Agnus/Blitter/RrBlitterShape.h'


def _between(text: str, start: str, end: str, where: str) -> str:
    """The text from `start` up to `end`, each found exactly once: an upstream change fails loudly."""
    if text.count(start) != 1:
        raise ValueError(f'vAmiga {where}: the pinned text was not found exactly once: {start!r}')
    at = text.index(start)
    stop = text.find(end, at)
    if stop < 0:
        raise ValueError(f'vAmiga {where}: the pinned text was not found: {end!r}')
    return text[at:stop]


def _rewrite(text: str, pairs: list, where: str) -> str:
    for old, new, count in pairs:
        if text.count(old) != count:
            raise ValueError(f'vAmiga {where}: {old!r} was not found {count} times.')
        text = text.replace(old, new)
    return text


def blitter_shape_header(core: Path) -> str:
    """The Blitter's own code, made ready to be compiled once per shape (MPL-2.0, like the files it comes from). Nothing is written by hand here: the text of `exec`, of the shifter,
    of the minterm switch and of the fill comes out of the adapted sources with the shape's values as template parameters, so a compiler folds what the shape fixes; the microprogram
    is read from the table it fills. One step per slot, the same bus requests in the same slots as the reference: its accuracy level 2."""
    slow = (core / 'Components/Agnus/Blitter/SlowBlitter.cpp').read_text(encoding='utf-8')
    blitter = (core / 'Components/Agnus/Blitter/Blitter.cpp').read_text(encoding='utf-8')
    constants = _between(slow, 'static constexpr u16 NOTHING', 'void\nBlitter::initSlowBlitter()', 'SlowBlitter.cpp')
    table = _between(slow, 'void (Blitter::*copyBlitInstr[16][2][2][6])(void) = {', '/* The Line Blitter micro programs', 'SlowBlitter.cpp')
    entries = re.findall(r'&Blitter::(exec|fakeExec) *<([^>]+)>', table)
    if len(entries) != 16 * 2 * 2 * 6 or any((kind == 'exec') != (n % 24 < 12) for n, (kind, _) in enumerate(entries)):
        raise ValueError('vAmiga SlowBlitter.cpp: the copy microprograms do not have the pinned layout.')
    programs = ''.join('    {' + ', '.join('{' + ', '.join(entries[use * 24 + fill * 6 + slot][1] for slot in range(6)) + '}' for fill in (0, 1)) + '},\n' for use in range(16))
    execute = _rewrite(_between(slow, 'template <u16 instr> void\nBlitter::exec()\n{', 'template <u16 instr> void\nBlitter::fakeExec()', 'SlowBlitter.cpp'), [
        ('template <u16 instr> void\nBlitter::exec()\n', 'template <u16 instr, u8 MINTERM, bool DESC, bool EFE> inline void\nBlitter::rrExec()\n', 1),
        ('bool desc = bltconDESC();', 'constexpr bool desc = DESC;', 1),
        ('barrelShifter(anew & mask, aold, bltconASH(), desc)', 'rrBarrelShifter<desc>(anew & mask, aold, bltconASH())', 1),
        ('barrelShifter(bnew, bold, bltconBSH(), desc)', 'rrBarrelShifter<desc>(bnew, bold, bltconBSH())', 1),
        ('doMintermLogic(ahold, bhold, chold, bltcon0 & 0xFF)', '(u16)rrMinterm<MINTERM>(ahold, bhold, chold)', 2),
        ('doFill(dhold, fillCarry)', 'rrFill<EFE>(dhold, fillCarry)', 1),
    ], 'SlowBlitter.cpp')
    shifter = _rewrite(_between(blitter, 'u16\nBlitter::barrelShifter(u16 anew, u16 aold, u16 shift, bool desc) const\n{', 'u16\nBlitter::doMintermLogic(', 'Blitter.cpp'), [
        ('u16\nBlitter::barrelShifter(u16 anew, u16 aold, u16 shift, bool desc) const\n', 'template <bool desc> static inline u16\nrrBarrelShifter(u16 anew, u16 aold, u16 shift)\n', 1),
        ('if (desc) {', 'if constexpr (desc) {', 1),
    ], 'Blitter.cpp')
    minterm = _rewrite(_between(blitter, 'int\nBlitter::doMintermLogicQuick(u16 a, u16 b, u16 c, u8 minterm) const\n{', 'void\nBlitter::doFill(', 'Blitter.cpp'), [
        ('int\nBlitter::doMintermLogicQuick(u16 a, u16 b, u16 c, u8 minterm) const\n', 'template <u8 minterm> static inline int\nrrMinterm(u16 a, u16 b, u16 c)\n', 1),
    ], 'Blitter.cpp')
    fill = _rewrite(_between(blitter, 'void\nBlitter::doFill(u16 &data, bool &carry) const\n{', 'void\nBlitter::doLine()', 'Blitter.cpp'), [
        ('void\nBlitter::doFill(u16 &data, bool &carry) const\n', 'template <bool EFE> inline void\nBlitter::rrFill(u16 &data, bool &carry) const\n', 1),
        ('u8 exclusive = !!bltconEFE();', 'constexpr u8 exclusive = EFE;', 1),
    ], 'Blitter.cpp')
    steps = ''.join(f'        case {slot}: rrExec<rrCopyProgram[use][fill][{slot}], (u8)CON0, desc, efe>(); break;\n' for slot in range(6))
    return ('// Written by retrorecomp/amiga_vamiga.py from vAmiga\'s Blitter (Dirk W. Hoffmann, MPL-2.0, like this file): its copy microprograms, compiled per shape.\n'
            '#pragma once\n#include "vaconfig.h"\n#include "Blitter.h"\n#include "Agnus.h"\n#include "Memory.h"\n#include "Paula.h"\n\nnamespace vamiga {\n\n'
            + constants + '\nstatic constexpr u16 rrCopyProgram[16][2][6] = {\n' + programs + '};\n\n' + shifter + minterm + fill + execute
            + 'template <u16 CON0, u16 CON1> inline void\nBlitter::rrRun()\n{\n'
            f'    if ((bltcon0 & 0x{SHAPE_CON0_MASK:04x}) != CON0 || (bltcon1 & 0x{SHAPE_CON1_MASK:04x}) != CON1) {{\n'
            '        // BLTCON0 or BLTCON1 changed during the blit: the table goes on with it, as it reads them at every slot.\n'
            '        rrShape = nullptr;\n        rr_blit_left_midway++;\n'
            '        (this->*copyBlitInstr[bltconUSE()][0][bltconFE()][bltpc])();\n        return;\n    }\n'
            '    constexpr int use = (CON0 >> 8) & 0xF;\n    constexpr int fill = (CON1 & 0x18) != 0;\n    constexpr bool desc = (CON1 & 2) != 0;\n    constexpr bool efe = (CON1 & 0x10) != 0;\n'
            '    switch (bltpc) {\n' + steps + '        default: (this->*copyBlitInstr[bltconUSE()][0][bltconFE()][bltpc])(); break;\n    }\n}\n\n}\n')


def adaptation_digest() -> str:
    """What the adapted tree depends on besides the pin: the replacements themselves and how the Blitter's shape header is made."""
    value = hashlib.sha256(b'amiga-vamiga-adaptation\0' + str(FORMAT).encode() + b'\0' + VAMIGA_REV.encode())
    for rel, old, new in REPLACEMENTS:
        value.update(b'\0' + rel.encode() + b'\0' + old.encode() + b'\0' + new.encode())
    value.update(b'\0' + BLITTER_SHAPE_HEADER.encode() + b'\0' + str(FORMAT).encode())
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
    (core / BLITTER_SHAPE_HEADER).write_text(blitter_shape_header(core), encoding='utf-8', newline='\n')
    ready.write_text(json.dumps({'revision': VAMIGA_REV, 'adaptation': digest, 'replacements': len(REPLACEMENTS)}) + '\n',
                     encoding='utf-8')
    return core
