"""The authored GSU case library (see snes_superfx_model.py for the rules it is checked against)."""
from itertools import product

from tools.snes_superfx_case import Case
from tools.snes_superfx_programs import build as random_programs
from tools.snes_superfx_model import (ALT1, ALT2, ALT3, BCC, BCS, BEQ, BGE, BLT, BMI, BNE, BPL,
                                      BRA, BVC, BVS, CACHE, NOP, PREFIX, SFR_CY, SFR_OV, SFR_S,
                                      SFR_Z, STOP, branch, frm, ibt, iwt, lm, lms, sm, sms, to,
                                      with_)

VALUES = [0x0000, 0x0001, 0x007F, 0x7FFF, 0x8000, 0x8001, 0xFFFF, 0x5A96]
WIDE = [0x0000, 0x0001, 0x0002, 0x007F, 0x0080, 0x00FF, 0x0100, 0x1234, 0x7FFE, 0x7FFF,
        0x8000, 0x8001, 0xFFFE, 0xFFFF, 0xA5C3]
FLAG_STATES = [0, SFR_CY, SFR_OV | SFR_S, SFR_Z | SFR_CY | SFR_S | SFR_OV, SFR_Z | SFR_OV,
               SFR_S | SFR_CY, SFR_Z, SFR_OV | SFR_CY]
DATA = 0x2000          # ROM data table (ROMBR 0, address 2000, and linear bank 40 offset 2000)

# Findings tied to cases (see the report): documentation versus the engine's core.
F_IRQ_MASKED, F_CACHE_SAME_CBR, F_TRANSPARENT_2BPP, F_HIGH_NIBBLE, F_FMULT_R4 = 1, 2, 3, 4, 5
# finding 6 (CPU view of the code cache with CBR not a multiple of 100h) is fixed by the engine
# adaptation retrorecomp.snes_chips.superfx; its cases are ordinary assertions now
F_LOAD_FIGURES, F_PIXEL_AT_STOP, F_GETB_OTHER_BYTE = 7, 8, 9


def inc(n):
    return bytes([0xD0 + n])


def dec(n):
    return bytes([0xE0 + n])


def asm(base, *parts):
    """Tiny two-pass assembler: bytes, 'label' strings, ('iwt', n, label[, adj]),
    ('ibt', n, label), ('br', opcode, label) (displacement from the delay slot)."""
    labels, addr = {}, base
    for part in parts:
        if isinstance(part, bytes):
            addr += len(part)
        elif isinstance(part, str):
            labels[part] = addr
        else:
            addr += {'iwt': 3, 'ibt': 2, 'br': 2}[part[0]]
    out, addr = b'', base
    for part in parts:
        if isinstance(part, bytes):
            out += part
            addr += len(part)
        elif isinstance(part, str):
            continue
        elif part[0] == 'iwt':
            out += iwt(part[1], labels[part[2]] + (part[3] if len(part) > 3 else 0))
            addr += 3
        elif part[0] == 'ibt':
            out += ibt(part[1], labels[part[2]])
            addr += 2
        else:
            out += branch(part[1], labels[part[2]] - (addr + 2))
            addr += 2
    return out


def cmode(por, reg=5):
    return ibt(reg, por) + frm(reg) + ALT1 + b'\x4e'


def color(value, reg=6):
    return ibt(reg, value) + frm(reg) + b'\x4e'


PLOT = b'\x4c'


def rpix(dst):
    return to(dst) + ALT1 + PLOT


class Library:
    def __init__(self):
        self.cases = []
        self.index = 0

    # The fetch regime and clock selection rotate through the sweeps so that the same
    # functional expectation is exercised from the cold cache, a preloaded cache and
    # plain ROM opcode fetches, at both clock selections.
    def add(self, name, code, rotate=True, every=False, **kw):
        if every:                    # buffer-timing sensitive: all three regimes at both clocks
            for mode in ('cold', 'warm', 'rom'):
                for clsr in (0, 1):
                    self.add('%s_%s_c%d' % (name, mode, clsr), code, rotate=False, mode=mode, clsr=clsr, **kw)
            return None
        i = self.index
        self.index += 1
        if rotate and 'mode' not in kw and 'pbr' not in kw and 'start' not in kw:
            kw['mode'] = ('cold', 'warm', 'rom')[i % 3]
            kw.setdefault('clsr', (i // 3) & 1)
        if kw.get('mode') == 'rom':
            kw.setdefault('start', 0x400)
        base = kw.get('start', 0)
        body = code(base) if callable(code) else code
        self.cases.append(Case(name, body, **kw))
        return self.cases[-1]

    # ---- ALU ---------------------------------------------------------------
    def alu(self):
        specs = [('add', 0x50, 0), ('adc', 0x50, 1), ('sub', 0x60, 0), ('sbc', 0x60, 1), ('cmp', 0x60, 3)]
        for (name, base, alt) in specs:
            k = 0
            for s, q in product(VALUES, VALUES):
                cin = k & 1
                k += 1
                flags = (FLAG_STATES[k % len(FLAG_STATES)] & ~SFR_CY) | (SFR_CY if cin else 0)
                code = frm(1) + to(2) + PREFIX[alt] + bytes([base + 3]) + STOP
                self.add('alu_%s_rr_%04x_%04x' % (name, s, q), code, regs={1: s, 3: q}, sfr=flags)
            for layout, (src, n, dst) in enumerate([(1, 1, 2), (1, 3, 3), (1, 1, 1), (4, 4, 4)]):
                for s in VALUES:
                    for cin in (0, 1):
                        code = frm(src) + to(dst) + PREFIX[alt] + bytes([base + n]) + STOP
                        regs = {src: s}
                        if n != src:
                            regs[n] = 0x0F0F
                        self.add('alu_%s_alias%d_%04x_c%d' % (name, layout, s, cin), code,
                                 regs=regs, sfr=(SFR_CY if cin else 0) | SFR_OV)
            code = PREFIX[alt] + bytes([base + 3]) + STOP        # no TO/FROM: R0 op R3 -> R0
            for s, q in [(0x1234, 0x0F0F), (0xFFFF, 0x0001), (0x7FFF, 0x0001)]:
                self.add('alu_%s_r0_%04x_%04x' % (name, s, q), code, regs={0: s, 3: q}, sfr=SFR_CY)
        for (name, base, alt) in [('add', 0x50, 2), ('adc', 0x50, 3), ('sub', 0x60, 2)]:
            for n, s, cin in product([0, 1, 7, 15], VALUES, (0, 1)):
                code = frm(1) + to(2) + PREFIX[alt] + bytes([base + n]) + STOP
                self.add('alu_%s_imm%d_%04x_c%d' % (name, n, s, cin), code, regs={1: s},
                         sfr=(SFR_CY if cin else 0) | (SFR_Z if n & 1 else 0))

    def logic(self):
        specs = [('and', 0x70, 0), ('bic', 0x70, 1), ('or', 0xC0, 0), ('xor', 0xC0, 1)]
        for (name, base, alt) in specs:
            for s, q in product(VALUES, VALUES):
                code = frm(1) + to(2) + PREFIX[alt] + bytes([base + 3]) + STOP
                self.add('logic_%s_rr_%04x_%04x' % (name, s, q), code, regs={1: s, 3: q},
                         sfr=SFR_CY | SFR_OV if (s ^ q) & 1 else SFR_S)
            for s in VALUES:
                for layout, (src, n, dst) in enumerate([(1, 1, 2), (1, 3, 1)]):
                    code = frm(src) + to(dst) + PREFIX[alt] + bytes([base + n]) + STOP
                    regs = {src: s}
                    if n != src:
                        regs[n] = 0x00FF
                    self.add('logic_%s_alias%d_%04x' % (name, layout, s), code, regs=regs)
        for (name, base, alt) in [('and', 0x70, 2), ('bic', 0x70, 3), ('or', 0xC0, 2), ('xor', 0xC0, 3)]:
            for n, s in product([1, 5, 15], VALUES):
                code = frm(1) + to(2) + PREFIX[alt] + bytes([base + n]) + STOP
                self.add('logic_%s_imm%d_%04x' % (name, n, s), code, regs={1: s}, sfr=SFR_CY | SFR_OV)

    def unary(self):
        ops = [('lsr', 0x03, 0, (0,)), ('rol', 0x04, 0, (0, 1)), ('ror', 0x97, 0, (0, 1)),
               ('asr', 0x96, 0, (0,)), ('div2', 0x96, 1, (0,)), ('not', 0x4F, 0, (0,)),
               ('swap', 0x4D, 0, (0,)), ('sex', 0x95, 0, (0,)), ('lob', 0x9E, 0, (0,)),
               ('hib', 0xC0, 0, (0,))]
        for name, op, alt, cins in ops:
            for s in WIDE:
                for cin in cins:
                    code = frm(1) + to(2) + PREFIX[alt] + bytes([op]) + STOP
                    self.add('unary_%s_%04x_c%d' % (name, s, cin), code, regs={1: s},
                             sfr=(SFR_CY if cin else 0) | SFR_OV)
        for name, base in (('inc', 0xD0), ('dec', 0xE0)):
            for n, s in product([0, 1, 5, 13], [0xFFFF, 0x7FFF, 0x0000, 0x0001, 0x8000]):
                code = bytes([base + n]) + STOP
                self.add('unary_%s_r%d_%04x' % (name, n, s), code, regs={n: s}, sfr=SFR_CY | SFR_OV)
        for r7, r8 in [(0x1234, 0x5678), (0xFF00, 0xFF00), (0x0000, 0x0000), (0x8000, 0x0000),
                       (0x00FF, 0x8000), (0x4000, 0x4000), (0x2000, 0x2000), (0x1000, 0x1000),
                       (0x0F00, 0x0F00), (0x0100, 0x1000)]:
            for dst in (2, 7):
                code = to(dst) + b'\x70' + STOP
                self.add('merge_%04x_%04x_to%d' % (r7, r8, dst), code, regs={7: r7, 8: r8},
                         sfr=SFR_CY)

    def multiply(self):
        k = 0
        for alt, name in ((0, 'mult'), (1, 'umult')):
            for s, q in product(VALUES, VALUES):
                code = frm(1) + to(2) + PREFIX[alt] + bytes([0x83]) + STOP
                self.add('mul_%s_%04x_%04x' % (name, s, q), code, regs={1: s, 3: q},
                         sfr=SFR_CY | SFR_OV, cfgr=0x20 if (k % 5 == 0) else 0, clsr=0)
                k += 1
        for alt, name in ((2, 'mult'), (3, 'umult')):
            for n, s in product([0, 1, 15], VALUES):
                code = frm(1) + to(2) + PREFIX[alt] + bytes([0x80 + n]) + STOP
                self.add('mul_%s_imm%d_%04x' % (name, n, s), code, regs={1: s}, sfr=SFR_CY)
        for alt, name in ((0, 'fmult'), (1, 'lmult')):
            for s, q in product(VALUES, VALUES):
                code = frm(1) + to(2) + PREFIX[alt] + b'\x9f' + STOP
                self.add('mul_%s_%04x_%04x' % (name, s, q), code, regs={1: s, 6: q}, ares=True,
                         sfr=SFR_OV)
        for s, q in [(0x1234, 0x4321), (0x8000, 0x8000), (0x7FFF, 0xFFFF)]:
            code = frm(1) + to(4) + ALT1 + b'\x9f' + STOP            # LMULT, Rd=R4: only the high half stays
            self.add('mul_lmult_r4_%04x_%04x' % (s, q), code, regs={1: s, 6: q}, ares=True)
            code = frm(1) + to(4) + b'\x9f' + STOP                   # FMULT, Rd=R4: documented "unchanged"
            self.add('mul_fmult_r4_%04x_%04x' % (s, q), code, regs={1: s, 6: q, 4: 0x4444},
                     ares=True, finding=F_FMULT_R4)
            code = frm(6) + to(2) + b'\x9f' + STOP                   # source is R6 itself
            self.add('mul_fmult_selfsq_%04x' % s, code, regs={6: s}, ares=True)

    # ---- prefixes, moves ---------------------------------------------------
    def prefixes(self):
        for s, d in [(1, 2), (5, 3), (13, 0), (0, 9), (7, 7)]:
            for v in (0x1234, 0x8000, 0x0000):
                self.add('move_r%d_to_r%d_%04x' % (s, d, v), with_(s) + to(d) + STOP, regs={s: v},
                         sfr=SFR_CY | SFR_Z)
        for d, s in [(2, 1), (3, 9), (0, 5)]:
            for v in (0x0000, 0x007F, 0x0080, 0x00FF, 0x8000, 0xFF80, 0x1234, 0x8081):
                self.add('moves_r%d_from_r%d_%04x' % (d, s, v), with_(d) + frm(s) + STOP,
                         regs={s: v}, sfr=SFR_CY)
        self.add('to_without_from', to(5) + b'\x95' + STOP, regs={0: 0x0080})        # SEX R0 -> R5
        self.add('from_without_to', frm(5) + b'\x95' + STOP, regs={5: 0x0080})       # SEX R5 -> R0
        self.add('with_alu', with_(4) + bytes([0x50 + 3]) + STOP, regs={4: 5, 3: 6})  # ADD R3 -> R4
        self.add('with_then_alt', with_(4) + ALT2 + bytes([0x50 + 3]) + STOP, regs={4: 5})
        # every order of ALTx / FROM / TO in front of the opcode
        orders = [(0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)]
        for alt in (1, 2, 3):
            for order in orders:
                pieces = [PREFIX[alt], frm(1), to(2)]
                code = b''.join(pieces[i] for i in order) + bytes([0x50 + 3]) + STOP
                self.add('prefix_order_alt%d_%d%d%d' % ((alt,) + order), code,
                         regs={1: 0x00F0, 3: 0x0005}, sfr=SFR_CY)
        # the prefix state is consumed by the next ordinary opcode
        self.add('prefix_consumed_by_nop', frm(1) + to(2) + NOP + bytes([0x50 + 3]) + STOP,
                 regs={1: 10, 3: 20, 0: 1})
        self.add('prefix_consumed_by_stw', frm(1) + to(2) + b'\x30' + bytes([0x50 + 3]) + STOP,
                 regs={1: 10, 3: 20, 0: 1})
        self.add('alt_consumed', ALT2 + NOP + bytes([0x50 + 3]) + STOP, regs={0: 1, 3: 20})
        # Bxx keeps the prefixes: the delay slot runs with ALT2/FROM/TO still active
        self.add('branch_keeps_prefix', frm(1) + to(2) + ALT2 + branch(BRA, 0) +
                 bytes([0x50 + 3]) + STOP, regs={1: 0x0100, 3: 7})
        self.add('branch_not_taken_keeps_prefix', frm(1) + to(2) + ALT2 +
                 branch(BEQ, 0) + bytes([0x50 + 3]) + STOP, regs={1: 0x0100, 3: 7})

    # ---- immediates and absolute RAM ---------------------------------------
    def immediates(self):
        for n, v in product([0, 1, 5, 13], [0x00, 0x01, 0x7F, 0x80, 0xFF]):
            self.add('ibt_r%d_%02x' % (n, v), ibt(n, v) + STOP, sfr=SFR_Z | SFR_CY)
        for n, v in product([0, 3, 12], [0x0000, 0x0001, 0x1234, 0x8000, 0xFFFF]):
            self.add('iwt_r%d_%04x' % (n, v), iwt(n, v) + STOP)
        for n in (1, 6, 13):
            self.add('iwt_all_%d' % n, iwt(n, 0xBEEF) + iwt(0, 0x0102) + ibt(2, 0xFE) + STOP)
        ram = [(0x0000, bytes(range(0x11, 0x11 + 0x20))), (0x01FC, bytes([0xA1, 0xA2, 0xA3, 0xA4])),
               (0x3000, bytes([0x5A, 0xB6, 0x77, 0x88])), (0xFFFC, bytes([1, 2, 3, 4]))]
        for n, kk in product([1, 4], [0x00, 0x01, 0x08, 0xFE, 0xFF]):
            self.add('lms_r%d_%02x' % (n, kk), lms(n, kk) + STOP, ram=ram)
        for n, kk in product([1, 9], [0x00, 0x02, 0x7F, 0xFF]):
            self.add('sms_r%d_%02x' % (n, kk), sms(n, kk) + STOP, regs={n: 0xCAFE}, ram=ram)
        for n, addr in product([2, 7], [0x0000, 0x0001, 0x0010, 0x3000, 0x3001, 0xFFFE, 0xFFFF]):
            self.add('lm_r%d_%04x' % (n, addr), lm(n, addr) + STOP, ram=ram)
        for n, addr in product([2, 7], [0x0000, 0x0001, 0x0010, 0x3000, 0x3001, 0xFFFE, 0xFFFF]):
            self.add('sm_r%d_%04x' % (n, addr), sm(n, addr) + STOP, regs={n: 0xD00D}, ram=ram)

    # ---- branches, jumps, loops -------------------------------------------
    def branches(self):
        names = {BRA: 'bra', BGE: 'bge', BLT: 'blt', BNE: 'bne', BEQ: 'beq', BPL: 'bpl',
                 BMI: 'bmi', BCC: 'bcc', BCS: 'bcs', BVC: 'bvc', BVS: 'bvs'}
        for op, name in names.items():
            for flags in range(16):
                sfr = ((flags & 1) << 1) | ((flags & 2) << 1) | ((flags & 4) << 1) | ((flags & 8) << 1)
                # branch, delay slot INC R1, skipped INC R2, target INC R3, STOP
                code = branch(op, 2) + inc(1) + inc(2) + inc(3) + STOP
                self.add('branch_%s_zcsv%x' % (name, flags), code, sfr=sfr)
        # backward displacement: INC R2 three times through a backward BNE
        self.add('branch_backward', lambda b: asm(b, ibt(1, 3), 'top', inc(2), dec(1), ('br', BNE, 'top'),
                                                  NOP, STOP))
        self.add('branch_zero_displacement', branch(BRA, 0) + inc(1) + inc(2) + STOP)
        self.add('branch_forward_far', branch(BRA, 20) + inc(1) + inc(2) * 20 + inc(3) + STOP)
        self.add('jmp_r8_delay_slot', lambda b: asm(b, ('iwt', 8, 'dest'), b'\x98', inc(1), inc(2),
                                                    'dest', inc(3), STOP))
        self.add('jmp_r13_delay_slot', lambda b: asm(b, ('iwt', 13, 'dest'), b'\x9d', inc(1), inc(2),
                                                     'dest', inc(3), STOP))
        self.add('iwt_r15_jump', lambda b: asm(b, ('iwt', 15, 'dest'), inc(1), inc(2), 'dest', inc(3), STOP))
        self.add('ibt_r15_jump', lambda b: asm(b, ('ibt', 15, 'dest'), inc(1), inc(2), 'dest', inc(3), STOP),
                 rotate=False)
        # LJMP: bank in Rn, address in Rs; the delay slot comes from the old bank
        far = inc(4) + inc(5) + inc(6) + STOP
        self.add('ljmp_bank1', frm(9) + ALT1 + b'\x98' + inc(1) + inc(2) + STOP, regs={8: 1, 9: 0x0000},
                 rom=[(0x8000, far)], rotate=False)
        self.add('ljmp_bank1_r11', frm(9) + ALT1 + b'\x9b' + inc(1) + STOP, regs={11: 1, 9: 0x0004},
                 rom=[(0x8000, bytes(4) + far)], rotate=False)
        self.add('ljmp_bank_masked', frm(9) + ALT1 + b'\x98' + inc(1) + STOP, regs={8: 0x81, 9: 0x0000},
                 rom=[(0x8000, far)], rotate=False)
        # linear banks 40-5F: bank 41 address 0010 is ROM offset 10010
        self.add('ljmp_bank41', frm(9) + ALT1 + b'\x98' + inc(1) + STOP, regs={8: 0x41, 9: 0x0010},
                 rom=[(0x10010, far)], rotate=False)
        self.add('ljmp_bank5f_wrap', frm(9) + ALT1 + b'\x98' + inc(1) + STOP, regs={8: 0x5F, 9: 0x0010},
                 rom=[(0x0010, far)], rotate=False)
        # LOOP: R12 decrements, R13 is the loop target, delay slot after LOOP
        for count in (1, 2, 5, 17):
            self.add('loop_count%d' % count, lambda b, count=count: asm(
                b, ('iwt', 13, 'top'), iwt(12, count), 'top', inc(1), b'\x3c', inc(2), inc(3), STOP))
        self.add('loop_wraps_from_zero', lambda b: asm(
            b, ('iwt', 13, 'top'), iwt(12, 0), 'top', inc(1), b'\x3c', inc(2), STOP), sfr=SFR_Z,
            regs={12: 0})
        # LINK n: R11 = address of the next opcode + n
        for n in (1, 2, 3, 4):
            self.add('link_%d' % n, bytes([0x90 + n]) + STOP)
        self.add('link_call_return', lambda b: asm(
            b, bytes([0x94]), ('iwt', 8, 'sub'), b'\x98', inc(1), inc(2), STOP, 'sub', inc(3), b'\x9b', NOP, STOP))

    # ---- ROM buffer ---------------------------------------------------------
    def rom_buffer(self):
        table = bytes([0x80, 0x7F, 0x34, 0x12, 0xFF, 0x01, 0xA5, 0x5A])
        rom = [(DATA, table), (0x8000 + 0x10, bytes([0xC3, 0x3C])), (0x10000 + 0x1000, bytes([0x9D, 0xD9]))]
        for alt, name in enumerate(('getb', 'getbh', 'getbl', 'getbs')):
            for i in range(len(table)):
                for dst_init in (0x0000, 0xBEEF):
                    code = iwt(14, DATA + i) + frm(5) + to(5) + PREFIX[alt] + b'\xef' + STOP
                    self.add('rombuf_%s_%d_%04x' % (name, i, dst_init), code, regs={5: dst_init},
                             rom=rom, sfr=SFR_CY | SFR_Z)
        code = (iwt(14, DATA) + to(1) + b'\xef' + inc(14) + to(2) + b'\xef' + inc(14) + to(3) + b'\xef' +
                dec(14) + dec(14) + to(4) + b'\xef' + STOP)
        self.add('rombuf_walk', code, rom=rom, every=True)
        # fullsnes: GETBH/GETBL leave the other byte of Rd unchanged; the core (like ares) takes it from Rs
        for alt, name in ((1, 'getbh'), (2, 'getbl')):
            code = iwt(14, DATA) + frm(4) + to(5) + PREFIX[alt] + b'\xef' + STOP
            self.add('rombuf_%s_rs_differs_from_rd' % name, code, regs={4: 0x1111, 5: 0x2222}, rom=rom,
                     finding=F_GETB_OTHER_BYTE, rotate=False)
        # ROMBR through ROMB (ALT3 DF): linear bank 40/41 and LoROM banks 0/1
        for bank, r14 in [(0x40, DATA + 2), (0x01, 0x0010), (0x41, 0x1000), (0x00, DATA)]:
            code = ibt(5, bank) + frm(5) + ALT3 + b'\xdf' + iwt(14, r14) + to(6) + b'\xef' + STOP
            self.add('romb_bank%02x' % bank, code, rom=rom)
        # documented: after ROMBR changes, a following GETxx still returns [old ROMBR:R14]
        code = iwt(14, DATA) + ibt(5, 0x01) + frm(5) + ALT3 + b'\xdf' + to(6) + b'\xef' + STOP
        self.add('romb_old_bank_after_change', code, rom=rom, every=True)
        # GETC loads COLOR; PLOT it into a 4bpp bitmap and read it back
        for por in (0x00, 0x04, 0x08 | 0x10, 0x04 | 0x08 | 0x10):
            code = (iwt(14, DATA + 6) + cmode(por) + b'\xdf' + ibt(1, 3) + ibt(2, 4) + PLOT + ibt(1, 3) +
                    rpix(9) + STOP)
            self.add('getc_plot_por%02x' % por, code, rom=rom, scmr=0x19)
        self.add('rombuf_table_sum', lambda b: asm(
            b, ('iwt', 13, 'top'), iwt(14, DATA), iwt(12, 8), ibt(1, 0), 'top', to(0), b'\xef',
            with_(1), bytes([0x50]), inc(14), b'\x3c', NOP, STOP),
            rom=rom, resume=(40, 97, 211, 380, 777, 1500))

    # ---- RAM ---------------------------------------------------------------
    def ram_access(self):
        ram = [(0x0100, bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88])),
               (0x0200, bytes([0xF0, 0xE1, 0xD2, 0xC3])), (0x10100, bytes([0xB1, 0xB2, 0xB3, 0xB4]))]
        for addr in (0x0100, 0x0101, 0x0102, 0x0107, 0x0200, 0xFFFF):
            self.add('ldw_%04x' % addr, to(2) + b'\x41' + STOP, regs={1: addr}, ram=ram)
            self.add('ldb_%04x' % addr, to(2) + ALT1 + b'\x41' + STOP, regs={1: addr, 2: 0xFFFF}, ram=ram)
            self.add('stw_%04x' % addr, frm(2) + b'\x31' + STOP, regs={1: addr, 2: 0xA1B2}, ram=ram)
            self.add('stb_%04x' % addr, frm(2) + ALT1 + b'\x31' + STOP, regs={1: addr, 2: 0xA1B2}, ram=ram)
        self.add('sbk_after_stw', frm(2) + b'\x31' + frm(3) + b'\x90' + STOP, regs={1: 0x0300, 2: 1, 3: 0x7777}, every=True)
        self.add('sbk_after_ldw', to(4) + b'\x41' + frm(3) + b'\x90' + STOP, regs={1: 0x0104, 3: 0x7777}, ram=ram, every=True)
        self.add('sbk_odd', frm(2) + b'\x31' + frm(3) + b'\x90' + STOP, regs={1: 0x0301, 2: 1, 3: 0x7788}, every=True)
        for bank in (0, 1):
            code = ibt(5, bank) + frm(5) + ALT2 + b'\xdf' + to(2) + b'\x41' + frm(2) + b'\x33' + STOP
            self.add('ramb_%d' % bank, code, regs={1: 0x0100, 3: 0x0400}, ram=ram)
        self.add('ramb_masks_bit0', ibt(5, 0xFF) + frm(5) + ALT2 + b'\xdf' + to(2) + b'\x41' + STOP,
                 regs={1: 0x0100}, ram=ram)
        self.add('ram_copy_words', lambda b: asm(
            b, iwt(1, 0x0100), iwt(2, 0x0600), iwt(12, 8), ('iwt', 13, 'top'), 'top', to(5), b'\x41',
            frm(5), b'\x32', inc(1), inc(1), inc(2), inc(2), b'\x3c', NOP, STOP),
            ram=ram, resume=(30, 71, 140, 255, 410, 900, 1600))
        self.add('ram_store_load_same', frm(2) + b'\x31' + to(4) + b'\x41' + frm(2) + ALT1 + b'\x31' + to(5) +
                 ALT1 + b'\x41' + STOP, regs={1: 0x0500, 2: 0x1234}, every=True)
        self.add('ram_back_to_back_stw', frm(2) + b'\x31' + frm(3) + b'\x32' + frm(2) + b'\x33' + STOP,
                 regs={1: 0x0500, 2: 0x1234, 3: 0xABCD}, every=True)

    # ---- pixels ------------------------------------------------------------
    def pixels(self):
        colours = {0: [0x00, 0x01, 0x02, 0x03, 0x07], 1: [0x00, 0x05, 0x0F, 0x9A], 3: [0x00, 0x55, 0xFF, 0xA0]}
        pors = {0: [0x00, 0x01, 0x02, 0x03, 0x10, 0x11], 1: [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x10, 0x11],
                3: [0x00, 0x01, 0x02, 0x03, 0x10, 0x11]}
        count = 0
        for md, ht in product((0, 1, 3), (0, 1, 2, 3)):
            scmr = 0x18 | md | ((ht & 1) << 2) | ((ht >> 1) << 5)
            for colour in colours[md]:
                por = pors[md][count % len(pors[md])]
                count += 1
                setup = cmode(por) + color(colour)
                row = setup + ibt(1, 4) + ibt(2, 5) + (PLOT * 16)
                col = setup + ibt(1, 9) + ibt(2, 6) + (PLOT + dec(1) + inc(2)) * 16
                diag = setup + ibt(1, 20) + ibt(2, 20) + (PLOT + inc(2)) * 12
                edge = (setup + ibt(1, 0) + ibt(2, 0) + PLOT + ibt(1, 255) + ibt(2, 255) + PLOT +
                        ibt(1, 127) + ibt(2, 128) + PLOT + PLOT)
                readback = ibt(1, 6) + ibt(2, 5) + rpix(9) + ibt(1, 13) + rpix(10)
                for label, body in (('row', row), ('col', col), ('diag', diag), ('edge', edge)):
                    code = body + readback + STOP
                    if label == 'edge':
                        code = body + ibt(1, 255) + ibt(2, 255) + rpix(9) + STOP
                    self.add('plot_md%d_ht%d_c%02x_por%02x_%s' % (md, ht, colour, por, label), code,
                             scmr=scmr, scbr=count & 3)
        for md in (0, 1):
            code = (cmode(0x03) + color(0xA5) + ibt(1, 0) + ibt(2, 0) + (PLOT * 8) + ibt(1, 0) + ibt(2, 1) +
                    (PLOT * 8) + ibt(1, 0) + ibt(2, 1) + rpix(9) + STOP)
            self.add('plot_dither_md%d' % md, code, scmr=0x18 | md)
        code = cmode(0x03) + color(0xA5) + ibt(1, 0) + ibt(2, 0) + (PLOT * 8) + ibt(1, 1) + rpix(9) + STOP
        self.add('plot_dither_ignored_8bpp', code, scmr=0x18 | 3)
        for md in (0, 1, 3):
            code = (color(0) + ibt(1, 2) + ibt(2, 2) + PLOT + PLOT + ibt(1, 2) + rpix(9) + STOP)
            self.add('plot_transparent_md%d' % md, code, scmr=0x18 | md)
            code = (color(3) + ibt(1, 2) + ibt(2, 2) + PLOT + color(0) + cmode(1) + ibt(1, 2) + PLOT +
                    ibt(1, 2) + rpix(9) + STOP)
            self.add('plot_overwrite_md%d' % md, code, scmr=0x18 | md)
        # documented-difference candidates -----------------------------------
        # 2bpp transparency looks at the lower two bits of COLOR (fullsnes), the core looks at four
        for colour in (0x04, 0x0C, 0x08):
            # first a visible pixel (colour 3), then colour 04/0C/08 over it: documented transparent
            code = (color(3) + ibt(1, 1) + ibt(2, 1) + PLOT + color(colour) + ibt(1, 1) + PLOT + ibt(1, 1) +
                    rpix(9) + STOP)
            self.add('plot_2bpp_transparent_low2_c%02x' % colour, code, scmr=0x18, finding=F_TRANSPARENT_2BPP,
                     rotate=False)
        # high-nibble: the incoming LSB is replaced by the incoming MSB, the whole byte goes to COLOR
        for first, data in ((0x00, 0x5A), (0x33, 0xC7), (0xF0, 0x2E)):
            code = (color(first) + cmode(0x04) + color(data, 7) + ibt(1, 1) + ibt(2, 1) + PLOT + ibt(1, 1) +
                    rpix(9) + STOP)
            self.add('plot_highnibble_8bpp_%02x_%02x' % (first, data), code, scmr=0x18 | 3,
                     finding=F_HIGH_NIBBLE, rotate=False)
        # freeze-high (OBJ layout): only the low nibble of COLOR changes
        for first, data in ((0x30, 0x5A), (0xC0, 0x07)):
            code = (color(first) + cmode(0x18) + color(data, 7) + ibt(1, 1) + ibt(2, 1) + PLOT + ibt(1, 1) +
                    rpix(9) + STOP)
            self.add('plot_freezehigh_%02x_%02x' % (first, data), code, scmr=0x18 | 3, rotate=False)
        code = (color(0xA0) + cmode(0x18) + ibt(1, 1) + ibt(2, 1) + PLOT + ibt(1, 1) + rpix(9) + STOP)
        self.add('plot_freezehigh_transparent_low4', code, scmr=0x18 | 3, rotate=False)

    # ---- cache, CBR --------------------------------------------------------
    def cache(self):
        for start in (0x0000, 0x000F, 0x0123, 0x0FFE, 0x7FF0, 0xC39F):
            self.add('cache_cbr_%04x' % start, CACHE + inc(1) + STOP, start=start)
        # fullsnes example: CBR C3A0 shows GSU C3A0.. at SNES 32A0.. ((CBR AND 1FFh)+3100h)
        self.add('cache_window_c3a0', CACHE + (inc(1) * 40) + STOP, start=0xC39F,
                 cache_check=[(0xC3A0, 32)])
        self.add('cache_window_0110', CACHE + (inc(1) * 60) + STOP, start=0x010F,
                 cache_check=[(0x0110, 48)])
        self.add('cache_window_0200', CACHE + (inc(1) * 60) + STOP, start=0x01FF,
                 cache_check=[(0x0200, 48)])
        self.add('cache_window_0100', CACHE + (inc(1) * 60) + STOP, start=0x00FF,
                 cache_check=[(0x0100, 48)])
        # the S-CPU writes the cache; the last byte of a line validates it; it is executed instead of ROM
        cache = bytearray(512)
        prog = inc(1) + inc(1) + inc(1) + STOP
        cache[0:len(prog)] = prog
        self.add('cache_cpu_written_code', STOP, mode='warm', cache=bytes(cache), timed=True)
        rom_code = branch(BRA, 0x0E) + NOP
        cache = bytearray(512)
        cache[0:len(rom_code)] = rom_code
        prog = ibt(2, 0x42) + STOP
        cache[0x10:0x10 + len(prog)] = prog
        self.add('cache_cpu_written_second_line', rom_code, mode='warm', cache=bytes(cache))
        far = inc(4) + inc(5) + STOP
        self.add('ljmp_sets_cbr', frm(9) + ALT1 + b'\x98' + inc(1) + STOP, regs={8: 1, 9: 0x0013},
                 rom=[(0x8000, bytes(0x13) + far)])
        # documented: CACHE empties all lines even when CBR stays the same (the core keeps them)
        cache = bytearray(512)
        cache[0:6] = CACHE + NOP + inc(1) + STOP + NOP
        self.add('cache_flush_same_cbr', CACHE + NOP + inc(2) + STOP, mode='warm', cache=bytes(cache),
                 finding=F_CACHE_SAME_CBR)
        self.add('cache_cold_fill_lines', inc(1) * 40 + STOP, mode='cold', timed=2)
        self.add('cache_cold_fill_lines_clsr1', inc(1) * 40 + STOP, mode='cold', timed=2, clsr=1)

    # ---- STOP, IRQ, restart ------------------------------------------------
    def stop(self):
        self.add('stop_irq_unmasked', inc(1) + STOP, mode='cold')
        self.add('stop_irq_masked', inc(1) + STOP, cfgr=0x80, finding=F_IRQ_MASKED, mode='cold')
        self.add('stop_r15', NOP + NOP + STOP, mode='cold', start=0x0010, timed=2)
        for tag, pre in (('with', with_(1)), ('alt1', ALT1), ('alt2', ALT2), ('alt3', ALT3), ('from', frm(1)),
                         ('to', to(1))):
            self.add('stop_clears_prefix_' + tag, pre + STOP, mode='cold')
        # a restart after STOP starts with clean prefixes (WITH R1 before STOP must not survive)
        self.add('restart_prefix_cleared', with_(1) + STOP + NOP + bytes([0x53]) + STOP, mode='cold',
                 regs={0: 7, 1: 100, 3: 5}, jobs=[{}, {}])
        self.add('stop_prefetch_not_executed', frm(1) + to(2) + STOP + inc(5), regs={1: 5}, mode='cold')
        self.add('restart_after_stop', inc(1) + STOP + NOP + inc(2) + STOP, mode='cold', jobs=[{}, {}, {}])
        self.add('restart_new_registers', inc(1) + STOP, mode='cold', jobs=[{}, {15: 0, 1: 5}, {15: 0, 1: 0xFFFF}])
        self.add('restart_after_stop_masked', inc(1) + STOP + NOP + inc(2) + STOP, cfgr=0x80,
                 finding=F_IRQ_MASKED, mode='cold', jobs=[{}, {}])
        self.add('nops_from_rom', NOP * 100 + STOP, mode='rom')
        self.add('nops_cold_cache', NOP * 100 + STOP, mode='cold', timed=2)
        self.add('nops_cold_cache_clsr1', NOP * 100 + STOP, mode='cold', timed=2, clsr=1)
        self.add('ram_code_pbr70', inc(1) + inc(2) + STOP, pbr=0x70, start=0x0000)
        self.add('ram_code_pbr71_far', inc(1) + inc(2) + STOP, pbr=0x71, start=0x0400)
        self.add('ram_code_pbr70_ldw', to(2) + b'\x41' + STOP, pbr=0x70, start=0x0400, regs={1: 0x0400})

    # ---- timing: cached, uncached and multiplier prices -------------------
    def timing(self):
        forms = [
            ('stop_only', STOP),
            ('nop', NOP + STOP),
            ('inc', inc(1) + STOP),
            ('add_r', frm(1) + to(2) + b'\x53' + STOP),
            ('add_imm', frm(1) + to(2) + ALT2 + b'\x55' + STOP),
            ('adc', frm(1) + to(2) + ALT1 + b'\x53' + STOP),
            ('and', b'\x73' + STOP),
            ('not', b'\x4f' + STOP),
            ('swap', b'\x4d' + STOP),
            ('lsr', b'\x03' + STOP),
            ('ibt', ibt(1, 5) + STOP),
            ('iwt', iwt(1, 0x1234) + STOP),
            ('merge', b'\x70' + STOP),
            ('move', with_(1) + to(2) + STOP),
            ('cmode', frm(5) + ALT1 + b'\x4e' + STOP),
            ('color', frm(5) + b'\x4e' + STOP),
            ('ramb', frm(0) + ALT2 + b'\xdf' + STOP),
            ('romb', frm(0) + ALT3 + b'\xdf' + STOP),
            ('link', b'\x93' + STOP),
            ('branch_taken', branch(BRA, 1) + NOP + NOP + STOP),
            ('branch_not_taken', branch(BNE, 1) + NOP + NOP + STOP),
            ('jmp', lambda b: asm(b, ('iwt', 8, 'dest'), b'\x98', NOP, NOP, 'dest', STOP)),
            ('mult', frm(1) + to(2) + b'\x83' + STOP),
            ('umult', frm(1) + to(2) + ALT1 + b'\x83' + STOP),
            ('mult_imm', frm(1) + to(2) + ALT2 + b'\x85' + STOP),
            ('umult_imm', frm(1) + to(2) + ALT3 + b'\x85' + STOP),
            ('fmult', frm(1) + to(2) + b'\x9f' + STOP),
            ('lmult', frm(1) + to(2) + ALT1 + b'\x9f' + STOP),
            ('loop', lambda b: asm(b, ('iwt', 13, 'top'), iwt(12, 3), 'top', inc(1), b'\x3c', NOP, STOP)),
        ]
        for name, code in forms:
            for mode, clsr, cfgr in [(m, c, g) for m in ('warm', 'rom', 'cold') for c in (0, 1) for g in (0, 0x20)]:
                if cfgr and (clsr or 'mult' not in name):
                    continue          # fullsnes: MS0 must be zero at 21 MHz; only multiplies care
                self.add('timing_%s_%s_clsr%d_ms%d' % (name, mode, clsr, 1 if cfgr else 0), code,
                         mode=mode, clsr=clsr, cfgr=cfgr, timed=2 if mode == 'cold' else 1,
                         regs={1: 0x0203, 3: 5, 6: 0x0300})

    # ---- documented cycle ranges (fullsnes lists a range or a figure per opcode) --------------
    def ranged(self, name, pre, op, lo, hi, finding=0, **kw):
        for clsr in (0, 1):
            base = self.add('range_%s_base_clsr%d' % (name, clsr), pre + STOP, mode='warm', clsr=clsr, **kw)
            self.add('range_%s_clsr%d' % (name, clsr), pre + op + STOP, mode='warm', clsr=clsr, base=base,
                     cycles=(lo, hi), finding=finding, **kw)

    def ranges(self):
        rom = [(DATA, bytes([0x80, 0x7F, 0x34, 0x12, 0xFF, 0x01, 0xA5, 0x5A]))]
        for tag, pre in (('now', iwt(14, DATA)), ('late', iwt(14, DATA) + NOP * 8)):
            self.ranged('getb_' + tag, pre, b'\xef', 1, 6, rom=rom)
            self.ranged('getbh_' + tag, pre, ALT1 + b'\xef', 2, 6, rom=rom)
            self.ranged('getbl_' + tag, pre, ALT2 + b'\xef', 2, 6, rom=rom)
            self.ranged('getbs_' + tag, pre, ALT3 + b'\xef', 2, 6, rom=rom)
            self.ranged('getc_' + tag, pre, b'\xdf', 1, 6, rom=rom)
        addr = iwt(1, 0x0100)
        self.ranged('stb', addr, ALT1 + b'\x31', 2, 5)
        self.ranged('stw', addr, b'\x31', 1, 6)
        self.ranged('stw_after_stw', addr + b'\x31', b'\x31', 1, 6, finding=F_LOAD_FIGURES)
        self.ranged('stb_after_stb', addr + ALT1 + b'\x31', ALT1 + b'\x31', 2, 5)
        self.ranged('sm', addr, sm(2, 0x0200), 4, 9)
        self.ranged('sms', addr, sms(2, 0x10), 3, 8)
        self.ranged('sbk', addr + b'\x31' + NOP * 10, b'\x90', 1, 6)
        pix = color(5) + ibt(1, 0) + ibt(2, 0)
        self.ranged('plot_first', pix, PLOT, 1, 48, scmr=0x19, no_ram=True)
        self.ranged('plot_next_tile', pix + PLOT + ibt(1, 8), PLOT, 1, 48, scmr=0x19, no_ram=True)
        self.ranged('rpix_idle', pix, ALT1 + PLOT, 20, 74, scmr=0x19, no_ram=True)
        self.ranged('rpix_after_plot', pix + PLOT + ibt(1, 0), ALT1 + PLOT, 20, 74, scmr=0x19, no_ram=True)
        self.ranged('rpix_2bpp', pix + PLOT + ibt(1, 0), ALT1 + PLOT, 20, 74, scmr=0x18, no_ram=True)
        # fullsnes also gives single figures for the RAM loads; the conditions behind them are
        # not stated, so a difference is reported as an observation, not as a defect
        ram = [(0x0100, bytes([1, 2, 3, 4]))]
        self.ranged('ldb', addr, ALT1 + b'\x41', 6, 6, finding=F_LOAD_FIGURES, ram=ram)
        self.ranged('ldw', addr, b'\x41', 7, 7, finding=F_LOAD_FIGURES, ram=ram)
        self.ranged('lm', addr, lm(2, 0x0100), 11, 11, finding=F_LOAD_FIGURES, ram=ram)
        self.ranged('lms', addr, lms(2, 0x80), 10, 10, finding=F_LOAD_FIGURES, ram=ram)
        # a PLOT left in the pixel cache when the job stops is not in Game Pak RAM yet
        self.add('plot_pending_at_stop', color(5) + ibt(1, 2) + ibt(2, 2) + PLOT + STOP, scmr=0x19,
                 mode='cold', finding=F_PIXEL_AT_STOP)

    # ---- save/resume sweeps: dense resume points so queued stores, ROM reads, pixels and
    # multiplies are all caught mid-flight, in every fetch regime at both clocks ----------------
    def resume_sweeps(self):
        sweep = tuple(range(6, 180, 6))
        rom = [(DATA, bytes([0x80, 0x7F, 0x34, 0x12, 0xFF, 0x01, 0xA5, 0x5A]))]
        self.add('resume_ram_stores', iwt(1, 0x0200) + frm(2) + b'\x31' + frm(3) + ALT1 + b'\x31' + inc(1) +
                 frm(2) + b'\x31' + to(4) + b'\x41' + to(5) + ALT1 + b'\x41' + STOP,
                 regs={2: 0x1234, 3: 0xAB}, every=True, resume=sweep)
        self.add('resume_rom_buffer', iwt(14, DATA) + to(1) + b'\xef' + inc(14) + frm(2) + to(2) + ALT1 + b'\xef' +
                 inc(14) + to(3) + ALT3 + b'\xef' + STOP, rom=rom, every=True, resume=sweep)
        self.add('resume_pixels', color(5) + ibt(1, 6) + ibt(2, 3) + PLOT * 5 + ibt(1, 30) + PLOT + rpix(9) + STOP,
                 scmr=0x19, every=True, resume=sweep)
        self.add('resume_multiply', frm(1) + to(2) + b'\x9f' + frm(2) + to(3) + ALT1 + b'\x9f' + frm(3) + to(4) +
                 b'\x83' + STOP, regs={1: 0x4321, 6: 0x1234}, every=True, resume=sweep)
        self.add('resume_branch_delay', branch(BEQ, 2) + inc(1) + inc(2) + inc(3) + b'\x98' + STOP,
                 sfr=SFR_Z, every=True, resume=sweep[:10])

    # ---- longer authored programs ------------------------------------------
    def programs(self):
        blob = bytes((i * 37 + 11) & 0xFF for i in range(64))
        self.add('prog_rom_checksum', lambda b: asm(
            b, ('iwt', 13, 'top'), iwt(14, 0x3000), iwt(12, 64), ibt(1, 0), 'top', to(0), b'\xef', with_(1),
            bytes([0x50]), inc(14), b'\x3c', NOP, STOP),
            rom=[(0x3000, blob)], resume=(20, 55, 180, 400, 777, 1400, 3000, 5000), mode='cold')
        a = [0x4000, 0x2000, 0xE000, 0x1234, 0x7FFF, 0x8001, 0x0100, 0x0001]
        v = [0x1000, 0x4000, 0x4000, 0xFFFF, 0x0002, 0x7FFF, 0x0100, 0x8000]
        ram = [(0x0100, b''.join(x.to_bytes(2, 'little') for x in a)),
               (0x0200, b''.join(x.to_bytes(2, 'little') for x in v))]

        def dot(base):
            return asm(base, ('iwt', 13, 'top'), iwt(1, 0x0100), iwt(2, 0x0200), iwt(12, 8), ibt(7, 0),
                       'top', to(0), b'\x41', to(6), b'\x42', frm(0), to(3), b'\x9f', with_(7), bytes([0x53]),
                       inc(1), inc(1), inc(2), inc(2), b'\x3c', NOP, STOP)
        self.add('prog_fmult_dot', dot, ram=ram, cfgr=0, clsr=0, mode='cold', ares=True,
                 resume=(15, 80, 160, 300, 600, 1100))
        self.add('prog_fmult_dot_clsr1', dot, ram=ram, clsr=1, mode='cold', ares=True)
        self.add('prog_fmult_dot_ms0', dot, ram=ram, cfgr=0x20, clsr=0, mode='cold', ares=True,
                 resume=(50, 333))

        def draw(base):
            return asm(base, cmode(1), color(0x0B), ibt(1, 10), ibt(2, 10), ibt(12, 24), ('iwt', 13, 'top'),
                       'top', PLOT, inc(2), dec(1), b'\x3c', NOP,
                       ibt(1, 40), ibt(2, 2), (PLOT + dec(1) + inc(2)) * 30,
                       ibt(1, 10), ibt(2, 10), rpix(9), ibt(1, 9), ibt(2, 11), rpix(10), STOP)
        self.add('prog_draw_4bpp', draw, scmr=0x19, scbr=1, mode='cold',
                 resume=(100, 333, 999, 1777, 3000, 4800, 6500))
        self.add('prog_draw_obj_8bpp', draw, scmr=0x3B, scbr=2, mode='cold', resume=(500, 2500))
        self.add('prog_odd_addresses', lambda b: (
            iwt(1, 0x0101) + iwt(2, 0x0301) + to(3) + ALT1 + b'\x41' + frm(3) + ALT1 + b'\x32' + inc(1) + inc(2) +
            to(3) + b'\x41' + frm(3) + b'\x90' + STOP), ram=[(0x0100, bytes([1, 2, 3, 4, 5, 6]))], mode='cold',
            resume=(30, 90, 150))
        self.add('prog_lookup_store', lambda b: asm(
            b, ('iwt', 13, 'top'), ibt(5, 0x40), frm(5), ALT3, b'\xdf', iwt(14, 0x2000), iwt(12, 8), iwt(1, 0x0400),
            'top', to(0), b'\xef', frm(0), ALT1, b'\x31', inc(1), inc(14), b'\x3c', NOP, STOP),
            rom=[(DATA, bytes(range(0x80, 0x88)))], mode='cold', resume=(22, 70, 190, 400))

    def random_programs(self):
        self.cases.extend(random_programs())

    def build(self):
        for family in (self.alu, self.logic, self.unary, self.multiply, self.prefixes,
                       self.immediates, self.branches, self.rom_buffer, self.ram_access,
                       self.pixels, self.cache, self.stop, self.timing, self.ranges, self.resume_sweeps, self.programs, self.random_programs):
            family()
        return self.cases


def build_cases():
    return Library().build()
