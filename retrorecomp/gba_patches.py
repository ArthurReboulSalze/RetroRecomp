"""Our fixes to the pinned Game Boy Advance engine, as anchored text replacements (docs/UPSTREAMS.md).

Each entry is `(file under the engine, old text, new text, note)`, written with LF line ends (the staged copy is LF). `old text`
must occur exactly once in the pinned file: an engine whose text moved is refused (`gba_engine.stage`), never patched blindly, and
a bump of the pin re-checks every anchor. The set is part of the identity of the recompiler and of every game built with it
(`gba_engine.patch_digest`).

A fix belongs here when it is a general cause (a hardware behaviour, a rule of the CPU), found by an authored test or a vector,
never a case of one game. Each one is offered upstream to its author when that makes sense; the maintainer posts.
"""
from __future__ import annotations

HARDWARE_NOTES = "bus and memory behaviours found with the authored test ROMs (jsmolka gba-tests, MIT)"

# Files of ours the staged copy gains: (path under the engine, name of our file under native/).
ADDED_FILES: tuple[tuple[str, str], ...] = (('src/runtime/rr_driver.h', 'gba_driver.h'),)

PATCHES: tuple[tuple[str, str, str, str], ...] = (
    # Hardware found with the authored test ROMs (jsmolka gba-tests, MIT): the VRAM mirror, the 8-bit save bus, byte stores to
    # video memory (a development trial: 5 failing authored ROMs passed, the other 6 kept their result).
    ('src/gba/gba_memory.cpp',
     '            return static_cast<std::size_t>(addr & 0x1FFFFu);\n        }',
     '            // The 32 KB above the first 64 KB (0x06018000..0x0601FFFF) is\n            // the upper 32 KB of VRAM again (GBATEK "GBA Memory Map").\n            std::size_t off = static_cast<std::size_t>(addr & 0x1FFFFu);\n            if (off >= 0x18000u) off -= 0x8000u;\n            return off;\n        }',
     'VRAM: fold 0x18000..0x1FFFF onto 0x10000..0x17FFF'),
    ('src/gba/gba_bus.cpp',
     '            log_unmapped(addr, 0, false, 1);\n            return 0;\n        case Region::OpenBus:',
     '            // No save chip: the open 8-bit save bus reads as 0xFF.\n            log_unmapped(addr, 0, false, 1);\n            return 0xFF;\n        case Region::OpenBus:',
     'save window read8 without chip -> 0xFF'),
    ('src/gba/gba_bus.cpp',
     '            log_unmapped(addr, 0, false, 2);\n            return 0;\n        case Region::OpenBus:',
     '            log_unmapped(addr, 0, false, 2);\n            return 0xFFFF;\n        case Region::OpenBus:',
     'save window read16 without chip -> 0xFFFF'),
    ('src/gba/gba_bus.cpp',
     '            log_unmapped(addr, 0, false, 4);\n            return 0;\n        case Region::OpenBus:',
     '            log_unmapped(addr, 0, false, 4);\n            return 0xFFFFFFFFu;\n        case Region::OpenBus:',
     'save window read32 without chip -> 0xFFFFFFFF'),
    ('src/gba/gba_bus.cpp',
     '            if (save_.sram_enabled()) {\n                save_.sram_write(static_cast<uint32_t>(off),\n                                 static_cast<uint8_t>(v & 0xFF));\n                return;\n            }\n            if (save_.flash_enabled()) {\n                save_.flash_write(static_cast<uint32_t>(off),\n                                  static_cast<uint8_t>(v & 0xFF));\n                return;\n            }\n            log_unmapped(addr, v, true, 2);',
     '            // The save bus is 8 bits wide: a halfword store writes one byte,\n            // the lane selected by the low address bit, at the unaligned address.\n            if (save_.sram_enabled()) {\n                save_.sram_write(static_cast<uint32_t>(off),\n                                 static_cast<uint8_t>(v >> (8u * (addr & 1u))));\n                return;\n            }\n            if (save_.flash_enabled()) {\n                save_.flash_write(static_cast<uint32_t>(off),\n                                  static_cast<uint8_t>(v >> (8u * (addr & 1u))));\n                return;\n            }\n            log_unmapped(addr, v, true, 2);',
     'save write16: byte lane by address bit 0'),
    ('src/gba/gba_bus.cpp',
     '            if (save_.sram_enabled()) {\n                save_.sram_write(static_cast<uint32_t>(off),\n                                 static_cast<uint8_t>(v & 0xFF));\n                return;\n            }\n            if (save_.flash_enabled()) {\n                save_.flash_write(static_cast<uint32_t>(off),\n                                  static_cast<uint8_t>(v & 0xFF));\n                return;\n            }\n            log_unmapped(addr, v, true, 4);',
     '            // 8-bit save bus: a word store writes the byte of the lane\n            // selected by the two low address bits, at the unaligned address.\n            if (save_.sram_enabled()) {\n                save_.sram_write(static_cast<uint32_t>(off),\n                                 static_cast<uint8_t>(v >> (8u * (addr & 3u))));\n                return;\n            }\n            if (save_.flash_enabled()) {\n                save_.flash_write(static_cast<uint32_t>(off),\n                                  static_cast<uint8_t>(v >> (8u * (addr & 3u))));\n                return;\n            }\n            log_unmapped(addr, v, true, 4);',
     'save write32: byte lane by address bits 1..0'),
    ('src/gba/gba_bus.cpp',
     '        case Region::Pal:   pal_[off]   = v; return;\n        case Region::Vram:\n            if (off < vram_.size()) {\n                vram_[off] = v;\n#if defined(GBARECOMP_NATIVE_DRAW_JOBS)\n                if (draw_memory_ && !draw_vram_alias_exposed_) draw_memory_->mark(off, 1);\n#endif\n            }\n            return;\n        case Region::Oam:   oam_[off] = v; return;\n        case Region::Bios:',
     '        case Region::Pal:\n            // Byte stores to palette RAM write the byte to both halves of\n            // the aligned halfword (GBATEK "GBA LCD Video Memory").\n            store_u16(&pal_[off & ~std::size_t{1}], static_cast<uint16_t>(v * 0x0101u));\n            return;\n        case Region::Vram: {\n            // Byte stores reach VRAM only in the BG area (below 0x10000, or\n            // 0x14000 in bitmap modes 3-5), as a duplicated halfword; the OBJ\n            // area ignores them. OAM ignores byte stores altogether.\n            const std::size_t bg_end = (io_dispatch_.raw()[0] & 7u) >= 3u ? 0x14000u : 0x10000u;\n            if (off < bg_end) {\n                const std::size_t even = off & ~std::size_t{1};\n                store_u16(&vram_[even], static_cast<uint16_t>(v * 0x0101u));\n#if defined(GBARECOMP_NATIVE_DRAW_JOBS)\n                if (draw_memory_ && !draw_vram_alias_exposed_) draw_memory_->mark(even, 2);\n#endif\n            }\n            return;\n        }\n        case Region::Oam:   return;\n        case Region::Bios:',
     'write8: palette/VRAM byte stores as duplicated halfword, OBJ VRAM and OAM ignored'),
    ('external/arm-recomp-core/profiles/armv4t_gba/arm_codegen.cpp',
     '                body << indent << "bus_write_u32(" << ea_var << " & ~3u, "\n                     << val_expr << ");\\n";',
     '                // The save window (0x0E000000 and above) is an 8-bit bus that\n                // keeps the low address bits to pick the stored byte lane;\n                // every other region sees the aligned address.\n                body << indent << "bus_write_u32(" << ea_var << " >= 0x0E000000u ? "\n                     << ea_var << " : " << ea_var << " & ~3u, "\n                     << val_expr << ");\\n";',
     'codegen STR: keep low address bits for the save window'),
    ('external/arm-recomp-core/profiles/armv4t_gba/arm_codegen.cpp',
     '                body << indent << "bus_write_u16(" << ea_var << " & ~1u, (uint16_t)("\n                     << val_expr << " & 0xFFFFu));\\n";',
     '                body << indent << "bus_write_u16(" << ea_var << " >= 0x0E000000u ? "\n                     << ea_var << " : " << ea_var << " & ~1u, (uint16_t)("\n                     << val_expr << " & 0xFFFFu));\\n";',
     'codegen STRH: keep low address bit for the save window'),
    ('external/arm-recomp-core/profiles/armv4t_gba/interpreter.cpp',
     '                    case IrOp::STR:  bus.write32(effective_addr & ~3u, val); break;\n                    case IrOp::STRB: bus.write8 (effective_addr, val & 0xFFu); break;\n                    case IrOp::STRH: bus.write16(effective_addr & ~1u, val & 0xFFFFu); break;',
     '                    // Save window (>= 0x0E000000): 8-bit bus, low address bits kept.\n                    case IrOp::STR:\n                        bus.write32(effective_addr >= 0x0E000000u ? effective_addr\n                                                                  : effective_addr & ~3u, val);\n                        break;\n                    case IrOp::STRB: bus.write8 (effective_addr, val & 0xFFu); break;\n                    case IrOp::STRH:\n                        bus.write16(effective_addr >= 0x0E000000u ? effective_addr\n                                                                  : effective_addr & ~1u,\n                                    val & 0xFFFFu);\n                        break;',
     'interpreter STR/STRH: same rule'),
    # cpu
    ('external/arm-recomp-core/profiles/armv4t_gba/arm_codegen.cpp',
     '    bool spsr_restore_test = ins.set_flags && (ins.rd == 15) && is_test;',
     '    bool spsr_restore_test = ins.set_flags && (ins.rd == 15) && is_test && !ins.thumb;',
     'codegen: no SPSR->CPSR restore for Thumb CMP PC, Rm'),
    ('external/arm-recomp-core/profiles/armv4t_gba/interpreter.cpp',
     '            bool excpt_return =',
     '            bool excpt_return = (i.op != IrOp::TST && i.op != IrOp::TEQ) &&',
     'interpreter: a logical test op is not an exception return'),
    ('external/arm-recomp-core/profiles/armv4t_gba/interpreter.cpp',
     '            bool excpt_return_arith =',
     '            bool excpt_return_arith = (i.op != IrOp::CMP && i.op != IrOp::CMN) &&',
     'interpreter: an arithmetic test op is not an exception return'),
    ('external/arm-recomp-core/profiles/armv4t_gba/interpreter.cpp',
     '                (i.op == IrOp::TST || i.op == IrOp::TEQ) &&',
     '                !i.thumb && (i.op == IrOp::TST || i.op == IrOp::TEQ) &&',
     'interpreter: no SPSR restore in Thumb (logical tests)'),
    ('external/arm-recomp-core/profiles/armv4t_gba/interpreter.cpp',
     '                (i.op == IrOp::CMP || i.op == IrOp::CMN) &&',
     '                !i.thumb && (i.op == IrOp::CMP || i.op == IrOp::CMN) &&',
     'interpreter: no SPSR restore in Thumb (CMP hi-register form)'),
    ('external/arm-recomp-core/profiles/armv4t_gba/interpreter.cpp',
     '    // Save CPSR into SPSR_irq.',
     '    if (cpu.cpsr.mode == static_cast<uint8_t>(Mode::FIQ)) {  // FIQ R8-R12 are banked\n        for (int i = 0; i < 5; ++i) { cpu.r8_12_fiq[i] = cpu.R[8 + i]; cpu.R[8 + i] = cpu.r8_12_user[i]; }\n    }\n    // Save CPSR into SPSR_irq.',
     'interpreter: enter_irq swaps the FIQ R8-R12 bank'),
    ('external/arm-recomp-core/profiles/armv4t_gba/interpreter.cpp',
     '    cpu.banked_spsr[Bank_Supervisor] = cpsr_u32;',
     '    if (cpu.cpsr.mode == static_cast<uint8_t>(Mode::FIQ)) {  // FIQ R8-R12 are banked\n        for (int i = 0; i < 5; ++i) { cpu.r8_12_fiq[i] = cpu.R[8 + i]; cpu.R[8 + i] = cpu.r8_12_user[i]; }\n    }\n    cpu.banked_spsr[Bank_Supervisor] = cpsr_u32;',
     'interpreter: enter_swi swaps the FIQ R8-R12 bank'),
    ('external/arm-recomp-core/profiles/armv4t_gba/interpreter.cpp',
     '                uint32_t rm_val = cpu.R[i.mem.reg_offset.rm];',
     '                uint32_t rm_val = read_reg(cpu, i.mem.reg_offset.rm, i);',
     'interpreter: register offset Rm = R15 reads the pipeline value, like the generated code'),
    # Runtime: the guest call-return entries a finished IRQ handler pushed were never dropped, so a game whose mainline sat a
    # few entries below the fixed 1,024 aborted inside its next interrupt (one cartridge of the four of the engine trial, after
    # about 850 frames with scripted input). A general cause: the handler's frames are dead once it has executed its iret.
    ('src/armv4t/runtime_arm.cpp',
     '    uint32_t saved_floor   = g_call_return_floor;\n    g_call_return_floor    = g_call_return_depth;\n    if (g_resumable_context) {',
     '    uint32_t saved_floor   = g_call_return_floor;\n    const uint32_t entry_call_depth = g_call_return_depth;\n    g_call_return_floor    = g_call_return_depth;\n    if (g_resumable_context) {',
     'runtime_irq: remember the call-return depth at entry'),
    ('src/armv4t/runtime_arm.cpp',
     "    g_irq_iret_depth = saved_iret;  // restore an enclosing IRQ's expectation\n    g_call_return_floor = saved_floor;\n    --g_irq_nest_depth;\n}",
     "    g_irq_iret_depth = saved_iret;  // restore an enclosing IRQ's expectation\n    g_call_return_floor = saved_floor;\n    // The handler has executed its iret: every guest call-return entry it pushed is dead (its host frames are gone).\n    // Left in place they pile up, one or more per interrupt, until the fixed stack overflows at the next IRQ.\n    if (g_call_return_depth > entry_call_depth) {\n        g_call_return_depth = entry_call_depth;\n        clamp_call_return_hostless();\n    }\n    --g_irq_nest_depth;\n}",
     'runtime_irq: drop the call-return entries of a finished handler'),
    # Timing: the interpreter charged an instruction's own opcode fetch with the wait states in force AFTER it ran, the generated
    # code with those in force before it; they differ by a cycle on the store that changes WAITCNT, and every later cycle count
    # (and any code that polls the scanline) moved with it. The generated code follows the hardware (the opcode was already
    # fetched), so the interpreter is brought to it.
    ('external/arm-recomp-core/profiles/armv4t_gba/interpreter.cpp',
     '    uint32_t mem_cycles = 0;\n    uint32_t extra_cycles = 0;\n',
     '    uint32_t mem_cycles = 0;\n    uint32_t extra_cycles = 0;\n    // The opcode of this instruction was fetched under the wait states in force before it ran: a store to WAITCNT changes\n    // the waits of the fetches after it, not of this one (the generated code reads them before the instruction too).\n    const uint32_t fetch_wait_s = bus.code_wait(i.pc, i.thumb, true);\n    const uint32_t fetch_wait_n = bus.code_wait(i.pc, i.thumb, false);\n',
     'interpreter: remember the opcode-fetch waits before the instruction runs'),
    ('external/arm-recomp-core/profiles/armv4t_gba/interpreter.cpp',
     '        const uint32_t fetch_s = bus.code_wait(i.pc, i.thumb, true);\n        const bool fetch_n = next_fetch_nonsequential(i.op);\n        c += fetch_n ? bus.code_wait(i.pc, i.thumb, false) : fetch_s;\n',
     '        const bool fetch_n = next_fetch_nonsequential(i.op);\n        c += fetch_n ? fetch_wait_n : fetch_wait_s;\n',
     'interpreter: charge the opcode fetch with the waits of before the instruction'),
    # Input: a scripted key word of a headless run reaches the machine at one cycle in every mode (see the comment of the text).
    ('src/runtime/runtime.cpp',
     '    if (input_replay_requested) apply_input_replay();\n    if (args.window) pump_host_input();\n',
     '    if (input_replay_requested) apply_input_replay();\n    if (args.window) pump_host_input();\n    // A scripted key word of a headless run is applied inside the VBlank tick, at the same machine cycle in the generated code\n    // and in the interpreter. Applied between two dispatches it took effect at different cycles in the two (the generated code\n    // runs to the next VBlank unwind, the interpreter checks after every instruction), so a game that polls KEYINPUT around\n    // the VBlank read different keys and the two runs diverged without any difference in the CPU.\n    // A clock cartridge (the Seiko RTC of the Pokémon games) reads the host\'s wall clock, and the interpreter replay lasts a hundred\n    // times longer than the generated code\'s run, so the two saw different seconds and a game that shows the time differed by a\n    // frame without any difference in the CPU. The checks start the clock from a fixed time and advance it with the guest\'s cycles.\n    const char* rtc_guest_epoch = std::getenv("GBARECOMP_RTC_GUEST_EPOCH");\n    auto apply_guest_clock = [&]() {\n        if (rtc_guest_epoch && bus.rtc().active())\n            bus.rtc().set_diagnostic_host_seconds(std::strtoll(rtc_guest_epoch, nullptr, 10) + static_cast<long long>(g_runtime_cycles / 16777216ull));\n    };\n    apply_guest_clock();\n    if ((input_replay_requested || rtc_guest_epoch) && !args.window)\n        runtime_set_vblank_input_hook([&]() { apply_input_replay(); apply_guest_clock(); });\n',
     'headless input replay: apply the key word inside the VBlank tick (deterministic in both execution modes); guest-timed RTC for the checks'),
    ('src/runtime/runtime.cpp',
     '            if (!(args.window && diag.recording())) apply_input_replay();\n',
     '            if (args.window && !diag.recording()) apply_input_replay();\n',
     'headless input replay: no application between dispatches'),
    # The end of a bounded headless run: the generated code leaves at the first yield point of the first VBlank after the frame counter
    # reaches the limit (frame `limit` drawn and latched), the interpreter left as the counter changed, a whole frame earlier. On an
    # animated screen the two final pictures differed by one step with equal CPU state. The interpreter now waits for the same VBlank.
    ('src/runtime/runtime.cpp',
     '    const uint64_t headless_base_frame = ppu.frame_count();\n',
     '    const uint64_t headless_base_frame = ppu.frame_count();\n    bool interp_stop_armed = false;                  // the interpreter\'s end of a bounded run waits for the next VBlank\n    unsigned long long interp_stop_vblanks = 0;\n',
     'bounded run: state of the interpreter\'s stop on the first VBlank after the limit'),
    ('src/runtime/runtime.cpp',
     '        if (!args.window && args.frames >= 0 &&\n            ppu.frame_count() - headless_base_frame >=\n                static_cast<uint64_t>(args.frames)) {\n            break;\n        }\n    }\n',
     '        if (!args.window && args.frames >= 0 &&\n            ppu.frame_count() - headless_base_frame >=\n                static_cast<uint64_t>(args.frames)) {\n            if (!g_force_interp) break;\n            // Interpreter alone: stop on the same event as the generated code, the first VBlank after the counter reached the limit.\n            if (!interp_stop_armed) { interp_stop_armed = true; interp_stop_vblanks = g_runtime_vblank_starts; }\n            if (g_runtime_vblank_starts != interp_stop_vblanks) break;\n        }\n    }\n',
     'bounded run: the interpreter ends on the first VBlank after the limit, as the generated code does'),
    # The player: the host kit drives the machine one frame at a time (native/gba_driver.h), with the cartridge and the system ROM linked in.
    ('src/runtime/runtime.cpp',
     '#include "runtime.h"\n',
     '#include "runtime.h"\n#include "rr_driver.h"\n',
     'runtime.cpp: include the player seam'),
    ('src/runtime/runtime.cpp',
     'void runtime_set_vblank_input_hook(std::function<void()>);\n',
     'void runtime_set_vblank_input_hook(std::function<void()>);\n\nnamespace gbarecomp {\nint (*g_rr_driver)(const RrDriverApi&) = nullptr;\nRrEmbedded g_rr_embedded_bios;\nRrEmbedded g_rr_embedded_rom;\n}  // namespace gbarecomp\n',
     'runtime.cpp: the player seam (driver and embedded images), null for the probe host'),
    ('src/runtime/runtime.cpp',
     '    if (args.tcp_port > 0) {\n        // ── Free-run threading model',
     '    if (g_rr_driver) {\n        // The Retro-Recomp player: the host kit owns the loop and asks for one frame at a time. The machine is built, the saves\n        // are loaded, the generated code is linked; what the window loop does around it (pacing, presentation, the battery\n        // flush, the exit) is the player\'s, through this table.\n        RrDriverApi api;\n        const char* rtc_guest_epoch = std::getenv("GBARECOMP_RTC_GUEST_EPOCH");\n        auto guest_clock = [&]() {\n            if (rtc_guest_epoch && bus.rtc().active())\n                bus.rtc().set_diagnostic_host_seconds(std::strtoll(rtc_guest_epoch, nullptr, 10) + static_cast<long long>(g_runtime_cycles / 16777216ull));\n        };\n        guest_clock();\n        api.step_frame = [&]() { guest_clock(); return step_frame(); };\n        api.set_keyinput = [&](uint16_t keys) { bus.io().set_keyinput(keys); };\n        api.picture = [&](int* width, int* height) -> const uint8_t* {\n            *width = static_cast<int>(ppu.render_width());\n            *height = static_cast<int>(ppu.render_height());\n            return ppu.latched_framebuffer();\n        };\n        api.drain_audio = [&](int16_t* out, size_t capacity, uint32_t* rate) -> size_t {\n            uint32_t block_rate = 0;\n            const size_t count = bus.audio().drain_sample_block(out, capacity, block_rate);\n            *rate = block_rate;\n            return count;\n        };\n        api.save_state = [&](std::vector<uint8_t>& bytes, std::string& error) { return do_savestate_save_bytes(bytes, error); };\n        api.load_state = [&](const std::vector<uint8_t>& bytes, std::string& error) { return do_savestate_load_bytes(bytes, error); };\n        api.flush_save = [&]() { return flush_save() != SaveFlush::Failed; };\n        api.save_dirty = [&]() { return bus.save().dirty(); };\n        api.interpreted_instructions = [&]() { return static_cast<uint64_t>(self_heal_interpreted_insns()); };\n        api.frames = [&]() { return static_cast<uint64_t>(ppu.frame_count()); };\n        const int driver_status = g_rr_driver(api);\n        const bool driver_save_ok = flush_save() != SaveFlush::Failed;\n        write_session_diagnostics(opts, "exit", ppu.frame_count());\n        emit_exit_diagnostics();\n        gbarecomp::overlay_loader_shutdown();\n        runtime_shutdown();\n        return (driver_status == 0 && driver_save_ok) ? 0 : 1;\n    }\n    if (args.tcp_port > 0) {\n        // ── Free-run threading model',
     'runtime.cpp: hand the built machine to the player instead of running a loop'),
    ('src/runtime/asset_picker.cpp',
     '#include "../gba/sha1.h"\n',
     '#include "../gba/sha1.h"\n#include "rr_driver.h"\n#include <cstring>\n',
     'asset_picker.cpp: include the player seam'),
    ('src/runtime/asset_picker.cpp',
     'AssetResult load_and_validate(const std::string& path,\n                              const AssetSpec& spec) {\n    AssetResult r;\n    r.path = path;\n    std::string err;\n    r.bytes = read_file(path, &err);\n',
     'const RrEmbedded& embedded_for(const AssetSpec& spec) {\n    static const RrEmbedded none;\n    if (spec.cache_filename && std::strcmp(spec.cache_filename, "bios.cfg") == 0) return g_rr_embedded_bios;\n    if (spec.cache_filename && std::strcmp(spec.cache_filename, "rom.cfg") == 0) return g_rr_embedded_rom;\n    return none;\n}\n\nAssetResult load_and_validate(const std::string& path,\n                              const AssetSpec& spec) {\n    AssetResult r;\n    r.path = path;\n    std::string err;\n    if (embedded_for(spec).data) {            // the player carries its own copy: same checks, no file\n        const RrEmbedded& image = embedded_for(spec);\n        r.bytes.assign(image.data, image.data + image.size);\n    } else {\n        r.bytes = read_file(path, &err);\n    }\n',
     'asset_picker.cpp: an image linked into the player stands in for the file'),
    ('src/runtime/asset_picker.cpp',
     '    const std::string cache = cache_path(exe_dir, spec.cache_filename);\n',
     '    const std::string cache = cache_path(exe_dir, spec.cache_filename);\n    if (embedded_for(spec).data) return load_and_validate("(embedded)", spec);\n',
     'asset_picker.cpp: take the linked image before any path, cache or picker'),
)
