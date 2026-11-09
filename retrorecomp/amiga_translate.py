"""Amiga 68000 instructions translated to C, one routine per opcode, with the exact order of Moira's bus accesses (MIT).

`translate(opcode, handler, mode, size)` writes the body of an instruction form as C++ text: the effective address, the operation and the flags written out for that
opcode, every register a literal index. What stays the machine's is the bus: `read`, `write`, `prefetch`, `fullPrefetch`, `readExt` and `sync`, the functions through which
the CPU reaches Agnus and chip RAM, in the same order and at the same cycles as Moira's handler for the opcode, including where an address error stops the instruction.
Extension words are read live on the bus, as the interpreter reads them, so a form is right for its opcode at any address and with any extension words.

It returns None for a form it does not translate, which then stays Moira's code specialised (`amiga_codegen`), counted apart. The choice of what comes first follows what
four games execute: these handlers are about 99 % of their instructions. Written from Moira's handlers (MIT, the reference of every proof): `tools/amiga_vector_selftest.py`
compares every translated opcode with Moira's handler on the bus, the registers and the internal buffers, and each conversion compares every frame with the fresh reference.
The 68000 only: on another core `translate` answers None.
"""
from __future__ import annotations

# Moira's Mode values (MoiraTypes.h).
DN, AN, AI, PI, PD, DI, IX, AW, AL, DIPC, IXPC, IM, IP = range(13)
BYTE, WORD, LONG = 1, 2, 4
SIZE = {BYTE: 'Byte', WORD: 'Word', LONG: 'Long'}
C = 'Core::C68000'
# The 68000's conditions by their field in the opcode.
CONDITION = ('true', 'false', '!r.sr.c && !r.sr.z', 'r.sr.c || r.sr.z', '!r.sr.c', 'r.sr.c', '!r.sr.z', 'r.sr.z', '!r.sr.v', 'r.sr.v', '!r.sr.n', 'r.sr.n',
             'r.sr.n == r.sr.v', 'r.sr.n != r.sr.v', 'r.sr.n == r.sr.v && !r.sr.z', 'r.sr.n != r.sr.v || r.sr.z')


def _is_mem(mode: int) -> bool:
    return AI <= mode <= IXPC


def _is_reg(mode: int) -> bool:
    return mode in (DN, AN)


def _std_frame(mode: int, size: int) -> str:
    """Moira's STD_AE_FRAME for this mode and size."""
    if mode == PD and size != LONG:
        return 'AE_INC_PC'
    return 'AE_DEC_PC' if mode in (DI, IX, DIPC, IXPC) else '0'


def _step(n: int, size: int) -> int:
    return 2 if n == 7 and size == BYTE else size


EXT = f'm.readExt<{C}>();'


def _indexed(base: str, last: str) -> list:
    return ['{ i8 d = (i8)q.irc; u32 xi = r.r[(q.irc >> 12) & 0b1111];',
            f'  ea = U32_ADD3({base}, d, ((q.irc & 0x800) ? xi : SEXT<Word>(xi))); }}', 'm.sync(2);', last]


def _ea(mode: int, n: int, size: int, *, skip_last: bool = False, implied_decrement: bool = False) -> list:
    """Lines that compute `ea` (Moira's computeEA on a 68000). `skip_last`: the last extension word is passed, not fetched."""
    last = 'r.pc += 2;' if skip_last else EXT
    if mode in (AI, PI):
        return [f'ea = r.a[{n}];']
    if mode == PD:
        return ([] if implied_decrement else ['m.sync(2);']) + [f'ea = r.a[{n}] - {_step(n, size)};']
    if mode == DI:
        return [f'ea = U32_ADD(r.a[{n}], (i16)q.irc);', last]
    if mode == IX:
        return _indexed(f'r.a[{n}]', last)
    if mode == AW:
        return ['ea = (i16)q.irc;', 'm.readBuffer = q.irc;', last]
    if mode == AL:
        return ['ea = q.irc << 16;', EXT, 'ea |= q.irc;', 'm.readBuffer = q.irc;', last]
    if mode == DIPC:
        return ['ea = U32_ADD(r.pc, (i16)q.irc);', last]
    if mode == IXPC:
        return _indexed('r.pc', last)
    raise ValueError(mode)


def _space(mode: int) -> str:
    return 'AddrSpace::PROG' if mode in (DIPC, IXPC) else 'AddrSpace::DATA'


def _read(mode: int, size: int, flags: str, address: str = 'ea') -> str:
    return f'm.read<{C}, {_space(mode)}, {SIZE[size]}, {flags}>({address})'


def _write(mode: int, size: int, flags: str, value: str, address: str = 'ea') -> str:
    return f'm.write<{C}, {_space(mode)}, {SIZE[size]}, {flags}>({address}, {value});'


def _immediate(size: int, target: str = 'data') -> list:
    """Moira's readI."""
    if size == BYTE:
        lines = [f'{target} = (u8)q.irc;', EXT]
    elif size == WORD:
        lines = [f'{target} = q.irc;', EXT]
    else:
        lines = [f'{target} = q.irc << 16;', EXT, f'{target} |= q.irc;', EXT]
    return lines + ['m.readBuffer = q.irc;']


def _read_op(mode: int, n: int, size: int, flags: str = '0', target: str = 'data') -> list:
    """Moira's readOp: `data`, and `ea` for a memory operand."""
    if mode == DN:
        return [f'{target} = CLIP<{SIZE[size]}>(r.d[{n}]);']
    if mode == AN:
        return [f'{target} = CLIP<{SIZE[size]}>(r.a[{n}]);']
    if mode == IM:
        return _immediate(size, target)
    lines = _ea(mode, n, size)
    if mode == PD:
        lines.append(f'U32_DEC(r.a[{n}], {_step(n, size)});')
    lines.append(f'{target} = {_read(mode, size, flags)};')
    if mode == PI:
        lines.append(f'U32_INC(r.a[{n}], {_step(n, size)});')
    return lines


def _write_reg(mode: int, n: int, size: int, value: str) -> str:
    bank = 'd' if mode == DN else 'a'
    return f'r.{bank}[{n}] = WRITE<{SIZE[size]}>(r.{bank}[{n}], {value});'


def _buffer(size: int, value: str) -> str:
    return f'm.writeBuffer = {f"u16(({value}) >> 16)" if size == LONG else f"u16(({value}) & 0xFFFF)"};'


def _write_op(mode: int, n: int, size: int, flags: str, value: str) -> list:
    """Moira's writeOp with the address still to compute."""
    if _is_reg(mode):
        return [_write_reg(mode, n, size, value)]
    lines = [_buffer(size, value)] + _ea(mode, n, size)
    if mode == PD:
        lines.append(f'U32_DEC(r.a[{n}], {_step(n, size)});')
    lines.append(_write(mode, size, flags, value))
    if mode == PI:
        lines.append(f'U32_INC(r.a[{n}], {_step(n, size)});')
    return lines


def _write_back(mode: int, n: int, size: int, flags: str, value: str) -> list:
    """Moira's writeOp with `ea` known."""
    if _is_reg(mode):
        return [_write_reg(mode, n, size, value)]
    return [_buffer(size, value), _write(mode, size, flags, value)]


def _nz00(size: int, value: str = 'data') -> list:
    s = SIZE[size]
    return [f'r.sr.n = NBIT<{s}>({value});', f'r.sr.z = ZERO<{s}>({value});', 'r.sr.v = 0;', 'r.sr.c = 0;']


PREFETCH_POLL = f'm.prefetch<{C}, POLL>();'
PREFETCH = f'm.prefetch<{C}>();'
FULL_POLL = f'm.fullPrefetch<{C}, POLL>();'


def _cmp(size: int, source: str, target: str) -> list:
    s = SIZE[size]
    return [f'{{ u32 op1 = {source}, op2 = {target}; u64 res = U64_SUB(op2, op1);',
            f'  r.sr.c = NBIT<{s}>(res >> 1); r.sr.v = NBIT<{s}>((op2 ^ op1) & (op2 ^ res)); r.sr.z = ZERO<{s}>(res); r.sr.n = NBIT<{s}>(res); }}']


def _addsub(kind: str, size: int, source: str, target: str) -> list:
    """Moira's addsub: `result` from op1 (the source) and op2."""
    s = SIZE[size]
    if kind == 'add':
        body = [f'u64 res = U64_ADD(op1, op2);', f'r.sr.x = r.sr.c = CARRY<{s}>(res); r.sr.v = NBIT<{s}>((op1 ^ res) & (op2 ^ res)); r.sr.z = ZERO<{s}>(res);']
    elif kind == 'addx':
        body = ['u64 res = U64_ADD3(op1, op2, r.sr.x);', f'r.sr.x = r.sr.c = CARRY<{s}>(res); r.sr.v = NBIT<{s}>((op1 ^ res) & (op2 ^ res)); if (CLIP<{s}>(res)) r.sr.z = 0;']
    elif kind == 'sub':
        body = ['u64 res = U64_SUB(op2, op1);', f'r.sr.x = r.sr.c = CARRY<{s}>(res); r.sr.v = NBIT<{s}>((op1 ^ op2) & (op2 ^ res)); r.sr.z = ZERO<{s}>(res);']
    else:
        body = ['u64 res = U64_SUB3(op2, op1, r.sr.x);', f'r.sr.x = r.sr.c = CARRY<{s}>(res); r.sr.v = NBIT<{s}>((op1 ^ op2) & (op2 ^ res)); if (CLIP<{s}>(res)) r.sr.z = 0;']
    return [f'{{ u32 op1 = {source}, op2 = {target};'] + ['  ' + line for line in body] + [f'  r.sr.n = NBIT<{s}>(res); result = (u32)res; }}']


def _logic(kind: str, size: int, source: str, target: str) -> list:
    operator = {'and': '&', 'or': '|', 'eor': '^'}[kind]
    return [f'result = ({source}) {operator} ({target});'] + _nz00(size, 'result')


# ------------------------------------------------------------------------------------------------------------ the handlers
def _bcc(op, mode, size):
    disp = f'0x{op & 0xff:x}u' if size == BYTE else 'q.irc'
    taken = ['u32 newpc = U32_ADD(oldpc, SEXT<' + SIZE[size] + f'>({disp}));', f'if (m.misaligned<{C}>(newpc)) throw AddressError(m.makeFrame(newpc));',
             'r.pc = newpc;', FULL_POLL]
    other = ['m.sync(2);'] + ([EXT] if size == WORD else []) + [PREFETCH_POLL]
    return ['u32 oldpc = r.pc;', 'm.sync(2);', f'if ({CONDITION[op >> 8 & 15]}) {{'] + taken + ['} else {'] + other + ['}']


def _bra(op, mode, size):
    disp = f'0x{op & 0xff:x}u' if size == BYTE else 'q.irc'
    return ['u32 oldpc = r.pc;', 'm.sync(2);', 'u32 newpc = U32_ADD(oldpc, SEXT<' + SIZE[size] + f'>({disp}));',
            f'if (m.misaligned<{C}>(newpc)) throw AddressError(m.makeFrame(newpc));', 'r.pc = newpc;', FULL_POLL]


def _bsr(op, mode, size):
    disp = f'0x{op & 0xff:x}u' if size == BYTE else 'q.irc'
    return ['u32 oldpc = r.pc;', 'u32 newpc = U32_ADD(oldpc, SEXT<' + SIZE[size] + f'>({disp}));', f'u32 retpc = U32_ADD(r.pc, {2 if size == WORD else 0});', 'm.sync(2);',
            f'if (m.misaligned<{C}>(r.sp)) {{ r.sp -= 4; throw AddressError(m.makeFrame<AE_WRITE|AE_DATA>(r.sp)); }}',
            f'if (m.misaligned<{C}>(newpc)) throw AddressError(m.makeFrame(newpc));', 'r.sp -= 4;', f'm.write<{C}, AddrSpace::DATA, Long>(r.sp, retpc);',
            'r.pc = newpc;', FULL_POLL]


def _dbcc(op, mode, size):
    n = op & 7
    return ['m.sync(2);', f'if (!({CONDITION[op >> 8 & 15]})) {{', 'u32 newpc = U32_ADD(r.pc, (i16)q.irc);', f'bool take = CLIP<Word>(r.d[{n}]) != 0;',
            f'if (m.misaligned<{C}, Word>(newpc)) throw AddressError(m.makeFrame<AE_INC_PC>(newpc, newpc));',
            f'r.d[{n}] = WRITE<Word>(r.d[{n}], U32_SUB(CLIP<Word>(r.d[{n}]), 1));',
            'if (take) {', 'r.pc = newpc;', FULL_POLL, '} else {', f'(void)m.read<{C}, AddrSpace::PROG, Word>(r.pc + 2);', 'r.pc += 2;', FULL_POLL, '}',
            '} else {', 'm.sync(2);', 'r.pc += 2;', FULL_POLL, '}']


def _cmp_ea(op, mode, size):
    return ['u32 ea, data;', *_read_op(mode, op & 7, size, _std_frame(mode, size)), *_cmp(size, 'data', f'CLIP<{SIZE[size]}>(r.d[{op >> 9 & 7}])'),
            PREFETCH_POLL] + (['m.sync(2);'] if size == LONG else [])


def _cmpi_ea(op, mode, size):
    return ['u32 src, ea, data;', *_immediate(size, 'src'), *_read_op(mode, op & 7, size, _std_frame(mode, size)), PREFETCH_POLL, *_cmp(size, 'src', 'data')]


def _cmpi_rg(op, mode, size):
    return ['u32 src;', *_immediate(size, 'src'), PREFETCH_POLL] + (['m.sync(2);'] if size == LONG else []) + _cmp(size, 'src', f'CLIP<{SIZE[size]}>(r.d[{op & 7}])')


def _cmpa(op, mode, size):
    return ['u32 ea, data;', *_read_op(mode, op & 7, size, _std_frame(mode, size)), f'data = SEXT<{SIZE[size]}>(data);', *_cmp(LONG, 'data', f'r.a[{op >> 9 & 7}]'), PREFETCH_POLL, 'm.sync(2);']


def _tst(op, mode, size):
    return ['u32 ea, data;', *_read_op(mode, op & 7, size, _std_frame(mode, size)), *_nz00(size), PREFETCH_POLL]


def _move0(op, mode, size):
    return ['u32 ea, data;', *_read_op(mode, op & 7, size, _std_frame(mode, size)), *_nz00(size), _write_reg(DN, op >> 9 & 7, size, 'data'), PREFETCH_POLL]


def _word_flags_then_write(size, write):
    s = SIZE[size]
    return ['r.sr.n = NBIT<Word>(data);', 'r.sr.z = ZERO<Word>(data);', 'r.sr.v = 0;', 'r.sr.c = 0;', *write, f'r.sr.n = NBIT<{s}>(data);', f'r.sr.z = ZERO<{s}>(data);']


def _move2(op, mode, size):
    n = op >> 9 & 7
    head = ['u32 ea, data;', *_read_op(mode, op & 7, size, _std_frame(mode, size))]
    if not _is_mem(mode) and size == LONG:
        return head + _write_op(AI, n, size, 'AE_INC_PC|POLL', 'data') + _nz00(size) + [PREFETCH]
    return head + _word_flags_then_write(size, _write_op(AI, n, size, 'AE_INC_PC', 'data')) + [PREFETCH_POLL]


def _move3(op, mode, size):
    n = op >> 9 & 7
    head = ['u32 ea, data;', *_read_op(mode, op & 7, size, _std_frame(mode, size))]
    if not _is_mem(mode) and size == LONG:
        return head + _write_op(PI, n, size, 'AE_INC_PC|POLL', 'data') + _nz00(size) + [PREFETCH]
    return head + _word_flags_then_write(size, _write_op(PI, n, size, 'AE_INC_PC|POLL', 'data')) + [PREFETCH]


def _move4(op, mode, size):
    n = op >> 9 & 7
    return ['u16 ird = m.getIRD();', 'u32 ea, data;', *_read_op(mode, op & 7, size, _std_frame(mode, size)),
            f'int format = {"0" if size == LONG else "(r.sr.s || r.sr.c) ? 2 : 1"};', *_nz00(size), PREFETCH_POLL,
            *_ea(PD, n, size, implied_decrement=True), 'm.writeBuffer = u16(data);',
            f'if (m.misaligned<{C}, {SIZE[size]}>(ea)) {{',
            *([] if size == LONG else [f'U32_DEC(r.a[{n}], {_step(n, size)});']),
            'if (format == 0) throw AddressError(m.makeFrame<AE_WRITE|AE_DATA>(ea + 2, r.pc + 2, m.getSR(), ird));',
            'if (format == 1) { m.sync(2); throw AddressError(m.makeFrame<AE_WRITE|AE_DATA|AE_SET_CB3>(ea, r.pc + 2)); }',
            'if (format == 2) { m.sync(2); throw AddressError(m.makeFrame<AE_WRITE|AE_DATA>(ea, r.pc + 2)); }', '}',
            _write(PD, size, 'REVERSE', 'data'), f'U32_DEC(r.a[{n}], {_step(n, size)});']


def _move56(target):
    def build(op, mode, size):
        n = op >> 9 & 7
        head = ['u32 ea, data;', *_read_op(mode, op & 7, size, _std_frame(mode, size))]
        if not _is_mem(mode) and size == LONG:
            return head + ['r.sr.n = NBIT<Word>(data >> 16);', 'r.sr.z = ZERO<Word>(data >> 16) && r.sr.z;', *_write_op(target, n, size, 'POLL', 'data'), *_nz00(size), PREFETCH]
        return head + _nz00(size) + _write_op(target, n, size, '0', 'data') + [PREFETCH_POLL]
    return build


def _move7(op, mode, size):
    return ['u32 ea, data;', *_read_op(mode, op & 7, size, _std_frame(mode, size)), *_nz00(size), *_write_op(AW, op >> 9 & 7, size, '0', 'data'), PREFETCH_POLL]


def _move8(op, mode, size):
    if _is_mem(mode):
        return ['u32 ea, data;', *_read_op(mode, op & 7, size, _std_frame(mode, size)), 'r.sr.n = NBIT<Word>(data);', 'r.sr.z = ZERO<Word>(data);', 'r.sr.v = 0;', 'r.sr.c = 0;',
                'u32 ea2 = q.irc << 16;', EXT, 'ea2 |= q.irc;', f'if (m.misaligned<{C}, {SIZE[size]}>(ea2)) throw AddressError(m.makeFrame<AE_WRITE|AE_DATA>(ea2));',
                *_nz00(size), _write(AL, size, '0', 'data', 'ea2'), EXT, PREFETCH_POLL]
    return ['u32 ea, data;', *_read_op(mode, op & 7, size, '0'), *_nz00(size), *_write_op(AL, op >> 9 & 7, size, '0', 'data'), PREFETCH_POLL]


def _movea(op, mode, size):
    frame = _std_frame(mode, size)
    return ['u32 ea = 0, data;', 'try {', *_read_op(mode, op & 7, size, '0'), f'}} catch (AddressError &exc) {{ exc.stackFrame = m.makeFrame<({frame})|AE_SET_RW|AE_SET_DF>(ea); throw exc; }}',
            PREFETCH_POLL, f'r.a[{op >> 9 & 7}] = SEXT<{SIZE[size]}>(data);']


def _moveq(op, mode, size):
    n = op >> 9 & 7
    return [f'i8 src = (i8)0x{op & 0xff:02x};', f'r.d[{n}] = (u32)(i32)src;', 'r.sr.n = NBIT<Byte>(src);', 'r.sr.z = ZERO<Byte>(src);', 'r.sr.v = 0;', 'r.sr.c = 0;', PREFETCH_POLL]


_SHIFTS = {
    0: ('as', "bool carry = false; u32 changed = 0;", {
        1: 'carry = NBIT<S>(v); u64 next = (v & 0xFFFFFFFF) << 1; changed |= (u32)(v ^ next); v = next;',
        0: 'carry = v & 1; u64 next = SEXT<S>(v) >> 1; changed |= (u32)(v ^ next); v = next;'}),
    1: ('ls', 'bool carry = false;', {1: 'carry = NBIT<S>(v); v = v << 1;', 0: 'carry = v & 1; v = v >> 1;'}),
    2: ('rox', 'bool carry = r.sr.x;', {1: 'bool extend = carry; carry = NBIT<S>(v); v = v << 1 | (extend ? 1 : 0);',
                                        0: 'bool extend = carry; carry = v & 1; v >>= 1; if (extend) v |= MSBIT<S>();'}),
    3: ('ro', 'bool carry = false;', {1: 'carry = NBIT<S>(v); v = v << 1 | (carry ? 1 : 0);', 0: 'carry = v & 1; v >>= 1; if (carry) v |= MSBIT<S>();'}),
}


def _shift_lines(kind: int, left: int, size: int, target: str) -> list:
    """Moira's shift on a register, `cnt` being known."""
    name, start, step = _SHIFTS[kind]
    s = SIZE[size]
    tail = {'as': [f'if (cnt) r.sr.x = carry;', 'r.sr.c = carry;', f'r.sr.v = NBIT<{s}>(changed);'],
            'ls': ['if (cnt) r.sr.x = carry;', 'r.sr.c = carry;', 'r.sr.v = 0;'],
            'rox': ['r.sr.x = carry;', 'r.sr.c = carry;', 'r.sr.v = 0;'], 'ro': ['r.sr.c = carry;', 'r.sr.v = 0;']}[name]
    return [f'{{ u64 v = CLIP<{s}>({target}); {start}', f'  for (int i = 0; i < cnt; i++) {{ {step[left].replace("<S>", "<" + s + ">")} }}', *['  ' + t for t in tail],
            f'  r.sr.n = NBIT<{s}>(v); r.sr.z = ZERO<{s}>(v);', f'  r.d[{{n}}] = WRITE<{s}>(r.d[{{n}}], CLIP<{s}>(v)); }}']


def _shift_im(op, mode, size):
    src, n, left, kind = op >> 9 & 7, op & 7, op >> 8 & 1, op >> 3 & 3
    cnt = src or 8
    cycles = (4 if size == LONG else 2) + 2 * cnt
    return [f'const int cnt = {cnt};', PREFETCH_POLL, f'm.sync({cycles});', *[line.replace('{n}', str(n)) for line in _shift_lines(kind, left, size, f'r.d[{n}]')]]


def _shift_rg(op, mode, size):
    src, n, left, kind = op >> 9 & 7, op & 7, op >> 8 & 1, op >> 3 & 3
    return [f'int cnt = r.d[{src}] & 0x3F;', f'int cyc = {4 if size == LONG else 2} + 2 * cnt;', PREFETCH_POLL, 'm.sync(cyc);',
            *[line.replace('{n}', str(n)) for line in _shift_lines(kind, left, size, f'r.d[{n}]')]]


def _logic_of_immediate(op):
    return {0: 'or', 1: 'and', 5: 'eor'}[op >> 9 & 7]


def _andi_rg(op, mode, size):
    n = op & 7
    return ['u32 src, result;', *_immediate(size, 'src'), *_logic(_logic_of_immediate(op), size, 'src', f'CLIP<{SIZE[size]}>(r.d[{n}])'), PREFETCH_POLL,
            *(['m.sync(4);'] if size == LONG else []), _write_reg(DN, n, size, 'result')]


def _andi_ea(op, mode, size):
    n = op & 7
    return ['u32 src, ea, data, result;', *_immediate(size, 'src'), *_read_op(mode, n, size, _std_frame(mode, size)), *_logic(_logic_of_immediate(op), size, 'src', 'data'),
            PREFETCH_POLL, *_write_back(mode, n, size, 'REVERSE', 'result')]


def _add_kind(op):
    return 'add' if op >> 12 == 0xd else 'sub'


def _addx_rg(op, mode, size):
    s = SIZE[size]
    n = op >> 9 & 7
    return ['u32 result;', *_addsub('addx' if op >> 12 == 0xd else 'subx', size, f'CLIP<{s}>(r.d[{op & 7}])', f'CLIP<{s}>(r.d[{n}])'), PREFETCH_POLL,
            *(['m.sync(4);'] if size == LONG else []), _write_reg(DN, n, size, 'result')]


def _add_ea_rg(op, mode, size):
    s = SIZE[size]
    n = op >> 9 & 7
    return ['u32 ea, data, result;', *_read_op(mode, op & 7, size, _std_frame(mode, size)), *_addsub(_add_kind(op), size, 'data', f'CLIP<{s}>(r.d[{n}])'),
            _write_reg(DN, n, size, 'result'), PREFETCH_POLL, *([f'm.sync({2 if _is_mem(mode) else 4});'] if size == LONG else [])]


def _add_rg_ea(op, mode, size):
    s = SIZE[size]
    return ['u32 ea, data, result;', *_read_op(mode, op & 7, size, _std_frame(mode, size)), *_addsub(_add_kind(op), size, f'CLIP<{s}>(r.d[{op >> 9 & 7}])', 'data'),
            PREFETCH_POLL, _write(mode, size, '0', 'result')]


def _quick(op):
    return (op >> 9 & 7) or 8, 'sub' if op >> 8 & 1 else 'add'


def _addq_dn(op, mode, size):
    value, kind = _quick(op)
    n = op & 7
    return ['u32 result;', *_addsub(kind, size, str(value), f'CLIP<{SIZE[size]}>(r.d[{n}])'), PREFETCH_POLL, *(['m.sync(4);'] if size == LONG else []), _write_reg(DN, n, size, 'result')]


def _addq_an(op, mode, size):
    value, kind = _quick(op)
    n = op & 7
    return [f'u32 result = {"U32_ADD" if kind == "add" else "U32_SUB"}(r.a[{n}], {value});', PREFETCH_POLL, 'm.sync(4);', f'r.a[{n}] = result;']


def _addq_ea(op, mode, size):
    value, kind = _quick(op)
    n = op & 7
    return ['u32 ea, data, result;', *_read_op(mode, n, size, _std_frame(mode, size)), *_addsub(kind, size, str(value), 'data'), PREFETCH_POLL, *_write_back(mode, n, size, '0', 'result')]


def _immediate_add_kind(op):
    return 'add' if op >> 8 == 0x06 else 'sub'


def _addi_rg(op, mode, size):
    n = op & 7
    return ['u32 src, result;', *_immediate(size, 'src'), *_addsub(_immediate_add_kind(op), size, 'src', f'CLIP<{SIZE[size]}>(r.d[{n}])'), PREFETCH_POLL,
            *(['m.sync(4);'] if size == LONG else []), _write_reg(DN, n, size, 'result')]


def _addi_ea(op, mode, size):
    n = op & 7
    return ['u32 src, ea, data, result;', *_immediate(size, 'src'), *_read_op(mode, n, size, _std_frame(mode, size)), *_addsub(_immediate_add_kind(op), size, 'src', 'data'), PREFETCH,
            *_write_back(mode, n, size, 'POLL', 'result')]


def _adda(op, mode, size):
    n = op >> 9 & 7
    extra = size == WORD or _is_reg(mode) or mode == IM
    return ['u32 ea, data;', *_read_op(mode, op & 7, size, _std_frame(mode, size)), f'data = SEXT<{SIZE[size]}>(data);',
            f'r.a[{n}] = {"U32_ADD" if op >> 12 == 0xd else "U32_SUB"}(r.a[{n}], data);', PREFETCH_POLL, 'm.sync(2);', *(['m.sync(2);'] if extra else [])]


_BIT = {0: '', 1: 'data ^= (1u << b);', 2: 'data &= ~(1u << b);', 3: 'data |= (1u << b);'}


def _bit_flag_and_change(kind):
    return ['r.sr.z = 1 ^ ((data >> b) & 1);'] + ([_BIT[kind]] if kind else [])


def _bit_cycles(kind):
    return ('2', 'b > 15 ? 4 : 2', 'b > 15 ? 6 : 4', 'b > 15 ? 4 : 2')[kind]


def _bit_im_ea(op, mode, size):
    kind = op >> 6 & 3
    n = op & 7
    return ['u32 src, ea, data;', *_immediate(BYTE, 'src'), 'u8 b = (u8)src & 0b111;', *_read_op(mode, n, BYTE, '0'), *_bit_flag_and_change(kind), PREFETCH_POLL,
            *([_write(mode, BYTE, '0', 'data')] if kind else [])]


def _bit_im_dy(op, mode, size):
    kind = op >> 6 & 3
    n = op & 7
    return ['u32 src;', *_immediate(BYTE, 'src'), 'u8 b = (u8)src & 0b11111;', f'u32 data = r.d[{n}];', *_bit_flag_and_change(kind), PREFETCH_POLL,
            f'm.sync({_bit_cycles(kind)});', *([f'r.d[{n}] = data;'] if kind else [])]


def _bit_dx_ea(op, mode, size):
    kind = op >> 6 & 3
    n = op & 7
    return [f'u8 b = r.d[{op >> 9 & 7}] & 0b111;', 'u32 ea, data;', *_read_op(mode, n, BYTE, '0'), *_bit_flag_and_change(kind), PREFETCH_POLL,
            *([_write(mode, BYTE, '0', 'data')] if kind else [])]


def _bit_dx_dy(op, mode, size):
    kind = op >> 6 & 3
    n = op & 7
    return [f'u8 b = r.d[{op >> 9 & 7}] & 0b11111;', f'int c = {_bit_cycles(kind)};', f'u32 data = r.d[{n}];', *_bit_flag_and_change(kind), PREFETCH_POLL, 'm.sync(c);',
            *([f'r.d[{n}] = data;'] if kind else [])]


def _lea(op, mode, size):
    return ['u32 ea;', *_ea(mode, op & 7, LONG), f'r.a[{op >> 9 & 7}] = ea;', *(['m.sync(2);'] if mode in (IX, IXPC) else []), PREFETCH_POLL]


def _rts(op, mode, size):
    return [f'if (m.misaligned<{C}>(r.sp)) {{', f'm.setFC<(Mode){mode}>();', f'm.readBuffer = u16(m.read<{C}, AddrSpace::DATA, Word>(r.sp & ~1u));',
            'throw AddressError(m.makeFrame<AE_SET_RW|AE_SET_DF>(r.sp)); }', f'u32 newpc = m.read<{C}, AddrSpace::DATA, Long>(r.sp);', 'r.sp += 4;',
            f'if (m.misaligned<{C}>(newpc)) throw AddressError(m.makeFrame<AE_PROG>(newpc));', 'r.pc = newpc;', FULL_POLL]


def _and_kind(op):
    return {0xc: 'and', 0x8: 'or', 0xb: 'eor'}[op >> 12]


def _and_ea_rg(op, mode, size):
    n = op >> 9 & 7
    return ['u32 ea, data, result;', *_read_op(mode, op & 7, size, _std_frame(mode, size)), *_logic(_and_kind(op), size, 'data', f'CLIP<{SIZE[size]}>(r.d[{n}])'),
            _write_reg(DN, n, size, 'result'), PREFETCH_POLL, *([f'm.sync({4 if _is_reg(mode) or mode == IM else 2});'] if size == LONG else [])]


def _and_rg_ea(op, mode, size):
    n = op & 7
    return ['u32 ea, data, result;', *_read_op(mode, n, size, _std_frame(mode, size)), *_logic(_and_kind(op), size, f'CLIP<{SIZE[size]}>(r.d[{op >> 9 & 7}])', 'data'), PREFETCH_POLL,
            *(['m.sync(4);'] if size == LONG and _is_reg(mode) else []), *_write_back(mode, n, size, 'REVERSE', 'result')]


def _swap(op, mode, size):
    n = op & 7
    return [f'u32 data = r.d[{n}];', PREFETCH_POLL, 'data = (data >> 16) | (data & 0xFFFF) << 16;', f'r.d[{n}] = data;', *_nz00(LONG)]


# Moira's extra delay of JMP, JSR by mode.
_JUMP_DELAY = (0, 0, 0, 0, 0, 2, 4, 2, 0, 2, 4, 0)


def _jmp(op, mode, size):
    delay = _JUMP_DELAY[mode]
    return ['u32 oldpc = r.pc;', 'u32 ea;', *_ea(mode, op & 7, LONG, skip_last=True), *([f'm.sync({delay});'] if delay else []),
            f'if (m.misaligned<{C}, Word>(ea)) throw AddressError(m.makeFrame(ea, oldpc));', 'r.pc = ea;', FULL_POLL]


def _jsr(op, mode, size):
    delay = _JUMP_DELAY[mode]
    frame = 'm.makeFrame<AE_DEC_PC>(ea)' if mode in (DI, IX, DIPC, IXPC) else 'm.makeFrame(ea)'
    return ['u32 ea;', *_ea(mode, op & 7, LONG, skip_last=True), *([f'm.sync({delay});'] if delay else []), f'if (m.misaligned<{C}>(ea)) throw AddressError({frame});',
            'r.sp -= 4;', f'm.write<{C}, AddrSpace::DATA, Long>(r.sp, r.pc);', 'r.pc = ea;', f'q.irc = (u16)m.read<{C}, AddrSpace::PROG, Word>(ea);', PREFETCH_POLL]


def _clr(op, mode, size):
    n = op & 7
    return ['u32 ea, data;', *_read_op(mode, n, size, _std_frame(mode, size)), PREFETCH_POLL, *(['m.sync(2);'] if size == LONG and _is_reg(mode) else []),
            *_write_back(mode, n, size, 'REVERSE', '0'), 'r.sr.n = 0;', 'r.sr.z = 1;', 'r.sr.v = 0;', 'r.sr.c = 0;']


def _nop(op, mode, size):
    return [PREFETCH_POLL]


def _movem_ea_rg(op, mode, size):
    n = op & 7
    s = SIZE[size]
    frame = 'AE_DEC_PC|AE_SET_DF|AE_SET_RW' if mode in (IX, IXPC) else 'AE_INC_PC|AE_SET_DF|AE_SET_RW'
    return ['u32 src, ea;', *_immediate(WORD, 'src'), 'u16 mask = (u16)src;', *_ea(mode, n, size),
            f'if (m.misaligned<{C}, {s}>(ea)) {{ m.setFC<(Mode){mode}>(); throw AddressError(m.makeFrame<{frame}>(ea)); }}',
            *([f'(void)m.read<{C}, AddrSpace::DATA, Word>(ea);'] if size == LONG else []),
            f'for (int i = 0; i <= 15; i++) {{ if ((mask & (1 << i)) == 0) continue; r.r[i] = SEXT<{s}>({_read(mode, size, "0")}); ea += {size}; }}',
            *([f'r.a[{n}] = ea;'] if mode == PI else []), *([f'(void)m.read<{C}, AddrSpace::DATA, Word>(ea);'] if size == WORD else []), PREFETCH_POLL]


def _movem_rg_ea(op, mode, size):
    n = op & 7
    s = SIZE[size]
    if mode == PD:
        return ['u32 src;', *_immediate(WORD, 'src'), 'u16 mask = (u16)src;', f'u32 ea = r.a[{n}];',
                'for (int i = 15; i >= 0; i--) {', 'if ((mask & (0x8000 >> i)) == 0) continue;',
                f'if (m.misaligned<{C}, {s}>(ea)) {{ m.setFC<(Mode){mode}>(); m.readBuffer = mask; m.writeBuffer = u16(r.r[i] & 0xFFFF); '
                'throw AddressError(m.makeFrame<AE_INC_PC|AE_WRITE>(U32_SUB(ea, 2))); }', f'ea -= {size};', _write(mode, size, '0', 'r.r[i]'), '}',
                f'r.a[{n}] = ea;', PREFETCH_POLL]
    buffer = 'u16(r.r[i] >> 16)' if size == LONG else 'u16(r.r[i] & 0xFFFF)'
    return ['u32 src, ea;', *_immediate(WORD, 'src'), 'u16 mask = (u16)src;', *_ea(mode, n, size), 'for (int i = 0; i < 16; i++) {', 'if ((mask & (1 << i)) == 0) continue;',
            f'if (m.misaligned<{C}, {s}>(ea)) {{ m.setFC<(Mode){mode}>(); m.readBuffer = mask; m.writeBuffer = {buffer}; throw AddressError(m.makeFrame<AE_INC_PC|AE_WRITE>(ea)); }}',
            _write(mode, size, '0', 'r.r[i]'), f'ea += {size};', '}', PREFETCH_POLL]


def _ext(op, mode, size):
    n = op & 7
    return [f'u32 dn = r.d[{n}];', f'dn = {"SEXT<Word>(dn)" if size == LONG else "SEXT<Byte>(dn)"};', _write_reg(DN, n, size, 'dn'), *_nz00(size, 'dn'), PREFETCH_POLL]


def _neg_rg(op, mode, size):
    n = op & 7
    s = SIZE[size]
    kind = {0x44: 'sub', 0x40: 'subx', 0x46: 'not'}.get(op >> 8)
    if kind is None:
        return None
    if kind == 'not':
        operation = [f'result = ~CLIP<{s}>(r.d[{n}]);', *_nz00(size, 'result')]
    else:
        operation = _addsub(kind, size, f'CLIP<{s}>(r.d[{n}])', '0')
    return ['u32 result;', *operation, PREFETCH_POLL, *(['m.sync(2);'] if size == LONG else []), _write_reg(DN, n, size, 'result')]


def _pea(op, mode, size):
    absolute = mode in (AW, AL)
    indexed = mode in (IX, IXPC)
    frame = 'AE_WRITE|AE_DATA' if absolute else 'AE_WRITE|AE_DATA|AE_INC_PC'
    if absolute:
        order = ['r.sp -= 4;', f'm.write<{C}, AddrSpace::DATA, Long>(r.sp, ea);', PREFETCH_POLL]
    elif indexed:
        order = ['r.ipl = m.ipl;', PREFETCH, 'r.sp -= 4;', f'm.write<{C}, AddrSpace::DATA, Long>(r.sp, ea);']
    else:
        order = [PREFETCH_POLL, 'r.sp -= 4;', f'm.write<{C}, AddrSpace::DATA, Long>(r.sp, ea);']
    return ['u32 ea;', *_ea(mode, op & 7, LONG), *(['m.sync(2);'] if indexed else []), f'if (m.misaligned<{C}>(r.sp)) {{ U32_DEC(r.sp, {size}); throw AddressError(m.makeFrame<{frame}>(r.sp)); }}', *order]


HANDLERS = {
    'Bcc': _bcc, 'Bra': _bra, 'Bsr': _bsr, 'Dbcc': _dbcc, 'Cmp': _cmp_ea, 'CmpiEa': _cmpi_ea, 'CmpiRg': _cmpi_rg, 'Cmpa': _cmpa, 'Tst': _tst,
    'Move0': _move0, 'Move2': _move2, 'Move3': _move3, 'Move4': _move4, 'Move5': _move56(DI), 'Move6': _move56(IX), 'Move7': _move7, 'Move8': _move8, 'Movea': _movea, 'Moveq': _moveq,
    'ShiftIm': _shift_im, 'ShiftRg': _shift_rg, 'AndiRg': _andi_rg, 'AndiEa': _andi_ea, 'AndEaRg': _and_ea_rg, 'AndRgEa': _and_rg_ea,
    'AddxRg': _addx_rg, 'AddEaRg': _add_ea_rg, 'AddRgEa': _add_rg_ea, 'AddqDn': _addq_dn, 'AddqAn': _addq_an, 'AddqEa': _addq_ea, 'AddiRg': _addi_rg, 'AddiEa': _addi_ea, 'Adda': _adda,
    'BitImEa': _bit_im_ea, 'BitImDy': _bit_im_dy, 'BitDxEa': _bit_dx_ea, 'BitDxDy': _bit_dx_dy, 'Lea': _lea, 'Rts': _rts, 'Swap': _swap, 'Jmp': _jmp, 'Jsr': _jsr, 'Clr': _clr, 'Nop': _nop,
    'MovemEaRg': _movem_ea_rg, 'MovemRgEa': _movem_rg_ea, 'Ext': _ext, 'NegRg': _neg_rg, 'Pea': _pea,
}


def translate(opcode: int, handler: str, mode: int, size: int, *, core: str = 'C68000') -> str | None:
    """The body of the form of this opcode, or None when it stays Moira's code specialised."""
    if core != 'C68000' or handler not in HANDLERS:
        return None
    lines = HANDLERS[handler](opcode, mode, size)
    if lines is None:
        return None
    return ''.join(f'    {line}\n' for line in lines)
