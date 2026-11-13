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
] + [
    # Agnus and Denise, step 1 (hand optimisations at unchanged instants): the same events at the same instants, the same bytes in
    # every buffer after each function, fewer operations. tools/amiga_display_selftest.py --against compares a build with them
    # against one without, instruction by instruction and frame by frame.
    # Denise's draw routines: the slices of the shift registers and their expansion into the line buffer by table and by word.
    ('Components/Denise/Denise.cpp',
     'void\nDenise::updateShiftRegistersOdd()\n',
     '// Retro-Recomp modification (MPL-2.0, like this file): the per-16-pixel work of the draw routines by table. rrSpread gives, for\n'
     '// a byte of a shift register, one byte per pixel (left pixel first) holding that byte\'s bit; rrSlices ORs the planes first,\n'
     '// first + step, ... into the 16 slices extractSlices* make; rrExpand writes the slices into the line buffer as the loops of\n'
     '// drawOdd, drawEven and drawBoth do, keeping the bits `keep` of what is there. Same bytes, fewer operations.\n'
     'struct RrSpread {\n'
     '    u64 v[256];\n'
     '    constexpr RrSpread() : v() {\n'
     '        for (int b = 0; b < 256; b++) {\n'
     '            u64 x = 0;\n'
     '            for (int i = 0; i < 8; i++) x |= (u64)((b >> (7 - i)) & 1) << (8 * i);\n'
     '            v[b] = x;\n'
     '        }\n'
     '    }\n'
     '};\n'
     'static constexpr RrSpread rrSpread;\n'
     'static constexpr bool rrByTable = true;\n\n'
     'static inline void\n'
     'rrSlices(u8 slices[16], const u16 shiftReg[8], int first, int step)\n'
     '{\n'
     '    u64 left = 0, right = 0;\n'
     '    for (int p = first; p < 8; p += step) {\n'
     '        left |= rrSpread.v[shiftReg[p] >> 8] << p;\n'
     '        right |= rrSpread.v[shiftReg[p] & 0xFF] << p;\n'
     '    }\n'
     '    for (int i = 0; i < 8; i++) {\n'
     '        slices[i] = (u8)(left >> (8 * i));\n'
     '        slices[8 + i] = (u8)(right >> (8 * i));\n'
     '    }\n'
     '}\n\n'
     'template <Resolution mode, u8 keep> static inline void\n'
     'rrExpand(u8 *buffer, const u8 slices[16], u8 mask)\n'
     '{\n'
     '    for (isize i = 0; i < 16; i++) {\n'
     '        const u8 index = slices[i] & mask;\n'
     '        if constexpr (mode == Resolution::LORES) {\n'
     '            u32 v = index * 0x01010101u;\n'
     '            if constexpr (keep != 0) { u32 old; std::memcpy(&old, buffer, 4); v |= old & (keep * 0x01010101u); }\n'
     '            std::memcpy(buffer, &v, 4);\n'
     '            buffer += 4;\n'
     '        } else if constexpr (mode == Resolution::HIRES) {\n'
     '            u16 v = (u16)(index * 0x0101u);\n'
     '            if constexpr (keep != 0) { u16 old; std::memcpy(&old, buffer, 2); v = (u16)(v | (old & (keep * 0x0101u))); }\n'
     '            std::memcpy(buffer, &v, 2);\n'
     '            buffer += 2;\n'
     '        } else {\n'
     '            *buffer = keep != 0 ? (u8)((*buffer & keep) | index) : index;\n'
     '            buffer += 1;\n'
     '        }\n'
     '    }\n'
     '}\n\n'
     'void\nDenise::updateShiftRegistersOdd()\n'),
    ('Components/Denise/Denise.cpp',
     'Denise::extractSlices(u8 slices[16])\n{\n',
     'Denise::extractSlices(u8 slices[16])\n{\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): the same slices by table.\n'
     '    if (rrByTable) { rrSlices(slices, shiftReg, 0, 1); return; }\n'),
    ('Components/Denise/Denise.cpp',
     'Denise::extractSlicesOdd(u8 slices[16])\n{\n',
     'Denise::extractSlicesOdd(u8 slices[16])\n{\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): the same slices by table.\n'
     '    if (rrByTable) { rrSlices(slices, shiftReg, 0, 2); return; }\n'),
    ('Components/Denise/Denise.cpp',
     'Denise::extractSlicesEven(u8 slices[16])\n{\n',
     'Denise::extractSlicesEven(u8 slices[16])\n{\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): the same slices by table.\n'
     '    if (rrByTable) { rrSlices(slices, shiftReg, 1, 2); return; }\n'),
    ('Components/Denise/Denise.cpp',
     '    u8 slices[16];\n    extractSlicesOdd(slices);\n\n    for (isize i = 0; i < 16; i++) {\n',
     '    u8 slices[16];\n    extractSlicesOdd(slices);\n\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): the loop below, by word (it then runs no iteration).\n'
     '    if (rrByTable) rrExpand<mode, 0b10101010>(dBuffer + pixel, slices, (u8)mask);\n'
     '    for (isize i = 0; i < (rrByTable ? 0 : 16); i++) {\n'),
    ('Components/Denise/Denise.cpp',
     '    u8 slices[16];\n    extractSlicesEven(slices);\n\n    for (isize i = 0; i < 16; i++) {\n',
     '    u8 slices[16];\n    extractSlicesEven(slices);\n\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): the loop below, by word (it then runs no iteration).\n'
     '    if (rrByTable) rrExpand<mode, 0b01010101>(dBuffer + pixel, slices, (u8)mask);\n'
     '    for (isize i = 0; i < (rrByTable ? 0 : 16); i++) {\n'),
    ('Components/Denise/Denise.cpp',
     '    u8 slices[16];\n    extractSlices(slices);\n\n    for (isize i = 0; i < 16; i++) {\n',
     '    u8 slices[16];\n    extractSlices(slices);\n\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): the loop below, by word (it then runs no iteration).\n'
     '    if (rrByTable) rrExpand<mode, 0>(dBuffer + pixel, slices, (u8)mask);\n'
     '    for (isize i = 0; i < (rrByTable ? 0 : 16); i++) {\n'),
] + [
    # Both parities armed at the same offset: one pass of drawBoth writes the bytes the two passes leave, since
    # ((x & 0xAA) | odd) & 0x55 | even is odd | even (the odd bits are under 0x55, the even ones under 0xAA), its mask is the
    # union of the two, and it clears the eight shift registers the two passes clear. Otherwise the two passes, as before.
    ('Components/Denise/Denise.cpp',
     f'Denise::draw{name}Both()\n{{\n    draw{name}Odd();\n    draw{name}Even();\n}}\n',
     f'Denise::draw{name}Both()\n{{\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): one pass when both parities are armed at the same offset.\n'
     '    if (!isAGA() && armedOdd && armedEven && pixelOffsetOdd == pixelOffsetEven) {\n'
     '        updateShiftRegistersOdd();\n'
     '        updateShiftRegistersEven();\n'
     f'        drawBoth <Resolution::{mode}> (pixelOffsetOdd);\n'
     '        armedOdd = false;\n'
     '        armedEven = false;\n'
     '        return;\n'
     '    }\n'
     f'    draw{name}Odd();\n    draw{name}Even();\n}}\n')
    for name, mode in (('Lores', 'LORES'), ('Hires', 'HIRES'), ('Shres', 'SHRES'))
] + [
    # Dual playfield: translateDPF<prio> gives each pixel a pure function of its dBuffer byte and of the playfield state, so its own
    # loop runs once on the 256 bytes for a state and the line is looked up.
    ('Components/Denise/Denise.h',
     '    u16 zBuffer[BUF_CNT];\n',
     '    u16 zBuffer[BUF_CNT];\n\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): translateDPF\'s colour index and z value of each dBuffer byte for\n'
     '    // one playfield state (Denise.cpp, rrBuildDpf). Derived, rebuilt when the state changes; not part of a snapshot.\n'
     '    struct { bool valid = false; u64 key = 0; u8 m[256]; u16 z[256]; } rrDpf;\n'),
    ('Components/Denise/Denise.h',
     '    void translateDPF(Pixel from, Pixel to, PFState &state);\n',
     '    void translateDPF(Pixel from, Pixel to, PFState &state);\n'
     '    void rrBuildDpf(PFState &state, u64 key);   // Retro-Recomp modification (MPL-2.0, like this file)\n'),
    ('Components/Denise/Denise.cpp',
     'void\nDenise::translateDPF(Pixel from, Pixel to, PFState &state)\n{\n    if (state.prio) {\n'
     '        translateDPF <true> (from, to, state);\n    } else {\n        translateDPF <false> (from, to, state);\n    }\n}\n',
     'void\nDenise::translateDPF(Pixel from, Pixel to, PFState &state)\n{\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): the loop of translateDPF<prio> run once per state on the 256 bytes\n'
     '    // (rrBuildDpf), then looked up. The key holds everything that loop reads besides the byte.\n'
     '    const u64 key = (u64)state.prio << 48 | (u64)state.zpf1 << 32 | (u64)state.zpf2 << 16 | (u64)state.colxor << 8 |\n'
     '                    (u64)(u8)colorOffset(pf2of());\n'
     '    if (!rrDpf.valid || rrDpf.key != key) rrBuildDpf(state, key);\n'
     '    for (Pixel i = from; i < to; i++) {\n'
     '        const u8 s = dBuffer[i];\n'
     '        mBuffer[i] = rrDpf.m[s];\n'
     '        zBuffer[i] = rrDpf.z[s];\n'
     '    }\n'
     '}\n\n'
     '// Retro-Recomp modification (MPL-2.0, like this file): vAmiga\'s own loop on the bytes 0 to 255, the buffers it uses kept as they were.\n'
     'void\nDenise::rrBuildDpf(PFState &state, u64 key)\n{\n'
     '    u8 d[256], m[256];\n'
     '    u16 z[256];\n'
     '    std::memcpy(d, dBuffer, sizeof d);\n'
     '    std::memcpy(m, mBuffer, sizeof m);\n'
     '    std::memcpy(z, zBuffer, sizeof z);\n'
     '    for (isize i = 0; i < 256; i++) dBuffer[i] = (u8)i;\n'
     '    if (state.prio) {\n        translateDPF <true> (0, 256, state);\n    } else {\n        translateDPF <false> (0, 256, state);\n    }\n'
     '    std::memcpy(rrDpf.m, mBuffer, sizeof rrDpf.m);\n'
     '    std::memcpy(rrDpf.z, zBuffer, sizeof rrDpf.z);\n'
     '    std::memcpy(dBuffer, d, sizeof d);\n'
     '    std::memcpy(mBuffer, m, sizeof m);\n'
     '    std::memcpy(zBuffer, z, sizeof z);\n'
     '    rrDpf.key = key;\n'
     '    rrDpf.valid = true;\n'
     '}\n'),
    # The palette pass: eight entries at a time where none of them is border.
    ('Components/Denise/PixelEngine.cpp',
     '    for (Pixel i = from; i < to; i++)\n        dst[i] = u32(bbuf[i] == BORDER_NONE ? palette[mbuf[i]] : borderPalette[bbuf[i]]);\n',
     '    // Retro-Recomp modification (MPL-2.0, like this file): eight entries at a time where none is border (BORDER_NONE is 0).\n'
     '    static_assert(BORDER_NONE == 0);\n'
     '    Pixel i = from;\n'
     '    for (; i + 8 <= to; i += 8) {\n'
     '        u64 border;\n'
     '        std::memcpy(&border, bbuf + i, 8);\n'
     '        if (border == 0) {\n'
     '            for (isize k = 0; k < 8; k++) dst[i + k] = u32(palette[mbuf[i + k]]);\n'
     '        } else {\n'
     '            for (isize k = 0; k < 8; k++) dst[i + k] = u32(bbuf[i + k] == BORDER_NONE ? palette[mbuf[i + k]] : borderPalette[bbuf[i + k]]);\n'
     '        }\n'
     '    }\n'
     '    for (; i < to; i++)\n        dst[i] = u32(bbuf[i] == BORDER_NONE ? palette[mbuf[i]] : borderPalette[bbuf[i]]);\n'),
    # Agnus::execute, called by Moira::sync at every colour clock: defined in the header so that it can be inlined.
    ('Components/Agnus/Agnus.h',
     '    // Executes Agnus for a single cycle\n    void execute();\n\n    // Executes Agnus for a certain amount of cycles\n    void execute(DMACycle cycles);\n',
     '    // Executes Agnus for a single cycle\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): defined here, the same statements as in Agnus.cpp before, so that\n'
     '    // Moira::sync can inline them.\n'
     '    void execute() {\n'
     '        clock += DMA_CYCLES(1);\n'
     '        pos.h += 1;\n'
     '        if (nextTrigger <= clock) executeUntil(clock);\n'
     '    }\n\n'
     '    // Executes Agnus for a certain amount of cycles\n'
     '    void execute(DMACycle cycles) { for (DMACycle i = 0; i < cycles; i++) execute(); }\n'),
    ('Components/Agnus/Agnus.cpp',
     'void\nAgnus::execute()\n{\n    // Advance the internal clock and the horizontal counter\n    clock += DMA_CYCLES(1);\n    pos.h += 1;\n\n'
     '    // Process pending events\n    if (nextTrigger <= clock) executeUntil(clock);\n}\n\nvoid\nAgnus::execute(DMACycle cycles)\n{\n'
     '    for (DMACycle i = 0; i < cycles; i++) execute();\n}\n',
     '// Retro-Recomp modification (MPL-2.0, like this file): Agnus::execute() and execute(DMACycle) are defined in Agnus.h.\n'),
] + [
    # Agnus and Denise, step 2: the bitplane slots of a line taken in a batch. At the start of a line whose plan passes the guard,
    # its bitplane DMA slots are marked taken in busOwner (as vAmiga's own events mark them, before anyone else in their colour
    # clock) and are not scheduled. They run in their own order, at the beam position of their slot, whenever something could
    # observe them: a custom register access, a chip RAM write into a pending fetch, a read of the floating bus, the start of a
    # register-change event (HSYNC and EOL among them). A new plan for the line (computeBplEventTable) or a fetch leaving chip
    # RAM gives the rest of the line back to vAmiga's events. Line 0, where a host frame ends, always runs on vAmiga's events.
    # The data bus keeps the clock of its last write, so that a fetch run late never covers a later value.
    ('Components/Memory/Memory.h',
     '    // The last value on the data bus\n    u16 dataBus;\n',
     '    // The last value on the data bus\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): with the colour clock of its last write (`clock` points to Agnus\'s).\n'
     '    // A bitplane fetch of a batched line runs with `deferred` set to its own clock and leaves the bus to a later write.\n'
     '    struct RrDataBus {\n'
     '        static constexpr i64 NEVER = -0x7FFFFFFFFFFFFFFFLL - 1;\n'
     '        static inline const i64 noClock = 0;\n'
     '        u16 v = 0;\n'
     '        i64 at = NEVER;\n'
     '        i64 deferred = NEVER;\n'
     '        const i64 *clock = &noClock;\n'
     '        RrDataBus &operator=(u16 value) {\n'
     '            if (deferred != NEVER) {\n'
     '                if (deferred <= at) return *this;\n'
     '                v = value;\n'
     '                at = deferred;\n'
     '                return *this;\n'
     '            }\n'
     '            v = value;\n'
     '            at = *clock;\n'
     '            return *this;\n'
     '        }\n'
     '        RrDataBus &operator=(const RrDataBus &other) { v = other.v; at = other.at; return *this; }\n'
     '        operator u16() const { return v; }\n'
     '    };\n'
     '    RrDataBus dataBus;\n'),
    ('Components/Memory/Memory.h',
     '        << agnusMemSrc\n        << dataBus;\n',
     '        << agnusMemSrc\n        << dataBus.v;\n\n'
     '        // Retro-Recomp modification (MPL-2.0, like this file): a saved or loaded bus has no write still to come.\n'
     '        dataBus.at = RrDataBus::NEVER;\n'),
    ('Components/Memory/Memory.cpp', 'hex(dataBus)', 'hex(dataBus.v)'),
    ('Components/Memory/Memory.cpp',
     'Memory::Memory(Amiga& ref) : SubComponent(ref)\n{\n',
     'Memory::Memory(Amiga& ref) : SubComponent(ref)\n{\n'
     '    dataBus.clock = &agnus.clock;   // Retro-Recomp modification (MPL-2.0, like this file)\n\n'),
    ('Components/Memory/Memory.cpp',
     '    assert((addr & agnus.ptrMask) == addr);\n    dataBus = READ_CHIP_16(addr);\n    return dataBus;\n',
     '    assert((addr & agnus.ptrMask) == addr);\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): the word read, whether or not it stays on the bus.\n'
     '    const u16 rrValue = READ_CHIP_16(addr);\n'
     '    dataBus = rrValue;\n'
     '    return rrValue;\n'),
] + [
    # Chip RAM writes: the pending fetches of the write's address run first. Every writer: the CPU (8, 16, 32 bits), Agnus's DMA
    # (Blitter and disk) and the host's patch.
    ('Components/Memory/Memory.cpp', old,
     old.replace(write, '    agnus.rrBplWrite(addr);   // Retro-Recomp modification (MPL-2.0, like this file)\n' + write))
    for old, write in (('    agnus.busData[agnus.pos.h] = dataBus;\n\n    WRITE_CHIP_8(addr, value);\n', '    WRITE_CHIP_8(addr, value);\n'),
                       ('    agnus.busData[agnus.pos.h] = dataBus;\n\n    WRITE_CHIP_16(addr, value);\n', '    WRITE_CHIP_16(addr, value);\n'),
                       ('    WRITE_CHIP_32(addr, value);\n', '    WRITE_CHIP_32(addr, value);\n'),
                       ('    dataBus = value;\n    WRITE_CHIP_16(addr, value);\n', '    WRITE_CHIP_16(addr, value);\n'),
                       ('    ASSERT_CHIP_ADDR(addr);\n    WRITE_CHIP_8(addr, value);\n', '    WRITE_CHIP_8(addr, value);\n'))
] + [
    # Custom register accesses and the readers of the floating bus: the pending slots up to this colour clock run first.
    ('Components/Memory/Memory.cpp', head,
     head + '    agnus.rrBplSync();   // Retro-Recomp modification (MPL-2.0, like this file)\n')
    for head in ('Memory::peekCustom16(u32 addr)\n{\n', 'Memory::pokeCustom16(u32 addr, u16 value)\n{\n', 'Memory::peekRTC8(u32 addr) const\n{\n',
                 'Memory::peek8 <Accessor::CPU, MemSrc::NONE> (u32 addr)\n{\n', 'Memory::peek16 <Accessor::CPU, MemSrc::NONE> (u32 addr)\n{\n')
] + [
    ('Components/Agnus/Agnus.h',
     '    u16 busData[HPOS_CNT] = { };\n',
     '    u16 busData[HPOS_CNT] = { };\n\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): the bitplane slots of a line taken in a batch (AgnusEvents.cpp,\n'
     '    // rrBplLineStart). Derived state of the current line, never part of a snapshot: line 0 is never batched.\n'
     '    static inline bool rrBplBatching = true;   // false: every line on vAmiga\'s events\n'
     '    static inline int rrSaveFault = 0;          // 1: a batched line\'s slots left out of a snapshot (the display self-test)\n'
     '    bool rrLazy = false;                        // a batched line still has slots to run\n'
     '    isize rrNext = 0;                           // table position of the next slot to run\n'
     '    u8 rrRemain[8] = { };                       // fetches still to run per plane\n'
     '    u32 rrLo = 0, rrHi = 0;                     // chip RAM offsets those fetches read (a superset)\n'
     '    u32 rrChipMask = 0;\n'
     '    u64 rrLines[3] = { };                       // lines batched, lines on vAmiga\'s events, batched lines given back midway\n'
     '    u64 rrWords[2] = { };                       // bitplane words fetched in a batch, on vAmiga\'s events\n'
     '    void rrBplLineStart();\n'
     '    void rrBplCatchUp(isize to);\n'
     '    bool rrBplRangeOk();\n'
     '    void rrBplMaterialise(bool reschedule);\n'
     '    void rrBplDo(EventID id);\n'
     '    void rrBplSync() { if (rrLazy && rrNext <= pos.h) rrBplCatchUp(pos.h); }\n'
     '    void rrBplWrite(u32 addr) {\n'
     '        if (rrLazy) {\n'
     '            const u32 offset = addr & rrChipMask;\n'
     '            if (offset < rrHi && offset + 4 > rrLo) rrBplCatchUp(pos.h);\n'
     '        }\n'
     '    }\n'),
    ('Components/Agnus/Agnus.cpp',
     '    // Schedule the first BPL and DAS events\n    scheduleFirstBplEvent();\n    scheduleFirstDasEvent();\n',
     '    // Schedule the first BPL and DAS events\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): the line\'s bitplane slots in a batch when its plan allows it.\n'
     '    rrBplLineStart();\n    scheduleFirstDasEvent();\n'),
    ('Components/Agnus/Agnus.cpp',
     '    diskController.scheduleFirstDiskEvent();\n    scheduleFirstBplEvent();\n',
     '    diskController.scheduleFirstDiskEvent();\n'
     '    rrLazy = false;   // Retro-Recomp modification (MPL-2.0, like this file)\n'
     '    scheduleFirstBplEvent();\n'),
    ('Components/Agnus/AgnusEvents.cpp',
     'Agnus::serviceREGEvent(Cycle until)\n{\n',
     'Agnus::serviceREGEvent(Cycle until)\n{\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): the batched slots before this colour clock run first (a register\n'
     '    // change, HSYNC and EOL come before the bitplane slot of their own clock).\n'
     '    if (rrLazy && rrNext < pos.h) rrBplCatchUp(pos.h - 1);\n\n'),
    ('Components/Agnus/AgnusEvents.cpp',
     '    if (syncEvent & EVFL::PROBE) { logicAnalyzer.recordSignals(); }\n\n    scheduleNextREGEvent();\n}\n',
     '    if (syncEvent & EVFL::PROBE) { logicAnalyzer.recordSignals(); }\n\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): a pointer change may move the pending fetches out of chip RAM.\n'
     '    if (rrLazy && !rrBplRangeOk()) rrBplMaterialise(true);\n\n'
     '    scheduleNextREGEvent();\n}\n'),
    ('Components/Agnus/AgnusEvents.cpp',
     'void\nAgnus::serviceBPLEvent(EventID id)\n{\n',
     '// Retro-Recomp modification (MPL-2.0, like this file): the work of a bitplane slot (vAmiga\'s serviceBPLEvent without its last\n'
     '// line), for its event and for the batch.\n'
     'void\nAgnus::rrBplDo(EventID id)\n{\n'),
    ('Components/Agnus/AgnusEvents.cpp',
     '    // Schedule next event\n    scheduleNextBplEvent();\n}\n',
     '}\n\n'
     'void\nAgnus::serviceBPLEvent(EventID id)\n{\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): a batched line\'s earlier slots run first (the event at the end of\n'
     '    // the line, which vAmiga runs on NTSC long lines, comes after them).\n'
     '    if (rrLazy && rrNext < pos.h) rrBplCatchUp(pos.h - 1);\n'
     '    if (isize(id) >> 2) rrWords[1]++;\n'
     '    rrBplDo(id);\n\n'
     '    // Schedule next event\n    scheduleNextBplEvent();\n}\n\n'
     '// Retro-Recomp modification (MPL-2.0, like this file): a line\'s bitplane slots in a batch (Agnus.h). The guard: no AGA, not\n'
     '// line 0, every bitplane DMA slot in $18-$E1 (away from the refresh slots), no super-hires fetch, each plane\'s modulo on its\n'
     '// last fetch, every fetch of the line in chip RAM. Else the line runs on vAmiga\'s events, as before.\n'
     'void\nAgnus::rrBplLineStart()\n{\n'
     '    rrLazy = false;\n'
     '    const isize first = sequencer.bplEvent[0] ? 0 : sequencer.nextBplEvent[0];\n'
     '    u8 count[8] = { };\n'
     '    bool closed[8] = { };\n'
     '    bool fits = rrBplBatching && !isAGA() && pos.v != 0;\n'
     '    for (isize h = first; fits && h < HPOS_MAX; h = sequencer.nextBplEvent[h]) {\n'
     '        const isize k = isize(sequencer.bplEvent[h]) >> 2;\n'
     '        if (k == 0) continue;\n'
     '        const isize plane = ((k - 1) & 15) >> 1;\n'
     '        if (h < 0x18 || h > 0xE1 || ((k - 1) >> 4) == 2 || closed[plane]) { fits = false; break; }\n'
     '        if ((k - 1) & 1) closed[plane] = true;\n'
     '        count[plane]++;\n'
     '    }\n'
     '    if (fits) {\n'
     '        for (isize p = 0; p < 8; p++) rrRemain[p] = count[p];\n'
     '        rrChipMask = mem.chipMask;\n'
     '        fits = rrBplRangeOk();\n'
     '    }\n'
     '    if (!fits) {\n'
     '        rrLines[1]++;\n'
     '        scheduleFirstBplEvent();\n'
     '        return;\n'
     '    }\n'
     '    for (isize h = first; h < HPOS_MAX; h = sequencer.nextBplEvent[h]) {\n'
     '        const isize k = isize(sequencer.bplEvent[h]) >> 2;\n'
     '        if (k) busOwner[h] = BusOwner(BUS_BPL1 + (((k - 1) & 15) >> 1));\n'
     '    }\n'
     '    rrNext = first;\n'
     '    rrLazy = first < HPOS_MAX;\n'
     '    rrLines[0]++;\n'
     '    // The slot holds what vAmiga\'s chain of events leaves in it at the end of the line.\n'
     '    scheduleRel<SLOT_BPL>(DMA_CYCLES(HPOS_MAX - pos.h), sequencer.bplEvent[HPOS_MAX]);\n'
     '}\n\n'
     '// The pending slots up to table position `to`, in order, each at the beam position and with the bus clock of its own slot.\n'
     'void\nAgnus::rrBplCatchUp(isize to)\n{\n'
     '    const isize now = pos.h;\n'
     '    const Cycle real = clock;\n'
     '    while (rrNext <= to && rrNext < HPOS_MAX) {\n'
     '        const isize at = rrNext;\n'
     '        const EventID event = sequencer.bplEvent[at];\n'
     '        const isize k = isize(event) >> 2;\n'
     '        pos.h = at;\n'
     '        mem.dataBus.deferred = real - DMA_CYCLES(now - at);\n'
     '        rrBplDo(event);\n'
     '        if (k) {\n'
     '            rrRemain[((k - 1) & 15) >> 1]--;\n'
     '            rrWords[0]++;\n'
     '        }\n'
     '        rrNext = sequencer.nextBplEvent[at];\n'
     '    }\n'
     '    mem.dataBus.deferred = Memory::RrDataBus::NEVER;\n'
     '    pos.h = now;\n'
     '    if (rrNext >= HPOS_MAX) rrLazy = false;\n'
     '}\n\n'
     '// Whether the fetches still to run all read chip RAM; sets the offsets they cover (all of chip RAM when they wrap).\n'
     'bool\nAgnus::rrBplRangeOk()\n{\n'
     '    u32 lo = 0xFFFFFFFF, hi = 0;\n'
     '    bool whole = false;\n'
     '    for (isize p = 0; p < 8; p++) {\n'
     '        if (!rrRemain[p]) continue;\n'
     '        const u32 start = bplpt[p] & ptrMask;\n'
     '        const u32 size = 2 * u32(rrRemain[p]);\n'
     '        if (start + size - 1 > ptrMask) return false;\n'
     '        for (u32 b = start >> 16; b <= (start + size - 1) >> 16; b++) {\n'
     '            if (mem.agnusMemSrc[b] != MemSrc::CHIP) return false;\n'
     '        }\n'
     '        const u32 from = start & rrChipMask;\n'
     '        if (u64(from) + size > u64(rrChipMask) + 1) whole = true;\n'
     '        lo = std::min(lo, from);\n'
     '        hi = std::max(hi, from + size);\n'
     '    }\n'
     '    rrLo = whole ? 0 : lo;\n'
     '    rrHi = whole ? 0xFFFFFFFF : hi;\n'
     '    return true;\n'
     '}\n\n'
     '// The rest of a batched line back to vAmiga\'s events. The slots that ran stay; the marks of the others are removed. The\n'
     '// caller ran the slots its own colour clock has already seen. computeBplEventTable schedules the slot itself.\n'
     'void\nAgnus::rrBplMaterialise(bool reschedule)\n{\n'
     '    if (!rrLazy) return;\n'
     '    for (isize h = rrNext; h < HPOS_MAX; h = sequencer.nextBplEvent[h]) {\n'
     '        if (isize(sequencer.bplEvent[h]) >> 2) busOwner[h] = BusOwner::NONE;\n'
     '    }\n'
     '    rrLazy = false;\n'
     '    rrLines[2]++;\n'
     '    if (reschedule) scheduleBplEventForCycle(pos.h);\n'
     '}\n'),
] + [
    # Agnus and Denise, step 3: a quiet line's pass in one loop. On a line with no sprite, no BPLCON change, no HAM and no
    # super-hires, the colour index of every line-buffer byte is a pure function of the byte and of the line's start state
    # (translate's own loop gives it on the 256 bytes, kept in a table), so the texture row is written in one pass instead of
    # translate, then colorize. Colour changes inside the line are applied between chunks as colorize applies them. Other lines,
    # and the last visible line (the VBLANK branch after it reads the buffers translate leaves), take vAmiga's line pass.
    ('Components/Denise/Denise.h',
     '    struct { bool valid = false; u64 key = 0; u8 m[256]; u16 z[256]; } rrDpf;\n',
     '    struct { bool valid = false; u64 key = 0; u8 m[256]; u16 z[256]; } rrDpf;\n\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): a quiet line\'s pass in one loop (Denise.cpp, rrQuietLine). rrMap is\n'
     '    // translate\'s colour index of each dBuffer byte for the line\'s start state; derived, never part of a snapshot.\n'
     '    struct { bool valid = false; u64 key = 0; u8 m[256]; } rrMap;\n'
     '    static inline bool rrQuiet = true;           // false: every line on vAmiga\'s line pass\n'
     '    u64 rrQuietLines[2] = { };                   // visible lines in one pass, on vAmiga\'s pass\n'
     '    bool rrQuietLine(isize vpos);\n'
     '    void rrQuietPass();\n'),
    ('Components/Denise/Denise.h',
     '    void rrBuildDpf(PFState &state, u64 key);   // Retro-Recomp modification (MPL-2.0, like this file)\n',
     '    void rrBuildDpf(PFState &state, u64 key);   // Retro-Recomp modification (MPL-2.0, like this file)\n'
     '    void rrBuildMap(PFState &state, bool dual, u64 key);   // Retro-Recomp modification (MPL-2.0, like this file)\n'),
    ('Components/Denise/Denise.cpp',
     '        // Translate bitplane data to color register indices\n        translate();\n\n        // Draw sprites\n        drawSprites();\n\n'
     '        // Perform playfield-playfield collision check (if enabled)\n        if (config.clxPlfPlf) checkP2PCollisions();\n\n'
     '        // Synthesize RGBA values and write the result into the frame buffer\n        pixelEngine.colorize(vpos);\n',
     '        // Retro-Recomp modification (MPL-2.0, like this file): a quiet line in one pass (rrQuietLine), else vAmiga\'s pass.\n'
     '        if (rrQuietLine(vpos)) {\n'
     '            rrQuietPass();\n'
     '            if (config.clxPlfPlf) checkP2PCollisions();\n'
     '            pixelEngine.rrColorize(vpos, dBuffer, rrMap.m);\n'
     '            rrQuietLines[0]++;\n'
     '        } else {\n'
     '        rrQuietLines[1]++;\n\n'
     '        // Translate bitplane data to color register indices\n        translate();\n\n        // Draw sprites\n        drawSprites();\n\n'
     '        // Perform playfield-playfield collision check (if enabled)\n        if (config.clxPlfPlf) checkP2PCollisions();\n\n'
     '        // Synthesize RGBA values and write the result into the frame buffer\n        pixelEngine.colorize(vpos);\n'
     '        }\n'),
    ('Components/Denise/Denise.cpp',
     'void\nDenise::translateSPF(Pixel from, Pixel to, PFState &state)\n',
     '// Retro-Recomp modification (MPL-2.0, like this file): the guard of a quiet line. Nothing of translate, drawSprites and the\n'
     '// first part of colorize may depend on more than each byte and the line\'s start state: no sprite armed or recorded in the line,\n'
     '// no BPLCON change (conChanges), no BPLCON0 or BPLCON2 change for the pixel engine, no HAM, no super-hires, no border sprites,\n'
     '// no hidden bitplanes or X-ray layers, not AGA, and the next line visible (the VBLANK branch reads the buffers translate leaves).\n'
     'bool\nDenise::rrQuietLine(isize vpos)\n{\n'
     '    if (!rrQuiet || isAGA() || wasArmed || config.hiddenBitplanes || borderSprites()) return false;\n'
     '    if (!conChanges.isEmpty()) return false;\n'
     '    for (isize p = 0; p < 4; p++) if (!sprChanges[p].isEmpty()) return false;\n'
     '    if (agnus.xray.getConfig().mode == XRayMode::XRAY_LAYERS) return false;\n'
     '    if (hamMode(initialBplcon0) || pixelEngine.shresModeEcs() || pixelEngine.hamMode6() || pixelEngine.hamMode8()) return false;\n'
     '    if (vpos + 1 > VPOS_MAX || agnus.inVBlankArea(vpos + 1)) return false;\n'
     '    for (isize i = 0, end = pixelEngine.colChanges.end(); i < end; i++) {\n'
     '        const Reg reg = pixelEngine.colChanges.elements[i].reg;\n'
     '        if (reg == Reg::BPLCON0 || reg == Reg::BPLCON2) return false;\n'
     '    }\n'
     '    return true;\n'
     '}\n\n'
     '// The line\'s start state as translate takes it; the table of colour indices is rebuilt when that state changes.\n'
     'void\nDenise::rrQuietPass()\n{\n'
     '    PFState state;\n'
     '    state.zpf1 = zPF1(initialBplcon2);\n'
     '    state.zpf2 = zPF2(initialBplcon2);\n'
     '    state.prio = pf2pri(initialBplcon2);\n'
     '    state.ham = hamMode(initialBplcon0);\n'
     '    state.colxor = bplam(initialBplcon4);\n'
     '    const bool dual = dbplf(initialBplcon0);\n'
     '    const u64 key = (u64)dual << 56 | (u64)state.prio << 48 | (u64)state.zpf1 << 32 | (u64)state.zpf2 << 16 | (u64)state.colxor << 8 |\n'
     '                    (u64)(dual ? (u8)colorOffset(pf2of()) : 0);\n'
     '    if (!rrMap.valid || rrMap.key != key) rrBuildMap(state, dual, key);\n'
     '    // What translate leaves in its (empty) change history: its end-of-line entry, written and cleared (the entries are saved).\n'
     '    conChanges.insert(BUF_CNT, RegChange { .reg = Reg(0), .value = 0 });\n'
     '    conChanges.clear();\n'
     '}\n\n'
     '// translate\'s own loops on the bytes 0 to 255, the buffers they use kept as they were.\n'
     'void\nDenise::rrBuildMap(PFState &state, bool dual, u64 key)\n{\n'
     '    u8 d[256], m[256];\n'
     '    u16 z[256];\n'
     '    std::memcpy(d, dBuffer, sizeof d);\n'
     '    std::memcpy(m, mBuffer, sizeof m);\n'
     '    std::memcpy(z, zBuffer, sizeof z);\n'
     '    for (isize i = 0; i < 256; i++) dBuffer[i] = (u8)i;\n'
     '    if (dual) translateDPF(0, 256, state); else translateSPF(0, 256, state);\n'
     '    std::memcpy(rrMap.m, mBuffer, sizeof rrMap.m);\n'
     '    std::memcpy(dBuffer, d, sizeof d);\n'
     '    std::memcpy(mBuffer, m, sizeof m);\n'
     '    std::memcpy(zBuffer, z, sizeof z);\n'
     '    rrMap.key = key;\n'
     '    rrMap.valid = true;\n'
     '}\n\n'
     'void\nDenise::translateSPF(Pixel from, Pixel to, PFState &state)\n'),
    ('Components/Denise/PixelEngine.h',
     '    void colorize(isize line);\n',
     '    void colorize(isize line);\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): colorize of a quiet line, the colour index of each pixel read through\n'
     '    // the line\'s table from the line buffer (Denise.cpp, rrQuietLine).\n'
     '    void rrColorize(isize line, const u8 *dbuf, const u8 *map);\n'
     '    static inline int rrColourFault = 0;         // a planted fault for the self-test (1: a one-colour border chunk one bit off,\n'
     '                                                 // 2: a hires cell\'s second entry one bit off, 3: cells without the pair check)\n'
     '    static inline bool rrCells = true;           // false: one lookup per entry inside the display window\n'
     '    static inline u64 rrCellsRefused = 0;        // chunks inside the window whose pairs differ: one lookup per entry\n'
     '    static inline u64 rrCellsBroken = 0;         // RR_AMIGA_SHADOW only: cells written from a Texel whose halves differ (stays 0)\n'),
    ('Components/Denise/PixelEngine.cpp',
     'void\nPixelEngine::colorize(u32 *dst, Pixel from, Pixel to)\n',
     '// Retro-Recomp modification (MPL-2.0, like this file): colorize(line) of a quiet line. No sprite pixel exists on such a line, so\n'
     '// removing the border over sprites has nothing to do; the chunks between colour changes and the HBLANK wipe are colorize\'s.\n'
     'void\nPixelEngine::rrColorize(isize line, const u8 *dbuf, const u8 *map)\n{\n'
     '    auto *dst = (u32 *)workingPtr(line);\n'
     '    auto *bbuf = denise.bBuffer;\n'
     '    Pixel pixel = 0;\n'
     '    const Texel fault1 = rrColourFault == 1 ? TEXEL(0x100u) : 0;\n'
     '    const Texel fault2 = rrColourFault == 2 ? Texel(0x100u) << 32 : 0;\n'
     '    const u64 pairs = rrColourFault == 3 ? 0 : 0x00FF00FF00FF00FFull;\n'
     '    colChanges.insert(Denise::PIXEL_CNT, RegChange { .reg = Reg(0), .value = 0 } );\n'
     '    for (isize c = 0, end = colChanges.end(); c < end; c++) {\n'
     '        const Pixel to = (Pixel)colChanges.keys[c];\n'
     '        Pixel i = pixel;\n'
     '        // Whole hires cells. In lores and hires a pixel fills two or four entries from an even position (a draw starts at 8 h plus\n'
     '        // a scroll of 0 or 4), so entries 2k and 2k + 1 hold the same index and one lookup writes its Texel (the colour twice) over\n'
     '        // both. Super-hires draws do not (an ECS Agnus takes BPLCON0\'s SHRES bit while an OCS Denise\'s shresModeEcs() stays\n'
     '        // false, so such a line can be quiet), nor can a resolution change across the line\'s start or a state loaded mid-line be\n'
     '        // ruled out: each chunk checks its four pairs first, and one that fails keeps one lookup per entry (counted).\n'
     '        const bool cells = rrCells && !(i & 1);\n'
     '        for (; i + 8 <= to; i += 8) {\n'
     '            u64 border;\n'
     '            std::memcpy(&border, bbuf + i, 8);\n'
     '            if (border == 0) {\n'
     '                u64 d;\n'
     '                std::memcpy(&d, dbuf + i, 8);\n'
     '                if (cells && ((d ^ (d >> 8)) & pairs) == 0) {\n'
     '                    for (isize k = 0; k < 8; k += 2) {\n'
     '                        const Texel t = palette[map[dbuf[i + k]]];\n'
     '#ifdef RR_AMIGA_SHADOW\n'
     '                        if (u32(t) != u32(t >> 32)) rrCellsBroken++;\n'
     '#endif\n'
     '                        const Texel w = t ^ fault2;\n'
     '                        std::memcpy(dst + i + k, &w, 8);\n'
     '                    }\n'
     '                } else {\n'
     '                    rrCellsRefused += cells;\n'
     '                    for (isize k = 0; k < 8; k++) dst[i + k] = u32(palette[map[dbuf[i + k]]]);\n'
     '                }\n'
     '            } else if (border == (border & 0xFF) * 0x0101010101010101ull) {\n'
     '                // Eight entries of one border colour: a Texel holds that colour twice (TEXEL), so four stores write them.\n'
     '                const Texel t = borderPalette[bbuf[i]] ^ fault1;\n'
     '                for (isize k = 0; k < 8; k += 2) std::memcpy(dst + i + k, &t, 8);\n'
     '            } else {\n'
     '                for (isize k = 0; k < 8; k++) dst[i + k] = u32(bbuf[i + k] == BORDER_NONE ? palette[map[dbuf[i + k]]] : borderPalette[bbuf[i + k]]);\n'
     '            }\n'
     '        }\n'
     '        for (; i < to; i++) dst[i] = u32(bbuf[i] == BORDER_NONE ? palette[map[dbuf[i]]] : borderPalette[bbuf[i]]);\n'
     '        pixel = to;\n'
     '        applyRegisterChange(colChanges.elements[c]);\n'
     '    }\n'
     '    colChanges.clear();\n'
     '    auto start = agnus.pos.pixel(HBLANK_MIN);\n'
     '    auto stop  = agnus.pos.pixel(HBLANK_MAX);\n'
     '    auto hbcol = Texture::hblank;\n'
     '    for (pixel = start; pixel <= stop; pixel++) dst[pixel] = u32(hbcol);\n'
     '}\n\n'
     'void\nPixelEngine::colorize(u32 *dst, Pixel from, Pixel to)\n'),
] + [
    ('Components/Agnus/Sequencer/SequencerBpl.cpp',
     'Sequencer::computeBplEventTable(const SigRecorder &sr)\n{\n    // AGA takes the ECS path\n',
     'Sequencer::computeBplEventTable(const SigRecorder &sr)\n{\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): the table is about to change: a batched line goes back to events.\n'
     '    agnus.rrBplMaterialise(false);\n\n'
     '    // AGA takes the ECS path\n'),
] + [
    # Stage 7, in shadow: the hooks of our bus and DMA model (native/amiga_machine/amiga_bus.h, MIT). Compiled only with
    # RR_AMIGA_SHADOW (the display self-test, private reference players); without it every hook is preprocessed away and the Core
    # is the same code as before. The model computes beside vAmiga and changes nothing.
    ('Components/Agnus/Agnus.h',
     '#include "utl/wrappers.h"\n',
     '#include "utl/wrappers.h"\n'
     '#ifdef RR_AMIGA_SHADOW   // Retro-Recomp modification (MPL-2.0, like this file): stage 7\'s model in shadow\n'
     '#include "amiga_bus.h"\n'
     '#endif\n'),
    ('Components/Agnus/Agnus.h',
     'class Agnus : public SubComponent {\n',
     'class Agnus : public SubComponent {\n\n'
     '    friend struct RrBus;   // Retro-Recomp modification (MPL-2.0, like this file): stage 7\'s model in shadow reads Agnus\n'),
    ('Components/Agnus/Sequencer/Sequencer.h',
     'class Sequencer final : public SubComponent\n{\n',
     'class Sequencer final : public SubComponent\n{\n'
     '    friend struct RrBus;   // Retro-Recomp modification (MPL-2.0, like this file): stage 7\'s model in shadow reads the DDF registers\n\n'),
    ('Components/Agnus/Agnus.cpp',
     '    // Clear the bus usage table\n',
     '#ifdef RR_AMIGA_SHADOW   // Retro-Recomp modification (MPL-2.0, like this file): the line\'s owners against the model\'s table\n'
     '    RrBus::lineEnd(*this);\n'
     '#endif\n\n'
     '    // Clear the bus usage table\n'),
    ('Components/Agnus/Agnus.cpp',
     '    rrBplLineStart();\n    scheduleFirstDasEvent();\n',
     '    rrBplLineStart();\n    scheduleFirstDasEvent();\n'
     '#ifdef RR_AMIGA_SHADOW   // Retro-Recomp modification (MPL-2.0, like this file): the model\'s table of the line\n'
     '    RrBus::lineStart(*this);\n'
     '#endif\n'),
    ('Components/Agnus/Agnus.cpp',
     '    rrLazy = false;   // Retro-Recomp modification (MPL-2.0, like this file)\n',
     '    rrLazy = false;   // Retro-Recomp modification (MPL-2.0, like this file)\n'
     '#ifdef RR_AMIGA_SHADOW\n    RrBus::reset(*this);\n#endif\n'),
    ('Components/Agnus/Agnus.cpp',
     '    // Check if the bus is blocked\n    if (busOwner[pos.h] != BusOwner::NONE) {\n',
     '#ifdef RR_AMIGA_SHADOW   // Retro-Recomp modification (MPL-2.0, like this file): the model\'s prediction of this wait\n'
     '    RrBus::busWaitStart(*this);\n'
     '    long long rrDelay = 0;\n'
     '#endif\n\n'
     '    // Check if the bus is blocked\n    if (busOwner[pos.h] != BusOwner::NONE) {\n'),
    ('Components/Agnus/Agnus.cpp',
     '        cpu.addWaitStates(DMA_CYCLES(delay));\n    }\n\n    // Assign bus to the CPU\n',
     '        cpu.addWaitStates(DMA_CYCLES(delay));\n'
     '#ifdef RR_AMIGA_SHADOW\n        rrDelay = delay;\n#endif\n'
     '    }\n\n'
     '#ifdef RR_AMIGA_SHADOW   // Retro-Recomp modification (MPL-2.0, like this file)\n'
     '    RrBus::busWaitEnd(*this, rrDelay);\n'
     '#endif\n\n'
     '    // Assign bus to the CPU\n'),
    ('Components/Agnus/Agnus.cpp',
     '    // Sync with the E clock driving the CIA\n',
     '#ifdef RR_AMIGA_SHADOW   // Retro-Recomp modification (MPL-2.0, like this file)\n'
     '    RrBus::ciaWait(*this);\n'
     '#endif\n\n'
     '    // Sync with the E clock driving the CIA\n'),
    ('Components/Agnus/Agnus.cpp',
     'Agnus::executeUntil(Cycle cycle) {\n',
     'Agnus::executeUntil(Cycle cycle) {\n'
     '#ifdef RR_AMIGA_SHADOW   // Retro-Recomp modification (MPL-2.0, like this file): the events the model would meet\n'
     '    RrBus::events(*this, (long long)cycle);\n'
     '#endif\n'),
    ('Components/Agnus/AgnusRegs.cpp',
     '        // Rectify the currently scheduled DAS event\n        scheduleDasEventForCycle(pos.h);\n',
     '        // Rectify the currently scheduled DAS event\n        scheduleDasEventForCycle(pos.h);\n'
     '#ifdef RR_AMIGA_SHADOW   // Retro-Recomp modification (MPL-2.0, like this file): the model reads the line\'s new DAS slots\n'
     '        RrBus::dasChanged(*this);\n'
     '#endif\n'),
    ('Components/Agnus/Sequencer/SequencerBpl.cpp',
     '    agnus.isOCS() ? computeBplEventTable<false>(sr) : computeBplEventTable<true>(sr);\n',
     '    agnus.isOCS() ? computeBplEventTable<false>(sr) : computeBplEventTable<true>(sr);\n'
     '#ifdef RR_AMIGA_SHADOW   // Retro-Recomp modification (MPL-2.0, like this file): the model reads the new plan\n'
     '    RrBus::planChanged(agnus);\n'
     '#endif\n'),
] + [
    # Stage 7, checkpoint 3 (controls the machine): the idle disk controller caught up. While no drive is selected, its DMA is off,
    # DSKSYNC is not zero and the shift register already holds zero, a disk event only shifts zeros in, writes a zero byte into the
    # FIFO and advances the rotation delay: it cannot raise an interrupt or touch memory. Such events are taken off the scheduler:
    # one event is scheduled at the time of the last of them (never past the frame's end), and the others are run in order when it
    # comes or when something could see the controller first (its registers, the CIA-B port that selects a drive). Their times are
    # those vAmiga's own arithmetic gives. Agnus marks its event loop, so that a barrier inside it (a Copper or delayed write) runs
    # the events strictly before its colour clock, and a CPU access those of its own clock too, as vAmiga's order is.
    ('Components/Agnus/Agnus.h',
     '    void rrBplSync() { if (rrLazy && rrNext <= pos.h) rrBplCatchUp(pos.h); }\n',
     '    bool rrInEvents = false;                    // stage 7: inside executeUntil (derived, never saved)\n'
     '    bool rrFrameEnding = false;                 // stage 7: the host frame ends at the next instruction (vsyncHandler ran)\n'
     '    void rrBplSync() { if (rrLazy && rrNext <= pos.h) rrBplCatchUp(pos.h); }\n'),
    # No scope guard on rrInEvents: nothing the events run throws (vAmiga's StateChangeException is thrown by Amiga's run loop,
    # outside executeUntil; an option set from a register is a valid one), and a quick state's load clears it (rrAfterLoad).
    ('Components/Agnus/Agnus.cpp',
     'Agnus::executeUntil(Cycle cycle) {\n',
     'Agnus::executeUntil(Cycle cycle) {\n'
     '    rrInEvents = true;   // Retro-Recomp modification (MPL-2.0, like this file); no throw before it is cleared\n'),
    ('Components/Agnus/Agnus.cpp',
     '    nextTrigger = next;\n}\n',
     '    nextTrigger = next;\n'
     '    rrInEvents = false;   // Retro-Recomp modification (MPL-2.0, like this file)\n}\n'),
    # Stage 7, checkpoint 3b (controls the machine): the idle sprites' slots skipped. A sprite's DMA cycle does nothing on a line
    # where its DMA is off and that is not its stop line; both are known at the line's start (the DMA state is updated at $E1 of the
    # line before). Such a sprite's two slot events are left out of the line's schedule. A write to its SPRxPOS or SPRxCTL (always
    # applied by a register-change event, before the slot events of its colour clock) puts it back for the rest of the line. Line 0,
    # where the host frame ends, keeps every event.
    ('Components/Agnus/Agnus.h',
     '    bool rrFrameEnding = false;                 // stage 7: the host frame ends at the next instruction (vsyncHandler ran)\n',
     '    bool rrFrameEnding = false;                 // stage 7: the host frame ends at the next instruction (vsyncHandler ran)\n'
     '    u8 rrSprIdle = 0;                           // stage 7: sprites whose slot events this line leaves out (derived)\n'
     '    static inline bool rrSprSkip = true;        // false: every sprite slot event on the schedule\n'
     '    static inline int rrSprFault = 0;           // a planted fault (1: an armed sprite taken for idle), for the self-test\n'
     '    u64 rrSprSkipped = 0;                       // sprite slot events left out (lines ended)\n'
     '    u16 rrSprLeftMask = 0;                      // the line\'s sprite slots (S0_1 .. S7_2) its schedule passes over\n'
     '    void rrBeforeSave();\n'
     '    void rrAfterLoad();\n'
     '    void rrSprLineStart();\n'
     '    void rrSprWake(isize x);\n'
     '    isize rrSkipIdle(isize h);\n'),
    ('Components/Agnus/Agnus.cpp',
     '    rrBplLineStart();\n    scheduleFirstDasEvent();\n',
     '    rrBplLineStart();\n'
     '    rrSprLineStart();   // Retro-Recomp modification (MPL-2.0, like this file)\n'
     '    scheduleFirstDasEvent();\n'),
    ('Components/Agnus/Agnus.cpp',
     '    rrLazy = false;   // Retro-Recomp modification (MPL-2.0, like this file)\n',
     '    rrLazy = false;   // Retro-Recomp modification (MPL-2.0, like this file)\n'
     '    rrSprIdle = 0;\n'
     '    rrSprLeftMask = 0;\n'),
    ('Components/Agnus/AgnusEvents.cpp',
     '    u8 dmacycle = sequencer.nextDasEvent[0];\n    assert(dmacycle != 0);\n'
     '    scheduleRel<SLOT_DAS>(DMA_CYCLES(dmacycle), sequencer.dasEvent[dmacycle]);\n',
     '    u8 dmacycle = sequencer.nextDasEvent[0];\n    assert(dmacycle != 0);\n'
     '    dmacycle = u8(rrSkipIdle(dmacycle));   // Retro-Recomp modification (MPL-2.0, like this file)\n'
     '    scheduleRel<SLOT_DAS>(DMA_CYCLES(dmacycle), sequencer.dasEvent[dmacycle]);\n'),
    ('Components/Agnus/AgnusEvents.cpp',
     '    u8 next = sequencer.nextDasEvent[hpos];\n    assert(next >= 0 && next < HPOS_CNT);\n',
     '    u8 next = sequencer.nextDasEvent[hpos];\n    assert(next >= 0 && next < HPOS_CNT);\n'
     '    next = u8(rrSkipIdle(next));   // Retro-Recomp modification (MPL-2.0, like this file)\n'),
    ('Components/Agnus/AgnusEvents.cpp',
     '    if (sequencer.dasEvent[hpos] != EVENT_NONE) {\n'
     '        scheduleRel<SLOT_DAS>(DMA_CYCLES(hpos - pos.h), sequencer.dasEvent[hpos]);\n'
     '    } else {\n        scheduleNextDasEvent(hpos);\n    }\n}\n',
     '    // Retro-Recomp modification (MPL-2.0, like this file): an idle sprite\'s event is passed over. The sprite slots from hpos on\n'
     '    // are decided again (slot k of the mask is at $15 + 2k).\n'
     '    if (hpos <= 0x15) rrSprLeftMask = 0;\n'
     '    else if (hpos < 0x35) rrSprLeftMask &= u16((1 << ((hpos - 0x15 + 1) >> 1)) - 1);\n'
     '    if (sequencer.dasEvent[hpos] != EVENT_NONE && rrSkipIdle(hpos) == hpos) {\n'
     '        scheduleRel<SLOT_DAS>(DMA_CYCLES(hpos - pos.h), sequencer.dasEvent[hpos]);\n'
     '    } else {\n        scheduleNextDasEvent(hpos);\n    }\n}\n\n'
     '// Retro-Recomp modification (MPL-2.0, like this file): the idle sprites of the line (Agnus.h). Not on line 0, not on AGA.\n'
     'void\nAgnus::rrSprLineStart()\n{\n'
     '    for (u16 m = rrSprLeftMask; m; m &= u16(m - 1)) rrSprSkipped++;   // the line that ended: each slot passed over, once\n'
     '    rrSprLeftMask = 0;\n'
     '    rrSprIdle = 0;\n'
     '    if (!rrSprSkip || pos.v == 0 || isAGA()) return;\n'
     '    for (isize n = 0; n < 8; n++) {\n'
     '        if ((!sprDmaEnabled[n] || rrSprFault == 1) && pos.v != sprVStop[n]) rrSprIdle |= u8(1 << n);\n'
     '    }\n'
     '}\n\n'
     '// The first event at or after slot h that is not an idle sprite\'s.\n'
     'isize\nAgnus::rrSkipIdle(isize h)\n{\n'
     '    while (rrSprIdle) {\n'
     '        const EventID e = sequencer.dasEvent[h];\n'
     '        if (e < DAS_S0_1 || e > DAS_S7_2 || !(rrSprIdle & (1 << ((e - DAS_S0_1) >> 1)))) break;\n'
     '        rrSprLeftMask |= u16(1 << (e - DAS_S0_1));\n'
     '        h = sequencer.nextDasEvent[h];\n'
     '    }\n'
     '    return h;\n'
     '}\n\n'
     '// A write to the sprite\'s position or control (in a register-change event, before the slot events of this clock): its slots\n'
     '// are back for the rest of the line.\n'
     'void\nAgnus::rrSprWake(isize x)\n{\n'
     '    if (!(rrSprIdle & (1 << x))) return;\n'
     '    rrSprIdle &= u8(~(1 << x));\n'
     '    scheduleDasEventForCycle(pos.h);\n'
     '}\n\n'
     '// Before a snapshot (a quick state): the held-back disk events that are due run, the next one is scheduled. A frame cut short\n'
     '// after a batch started (VPOSW clearing LOF, BEAMCON0 from PAL to NTSC) can end with some, and a snapshot keeps none of them.\n'
     '// A batched line (never line 0, but one instruction can run past line 0 before a state is taken) is given back the same way:\n'
     '// the slots this colour clock has seen run (its own one included: Agnus::execute serves the events of the new clock), the\n'
     '// rest go back to vAmiga\'s events from the next slot on, which a snapshot keeps.\n'
     'void\nAgnus::rrBeforeSave()\n{\n'
     '    if (rrLazy && rrSaveFault != 1) {\n'
     '        rrBplSync();\n'
     '        if (rrLazy) {\n'
     '            rrBplMaterialise(false);\n'
     '            scheduleNextBplEvent(pos.h);\n'
     '        }\n'
     '    }\n'
     '    paula.diskController.rrBarrier();\n'
     '}\n\n'
     '// After a snapshot is loaded: stage 7\'s derived state belongs to the timeline left, and goes. The loaded schedule has every\n'
     '// event it needs (an idle sprite\'s slot that comes back only does nothing).\n'
     'void\nAgnus::rrAfterLoad()\n{\n'
     '    rrSprIdle = 0;\n'
     '    rrSprLeftMask = 0;\n'
     '    rrInEvents = false;\n'
     '    paula.diskController.rrForget();\n'
     '}\n'),
] + [
    ('Components/Agnus/AgnusRegs.cpp', head,
     head + '    rrSprWake(x);   // Retro-Recomp modification (MPL-2.0, like this file)\n\n')
    for head in ('Agnus::setSPRxPOS(u16 value)\n{\n', 'Agnus::setSPRxCTL(u16 value)\n{\n')
] + [
    ('Components/Agnus/Agnus.cpp',
     'Agnus::vsyncHandler()\n{\n',
     'Agnus::vsyncHandler()\n{\n'
     '    rrFrameEnding = true;   // Retro-Recomp modification (MPL-2.0, like this file): no disk event held back past this frame\n'),
    ('Components/Amiga.cpp',
     'Amiga::computeFrame()\n{\n',
     'Amiga::computeFrame()\n{\n'
     '    agnus.rrFrameEnding = false;   // Retro-Recomp modification (MPL-2.0, like this file)\n'),
    ('Components/Paula/DiskController/DiskController.h',
     '    double dskEventDelay = 0;\n',
     '    double dskEventDelay = 0;\n\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): the idle controller caught up (DiskControllerEvents.cpp). Derived\n'
     '    // state, never saved: no event is held back at a frame\'s end, where states are taken.\n'
     'public:\n'
     '    static inline bool rrLazyOn = true;         // false: every disk event on vAmiga\'s scheduler\n'
     '    static inline int rrFault = 0;              // a planted fault (1: one held-back event lost), for the self-test\n'
     '    u64 rrCounts[4] = { };                      // batches, batches run at their event, batches run at a barrier, events held back\n'
     '    void rrBarrier();\n'
     '    void rrForget() { rrLazy = false; rrLeft = 0; }   // after a snapshot\'s load (Agnus::rrAfterLoad)\n'
     '    void rrDebug(char *out, isize size) const;\n'
     'private:\n'
     '    bool rrLazy = false;\n'
     '    Cycle rrNext = 0;                           // the time of the next held-back event\n'
     '    isize rrLeft = 0;                           // held-back events before the scheduled one\n'
     '    bool rrIdle() const;\n'
     '    double rrDiskDelay();\n'
     '    Cycle rrAt(Cycle t) const;\n'
     '    void rrReplay(Cycle upTo, bool inclusive);\n'
     '    void rrEnter();\n'),
    ('Components/Paula/DiskController/DiskControllerEvents.cpp',
     'void\nDiskController::serviceDiskEvent()\n{        \n    // Receive next byte from the selected drive\n    transferByte();\n    \n'
     '    // Schedule next event\n    scheduleNextDiskEvent();\n}\n',
     'void\nDiskController::serviceDiskEvent()\n{\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): the held-back events before this one run first, in order.\n'
     '    if (rrLazy) {\n'
     '        rrReplay(agnus.clock, false);\n'
     '        rrLazy = false;\n'
     '        rrCounts[1]++;\n'
     '    }\n\n'
     '    // Receive next byte from the selected drive\n    transferByte();\n    \n'
     '    // Schedule next event\n    scheduleNextDiskEvent();\n\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file)\n'
     '    rrEnter();\n}\n\n'
     '// Retro-Recomp modification (MPL-2.0, like this file): the idle controller caught up (DiskController.h).\n'
     'bool\nDiskController::rrIdle() const\n{\n'
     '    return selected < 0 && state == DriveDmaState::OFF && dataReg == 0 && dsksync != 0 && !config.autoDskSync && !turboMode();\n'
     '}\n\n'
     '// Hold back the events after the one just scheduled, up to the frame\'s end (a lower bound of it) and at most 64.\n'
     'void\nDiskController::rrEnter()\n{\n'
     '    if (!rrLazyOn || agnus.rrFrameEnding || !rrIdle()) return;\n'
     '    const Cycle first = agnus.trigger[SLOT_DSK];\n'
     '    // The host frame ends at the first instruction after HSYNC of line 0 ($12): a lower bound of the distance to it.\n'
     '    const isize h = agnus.pos.h, v = agnus.pos.v;\n'
     '    const isize ahead = (v == 0 && h < 0x12) ? 0x12 - h : agnus.pos.hCnt() - h + (agnus.pos.vMax() - v) * 227 + 0x12;\n'
     '    const Cycle bound = agnus.clock + DMA_CYCLES(ahead - 1);\n'
     '    const double delay = rrDiskDelay();\n'
     '    double d = dskEventDelay;\n'
     '    Cycle t = first;\n'
     '    isize m = 1;\n'
     '    while (m < 64) {\n'
     '        d += delay;\n'
     '        const double rounded = round(d);\n'
     '        d -= rounded;\n'
     '        const Cycle next = rrAt(t) + Cycle(rounded);\n'
     '        if (rrAt(next) > bound) break;\n'
     '        t = next;\n'
     '        m++;\n'
     '    }\n'
     '    if (m < 2) return;\n'
     '    rrLazy = true;\n'
     '    rrNext = first;\n'
     '    rrLeft = m - 1 - (rrFault == 1 ? 1 : 0);\n'
     '    agnus.scheduleAbs<SLOT_DSK>(t, DSK_ROTATE);\n'
     '    rrCounts[0]++;\n'
     '    rrCounts[3] += u64(m - 1);\n'
     '}\n\n'
     '// An event triggered at t runs at the first colour clock of Agnus at or after t, and the next one is scheduled from there.\n'
     'Cycle\nDiskController::rrAt(Cycle t) const\n{\n'
     '    return t + (((agnus.clock - t) % DMA_CYCLES(1)) + DMA_CYCLES(1)) % DMA_CYCLES(1);\n'
     '}\n\n'
     '// The held-back events up to a colour clock, each as vAmiga runs it: the byte, then the delay to the next one.\n'
     'void\nDiskController::rrReplay(Cycle upTo, bool inclusive)\n{\n'
     '    while (rrLeft > 0 && (rrAt(rrNext) < upTo || (inclusive && rrAt(rrNext) == upTo))) {\n'
     '        transferByte();\n'
     '        dskEventDelay += rrDiskDelay();\n'
     '        const double rounded = round(dskEventDelay);\n'
     '        dskEventDelay -= rounded;\n'
     '        rrNext = rrAt(rrNext) + Cycle(rounded);\n'
     '        rrLeft--;\n'
     '    }\n'
     '}\n\n'
     '// The controller\'s state and its slot, for the self-test\'s diagnostics.\n'
     'void\nDiskController::rrDebug(char *out, isize size) const\n{\n'
     '    snprintf(out, size_t(size), "delay=%.17g incoming=%04x dataReg=%04x count=%d fifo=%llx fifoCount=%d sync=%lld counter=%ld "\n'
     '             "lazy=%d next=%lld left=%ld trigger=%lld sec=%lld nextTrigger=%lld", dskEventDelay, incoming, dataReg, dataRegCount,\n'
     '             (unsigned long long)fifo, fifoCount, (long long)syncCycle, (long)syncCounter, rrLazy, (long long)rrNext, (long)rrLeft,\n'
     '             (long long)agnus.trigger[SLOT_DSK], (long long)agnus.trigger[SLOT_SEC], (long long)agnus.nextTrigger);\n'
     '}\n\n'
     '// Something may see the controller (its registers, the drive select): the events before now run, the next one is scheduled.\n'
     'void\nDiskController::rrBarrier()\n{\n'
     '    if (!rrLazy) return;\n'
     '    rrReplay(agnus.clock, !agnus.rrInEvents);\n'
     '    rrLazy = false;\n'
     '    if (rrLeft > 0) agnus.scheduleAbs<SLOT_DSK>(rrNext, DSK_ROTATE);\n'
     '    rrLeft = 0;\n'
     '    rrCounts[2]++;\n'
     '}\n'),
    ('Components/Paula/DiskController/DiskControllerEvents.cpp',
     '    static constexpr double bytesPerTrack = 12668.0;\n\n    // How many revolutions per minute are we supposed to achieve?\n',
     '    // Retro-Recomp modification (MPL-2.0, like this file): the delay is computed in rrDiskDelay, the same statements.\n'
     '    const double delay = rrDiskDelay();\n'
     '    dskEventDelay += delay;\n'
     '    double rounded = round(dskEventDelay);\n'
     '    dskEventDelay -= rounded;\n\n'
     '    if (turboMode()) {\n'
     '        agnus.cancel<SLOT_DSK>();\n'
     '    } else {\n'
     '        agnus.scheduleRel<SLOT_DSK>(Cycle(rounded), DSK_ROTATE);\n'
     '    }\n'
     '}\n\n'
     'double\nDiskController::rrDiskDelay()\n{\n'
     '    static constexpr double bytesPerTrack = 12668.0;\n\n'
     '    // How many revolutions per minute are we supposed to achieve?\n'),
    ('Components/Paula/DiskController/DiskControllerEvents.cpp',
     '    dskEventDelay += delay;\n    double rounded = round(dskEventDelay);\n    dskEventDelay -= rounded;\n\n'
     '    if (turboMode()) {\n        agnus.cancel<SLOT_DSK>();\n    } else {\n'
     '        agnus.scheduleRel<SLOT_DSK>(Cycle(rounded), DSK_ROTATE);\n    }\n}\n\n}\n',
     '    return delay;\n}\n\n}\n'),
    ('Components/Paula/DiskController/DiskControllerEvents.cpp',
     '    dskEventDelay = 0.0;\n',
     '    dskEventDelay = 0.0;\n'
     '    rrLazy = false;   // Retro-Recomp modification (MPL-2.0, like this file)\n'
     '    rrLeft = 0;\n'),
] + [
    ('Components/Paula/DiskController/DiskControllerRegs.cpp', head,
     head + '    rrBarrier();   // Retro-Recomp modification (MPL-2.0, like this file): the held-back disk events first\n\n')
    for head in ('DiskController::pokeDSKLEN(u16 value)\n{\n', 'DiskController::pokeDSKDAT(u16 value)\n{\n', 'DiskController::peekDSKBYTR()\n{\n',
                 'DiskController::pokeDSKSYNC(u16 value)\n{\n', 'DiskController::PRBdidChange(u8 oldValue, u8 newValue)\n{\n')
] + [
    # The CPU's bus accesses as the model sees them (class of the address; custom and CIA accesses are its synchronisations).
    ('Components/CPU/CPU.cpp', head,
     head + '#ifdef RR_AMIGA_SHADOW   // Retro-Recomp modification (MPL-2.0, like this file)\n'
     f'    RrBus::cpuAccess(agnus, addr, {write});\n#endif\n')
    for head, write in (('Moira::read8(u32 addr) const\n{\n', 0), ('Moira::read16(u32 addr) const\n{\n', 0), ('Moira::read32(u32 addr) const\n{\n', 0),
                        ('Moira::write8(u32 addr, u8 val) const\n{\n', 1), ('Moira::write16(u32 addr, u16 val) const\n{\n', 1),
                        ('Moira::write32(u32 addr, u32 val) const\n{\n', 1))
] + [
    # And after it: a custom register or CIA access is complete, what it scheduled is known.
    ('Components/CPU/CPU.cpp', f'    return mem.peek{size}<Accessor::CPU>(addr);\n',
     f'#ifdef RR_AMIGA_SHADOW   // Retro-Recomp modification (MPL-2.0, like this file)\n'
     f'    const auto rrValue = mem.peek{size}<Accessor::CPU>(addr);\n    RrBus::cpuDone(agnus);\n    return rrValue;\n'
     f'#else\n    return mem.peek{size}<Accessor::CPU>(addr);\n#endif\n')
    for size in (8, 16, 32)
] + [
    ('Components/CPU/CPU.cpp', f'    mem.poke{size} <Accessor::CPU> (addr, val);\n',
     f'    mem.poke{size} <Accessor::CPU> (addr, val);\n'
     f'#ifdef RR_AMIGA_SHADOW   // Retro-Recomp modification (MPL-2.0, like this file)\n    RrBus::cpuDone(agnus);\n#endif\n')
    for size in (8, 16, 32)
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
