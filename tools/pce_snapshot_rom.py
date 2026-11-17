"""An authored PC Engine / TurboGrafx-16 HuCard that keeps many devices busy, deterministically.

It is for the snapshot / rollback determinism probe of the PC Engine machine: no commercial data, no ROM from a
player, only a hand-assembled HuC6280 program written here byte by byte (a tiny two-pass assembler below), a few
authored tiles, sprite patterns, palettes and waveforms, and distinct code and data in several ROM banks.

    python -B tools/pce_snapshot_rom.py out.pce [out.sym]      # 128 KiB, 16 banks of 8 KiB, standard HuCard (base profile)
    build_rom() -> bytes

What the program does, forever and with no input (the pad is read every frame and folded into a counter, the
scroll speed and the sprite speed, so pressing a button changes the state):

  * VDC: 256x240, background (32x32 map, 128 tiles) and 16 sprites; tiles, patterns and the map are copied to VRAM by
    TIA block transfers; every frame the sprite attribute table is rebuilt in work RAM and copied to VRAM, the
    automatic SATB DMA copies it at vertical blank, one VRAM to VRAM DMA rewrites an animated tile, and one random map
    cell is written by the CPU.  IRQ1 handler: vertical blank (scroll BXR/BYR, next raster compare line, one palette
    entry), raster compare (RCR line changes every frame; mid-frame BXR and backdrop colour change), end of SATB DMA,
    end of VRAM DMA.
  * HuC6280 timer IRQ (reload changes at every interrupt), BRK once per frame (vector $FFF6), reads of the timer
    counter and of the interrupt status port.
  * PSG: six channels (sine, square, saw, triangle waves, a noise channel, a channel whose waveform is reloaded by TIN
    every 16 frames), frequency, volume, balance and main volume change continuously.
  * VCE palette writes (TIA at start, then in the handlers).
  * MPR switching with TAM and TMA: bank 1, 2, 3 hold distinct code assembled for $4000 (MPR2); data banks 4, 5, 6 and
    banks 8 to 15 are switched into MPR3, bank 9 sits in MPR4; the timer handler saves and restores MPR3.
  * TII, TDD, TIA, TAI and TIN block transfers in work RAM, from ROM, to the PSG waveform port and to the VDC/VCE ports.
  * CSL / CSH speed switching, BRK/RTI, BSR, JMP (abs,x), SMB/RMB/BBR/BBS, TSB/TRB/TST/BIT, SXY, decimal mode.
  * A 16-bit Galois LFSR in zero page ($2000 logical, MPR1 = $F8 work RAM) fed by the pad, the timer counter and a
    checksum over the work RAM buffers.

Memory map used: MPR0=$FF (I/O) at $0000, MPR1=$F8 (work RAM) at $2000, MPR2 (banks 1-3 code) at $4000, MPR3 (data banks) at
$6000, MPR4=9 at $8000, MPR7=0 at $E000 (reset, handlers, common code and vectors).

Original RetroRecomp code: MIT.
"""
from __future__ import annotations

import math
import re
import sys

# --------------------------------------------------------------------------------------------------------------------
# The HuC6280 opcode map, one entry per opcode, name.mode (modes as the engine's own decoder names them).
_ROWS = """
BRK.brk ORA.idx SXY.imp ST0.imm TSB.zpg ORA.zpg ASL.zpg RMB0.zpg PHP.imp ORA.imm ASL.acc ILL.non TSB.abs ORA.abs ASL.abs BBR0.zrl
BPL.rel ORA.idy ORA.zpi ST1.imm TRB.zpg ORA.zpx ASL.zpx RMB1.zpg CLC.imp ORA.aby INA.imp ILL.non TRB.abs ORA.abx ASL.abx BBR1.zrl
JSR.abs AND.idx SAX.imp ST2.imm BIT.zpg AND.zpg ROL.zpg RMB2.zpg PLP.imp AND.imm ROL.acc ILL.non BIT.abs AND.abs ROL.abs BBR2.zrl
BMI.rel AND.idy AND.zpi ILL.non BIT.zpx AND.zpx ROL.zpx RMB3.zpg SEC.imp AND.aby DEA.imp ILL.non BIT.abx AND.abx ROL.abx BBR3.zrl
RTI.imp EOR.idx SAY.imp TMA.imm BSR.rel EOR.zpg LSR.zpg RMB4.zpg PHA.imp EOR.imm LSR.acc ILL.non JMP.abs EOR.abs LSR.abs BBR4.zrl
BVC.rel EOR.idy EOR.zpi TAM.imm CSL.imp EOR.zpx LSR.zpx RMB5.zpg CLI.imp EOR.aby PHY.imp ILL.non ILL.non EOR.abx LSR.abx BBR5.zrl
RTS.imp ADC.idx CLA.imp ILL.non STZ.zpg ADC.zpg ROR.zpg RMB6.zpg PLA.imp ADC.imm ROR.acc ILL.non JMP.ind ADC.abs ROR.abs BBR6.zrl
BVS.rel ADC.idy ADC.zpi TII.blk STZ.zpx ADC.zpx ROR.zpx RMB7.zpg SEI.imp ADC.aby PLY.imp ILL.non JMP.iax ADC.abx ROR.abx BBR7.zrl
BRA.rel STA.idx CLX.imp TST.imz STY.zpg STA.zpg STX.zpg SMB0.zpg DEY.imp BIT.imm TXA.imp ILL.non STY.abs STA.abs STX.abs BBS0.zrl
BCC.rel STA.idy STA.zpi TST.ima STY.zpx STA.zpx STX.zpy SMB1.zpg TYA.imp STA.aby TXS.imp ILL.non STZ.abs STA.abx STZ.abx BBS1.zrl
LDY.imm LDA.idx LDX.imm TST.izx LDY.zpg LDA.zpg LDX.zpg SMB2.zpg TAY.imp LDA.imm TAX.imp ILL.non LDY.abs LDA.abs LDX.abs BBS2.zrl
BCS.rel LDA.idy LDA.zpi TST.imx LDY.zpx LDA.zpx LDX.zpy SMB3.zpg CLV.imp LDA.aby TSX.imp ILL.non LDY.abx LDA.abx LDX.aby BBS3.zrl
CPY.imm CMP.idx CLY.imp TDD.blk CPY.zpg CMP.zpg DEC.zpg SMB4.zpg INY.imp CMP.imm DEX.imp ILL.non CPY.abs CMP.abs DEC.abs BBS4.zrl
BNE.rel CMP.idy CMP.zpi TIN.blk CSH.imp CMP.zpx DEC.zpx SMB5.zpg CLD.imp CMP.aby PHX.imp ILL.non ILL.non CMP.abx DEC.abx BBS5.zrl
CPX.imm SBC.idx ILL.non TIA.blk CPX.zpg SBC.zpg INC.zpg SMB6.zpg INX.imp SBC.imm NOP.imp ILL.non CPX.abs SBC.abs INC.abs BBS6.zrl
BEQ.rel SBC.idy SBC.zpi TAI.blk SET.imp SBC.zpx INC.zpx SMB7.zpg SED.imp SBC.aby PLX.imp ILL.non ILL.non SBC.abx INC.abx BBS7.zrl
""".split()
_OPCODE = {tuple(row.split('.')): code for code, row in enumerate(_ROWS) if not row.startswith('ILL')}
_LENGTH = {'imp': 1, 'acc': 1, 'imm': 2, 'zpg': 2, 'zpx': 2, 'zpy': 2, 'idx': 2, 'idy': 2, 'zpi': 2, 'rel': 2, 'abs': 3,
           'abx': 3, 'aby': 3, 'ind': 3, 'iax': 3, 'zrl': 3, 'imz': 3, 'izx': 3, 'ima': 4, 'imx': 4, 'blk': 7, 'brk': 2}
_BRANCH = {'BPL', 'BMI', 'BVC', 'BVS', 'BCC', 'BCS', 'BNE', 'BEQ', 'BRA', 'BSR'}
_BLOCK = {'TII', 'TDD', 'TIN', 'TIA', 'TAI'}
_ACC = {'ASL', 'LSR', 'ROL', 'ROR', 'INC', 'DEC'}


class AsmError(Exception):
    pass


def _split(text: str) -> list[str]:
    parts, depth, current = [], 0, ''
    for char in text:
        if char == ',' and depth == 0:
            parts.append(current.strip())
            current = ''
            continue
        depth += (char == '(') - (char == ')')
        current += char
    if current.strip():
        parts.append(current.strip())
    return parts


class Assembler:
    """Two passes over several sections (one per ROM bank), global labels, zero-page names."""

    def __init__(self) -> None:
        self.symbols: dict[str, int] = {}
        self.zero_page: set[str] = set()
        self.sections: dict[int, list] = {}
        self.origins: dict[int, int] = {}
        self._bank = 0

    # -- definitions
    def equ(self, name: str, value: int) -> None:
        if name in self.symbols:
            raise AsmError(f'symbol defined twice: {name}')
        self.symbols[name] = value

    def zp(self, name: str, offset: int) -> None:
        self.equ(name, offset)
        self.zero_page.add(name)

    def section(self, bank: int, origin: int) -> None:
        self._bank = bank
        self.origins[bank] = origin
        self.sections[bank] = []

    def source(self, text: str) -> None:
        items = self.sections[self._bank]
        for number, raw in enumerate(text.splitlines(), 1):
            line = raw.split(';', 1)[0].strip()
            while line:
                head = re.match(r'^([A-Za-z_]\w*):\s*(.*)$', line)
                if not head:
                    break
                items.append(('label', head.group(1)))
                line = head.group(2)
            if not line:
                continue
            items.append(self._parse(line, number))

    def data(self, payload: bytes) -> None:
        self.sections[self._bank].append(('bytes', bytes(payload)))

    # -- parsing
    def _is_zero_page(self, expr: str) -> bool:
        expr = expr.strip()
        if expr.startswith('!'):
            return False
        names = re.findall(r'(?<![0-9A-Za-z_$])[A-Za-z_]\w*', expr)
        if names:
            return names[0] in self.zero_page
        try:
            return self._evaluate(expr, {}, 0) < 0x100
        except (AsmError, NameError):
            return False

    def _parse(self, line: str, number: int):
        if line.startswith('.'):
            word, _, rest = line.partition(' ')
            if word == '.org':
                return ('org', rest.strip())
            if word == '.byte':
                return ('byte', _split(rest))
            if word == '.word':
                return ('word', _split(rest))
            raise AsmError(f'line {number}: unknown directive {word}')
        mnemonic, _, operand = line.partition(' ')
        mn, operand = mnemonic.upper(), operand.strip()
        if mn in ('INC', 'DEC') and operand.lower() == 'a':
            mn, operand = ('INA' if mn == 'INC' else 'DEA'), ''
        args = _split(operand)
        mode: str
        if mn in _BRANCH:
            mode = 'rel'
        elif re.match(r'^(BBR|BBS)[0-7]$', mn):
            mode = 'zrl'
        elif mn in _BLOCK:
            mode = 'blk'
        elif mn == 'TST':
            if len(args) < 2 or not args[0].startswith('#'):
                raise AsmError(f'line {number}: TST needs #mask, address')
            indexed = len(args) == 3
            zero = self._is_zero_page(args[1])
            mode = ('izx' if zero else 'imx') if indexed else ('imz' if zero else 'ima')
            args = [args[0][1:], args[1]]
        elif not operand:
            mode = 'imp'
        elif operand.lower() == 'a' and mn in _ACC:
            mode = 'acc'
            args = []
        elif operand.startswith('#'):
            mode = 'imm'
            args = [operand[1:]]
        elif (m := re.match(r'^\((.+),\s*x\)$', operand, re.I)):
            mode, args = ('iax' if mn == 'JMP' else 'idx'), [m.group(1)]
        elif (m := re.match(r'^\((.+)\),\s*y$', operand, re.I)):
            mode, args = 'idy', [m.group(1)]
        elif (m := re.match(r'^\((.+)\)$', operand)):
            mode, args = ('ind' if mn == 'JMP' else 'zpi'), [m.group(1)]
        elif len(args) == 2 and args[1].lower() in ('x', 'y'):
            zero = self._is_zero_page(args[0]) and (mn, 'zp' + args[1].lower()) in _OPCODE
            mode = ('zp' if zero else 'ab') + args[1].lower()
            args = [args[0]]
        elif mn in ('ST0', 'ST1', 'ST2', 'TAM', 'TMA'):
            mode, args = 'imm', [operand]
        elif mn in ('JMP', 'JSR'):
            mode = 'abs'
        else:
            mode = 'zpg' if self._is_zero_page(operand) and (mn, 'zpg') in _OPCODE else 'abs'
        if (mn, mode) not in _OPCODE:
            raise AsmError(f'line {number}: {mn} has no {mode} form ({line})')
        return ('ins', mn, mode, args, number)

    # -- evaluation
    def _evaluate(self, expr: str, symbols: dict, pc: int) -> int:
        expr = expr.strip().lstrip('!')
        low = high = False
        if expr.startswith('<'):
            low, expr = True, expr[1:]
        elif expr.startswith('>'):
            high, expr = True, expr[1:]
        expr = re.sub(r'\$([0-9A-Fa-f]+)', r'0x\1', expr)

        def lookup(match):
            name = match.group(0)
            if name not in symbols:
                raise AsmError(f'undefined symbol: {name}')
            return f'({symbols[name]})'
        expr = re.sub(r'(?<![0-9A-Za-z_])[A-Za-z_]\w*', lookup, expr)
        if not re.fullmatch(r'[0-9A-Fa-fx+\-*()<>&| ]*', expr):
            raise AsmError(f'bad expression: {expr}')
        value = int(eval(expr, {'__builtins__': {}}, {}))      # operands are our own text, digits and operators only
        return value & 0xFF if low else (value >> 8) & 0xFF if high else value

    # -- assembly
    def assemble(self) -> dict[int, bytes]:
        symbols = dict(self.symbols)
        addresses: dict[int, list[int]] = {}
        for bank, items in self.sections.items():            # pass 1: addresses and labels
            pc, addrs = self.origins[bank], []
            for item in items:
                addrs.append(pc)
                kind = item[0]
                if kind == 'label':
                    if item[1] in symbols:
                        raise AsmError(f'symbol defined twice: {item[1]}')
                    symbols[item[1]] = pc
                elif kind == 'org':
                    pc = self._evaluate(item[1], symbols, pc)
                elif kind == 'ins':
                    pc += _LENGTH[item[2]]
                elif kind == 'byte':
                    pc += len(item[1])
                elif kind == 'word':
                    pc += 2 * len(item[1])
                elif kind == 'bytes':
                    pc += len(item[1])
            addresses[bank] = addrs
        images: dict[int, bytes] = {}
        for bank, items in self.sections.items():            # pass 2: bytes
            origin = self.origins[bank]
            out = bytearray([0xFF] * 0x2000)
            for item, pc in zip(items, addresses[bank]):
                kind = item[0]
                offset = pc - origin
                if kind == 'label':
                    continue
                if kind == 'org':
                    continue
                if kind == 'bytes':
                    out[offset:offset + len(item[1])] = item[1]
                    continue
                if kind == 'byte':
                    for n, expr in enumerate(item[1]):
                        out[offset + n] = self._evaluate(expr, symbols, pc) & 0xFF
                    continue
                if kind == 'word':
                    for n, expr in enumerate(item[1]):
                        value = self._evaluate(expr, symbols, pc) & 0xFFFF
                        out[offset + 2 * n:offset + 2 * n + 2] = value.to_bytes(2, 'little')
                    continue
                _, mn, mode, args, number = item
                code = bytes([_OPCODE[(mn, mode)]])
                size = _LENGTH[mode]
                value = [self._evaluate(a, symbols, pc) for a in args] if mode not in ('rel', 'zrl') else None
                if mode in ('imp', 'acc'):
                    body = b''
                elif mode == 'rel':
                    delta = self._evaluate(args[0], symbols, pc) - (pc + 2)
                    if not -128 <= delta <= 127:
                        raise AsmError(f'line {number}: branch out of range ({delta}): {mn} {args[0]}')
                    body = bytes([delta & 0xFF])
                elif mode == 'zrl':
                    delta = self._evaluate(args[1], symbols, pc) - (pc + 3)
                    if not -128 <= delta <= 127:
                        raise AsmError(f'line {number}: branch out of range ({delta}): {mn} {args[1]}')
                    zero = self._evaluate(args[0], symbols, pc)
                    body = bytes([zero & 0xFF, delta & 0xFF])
                elif mode == 'blk':
                    body = b''.join((v & 0xFFFF).to_bytes(2, 'little') for v in value)
                elif mode in ('imz', 'izx'):
                    body = bytes([value[0] & 0xFF, value[1] & 0xFF])
                elif mode in ('ima', 'imx'):
                    body = bytes([value[0] & 0xFF]) + (value[1] & 0xFFFF).to_bytes(2, 'little')
                elif mode in ('abs', 'abx', 'aby', 'ind', 'iax'):
                    body = (value[0] & 0xFFFF).to_bytes(2, 'little')
                else:                                         # imm, zpg, zpx, zpy, idx, idy, zpi
                    if not 0 <= value[0] <= 0xFF and not -128 <= value[0] < 0:
                        raise AsmError(f'line {number}: operand does not fit a byte: {mn} {args[0]}')
                    body = bytes([value[0] & 0xFF])
                encoded = code + body
                if len(encoded) != size:
                    raise AsmError(f'line {number}: internal size mismatch for {mn} {mode}')
                out[offset:offset + size] = encoded
            images[bank] = bytes(out)
        self.final_symbols = symbols
        return images


# --------------------------------------------------------------------------------------------------------------------
# Authored data: tiles, sprite patterns, map, palettes, waveforms.
def _tile_pixel(k: int, x: int, y: int) -> int:
    base = 1 + (k // 8) % 15
    kind = k % 8
    if kind == 0:
        c = base if (x ^ y) & 1 else 0
    elif kind == 1:
        c = base if y % 4 < 2 else 0
    elif kind == 2:
        c = base if x % 4 < 2 else 0
    elif kind == 3:
        c = base if (x + y) % 4 == 0 else 0
    elif kind == 4:
        c = base if x in (0, 7) or y in (0, 7) else 0
    elif kind == 5:
        c = 1 + (x + y + k) % 15
    elif kind == 6:
        c = base if (x % 4 == 1 and y % 4 == 1) else 0
    else:
        c = base if x == y or x + y == 7 else 0
    return c & 15


def _bg_tile(k: int) -> bytes:
    words = []
    for half in (0, 1):                 # words 0-7: planes 0/1 of the eight rows, words 8-15: planes 2/3
        for y in range(8):
            planes = [0, 0, 0, 0]
            for x in range(8):
                c = _tile_pixel(k, x, y)
                for p in range(4):
                    planes[p] |= ((c >> p) & 1) << (7 - x)
            low, high = (planes[0], planes[1]) if half == 0 else (planes[2], planes[3])
            words.append(low | (high << 8))
    return b''.join(w.to_bytes(2, 'little') for w in words)


def _sprite_pattern(i: int) -> bytes:
    rows = [[0] * 16 for _ in range(16)]
    for y in range(16):
        for x in range(16):
            dx, dy = x - 7.5, y - 7.5
            kind = i % 4
            inside = (dx * dx + dy * dy <= 56 if kind == 0 else abs(dx) + abs(dy) <= 8 if kind == 1 else
                      max(abs(dx), abs(dy)) <= 7 if kind == 2 else 20 < dx * dx + dy * dy <= 56)
            rows[y][x] = 1 + (int(dx * dx + dy * dy) // 8 + i) % 15 if inside else 0
    words = []
    for p in range(4):
        for y in range(16):
            word = 0
            for x in range(16):
                word |= ((rows[y][x] >> p) & 1) << (15 - x)
            words.append(word)
    return b''.join(w.to_bytes(2, 'little') for w in words)


def _colour(r: int, g: int, b: int) -> int:
    return ((g & 7) << 6) | ((r & 7) << 3) | (b & 7)


def _palettes() -> tuple[bytes, bytes]:
    bg = []
    for p in range(4):
        for c in range(16):
            if c == 0:
                bg.append(_colour(0, 0, 1 + p))
            elif c == 15:
                bg.append(_colour(7, 7, 7))
            else:
                bg.append(_colour((c + p) % 8, (c * 3 + p * 2) % 8, (c * 7 + p * 5) % 8 or 1))
    spr = []
    for p in range(2):
        for c in range(16):
            spr.append(0 if c == 0 else _colour(7 - c % 8 if p == 0 else c % 8, (c * 5 + p * 3) % 8 | 2, (c * 3 + p) % 8 | 1))
    pack = lambda values: b''.join(v.to_bytes(2, 'little') for v in values)
    return pack(bg), pack(spr)


def _waves() -> bytes:
    sine = [round(15.5 + 15.5 * math.sin(2 * math.pi * k / 32)) for k in range(32)]
    square = [31 if k < 16 else 0 for k in range(32)]
    saw = list(range(32))
    triangle = [2 * k if k < 16 else 62 - 2 * k for k in range(32)]
    return bytes(sine + square + saw + triangle)


def _volumes() -> bytes:
    return bytes(min(15, 7 + abs(i - 8)) * 17 for i in range(16))


def _sprite_init() -> bytes:
    xs = [(i * 53 + 20) & 255 for i in range(16)]
    ys = [(i * 29 + 10) % 224 for i in range(16)]
    dxs = [1 + (i & 3) for i in range(16)]
    dys = [1 + ((i >> 2) & 3) for i in range(16)]
    return bytes(xs + ys + dxs + dys)


def _noise(count: int) -> bytes:
    state, out = 0xBEEF, bytearray()
    for _ in range(count):
        for _ in range(8):
            state = (state >> 1) ^ (0xB400 if state & 1 else 0)
        out.append(state & 0xFF)
    return bytes(out)


def _map() -> bytes:
    cells = []
    for r in range(32):
        for c in range(32):
            tile = 0x80 + ((c * 7 + r * 3 + r * c) & 0x7F)
            if (r + c) % 6 == 0:
                tile = 0x7F                     # the animated tile (VRAM to VRAM DMA)
            cells.append((((r >> 3) & 3) << 12) | tile)
    return b''.join(v.to_bytes(2, 'little') for v in cells)


# --------------------------------------------------------------------------------------------------------------------
def _vreg(n: int, value: int) -> str:
    return f'    st0 #{n}\n    st1 #${value & 255:02x}\n    st2 #${(value >> 8) & 255:02x}\n'


# Zero page (logical $2000 + offset) and work RAM buffers.
_ZP = ['frame_lo', 'frame_hi', 'vsync', 'rng_lo', 'rng_hi', 'pad_now', 'padacc_lo', 'padacc_hi', 'tcount_lo', 'tcount_hi',
       'rcount_lo', 'rcount_hi', 'dcount', 'vdcount', 'brk_count', 'vstat', 'bxr_lo', 'bxr_hi', 'byr_lo', 'byr_hi',
       'rcr_line', 'chk_lo', 'chk_hi', 'ptr_lo', 'ptr_hi', 'tmp0', 'tmp1', 'tmp2', 'b1_ok', 'timer_snap', 'irq_snap',
       'bcd', 'flags', 'hits', 'b2_count', 'b3_count', 'sweep']
BUFA, BUFB, BUFC, SPRX, SATB = 0x2200, 0x2300, 0x2400, 0x2500, 0x2600
SPRY, SPRDX, SPRDY = SPRX + 16, SPRX + 32, SPRX + 48
# Data bank 5 (at $6000): palettes, waveforms, volume table, sprite start values, noise.
PAL_BG, PAL_SPR, WAVES, VOLTAB, SPRINIT, NOISE = 0, 128, 192, 320, 336, 512

_IO = {'VDC_SEL': 0x0000, 'VDC_LO': 0x0002, 'VDC_HI': 0x0003, 'VCE_CTRL': 0x0400, 'VCE_ADDR_LO': 0x0402, 'VCE_ADDR_HI': 0x0403,
       'VCE_DATA_LO': 0x0404, 'VCE_DATA_HI': 0x0405, 'PSG_SEL': 0x0800, 'PSG_MAIN': 0x0801, 'PSG_FL': 0x0802, 'PSG_FH': 0x0803,
       'PSG_CTL': 0x0804, 'PSG_BAL': 0x0805, 'PSG_WAV': 0x0806, 'PSG_NOISE': 0x0807, 'TIMER_CNT': 0x0C00, 'TIMER_CTL': 0x0C01,
       'PAD': 0x1000, 'IRQ_MASK': 0x1402, 'IRQ_STAT': 0x1403}


def _inc16(lo: str, hi: str, tag: str) -> str:
    return f'    inc {lo}\n    bne {tag}\n    inc {hi}\n{tag}:\n'


def _bank0() -> str:
    t = []
    t.append(f""".org $E000
reset:
    sei
    csh
    cld
    lda #$ff
    tam #$01
    lda #$f8
    tam #$02
    ldx #$ff
    txs
    lda #$01
    tam #$04
    lda #$04
    tam #$08
    lda #$09
    tam #$10
    lda #$06
    tam #$20
    lda #$07
    tam #$40
    ldx #0
clrzp:
    stz 0,x
    inx
    bne clrzp
    stz BUFA
    tii BUFA, BUFA+1, $1DFF
    lda #$e1
    sta rng_lo
    lda #$ac
    sta rng_hi
    jsr init_video
    jsr init_psg
    jsr init_misc
    jsr init_irq
    cli
    jmp frame_loop

init_misc:
    lda #5
    tam #$08
    tii $6000+SPRINIT, SPRX, 64
    rts

init_irq:
    lda #0
    sta IRQ_MASK
    lda #47
    sta TIMER_CNT
    lda #1
    sta TIMER_CTL
    rts

init_video:
    stz VCE_CTRL
""")
    for n, v in ((5, 0x0000), (9, 0x0000), (10, 0x0202), (11, 0x031F), (12, 0x0F02), (13, 0x00EF), (14, 0x0002), (7, 0), (8, 0),
                 (6, 0x0070), (15, 0x0013), (19, 0x7F00)):
        t.append(_vreg(n, v))
    t.append(f"""    lda #5
    tam #$08
    stz VCE_ADDR_LO
    stz VCE_ADDR_HI
    tia $6000+PAL_BG, VCE_DATA_LO, 128
    stz VCE_ADDR_LO
    lda #1
    sta VCE_ADDR_HI
    tia $6000+PAL_SPR, VCE_DATA_LO, 64
    lda #4
    tam #$08
""")
    t.append(_vreg(0, 0x0800) + '    st0 #2\n    tia $6000, VDC_LO, 4096\n')
    t.append(_vreg(0, 0x1000) + '    st0 #2\n    tia $6000+4096, VDC_LO, 2048\n')
    t.append(_vreg(0, 0x0000) + '    st0 #2\n    tia $6000+6144, VDC_LO, 2048\n')
    t.append(_vreg(5, 0x00CC) + '    rts\n')

    waves_freq = [(0xF0, 0x00), (0xA0, 0x01), (0xC0, 0x02), (0xA0, 0x00), (0x00, 0x00), (0x80, 0x01)]
    balance = [0xFF, 0xF4, 0x4F, 0x88, 0xFF, 0xCC]
    t.append('init_psg:\n    lda #5\n    tam #$08\n    lda #$dd\n    sta PSG_MAIN\n')
    for c in range(6):
        t.append(f'    lda #{c}\n    sta PSG_SEL\n    stz PSG_CTL\n    tin $6000+WAVES+{32 * (c % 4)}, PSG_WAV, 32\n')
        t.append(f'    lda #${waves_freq[c][0]:02x}\n    sta PSG_FL\n    lda #${waves_freq[c][1]:02x}\n    sta PSG_FH\n')
        t.append(f'    lda #${balance[c]:02x}\n    sta PSG_BAL\n')
        if c == 4:
            t.append('    lda #$8a\n    sta PSG_NOISE\n')
        t.append(f'    lda #${0x9F - c:02x}\n    sta PSG_CTL\n')
    t.append('    rts\n\n')

    t.append("""frame_loop:
    lda vsync
    beq frame_loop
    stz vsync
    jsr read_pad
    jsr rng_step
    jsr rng_step
    jsr do_blocks
    jsr checksum
    jsr misc_ops
    lda #1
    tam #$04
    jsr $4000
    lda #2
    tam #$04
    jsr $4000
    lda #3
    tam #$04
    jsr $4000
    lda TIMER_CNT
    sta timer_snap
    lda IRQ_STAT
    sta irq_snap
    .byte 0, 0
    jmp frame_loop

read_pad:
    lda #$01
    sta PAD
    nop
    nop
    lda PAD
    and #$0f
    sta tmp0
    lda #$00
    sta PAD
    nop
    nop
    lda PAD
    and #$0f
    asl a
    asl a
    asl a
    asl a
    ora tmp0
    eor #$ff
    sta pad_now
    lda #$03
    sta PAD
    lda padacc_lo
    clc
    adc pad_now
    sta padacc_lo
    bcc rp_nc
    inc padacc_hi
rp_nc:
    lda rng_lo
    eor pad_now
    eor timer_snap
    sta rng_lo
    rts

rng_step:
    lsr rng_hi
    ror rng_lo
    bcc rs_nc
    lda rng_hi
    eor #$b4
    sta rng_hi
rs_nc:
    lda rng_lo
    ora rng_hi
    bne rs_ok
    lda #$01
    sta rng_lo
rs_ok:
    rts

do_blocks:
    lda #5
    tam #$08
    lda frame_lo
    and #3
    asl a
    tax
    jmp (blk_tbl,x)
blk_tbl:
    .word blk0, blk1, blk2, blk3
blk0:
    tii $6000+NOISE, BUFA, 256
    tdd BUFA+255, BUFC+255, 128
    rts
blk1:
    tii $6000+NOISE+256, BUFB, 256
    tia BUFA, BUFC, 32
    tai BUFB, BUFC+32, 32
    rts
blk2:
    tin BUFA, BUFC+200, 16
    tii BUFB, BUFA+128, 128
    tdd BUFC+127, BUFB+127, 64
    rts
blk3:
    tii $8000, BUFB, 200
    tai $8000+64, BUFA, 64
    tin BUFA, BUFC+250, 32
    rts

checksum:
    lda rng_lo
    sta BUFA
    lda rng_hi
    sta BUFB+3
    csl
    lda #<BUFA
    sta ptr_lo
    lda #>BUFA
    sta ptr_hi
    ldx #2
ck_page:
    ldy #0
ck_lp:
    lda (ptr_lo),y
    clc
    adc chk_lo
    sta chk_lo
    bcc ck_nc
    inc chk_hi
ck_nc:
    iny
    bne ck_lp
    inc ptr_hi
    dex
    bne ck_page
    csh
    lda rng_lo
    eor chk_hi
    sta rng_lo
    rts

misc_ops:
    smb0 flags
    smb3 flags
    rmb0 flags
    lda frame_lo
    sta tmp0
    bbs0 tmp0, mo_odd
    inc hits
mo_odd:
    bbr1 tmp0, mo_b1
    inc hits
mo_b1:
    lda #$0f
    tsb tmp1
    lda #$03
    trb tmp1
    tst #$f0, tmp0
    lda rng_lo
    bit rng_hi
    sxy
    sxy
    pha
    phx
    phy
    ply
    plx
    pla
    bsr mo_sub
    sed
    lda #$19
    clc
    adc #$28
    sta bcd
    cld
    cla
    clx
    cly
    rts
mo_sub:
    inc hits
    rts

nmi_rti:
    rti

brk_irq2:
    inc brk_count
    rti

timer_irq:
    pha
    phx
    sta IRQ_STAT
""")
    t.append(_inc16('tcount_lo', 'tcount_hi', 'ti_nc'))
    t.append("""    lda rng_lo
    and #$1f
    ora #$20
    sta TIMER_CNT
    tma #$08
    pha
    lda #5
    tam #$08
    lda tcount_lo
    and #$0f
    tax
    lda $6000+VOLTAB,x
    sta PSG_MAIN
    pla
    tam #$08
    plx
    pla
    rti

irq1:
    pha
    phx
    phy
    lda VDC_SEL
    sta vstat
    bbs5 vstat, i1_vb
    jmp i1_nvb
i1_vb:
""")
    t.append(_inc16('frame_lo', 'frame_hi', 'i1_f1'))
    t.append("""    lda #1
    sta vsync
    lda pad_now
    and #3
    sec
    adc bxr_lo
    sta bxr_lo
    lda bxr_hi
    adc #0
    and #3
    sta bxr_hi
    lda frame_lo
    and #1
    bne i1_nby
    inc byr_lo
    bne i1_nby
    lda byr_hi
    eor #1
    sta byr_hi
i1_nby:
    lda #7
    sta VDC_SEL
    lda bxr_lo
    sta VDC_LO
    lda bxr_hi
    sta VDC_HI
    lda #8
    sta VDC_SEL
    lda byr_lo
    sta VDC_LO
    lda byr_hi
    sta VDC_HI
    lda rng_lo
    and #$7f
    clc
    adc #$50
    sta rcr_line
    lda #6
    sta VDC_SEL
    lda rcr_line
    sta VDC_LO
    stz VDC_HI
    lda frame_lo
    and #$0f
    clc
    adc #1
    sta VCE_ADDR_LO
    stz VCE_ADDR_HI
    lda rng_lo
    sta VCE_DATA_LO
    lda rng_hi
    and #1
    sta VCE_DATA_HI
i1_nvb:
    bbs2 vstat, i1_rc
    jmp i1_nrc
i1_rc:
""")
    t.append(_inc16('rcount_lo', 'rcount_hi', 'i1_r1'))
    t.append("""    lda #7
    sta VDC_SEL
    lda rng_hi
    and #$3f
    clc
    adc bxr_lo
    sta VDC_LO
    lda bxr_hi
    adc #0
    and #3
    sta VDC_HI
    stz VCE_ADDR_LO
    stz VCE_ADDR_HI
    lda rng_hi
    sta VCE_DATA_LO
    lda rcount_lo
    and #1
    sta VCE_DATA_HI
i1_nrc:
    bbr3 vstat, i1_nds
    inc dcount
i1_nds:
    bbr4 vstat, i1_ndv
    inc vdcount
i1_ndv:
    ply
    plx
    pla
    rti

.org $FFF6
.word brk_irq2, irq1, timer_irq, nmi_rti, reset
""")
    return ''.join(t)


_BANK1 = """.org $4000
b1_entry:
    tma #$08
    sta tmp2
    ldx #8
b1_lp:
    txa
    tam #$08
    lda $6000
    eor $7FF0
    clc
    adc chk_lo
    sta chk_lo
    lda $6123
    eor chk_hi
    sta chk_hi
    inx
    cpx #16
    bne b1_lp
    lda tmp2
    tam #$08
    tma #$04
    cmp #1
    bne b1_bad
    inc b1_ok
b1_bad:
    inc sweep
    jsr rng_step
    rts
"""

_BANK2 = """.org $4000
b2_entry:
    inc b2_count
    lda frame_lo
    and #3
    sta PSG_SEL
    lda rng_lo
    sta PSG_FL
    lda rng_hi
    and #$0f
    sta PSG_FH
    lda frame_lo
    lsr a
    lsr a
    and #$1f
    ora #$80
    sta PSG_CTL
    lda rng_hi
    sta PSG_BAL
    lda #4
    sta PSG_SEL
    lda rng_lo
    and #$1f
    ora #$80
    sta PSG_NOISE
    lda frame_lo
    and #$0f
    bne b2_done
    lda #5
    sta PSG_SEL
    stz PSG_CTL
    tma #$08
    pha
    lda #5
    tam #$08
    lda frame_lo
    lsr a
    lsr a
    lsr a
    lsr a
    and #3
    cmp #1
    beq b2_t1
    cmp #2
    beq b2_t2
    cmp #3
    beq b2_t3
    tin $6000+WAVES, PSG_WAV, 32
    bra b2_wd
b2_t1:
    tin $6000+WAVES+32, PSG_WAV, 32
    bra b2_wd
b2_t2:
    tin $6000+WAVES+64, PSG_WAV, 32
    bra b2_wd
b2_t3:
    tin $6000+WAVES+96, PSG_WAV, 32
b2_wd:
    pla
    tam #$08
    lda #$9f
    sta PSG_CTL
b2_done:
    rts
"""

_BANK3 = """.org $4000
b3_entry:
    inc b3_count
    ldx #0
    ldy #0
b3_lp:
    lda pad_now
    and #3
    clc
    adc SPRDX,x
    clc
    adc SPRX,x
    sta SPRX,x
    lda SPRY,x
    clc
    adc SPRDY,x
    cmp #224
    bcc b3_ok
    sbc #224
b3_ok:
    sta SPRY,x
    clc
    adc #64
    sta SATB,y
    lda #0
    adc #0
    sta SATB+1,y
    lda SPRX,x
    clc
    adc #32
    sta SATB+2,y
    lda #0
    adc #0
    sta SATB+3,y
    txa
    asl a
    clc
    adc #$80
    sta SATB+4,y
    lda #0
    sta SATB+5,y
    txa
    and #1
    sta tmp1
    lsr a
    ror a
    ora tmp1
    sta SATB+6,y
    txa
    and #2
    asl a
    asl a
    sta tmp1
    txa
    and #4
    asl a
    asl a
    asl a
    asl a
    asl a
    ora tmp1
    sta SATB+7,y
    tya
    clc
    adc #8
    tay
    inx
    cpx #16
    beq b3_done
    jmp b3_lp
b3_done:
    php
    sei
    st0 #0
    st1 #$00
    st2 #$7f
    st0 #2
    tia SATB, VDC_LO, 128
    lda #0
    sta VDC_SEL
    lda rng_lo
    sta VDC_LO
    lda rng_hi
    and #3
    sta VDC_HI
    lda #2
    sta VDC_SEL
    lda rng_hi
    and #7
    ora #$80
    sta VDC_LO
    lda rng_lo
    and #$30
    sta VDC_HI
    lda #16
    sta VDC_SEL
    lda frame_lo
    lsr a
    lsr a
    and #7
    asl a
    asl a
    asl a
    asl a
    sta VDC_LO
    lda #$08
    sta VDC_HI
    lda #17
    sta VDC_SEL
    lda #$f0
    sta VDC_LO
    lda #$07
    sta VDC_HI
    lda #18
    sta VDC_SEL
    lda #15
    sta VDC_LO
    stz VDC_HI
    plp
    rts
"""


def _build() -> tuple[bytes, dict[str, int]]:
    asm = Assembler()
    for name, value in _IO.items():
        asm.equ(name, value)
    for n, name in enumerate(_ZP):
        asm.zp(name, n)
    for name, value in (('BUFA', BUFA), ('BUFB', BUFB), ('BUFC', BUFC), ('SPRX', SPRX), ('SPRY', SPRY), ('SPRDX', SPRDX),
                        ('SPRDY', SPRDY), ('SATB', SATB), ('PAL_BG', PAL_BG), ('PAL_SPR', PAL_SPR), ('WAVES', WAVES),
                        ('VOLTAB', VOLTAB), ('SPRINIT', SPRINIT), ('NOISE', NOISE)):
        asm.equ(name, value)
    asm.section(0, 0xE000)
    asm.source(_bank0())
    for bank, text in ((1, _BANK1), (2, _BANK2), (3, _BANK3)):
        asm.section(bank, 0x4000)
        asm.source(text)
    palettes_bg, palettes_spr = _palettes()
    bank4 = b''.join(_bg_tile(0x80 + k) for k in range(128)) + b''.join(_sprite_pattern(i) for i in range(16)) + _map()
    assert len(bank4) == 8192
    bank5 = bytearray(8192)
    for offset, blob in ((PAL_BG, palettes_bg), (PAL_SPR, palettes_spr), (WAVES, _waves()), (VOLTAB, _volumes()),
                         (SPRINIT, _sprite_init()), (NOISE, _noise(1024))):
        bank5[offset:offset + len(blob)] = blob
    bank6 = bytes(int(127.5 + 127.5 * math.sin(2 * math.pi * k / 256)) for k in range(256)) + _noise(8192 - 256)
    bank7 = bytes(((i * 7) ^ (i >> 5) ^ 0x77) & 0xFF for i in range(8192))
    code = asm.assemble()
    image = bytearray(16 * 8192)
    for bank in range(16):
        if bank in code:
            blob = code[bank]
        elif bank == 4:
            blob = bank4
        elif bank == 5:
            blob = bytes(bank5)
        elif bank == 6:
            blob = bank6
        elif bank == 7:
            blob = bank7
        else:
            blob = bytes((i * 37 + bank * 101 + (i >> 8) * 13) & 0xFF for i in range(8192))
        assert len(blob) == 8192
        image[bank * 8192:(bank + 1) * 8192] = blob
    symbols = {name: 0x2000 + value for name, value in asm.final_symbols.items() if name in asm.zero_page}
    symbols.update({name: asm.final_symbols[name] for name in ('reset', 'irq1', 'timer_irq', 'brk_irq2', 'frame_loop')})
    return bytes(image), symbols


def build_rom() -> bytes:
    """The 128 KiB HuCard image (16 banks of 8 KiB), standard base profile, linear, no copier header."""
    return _build()[0]


def symbols() -> dict[str, int]:
    """Logical addresses of the zero-page counters ($2000 + offset) and of the main entry points."""
    return _build()[1]


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print('usage: pce_snapshot_rom.py out.pce [out.sym]', file=sys.stderr)
        return 2
    image, names = _build()
    with open(argv[1], 'wb') as handle:
        handle.write(image)
    if len(argv) == 3:
        with open(argv[2], 'w', newline='\n') as handle:
            handle.write(''.join(f'{name} {value:04X}\n' for name, value in names.items()))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
