"""MC68000 static translation helpers shared by console adapters.

Extracted unchanged from our qualified Mega Drive generator. Bus, prefetch,
IRQ and cartridge mapping remain explicit responsibilities of each adapter.
Pinned upstream semantic helpers retain their original licence.
"""
from __future__ import annotations
from pathlib import Path
import re

from .core import ConversionError

def _masked(source: str) -> str:
    """Preserve offsets while hiding C comments and quoted literals."""
    pattern = r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    return re.sub(pattern, lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), source)


def operation_bodies(source: str) -> dict[str, str]:
    start = source.index('switch (ins->mnemonic)', source.index('static M68kiStatus exec_one('))
    masked = _masked(source)
    opening = masked.index('{', start)
    level = 1
    cursor = opening + 1
    labels = []
    case_label = re.compile(r'(?:case\s+(MN_\w+)|default)\s*:')
    while level:
        label = case_label.match(masked, cursor) if level == 1 else None
        if label:
            labels.append((label[1], cursor, cursor + len(label[0])))
            cursor += len(label[0]); continue
        level += (masked[cursor] == '{') - (masked[cursor] == '}')
        cursor += 1
    bodies = {}
    pending = []
    for i, (name, _, end) in enumerate(labels):
        if name is None:
            continue
        pending.append(name)
        stop = labels[i + 1][1] if i + 1 < len(labels) else cursor - 1
        if not masked[end:stop].strip():
            continue
        body = source[end:stop].strip()
        for item in pending:
            bodies[item] = body
        pending.clear()
    if pending or len(bodies) < 60:
        raise ConversionError('Pinned 68000 semantics changed; operation extraction refused.')
    return bodies


def mnemonic_names(engine: Path) -> list[str]:
    header = (engine / 'external/m68k-recomp-core/common/m68k_decoder.h').read_text(encoding='utf-8')
    block = _masked(header).split('MN_OTHER', 1)[1].split('} M68KMnemonic', 1)[0]
    return ['MN_OTHER'] + re.findall(r'\bMN_\w+\b', block)


def adapt_cycle_estimates(source: str) -> str:
    # MC68000 manual tables 8-12/8-14; these are also independently exercised
    # by the selected MAME states. Keep offline and reference estimates equal.
    anchor = '    case MN_TRAP:    return 34;'
    if source.count(anchor) != 1:
        raise ConversionError('Pinned 68000 cycle table changed; SR timing adaptation refused.')
    source = source.replace(anchor, '''    case MN_ORI_TO_SR: case MN_ANDI_TO_SR: case MN_EORI_TO_SR:
    case MN_ORI_TO_CCR: case MN_ANDI_TO_CCR: case MN_EORI_TO_CCR:
        return 20;
''' + anchor, 1)
    anchor = '    case MN_MOVE_SR:   return dst_is_reg ? 6 : (8 + ea_dst);'
    if source.count(anchor) != 1:
        raise ConversionError('Pinned 68000 cycle table changed; MOVE SR timing adaptation refused.')
    source = source.replace(anchor, '''    case MN_MOVE_SR:
        /* This decoder stores both MOVE SR directions' EA in src_ea. */
        return instr->dst_is_ea ? (((instr->src_ea >> 3) & 7) == 0 ? 6 : 8 + ea_src)
                               : 12 + ea_src;''', 1)
    from .gun16_runtime import replace
    # Single-EA operations store their operand in src_ea in this decoder.
    # The upstream timing table mistook zero-initialized dst_ea for D0.
    source = replace(source, '    int      dst_is_reg = (dst_mode <= 1);', '''    int      dst_is_reg = (dst_mode <= 1);
    switch(instr->mnemonic) {
    case MN_TST: case MN_CLR: case MN_NEG: case MN_NEGX: case MN_NOT:
    case MN_NBCD: case MN_TAS: case MN_Scc: case MN_ADDQ: case MN_SUBQ:
    case MN_ADDI: case MN_SUBI: case MN_ANDI: case MN_ORI: case MN_EORI: case MN_CMPI:
    case MN_BTST: case MN_BCHG: case MN_BCLR: case MN_BSET:
        ea_dst=ea_src;dst_mode=(instr->src_ea>>3)&7;dst_is_reg=dst_mode<=1;break;
    case MN_ADD: case MN_SUB: case MN_AND: case MN_OR: case MN_EOR:
        if((instr->words[0]&0x100u) || instr->mnemonic==MN_EOR) {
            ea_dst=ea_src;ea_src=0;dst_mode=(instr->src_ea>>3)&7;dst_is_reg=dst_mode<=1;
        }
        break;
    default: break;
    }''')
    source = replace(source, '    case MN_TST:\n    case MN_CLR:',
        '    case MN_TST: return 4 + ea_src;\n    case MN_CLR:')
    source = replace(source, '    case MN_BTST: return dst_is_reg ? 6 : (4 + ea_dst);\n'
        '    case MN_BCHG: case MN_BCLR: return dst_is_reg ? 8 : (8 + ea_dst);\n'
        '    case MN_BSET: return dst_is_reg ? 8 : (8 + ea_dst);', '''    case MN_BTST:
        return (instr->reg<0?4:0) + (dst_is_reg?6:4+interp_ea_read_cost(instr->src_ea,M68K_SIZE_B));
    case MN_BCHG: case MN_BCLR: case MN_BSET:
        return (instr->reg<0?4:0) + (dst_is_reg?(instr->mnemonic==MN_BCLR?10:8):
            8+interp_ea_read_cost(instr->src_ea,M68K_SIZE_B));''')
    source = replace(source, '        if (!dst_is_reg) return 8 + ea_dst;',
        '        if (instr->mem_shift) return 8+interp_ea_read_cost(instr->src_ea,M68K_SIZE_W);')
    source = replace(source, '        if (dst_is_reg) return is_long ? 8 : 4;',
        '        if (dst_mode==1) return 8;\n        if (dst_is_reg) return is_long ? 8 : 4;')
    source = replace(source, '    case MN_ADDX: case MN_SUBX:\n        return is_long ? 8 : 4;',
        '    case MN_CMPM: return is_long ? 20 : 12;\n'
        '    case MN_ADDX: case MN_SUBX:\n'
        '        return instr->predec_mem_form ? (is_long ? 30 : 18) : (is_long ? 8 : 4);')
    source = replace(source, '    case MN_ABCD: case MN_SBCD: return 6;',
        '    case MN_ABCD: case MN_SBCD: return instr->predec_mem_form ? 18 : 6;')
    source = replace(source, '    case MN_JSR:   return 18 + ea_src;',
        '    case MN_JSR: return 16 + interp_control_ea_cost(instr->src_ea,0);')
    source = replace(source, '    case MN_JMP:   return 10 + ea_src;',
        '    case MN_JMP: return 8 + interp_control_ea_cost(instr->src_ea,0);')
    source = replace(source, '    case MN_LEA:   return ea_src ? ea_src : 4;',
        '    case MN_LEA: return 4 + interp_control_ea_cost(instr->src_ea,1);')
    source = replace(source, '    case MN_PEA:   return 12 + ea_src;',
        '    case MN_PEA: return 12 + interp_control_ea_cost(instr->src_ea,1);')
    source = replace(source,'    case MN_MOVE:  return 4 + ea_src + ea_dst;',
        '    case MN_MOVE: return 4 + ea_src + ea_dst - (dst_mode==4?2:0);')
    source = replace(source, '        return (is_long ? 12 + 8*nregs : 8 + 4*nregs) + ea_src;',
        '''        unsigned mode=(instr->src_ea>>3)&7u,reg=instr->src_ea&7u;
        unsigned extra=mode<=4?0u:mode==6 || (mode==7 && reg==3)?6u:
                       mode==7 && reg==1?8u:4u;
        return ((instr->words[0]&0x400u)?12:8)+(is_long?8:4)*nregs+extra;''')
    source = replace(source,'static int interp_estimate_cycles(const M68KInstr *instr) {', '''static int interp_control_ea_cost(int ea,int address_only) {
    unsigned mode=(ea>>3)&7u,reg=ea&7u;
    if(mode==2)return 0;
    if(mode==6 || (mode==7 && reg==3))return address_only?8:6;
    if(mode==7 && reg==1)return address_only?8:4;
    return address_only?4:2;
}
static int interp_estimate_cycles(const M68KInstr *instr) {''')
    return source


def instruction_literal(ins: dict, name: str) -> str:
    words = ','.join(f'0x{word:04x}u' for word in ins['words'])
    tail = ','.join(str(ins[key]) for key in ('word_count', 'byte_length', 'src_ea',
        'dst_ea', 'reg', 'imm32', 'target_addr', 'has_target', 'dst_is_ea', 'predec_mem_form', 'mem_shift'))
    return f'{{0x{ins["addr"]:06x}u,{name},(M68KSize){ins["size"]},{{{words}}},{tail}}}'



def adapt_semantics(source: str, *, hook_prefix: str = 'rr_md') -> str:
    """Reuse our corrected CPU bodies with explicit board/prefetch hook names.

    The default retains the existing Mega Drive symbol names and behavior.
    A new board must implement every hook; it cannot substitute no-op timings.
    """
    if not re.fullmatch(r'rr_[a-z][a-z0-9_]*', hook_prefix):
        raise ValueError('Invalid MC68000 board hook prefix.')
    from .gun16_runtime import replace
    source=replace(source, 'static uint16_t er_next(ExtR *e)        { uint16_t v = e->ins->words[e->wi]; e->wi++; e->bp += 2; return v; }',
        'static uint16_t er_next(ExtR *e) { uint16_t v=rr_md_operand_extension(e->ins->addr,e->wi,e->ins->words[e->wi]);e->wi++;e->bp+=2;return v; }')
    source=replace(source, '        write_ea(ins, ins->dst_ea, sz, &er, v);',
        '        rr_md_move_source_done();\n        write_ea(ins, ins->dst_ea, sz, &er, v);')
    source=replace(source, '            if (sz == M68K_SIZE_L) m68k_write32(mb, rv); else m68k_write16(mb, (uint16_t)rv);',
        '            if(sz==M68K_SIZE_L) {m68k_write16(mb+2,(uint16_t)rv);m68k_write16(mb,(uint16_t)(rv>>16));}\n'
        '            else m68k_write16(mb,(uint16_t)rv);')
    anchor='        if (mode == 3) g_cpu.A[reg] = mb;\n    }\n}\n\n/* =========================================================================\n * Single-instruction execution.'
    source=replace(source,anchor,
        '        (void)m68k_read16(mb); /* MC68000 MOVEM load discards one final word. */\n'+anchor)
    source=replace(source, '    case 4: if (!rmw) g_cpu.A[reg] -= sb; mem_write(sz, g_cpu.A[reg], val); break;',
        '''    case 4:
        if(!rmw)g_cpu.A[reg]-=sb;
        if(ins->mnemonic==MN_MOVE && sz==M68K_SIZE_L) {
            m68k_write16(g_cpu.A[reg]+2,(uint16_t)val);
            m68k_write16(g_cpu.A[reg],(uint16_t)(val>>16));
        } else mem_write(sz,g_cpu.A[reg],val);
        break;''')
    # MC68000 TRAP #n is a vectored exception, not a host C-function call.
    # Games install RAM IRQ stubs using it; RTE must see the nested 6-byte
    # SR/PC frame on SSP, including a trap from user mode. The existing CPU
    # layout keeps the active A7 and inactive stack slot together in snapshots.
    anchor = '    case MN_NOP:\n        return M68KI_OK;'
    trap = '''    case MN_TRAP: {
        return rr_md_instruction_exception(next_pc, 32u + (ins->words[0] & 15u), fall, 34);
    }

    case MN_TRAPV:
        if (g_cpu.SR & SR_V)
            return rr_md_instruction_exception(next_pc, 7, fall, 34);
        return M68KI_OK;

    case MN_CHK: {
        int16_t bound = (int16_t)read_ea(ins, ins->src_ea, M68K_SIZE_W, &er);
        int16_t value = (int16_t)g_cpu.D[ins->reg];
        /* Z/V/C are undefined architecturally. Use the deterministic MAME
         * convention, without claiming physical fidelity for these bits. */
        g_cpu.SR &= ~(SR_N | SR_Z | SR_V | SR_C);
        if (!value) g_cpu.SR |= SR_Z;
        if (value > bound || value < 0) {
            if (value < 0) g_cpu.SR |= SR_N; else g_cpu.SR &= ~SR_N;
            /* The first comparison exits two clocks before the sign test,
             * including subtraction overflow. 40 + EA is Motorola's maximum;
             * the pinned microcoded corpus covers both paths. */
            rr_md_cpu_idle(value > bound || (int32_t)value - bound < -32768 ? 4u : 6u);
            return rr_md_instruction_exception(next_pc, 6, fall,
                (value > bound || (int32_t)value - bound < -32768 ? 38u : 40u) +
                (unsigned)interp_ea_read_cost(ins->src_ea, M68K_SIZE_W));
        }
        return M68KI_OK;
    }

    case MN_ILLEGAL: {
        unsigned line = ins->words[0] >> 12;
        unsigned vector = line == 10 ? 10u : line == 15 ? 11u : 4u;
        return rr_md_instruction_exception(next_pc, vector, ins->addr, 34);
    }

    case MN_RESET:
        if (!(g_cpu.SR & SR_S))
            return rr_md_instruction_exception(next_pc, 8, ins->addr, 34);
        /* External RESET wiring is a separate board feature. */
        g_m68ki_bad_pc = ins->addr; g_m68ki_bad_op = ins->words[0];
        return M68KI_HALT_UNIMPL;

'''
    if source.count(anchor) != 1:
        raise ConversionError('Pinned 68000 instruction semantics changed; TRAP adaptation refused.')
    stop = '''    case MN_STOP:
        if (!(g_cpu.SR & SR_S))
            return rr_md_instruction_exception(next_pc, 8, ins->addr, 34);
        rr_md_set_sr((uint16_t)ins->imm32);
        rr_md_cpu_stopped = 1;
        return M68KI_OK;

'''
    # MOVEP is a peripheral transfer: each successive byte is two bus
    # addresses apart. Word loads keep the upper half of Dn; neither form
    # changes CCR or An. MC68000 allows an odd peripheral address.
    movep = '''    case MN_MOVEP: {
        uint32_t address = g_cpu.A[ins->words[0] & 7u] + (int16_t)ins->words[1];
        unsigned count = ins->size == M68K_SIZE_L ? 4u : 2u;
        if (ins->words[0] & 0x80u) {
            uint32_t value = g_cpu.D[ins->reg];
            for (unsigned i = 0; i < count; ++i)
                m68k_write8((address + i * 2u) & 0xffffffu,
                           (uint8_t)(value >> ((count - 1u - i) * 8u)));
        } else {
            uint32_t value = 0;
            for (unsigned i = 0; i < count; ++i)
                value = (value << 8) | m68k_read8((address + i * 2u) & 0xffffffu);
            g_cpu.D[ins->reg] = count == 2u ? (g_cpu.D[ins->reg] & 0xffff0000u) | value : value;
        }
        return M68KI_OK;
    }

'''
    source = source.replace(anchor, trap + stop + movep + anchor, 1)
    old_rte = '''        g_cpu.SR = pop16() & 0xA71Fu;     /* mask to valid SR bits (T,S,I,CCR) */
        *next_pc = pop32();'''
    if source.count(old_rte) != 1:
        raise ConversionError('Pinned 68000 RTE operation changed; stack-mode adaptation refused.')
    source = source.replace(old_rte, '''        if (!(g_cpu.SR & SR_S))
            return rr_md_instruction_exception(next_pc, 8, ins->addr, 34);
        uint16_t restored_sr = pop16();
        *next_pc = pop32(); /* Read the entire frame on SSP, then select A7. */
        rr_md_set_sr(restored_sr);''', 1)
    old_move = 'if (!ins->dst_is_ea) g_cpu.SR = (uint16_t)(read_ea(ins, ins->src_ea, M68K_SIZE_W, &er) & 0xA71Fu);'
    if source.count(old_move) != 1:
        raise ConversionError('Pinned 68000 MOVE to SR changed; stack-mode adaptation refused.')
    source = source.replace(old_move, '''if (!ins->dst_is_ea) {
            if (!(g_cpu.SR & SR_S))
                return rr_md_instruction_exception(next_pc, 8, ins->addr, 34);
            uint16_t value = (uint16_t)read_ea(ins, ins->src_ea, M68K_SIZE_W, &er);
            rr_md_set_sr(value);
        }''', 1)
    for mnemonic, operator in (('ORI', '|'), ('ANDI', '&'), ('EORI', '^')):
        pattern = rf'case MN_{mnemonic}_TO_SR:[^\n]+'
        body = (f'case MN_{mnemonic}_TO_SR:\n'
                '        if (!(g_cpu.SR & SR_S))\n'
                '            return rr_md_instruction_exception(next_pc, 8, ins->addr, 34);\n'
                f'        rr_md_set_sr((uint16_t)(g_cpu.SR {operator} ins->imm32)); return M68KI_OK;')
        source, matches = re.subn(pattern, body, source)
        if matches != 1:
            raise ConversionError('Pinned 68000 SR operation changed; stack-mode adaptation refused.')
    source = source.replace('    case MN_MOVE_USP:\n',
        '    case MN_MOVE_USP:\n        if (!(g_cpu.SR & SR_S))\n'
        '            return rr_md_instruction_exception(next_pc, 8, ins->addr, 34);\n', 1)
    # Equality means a quotient of at least 65536, which cannot fit.
    if source.count('if (abs_src >= (abs_dest >> 16))') != 1:
        raise ConversionError('Pinned 68000 divide overflow precheck changed.')
    source = source.replace('if (abs_src >= (abs_dest >> 16))',
                            'if (abs_src > (abs_dest >> 16))', 1)
    for name, signed in (('MULU', 0), ('MULS', 1)):
        pattern = rf'(case MN_{name}: \{{\n[^\n]+\n)'
        hook = ('        rr_md_arithmetic_phase(rr_md_multiply_clocks((uint16_t)s, '
                f'{signed}), (unsigned)interp_ea_read_cost(ins->src_ea, M68K_SIZE_W), 1);\n')
        source, matches = re.subn(pattern, lambda match: match[1] + hook, source)
        if matches != 1:
            raise ConversionError('Pinned 68000 multiply body changed.')
    for name, signed in (('DIVU', 0), ('DIVS', 1)):
        old = (f'    case MN_{name}:\n'
               f'        do_div(ins->reg, read_ea(ins, ins->src_ea, M68K_SIZE_W, &er) & 0xFFFFu, {signed});\n'
               '        return M68KI_OK;')
        body = f'''    case MN_{name}: {{
        uint32_t divisor = read_ea(ins, ins->src_ea, M68K_SIZE_W, &er) & 0xffffu;
        if (divisor)
            rr_md_arithmetic_phase(rr_md_divide_clocks(g_cpu.D[ins->reg], (uint16_t)divisor, {signed}),
                (unsigned)interp_ea_read_cost(ins->src_ea, M68K_SIZE_W), 0);
        do_div(ins->reg, divisor, {signed});
        if (!divisor) {{
            if (rr_md_prefetch_active()) rr_md_cpu_idle(4);
            return rr_md_instruction_exception(next_pc, 5, fall,
                38u + (unsigned)interp_ea_read_cost(ins->src_ea, M68K_SIZE_W));
        }}
        return M68KI_OK;
    }}'''
        if source.count(old) != 1:
            raise ConversionError('Pinned 68000 divide operation changed; exception adaptation refused.')
        source = source.replace(old, body, 1)
    # CMPM has two independently postincremented address operands, including
    # the word step for either byte operand using A7.
    source = source.replace('g_cpu.A[ay] += sb;',
        'g_cpu.A[ay] += (ay==7 && sz==M68K_SIZE_B)?2:sb;')
    source = source.replace('g_cpu.A[ax] += sb;',
        'g_cpu.A[ax] += (ax==7 && sz==M68K_SIZE_B)?2:sb;')
    # Byte accesses via A7 still move the stack by a word on MC68000.
    source = source.replace('int mode = (ea >> 3) & 7, reg = ea & 7, sb = szbytes(sz);',
        'int mode = (ea >> 3) & 7, reg = ea & 7, sb = szbytes(sz);\n'
        '    if (sz == M68K_SIZE_B && reg == 7) sb = 2;')
    source = source.replace('g_cpu.A[ay] += sb;',
        'g_cpu.A[ay] += (sz == M68K_SIZE_B && ay == 7) ? 2 : sb;')
    source = source.replace('g_cpu.A[ax] += sb;',
        'g_cpu.A[ax] += (sz == M68K_SIZE_B && ax == 7) ? 2 : sb;')
    # MC68000 (unlike later variants) reads a memory destination before CLR
    # and Scc writes it. Retain predecrement/postincrement exactly once.
    from .gun16_runtime import replace
    source = replace(source, '        write_ea(ins, ins->src_ea, sz, &er, 0);', '''        ExtR save=er;
        (void)read_ea_ex(ins,ins->src_ea,sz,&er,1);
        er=save;write_ea_ex(ins,ins->src_ea,sz,&er,0,1);''')
    source = replace(source, '        write_ea(ins, ins->src_ea, M68K_SIZE_B, &er, val);', '''        ExtR save=er;
        (void)read_ea_ex(ins,ins->src_ea,M68K_SIZE_B,&er,1);
        er=save;write_ea_ex(ins,ins->src_ea,M68K_SIZE_B,&er,val,1);''')
    source = replace(source,'        discover(tgt);\n        push32(fall);',
        '        discover(tgt);\n        rr_md_prefetch_target(tgt);\n        push32(fall);')
    # MC68000 PRM, shift/rotate with a register count of zero (modulo 64):
    # X is unchanged and C is cleared, except ROXL/ROXR which load C from X.
    source = replace(source,
        '    } else if (reg_count && cnt == 0) {                        /* count 0: preserve X, C=0 */\n'
        '        g_cpu.SR &= ~0x0Fu;\n',
        '    } else if (reg_count && cnt == 0) {                        /* count 0: preserve X, C=0 */\n'
        '        g_cpu.SR &= ~0x0Fu;\n'
        '        if ((mn == MN_ROXL || mn == MN_ROXR) && (g_cpu.SR & SR_X)) g_cpu.SR |= SR_C;\n')
    # ASL.L by 31 tests 32 top bits: 1u << 32 is undefined in C, so the mask is 64-bit.
    source = replace(source,
        'uint32_t allm = (uint32_t)((1u << (cnt + 1)) - 1u);',
        'uint32_t allm = (uint32_t)((UINT64_C(1) << (cnt + 1)) - 1u);')
    result = adapt_cycle_estimates(source)
    return result if hook_prefix == 'rr_md' else result.replace('rr_md_', hook_prefix + '_')
