"""A small MC68000 assembler for the authored hardware-check programs of the Atari ST (gate G11). Original Retro-Recomp code, MIT.

No cross-compiler is needed and no ROM, TOS or game byte is involved: a program is a few lines of text, encoded here word by word
with the encodings of the Motorola M68000 Family Programmer's Reference Manual (instruction formats, effective-address modes and
condition codes). It handles the subset the checks use and refuses anything else loudly, so a program can never silently become
another instruction. Every form has one fixed size (absolute addresses are 32-bit unless written `.w`, branches have a 16-bit
displacement unless written `.s`), so one layout pass fixes every label.

    asm = Assembler(0xFC0020)
    words = asm.assemble('''
            move.b  #$0a,$ff8001
    loop:   bra.s   loop
    ''')

Syntax: `label:`; `mnemonic[.b|.w|.l|.s] operand, operand`; `;` comments; numbers `$ff`, `0x10`, `%101`, decimal; operands Dn, An, SP,
(An), (An)+, -(An), d(An), `#expr`, `expr` (absolute), `expr.w`; expressions with + - * / << >> & | ~ and symbols (labels or the
`symbols` given), `*` alone is the address of the instruction; `dc.b/w/l expr,...`, `ds.b n`, `even`.
"""
from __future__ import annotations

import re

SIZE_BITS = {'b': 0, 'w': 1, 'l': 2}
MOVE_SIZE = {'b': 1, 'w': 3, 'l': 2}
CONDITIONS = {'ra': 0x0, 'sr': 0x1, 'hi': 0x2, 'ls': 0x3, 'cc': 0x4, 'hs': 0x4, 'cs': 0x5, 'lo': 0x5, 'ne': 0x6, 'eq': 0x7,
              'vc': 0x8, 'vs': 0x9, 'pl': 0xA, 'mi': 0xB, 'ge': 0xC, 'lt': 0xD, 'gt': 0xE, 'le': 0xF}
# opcode bases of the immediate forms (ORI, ANDI, SUBI, ADDI, EORI, CMPI)
IMMEDIATE = {'ori': 0x0000, 'andi': 0x0200, 'subi': 0x0400, 'addi': 0x0600, 'eori': 0x0A00, 'cmpi': 0x0C00}
# the arithmetic/logic operations: base opcode of "ea,Dn"; the "Dn,ea" form is the same with the opmode + 4 (EOR has only that one)
ALU = {'or': 0x8000, 'sub': 0x9000, 'cmp': 0xB000, 'and': 0xC000, 'add': 0xD000}
IMMEDIATE_OF = {'or': 'ori', 'and': 'andi', 'sub': 'subi', 'add': 'addi', 'cmp': 'cmpi', 'eor': 'eori'}
SHIFTS = {'as': 0, 'ls': 1, 'rox': 2, 'ro': 3}
ONE_OPERAND = {'clr': 0x4200, 'neg': 0x4400, 'not': 0x4600, 'tst': 0x4A00}
BIT_OPS = {'btst': 0, 'bchg': 1, 'bclr': 2, 'bset': 3}
FIXED = {'nop': 0x4E71, 'rte': 0x4E73, 'rts': 0x4E75, 'reset': 0x4E70}


class AssemblyError(ValueError):
    pass


def split_operands(text: str) -> list[str]:
    """Operands separated by commas outside parentheses."""
    out, depth, current = [], 0, ''
    for char in text:
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        if char == ',' and depth == 0:
            out.append(current.strip())
            current = ''
        else:
            current += char
    if current.strip():
        out.append(current.strip())
    return out


class Assembler:
    def __init__(self, origin: int, symbols: dict[str, int] | None = None):
        self.origin = origin
        self.symbols = dict(symbols or {})
        self.labels: dict[str, int] = {}

    # --------------------------------------------------------------------------------------------------- expressions
    def value(self, text: str, here: int, strict: bool) -> int:
        text = text.strip()
        if not text:
            raise AssemblyError('empty expression')
        py = re.sub(r'\$([0-9a-fA-F]+)', r'0x\1', text)
        py = re.sub(r'%([01]+)', lambda m: str(int(m.group(1), 2)), py)
        if py.strip() == '*':
            return here
        names = {**self.symbols, **self.labels}

        def lookup(match: re.Match) -> str:
            word = match.group(0)
            if re.fullmatch(r'0[xX][0-9a-fA-F]+', word) or word.isdigit():
                return word
            if word in names:
                return str(names[word])
            if strict:
                raise AssemblyError(f'unknown symbol {word!r} in {text!r}')
            return '0'
        py = re.sub(r'[A-Za-z_][A-Za-z_0-9]*|0[xX][0-9a-fA-F]+|\d+', lookup, py)
        if not re.fullmatch(r'[0-9a-fA-FxX+\-*/<>&|~() ]*', py):
            raise AssemblyError(f'cannot evaluate {text!r}')
        return int(eval(py, {'__builtins__': {}}, {}))   # only numbers and operators remain (checked above)

    # ------------------------------------------------------------------------------------------------ effective addresses
    def ea(self, text: str, size: str, here: int, strict: bool) -> tuple[int, int, list[int]]:
        """(mode, register, extension words) of an operand."""
        t = text.strip()
        low = t.lower()
        if low == 'sp':
            low = 'a7'
        if re.fullmatch(r'd[0-7]', low):
            return 0, int(low[1]), []
        if re.fullmatch(r'a[0-7]', low):
            if size == 'b':
                raise AssemblyError('a byte operation cannot use an address register')
            return 1, int(low[1]), []
        m = re.fullmatch(r'\((a[0-7]|sp)\)', low)
        if m:
            return 2, 7 if m.group(1) == 'sp' else int(m.group(1)[1]), []
        m = re.fullmatch(r'\((a[0-7]|sp)\)\+', low)
        if m:
            return 3, 7 if m.group(1) == 'sp' else int(m.group(1)[1]), []
        m = re.fullmatch(r'-\((a[0-7]|sp)\)', low)
        if m:
            return 4, 7 if m.group(1) == 'sp' else int(m.group(1)[1]), []
        m = re.fullmatch(r'(.+)\((a[0-7]|sp)\)', t, re.I)
        if m:
            reg = 7 if m.group(2).lower() == 'sp' else int(m.group(2)[1])
            disp = self.value(m.group(1), here, strict)
            if not -32768 <= disp <= 32767:
                raise AssemblyError(f'displacement out of range in {text!r}')
            return 5, reg, [disp & 0xFFFF]
        if t.startswith('#'):
            v = self.value(t[1:], here, strict)
            if size == 'l':
                return 7, 4, [(v >> 16) & 0xFFFF, v & 0xFFFF]
            if size == 'w':
                return 7, 4, [v & 0xFFFF]
            if strict and not -128 <= v <= 255:
                raise AssemblyError(f'byte immediate out of range in {text!r}')
            return 7, 4, [v & 0xFF]
        if low.endswith('.w'):
            v = self.value(t[:-2], here, strict)
            if strict and not (0 <= v <= 0x7FFF or 0xFFFF8000 <= (v & 0xFFFFFFFF) or 0xFF8000 <= v <= 0xFFFFFF):
                raise AssemblyError(f'absolute word address out of range in {text!r}')
            return 7, 0, [v & 0xFFFF]
        v = self.value(t[:-2] if low.endswith('.l') else t, here, strict) & 0xFFFFFFFF
        return 7, 1, [(v >> 16) & 0xFFFF, v & 0xFFFF]

    # ------------------------------------------------------------------------------------------------------ instructions
    def instruction(self, mnemonic: str, operands: list[str], here: int, strict: bool) -> list[int]:
        name, _, suffix = mnemonic.lower().partition('.')
        size = suffix if suffix in ('b', 'w', 'l', 's') else None
        ops = operands

        def need(count: int) -> None:
            if len(ops) != count:
                raise AssemblyError(f'{mnemonic} takes {count} operand(s), got {len(ops)}')

        def sz(default: str = 'w') -> str:
            if size == 's':
                raise AssemblyError(f'{mnemonic}: .s only applies to branches')
            return size or default

        def ea(text: str, s: str = 'w') -> tuple[int, int, list[int]]:
            return self.ea(text, s, here, strict)

        if name in FIXED:
            need(0)
            return [FIXED[name]]
        if name == 'stop':
            need(1)
            return [0x4E72, self.value(ops[0].lstrip('#'), here, strict) & 0xFFFF]
        if name == 'trap':
            need(1)
            return [0x4E40 | (self.value(ops[0].lstrip('#'), here, strict) & 15)]
        if name == 'moveq':
            need(2)
            v, mode, reg = self.value(ops[0].lstrip('#'), here, strict), *ea(ops[1])[:2]
            if mode != 0 or (strict and not -128 <= v <= 127):
                raise AssemblyError(f'bad moveq {operands}')
            return [0x7000 | reg << 9 | (v & 0xFF)]
        if name in ('move', 'movea'):
            need(2)
            s = sz()
            low0, low1 = ops[0].lower(), ops[1].lower()
            if low1 == 'sr':       # MOVE <ea>,SR
                m, r, ext = ea(ops[0], 'w')
                return [0x46C0 | m << 3 | r, *ext]
            if low0 == 'sr':       # MOVE SR,<ea>
                m, r, ext = ea(ops[1], 'w')
                return [0x40C0 | m << 3 | r, *ext]
            sm, sr_, sext = ea(ops[0], s)
            dm, dr, dext = ea(ops[1], s)
            if dm == 1 and s == 'b':
                raise AssemblyError('movea.b does not exist')
            if dm == 7 and dr in (2, 3, 4):
                raise AssemblyError('bad destination')
            return [MOVE_SIZE[s] << 12 | dr << 9 | dm << 6 | sm << 3 | sr_, *sext, *dext]
        if name in IMMEDIATE_OF and ops and ops[0].startswith('#') and len(ops) == 2:
            name = IMMEDIATE_OF[name] if ops[1].lower() not in ('sr', 'a0', 'a1', 'a2', 'a3', 'a4', 'a5', 'a6', 'a7', 'sp') else name
        if name in IMMEDIATE:
            need(2)
            s = sz()
            if ops[1].lower() == 'sr':
                if name not in ('ori', 'andi', 'eori'):
                    raise AssemblyError('only ori/andi/eori take sr')
                return [IMMEDIATE[name] | 0x7C, self.value(ops[0].lstrip('#'), here, strict) & 0xFFFF]
            _, _, imm = ea(ops[0], s)
            m, r, ext = ea(ops[1], s)
            return [IMMEDIATE[name] | SIZE_BITS[s] << 6 | m << 3 | r, *imm, *ext]
        if name in ('addq', 'subq'):
            need(2)
            s = sz()
            n = self.value(ops[0].lstrip('#'), here, strict)
            if strict and not 1 <= n <= 8:
                raise AssemblyError('quick value must be 1..8')
            m, r, ext = ea(ops[1], s)
            return [0x5000 | (n & 7) << 9 | (0x100 if name == 'subq' else 0) | SIZE_BITS[s] << 6 | m << 3 | r, *ext]
        if name in ('adda', 'suba', 'cmpa'):
            need(2)
            s = sz()
            dm, dr, _ = ea(ops[1])
            if dm != 1:
                raise AssemblyError(f'{name} needs an address register')
            m, r, ext = ea(ops[0], s)
            base = {'adda': 0xD000, 'suba': 0x9000, 'cmpa': 0xB000}[name]
            return [base | dr << 9 | (3 if s == 'w' else 7) << 6 | m << 3 | r, *ext]
        if name in ALU or name == 'eor':
            need(2)
            s = sz()
            dm, dr, dext = ea(ops[1], s)
            sm, sr_, sext = ea(ops[0], s)
            if name == 'eor':
                if sm != 0:
                    raise AssemblyError('eor takes a data register as source')
                return [0xB000 | sr_ << 9 | (4 + SIZE_BITS[s]) << 6 | dm << 3 | dr, *dext]
            if dm == 1 and name in ('add', 'sub'):
                raise AssemblyError(f'use {name}a for an address register')
            if dm == 0:            # ea,Dn
                return [ALU[name] | dr << 9 | SIZE_BITS[s] << 6 | sm << 3 | sr_, *sext]
            if sm == 0 and name != 'cmp':     # Dn,ea
                return [ALU[name] | sr_ << 9 | (4 + SIZE_BITS[s]) << 6 | dm << 3 | dr, *dext]
            raise AssemblyError(f'bad operands for {mnemonic}: {operands}')
        if name == 'lea':
            need(2)
            dm, dr, _ = ea(ops[1])
            m, r, ext = ea(ops[0], 'l')
            if dm != 1:
                raise AssemblyError('lea needs an address register')
            return [0x41C0 | dr << 9 | m << 3 | r, *ext]
        if name in ONE_OPERAND:
            need(1)
            s = sz()
            m, r, ext = ea(ops[0], s)
            return [ONE_OPERAND[name] | SIZE_BITS[s] << 6 | m << 3 | r, *ext]
        if name in BIT_OPS:
            need(2)
            kind = BIT_OPS[name]
            m, r, ext = ea(ops[1], 'b')
            if ops[0].startswith('#'):
                return [0x0800 | kind << 6 | m << 3 | r, self.value(ops[0][1:], here, strict) & 0xFF, *ext]
            sm, sr_, _ = ea(ops[0])
            if sm != 0:
                raise AssemblyError('bit number must be a data register or immediate')
            return [0x0100 | sr_ << 9 | kind << 6 | m << 3 | r, *ext]
        shift = re.fullmatch(r'(as|ls|rox|ro)([lr])', name)
        if shift:
            need(2)
            s = sz()
            kind, left = SHIFTS[shift.group(1)], shift.group(2) == 'l'
            dm, dr, _ = ea(ops[1])
            if dm != 0:
                raise AssemblyError('shifts take a data register')
            if ops[0].startswith('#'):
                n = self.value(ops[0][1:], here, strict)
                if strict and not 1 <= n <= 8:
                    raise AssemblyError('shift count must be 1..8')
                count, ir = n & 7, 0
            else:
                cm, count, _ = ea(ops[0])
                ir = 1
                if cm != 0:
                    raise AssemblyError('shift count register must be Dn')
            return [0xE000 | count << 9 | (0x100 if left else 0) | SIZE_BITS[s] << 6 | ir << 5 | kind << 3 | dr]
        if name == 'swap':
            need(1)
            return [0x4840 | ea(ops[0])[1]]
        if name == 'ext':
            need(1)
            return [(0x48C0 if sz() == 'l' else 0x4880) | ea(ops[0])[1]]
        if name in ('mulu', 'muls', 'divu', 'divs'):
            need(2)
            dm, dr, _ = ea(ops[1])
            m, r, ext = ea(ops[0], 'w')
            base = {'mulu': 0xC0C0, 'muls': 0xC1C0, 'divu': 0x80C0, 'divs': 0x81C0}[name]
            return [base | dr << 9 | m << 3 | r, *ext]
        if name in ('jmp', 'jsr'):
            need(1)
            m, r, ext = ea(ops[0], 'l')
            return [(0x4EC0 if name == 'jmp' else 0x4E80) | m << 3 | r, *ext]
        branch = re.fullmatch(r'b(ra|sr|hi|ls|cc|hs|cs|lo|ne|eq|vc|vs|pl|mi|ge|lt|gt|le)', name)
        if branch:
            need(1)
            code = 0x6000 | CONDITIONS[branch.group(1)] << 8
            displacement = self.value(ops[0], here, strict) - (here + 2)
            if size == 's':
                if strict and (not -128 <= displacement <= 127 or displacement in (0, -1)):
                    raise AssemblyError(f'short branch out of range ({displacement}) in {mnemonic} {operands}')
                return [code | (displacement & 0xFF)]
            if strict and not -32768 <= displacement <= 32767:
                raise AssemblyError('branch out of range')
            return [code, displacement & 0xFFFF]
        db = re.fullmatch(r'db(ra|f|t|hi|ls|cc|cs|ne|eq|vc|vs|pl|mi|ge|lt|gt|le)', name)
        if db:
            need(2)
            cond = 1 if db.group(1) in ('ra', 'f') else 0 if db.group(1) == 't' else CONDITIONS[db.group(1)]
            _, reg, _ = ea(ops[0])
            displacement = self.value(ops[1], here, strict) - (here + 2)
            if strict and not -32768 <= displacement <= 32767:
                raise AssemblyError('dbcc out of range')
            return [0x50C8 | cond << 8 | reg, displacement & 0xFFFF]
        raise AssemblyError(f'unsupported instruction {mnemonic!r}')

    # --------------------------------------------------------------------------------------------------------- the program
    def parse(self, source: str) -> list[tuple[str | None, str, list[str]]]:
        lines = []
        for raw in source.splitlines():
            text = raw.split(';', 1)[0].strip()
            while True:
                m = re.match(r'^([A-Za-z_][A-Za-z_0-9]*):\s*', text)
                if not m:
                    break
                lines.append((m.group(1), '', []))
                text = text[m.end():]
            if text:
                mnemonic, _, rest = text.partition(' ')
                lines.append((None, mnemonic.strip(), split_operands(rest.strip())))
        return lines

    def assemble(self, source: str) -> bytes:
        """The program as bytes starting at `origin`."""
        lines = self.parse(source)
        for strict in (False, True):
            out = bytearray()
            here = self.origin
            for label, mnemonic, operands in lines:
                if label is not None:
                    if strict is False and label in self.labels:
                        raise AssemblyError(f'label {label} defined twice')
                    self.labels[label] = here
                    continue
                name, _, suffix = mnemonic.lower().partition('.')
                if name in ('dc', 'ds', 'even'):
                    chunk = self.data(name, suffix, operands, here, strict)
                else:
                    if here & 1:
                        raise AssemblyError(f'instruction at odd address ${here:06x}: {mnemonic} {operands}')
                    words = self.instruction(mnemonic, operands, here, strict)
                    chunk = b''.join(w.to_bytes(2, 'big') for w in words)
                out += chunk
                here += len(chunk)
        return bytes(out)

    def data(self, name: str, suffix: str, operands: list[str], here: int, strict: bool) -> bytes:
        if name == 'even':
            return b'\x00' if here & 1 else b''
        if name == 'ds':
            return bytes(self.value(operands[0], here, strict) * {'b': 1, '': 1, 'w': 2, 'l': 4}[suffix])
        width = {'b': 1, 'w': 2, 'l': 4}[suffix]
        return b''.join((self.value(op, here + n * width, strict) & ((1 << width * 8) - 1)).to_bytes(width, 'big') for n, op in enumerate(operands))
