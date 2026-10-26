"""Seeded random GSU programs built only from well-formed, documented instruction templates.

A fixed xorshift generator (not the random module, whose algorithms may change between Python
versions) assembles straight-line code with FROM/TO/ALT prefixes in random order, immediate
loads, multiplies, ROM-buffer reads, RAM access through pointer registers and forward
conditional branches that skip whole instructions (with their delay slot). The independent
model predicts the final state; the core must agree on every register, flag and RAM byte.
Two families keep the model's direct pixel writes comparable with the real pixel cache:
one has RAM access but no pixel opcodes, the other has pixel opcodes and no RAM access."""
from tools.snes_superfx_case import Case
from tools.snes_superfx_model import (ALT1, ALT2, ALT3, PREFIX, STOP, branch, frm, ibt, iwt, lm, lms, sm,
                                      sms, to, with_)

SCRATCH = 0x6000          # RAM scratch area, clear of the bitmap (bitmap uses < 0x4800 here)
DATA = 0x2000


class Rng:
    def __init__(self, seed):
        self.state = (seed * 2654435761 + 12345) & 0xFFFFFFFF or 1

    def next(self):
        x = self.state
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        self.state = x
        return x

    def n(self, k):
        return self.next() % k

    def pick(self, seq):
        return seq[self.n(len(seq))]

    def word(self):
        return self.next() & 0xFFFF


DST = [0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 13, 14]          # never the pointer registers or R15
SRC = DST + [9, 10, 11]
POINTERS = [9, 10, 11]
ALU = [(0x50, 0, 'reg'), (0x50, 1, 'reg'), (0x50, 2, 'imm'), (0x50, 3, 'imm'),
       (0x60, 0, 'reg'), (0x60, 1, 'reg'), (0x60, 2, 'imm'), (0x60, 3, 'reg'),
       (0x70, 0, 'reg'), (0x70, 1, 'reg'), (0x70, 2, 'imm'), (0x70, 3, 'imm'),
       (0xC0, 0, 'reg'), (0xC0, 1, 'reg'), (0xC0, 2, 'imm'), (0xC0, 3, 'imm')]
UNARY = [(0x03, 0), (0x04, 0), (0x97, 0), (0x96, 0), (0x96, 1), (0x4F, 0), (0x4D, 0), (0x95, 0), (0x9E, 0),
         (0xC0, 0), (0x70, 0)]
ONE_BYTE = [b'\x01', b'\x03', b'\x04', b'\x4f', b'\x4d', b'\x95', b'\xd1', b'\xd2', b'\xe1', b'\xe3',
            b'\x97', b'\x96', b'\x9e', b'\xc0', b'\x53', b'\x65', b'\x73', b'\xc3']


def prefixes(rng, src, dst, alt):
    pieces = []
    if src is not None:
        pieces.append(frm(src))
    if dst is not None:
        pieces.append(to(dst))
    if alt:
        pieces.append(PREFIX[alt])
    for i in range(len(pieces) - 1, 0, -1):
        j = rng.n(i + 1)
        pieces[i], pieces[j] = pieces[j], pieces[i]
    return b''.join(pieces)


def alu(rng):
    base, alt, form = rng.pick(ALU)
    n = rng.pick(SRC) if form == 'reg' else rng.n(16)
    if base in (0x70, 0xC0) and n == 0:
        n = 1 + rng.n(15) if form == 'imm' else rng.pick(SRC[1:])
    return prefixes(rng, rng.pick(SRC), rng.pick(DST), alt) + bytes([base + n])


def unary(rng):
    op, alt = rng.pick(UNARY)
    return prefixes(rng, rng.pick(SRC), rng.pick(DST), alt) + bytes([op])


def incdec(rng):
    return bytes([rng.pick((0xD0, 0xE0)) + rng.pick(DST)])


def multiply(rng):
    kind = rng.n(6)
    src, dst = rng.pick(SRC), rng.pick(DST)
    if kind < 4:
        alt = (0, 1, 2, 3)[kind]
        return prefixes(rng, src, dst, alt) + bytes([0x80 + (rng.pick(SRC) if alt < 2 else rng.n(16))])
    if kind == 4:
        return prefixes(rng, src, rng.pick([d for d in DST if d != 4]), 0) + b'\x9f'
    return prefixes(rng, src, dst, 1) + b'\x9f'


def immediate(rng):
    if rng.n(2):
        return ibt(rng.pick(DST), rng.n(256))
    return iwt(rng.pick(DST), rng.word())


def move(rng):
    if rng.n(2):
        return with_(rng.pick(SRC)) + to(rng.pick(DST))
    return with_(rng.pick(DST)) + frm(rng.pick(SRC))


def rom_buffer(rng):
    kind = rng.n(5)
    if kind == 4:
        return prefixes(rng, None, None, 0) + b'\xdf'                 # GETC (ColoR only matters for pixels)
    dst = rng.pick(DST)
    # GETBH/GETBL keep "the other byte" of Rd per fullsnes, of Rs per the emulators; they only
    # differ when Rs != Rd (finding 9), so the random programs keep Rs == Rd for those two
    src = dst if kind in (1, 2) else rng.pick(SRC)
    return prefixes(rng, src, dst, kind) + b'\xef'


def memory(rng):
    kind = rng.n(9)
    ptr, dst, src = rng.pick(POINTERS), rng.pick(DST), rng.pick(SRC)
    scratch = SCRATCH + rng.n(0x1F0)
    if kind == 0:
        return prefixes(rng, None, dst, 0) + bytes([0x40 + ptr])
    if kind == 1:
        return prefixes(rng, None, dst, 1) + bytes([0x40 + ptr])
    if kind == 2:
        return prefixes(rng, src, None, 0) + bytes([0x30 + ptr])
    if kind == 3:
        return prefixes(rng, src, None, 1) + bytes([0x30 + ptr])
    if kind == 4:
        return lm(dst, scratch)
    if kind == 5:
        return sm(src, scratch)
    if kind == 6:
        return prefixes(rng, src, None, 0) + b'\x90'
    if kind == 7:
        return lms(dst, 0x80 + rng.n(0x40))              # word addresses 0100-017E
    return sms(src, 0x80 + rng.n(0x40))


def pixel(rng, state):
    kind = rng.n(8)
    if kind == 0:
        por = rng.pick(state['pors'])
        # fullsnes: do not change the bitmap layout (SCMR; POR bit 4 forces OBJ) while pixels sit
        # in the pixel cache -- the core resolves the tile address at flush time -- so flush first
        return to(10) + ALT1 + b'\x4c' + ibt(5, por) + frm(5) + ALT1 + b'\x4e'
    if kind == 1:
        return ibt(6, rng.n(256)) + frm(6) + b'\x4e'
    if kind == 2:
        return ibt(1, rng.n(256)) + ibt(2, rng.n(256))
    if kind == 3:
        return b'\x4c' * (1 + rng.n(6))
    if kind == 4:
        return to(rng.pick((9, 10))) + ALT1 + b'\x4c'
    if kind == 5:
        return b'\x4c' + bytes([0xD2])
    return b'\x4c'


def forward_branch(rng, body):
    """Bxx over a block of whole instructions; the delay slot is one ordinary byte."""
    block = b''.join(body(rng) for _ in range(1 + rng.n(3)))
    delay = rng.pick(ONE_BYTE)
    op = rng.pick([5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15])
    return (prefixes(rng, None, None, 0) if rng.n(3) == 0 else b'') + branch(op, 1 + len(block)) + delay + block


def build(count=800):
    cases = []
    families = (
        ('mem', lambda rng, state: rng.pick([alu, alu, unary, incdec, multiply, immediate, move, rom_buffer,
                                             memory, memory])(rng), {'pors': []}),
        ('pix', lambda rng, state: rng.pick([alu, unary, incdec, multiply, immediate, move,
                                             lambda r: pixel(r, state), lambda r: pixel(r, state),
                                             lambda r: pixel(r, state)])(rng), None),
    )
    for serial in range(count):
        family, make, state = families[serial % 2]
        rng = Rng(serial + 1)
        scmr = 0x18
        if family == 'pix':
            md = rng.pick((1, 3, 0))
            ht = rng.n(4)
            scmr = 0x18 | md | ((ht & 1) << 2) | ((ht >> 1) << 5)
            pors = [0x01, 0x03, 0x10, 0x11, 0x13]
            if md == 0:
                pors = [0x01, 0x03, 0x11]           # 2bpp: colour 0 always drawn (low-two-bit transparency is a finding)
            if md == 1:
                pors += [0x00, 0x02, 0x12]     # transparent colour 0, with and without dither/OBJ
            if md == 3:
                pors += [0x00, 0x02]            # bits 2 and 3 stay out: high-nibble is finding 4
            state = {'pors': pors}
        body = []
        for _ in range(8 + rng.n(22)):
            if rng.n(7) == 0:
                body.append(forward_branch(rng, lambda r: make(r, state)))
            else:
                body.append(make(rng, state))
        code = b''.join(body)
        if family == 'pix':
            code += ibt(1, rng.n(256)) + ibt(2, rng.n(256)) + to(9) + ALT1 + b'\x4c'      # RPIX flushes both pixel caches
        code += STOP
        regs = {n: rng.word() for n in range(14)}
        for n in POINTERS:
            regs[n] = SCRATCH + rng.n(0x200)
        regs[14] = rng.word() & 0x7FFF
        regs[6] = rng.word()
        ram = [(SCRATCH, bytes(rng.n(256) for _ in range(0x300))), (0x100, bytes(rng.n(256) for _ in range(0x100)))] \
            if family == 'mem' else []
        rom = [(DATA, bytes(rng.n(256) for _ in range(0x400)))]
        mode = ('cold', 'warm', 'rom')[(serial // 2) % 3]
        kw = {'start': 0x400} if mode == 'rom' else {}
        cases.append(Case('fuzz_%s_%03d' % (family, serial), code, regs=regs, sfr=rng.pick((0, 2, 4, 6, 8, 16, 30)),
                          scmr=scmr, scbr=rng.n(4) if family == 'pix' else 0, mode=mode,
                          clsr=(serial // 6) & 1, rom=rom, ram=ram,
                          resume=(37 + rng.n(60), 150 + rng.n(300)) if serial % 5 == 0 else (), **kw))
    return cases
