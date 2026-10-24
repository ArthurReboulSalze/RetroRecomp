"""Emit live operand reads for instructions straddling a ROM bank window.

The opcode remains an AOT choice. Bytes across 3FFF/4000 or 7FFF/8000 cannot
be folded to constants from the ROM file: the live mapper/bus supplies them.
"""
from pathlib import Path
import re


_IMM8 = {0x06, 0x0E, 0x10, 0x16, 0x18, 0x1E, 0x20, 0x26, 0x28, 0x2E,
         0x30, 0x36, 0x38, 0x3E, 0xC6, 0xCB, 0xCE, 0xD6, 0xDE, 0xE0,
         0xE6, 0xE8, 0xEE, 0xF0, 0xF6, 0xF8, 0xFE}
_IMM16 = {0x01, 0x08, 0x11, 0x21, 0x31, 0xC2, 0xC3, 0xC4, 0xCA, 0xCC,
          0xCD, 0xD2, 0xD4, 0xDA, 0xDC, 0xEA, 0xFA}


def instruction_length(opcode: int) -> int:
    return 3 if opcode in _IMM16 else 2 if opcode in _IMM8 else 1


def boundary_instruction(opcode: int, address: int) -> str | None:
    """Return a native instruction with reference-equivalent timed bus work."""
    length = instruction_length(opcode)
    operand = f'0x{address + 1:04x}'
    following = f'0x{(address + length) & 0xffff:04x}'
    prefix = f'ctx->pc = {following};\n'
    if opcode in (0x06, 0x0E, 0x16, 0x1E, 0x26, 0x2E, 0x3E):
        register = ('b', 'c', 'd', 'e', 'h', 'l', None, 'a')[opcode >> 3]
        return prefix + f'ctx->{register} = gb_read8(ctx, {operand});\ngb_tick(ctx, 8);'
    if opcode in (0x01, 0x11, 0x21, 0x31):
        register = ('bc', 'de', 'hl', 'sp')[opcode >> 4]
        return prefix + f'ctx->{register} = gb_read16(ctx, {operand});\ngb_tick(ctx, 12);'
    if opcode in (0xE0, 0xF0, 0xEA, 0xFA):
        target = f'(uint16_t)(0xff00u + gb_read8(ctx, {operand}))' if length == 2 else f'gb_read16(ctx, {operand})'
        body = prefix + f'const uint16_t rr_target = {target};\n'
        ticks = 11 if length == 2 else 15
        if opcode in (0xF0, 0xFA):
            body += f'ctx->a = gbrt_timed_bus_read8(ctx, rr_target, {ticks});'
        else:
            body += f'gbrt_timed_bus_write8(ctx, rr_target, ctx->a, {ticks});'
        return body
    if opcode in (0xC3, 0xC2, 0xCA, 0xD2, 0xDA, 0xCD, 0xC4, 0xCC, 0xD4, 0xDC):
        # JP/CALL read immediate bytes at cycles 7/11, unlike simple LD.
        body = f'ctx->pc = {operand};\ngb_tick(ctx, 7);\n'
        body += 'const uint8_t rr_lo = gb_read8(ctx, ctx->pc++);\ngb_tick(ctx, 4);\n'
        body += 'const uint8_t rr_hi = gb_read8(ctx, ctx->pc++);\ngb_tick(ctx, 1);\n'
        if opcode in (0xCD, 0xC4, 0xCC, 0xD4, 0xDC):
            condition = '1' if opcode == 0xCD else ('!ctx->f_z', 'ctx->f_z', '!ctx->f_c', 'ctx->f_c')[(opcode - 0xC4) // 8]
            return body + f'if ({condition}) gbrt_timed_call_after_imm16(ctx, (uint16_t)(rr_lo | ((uint16_t)rr_hi << 8)), ctx->pc);'
        condition = '1' if opcode == 0xC3 else ('!ctx->f_z', 'ctx->f_z', '!ctx->f_c', 'ctx->f_c')[(opcode - 0xC2) // 8]
        return body + f'if ({condition}) gbrt_timed_jump(ctx, (uint16_t)(rr_lo | ((uint16_t)rr_hi << 8)), 4);'
    if opcode in (0x18, 0x20, 0x28, 0x30, 0x38):
        body = prefix + f'const int8_t rr_offset = (int8_t)gb_read8(ctx, {operand});\n'
        condition = '1' if opcode == 0x18 else ('!ctx->f_z', 'ctx->f_z', '!ctx->f_c', 'ctx->f_c')[(opcode - 0x20) // 8]
        return body + f'if ({condition}) {{ ctx->pc = (uint16_t)(ctx->pc + rr_offset); gb_tick(ctx, 12); }} else gb_tick(ctx, 8);'
    return None


_LABEL = re.compile(r'(^\w+:\n)(.*?)(?=^\w+:\n|^\}|\Z)', re.M | re.S)
_LOCATION = re.compile(r'/\* (?:(\w+):)?([0-9a-f]{4}) \*/')


def repair_bank_boundaries(source: str, rom: bytes) -> tuple[str, int, int]:
    native = fallback = 0

    def instruction(match):
        nonlocal native, fallback
        label, body = match.groups()
        location = _LOCATION.search(body)
        if not location:
            return match.group()
        bank = int(location[1] or '0', 16)
        address = int(location[2], 16)
        if address not in (0x3FFE, 0x3FFF, 0x7FFE, 0x7FFF):
            return match.group()
        offset = bank * 0x4000 + (address & 0x3FFF)
        if offset >= len(rom):
            return match.group()
        opcode = rom[offset]
        if (address & 0x3FFF) + instruction_length(opcode) <= 0x4000:
            return match.group()
        code = boundary_instruction(opcode, address)
        if code is None:
            # Unhandled boundary forms must never execute a stale operand.
            code = (f'ctx->pc = 0x{address:04x};\n'
                    'gbrt_execute_dispatch_fallback(ctx, gb_resolve_rom_bank(ctx, ctx->pc), '
                    'ctx->pc, GB_DISPATCH_FALLBACK_ADDRESS_NOT_COMPILED, 0);')
            fallback += 1
        else:
            native += 1
        return label + '    { /* Live bank-boundary operands. */\n        ' + code.replace('\n', '\n        ') + '\n        return;\n    }\n'

    return _LABEL.sub(instruction, source), native, fallback


def adapt_bank_boundaries(project: Path) -> dict:
    rom = (project / 'rom.gb').read_bytes()
    native = fallback = 0
    for path in project.glob('game_funcs_*.c'):
        source, n, f = repair_bank_boundaries(path.read_text(encoding='utf-8'), rom)
        path.write_text(source, encoding='utf-8')
        native += n
        fallback += f
    return dict(native_sites=native, guarded_fallback_sites=fallback)
