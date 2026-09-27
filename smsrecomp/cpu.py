"""Local, reproducible CPU corrections; never edit the pinned dependencies."""
from pathlib import Path


def replace(source: str, before: str, after: str) -> str:
    if source.count(before) != 1:
        raise ValueError(f'Pinned CPU source changed: {before[:100]!r}')
    return source.replace(before, after, 1)


def prepare_cpu_headers(game: Path, engine: Path) -> None:
    shared = engine / 'external/z80-recomp-core/include'
    state = (shared / 'sms_runtime.h').read_text(encoding='utf-8')
    state = replace(state, '    uint64_t cyc;',
        '    uint8_t q;             /* previous flag-producing result (NMOS Q latch) */\n'
        '    uint8_t p;             /* preceding LD A,I/R, for interrupt PV quirk */\n'
        '    uint64_t cyc;')
    (game / 'sms_runtime.h').write_text(state, encoding='utf-8')
    # Existing runner/test includes use both historical spellings.
    (game / 'include').mkdir(exist_ok=True)
    (game / 'include/sms_runtime.h').write_text('#include "../sms_runtime.h"\n', encoding='utf-8')
    ops = (shared / 'z80_ops.h').read_text(encoding='utf-8')
    for function in ('z80_scf', 'z80_ccf'):
        start = ops.index(f'static inline void {function}(')
        end = ops.index('\n}', start) + 2
        body = ops[start:end]
        body = body.replace('{\n', '{\n#ifdef SMSRECOMP_BANKED_AOT\n'
            '    uint8_t xy = (uint8_t)(s->a | (s->f & ~s->q));\n'
            '#else\n    uint8_t xy = s->a; /* legacy function emitter has no Q tracking */\n#endif\n', 1)
        body = body.replace('GB(3, s->a)', 'GB(3, xy)').replace('GB(5, s->a)', 'GB(5, xy)')
        ops = ops[:start] + body + ops[end:]
    (game / 'z80_ops.h').write_text(ops, encoding='utf-8')


def prepare_reference(game: Path, engine: Path) -> None:
    """Correct the pinned fallback/oracle in a generated copy.

    This CPU is checked against the same independent vectors as the emitter.
    Keep the separate implementation: it is never used to execute native code.
    """
    original = engine / 'runner/external/superzazu'
    header = (original / 'z80.h').read_text(encoding='utf-8')
    header = replace(header, '  uint8_t iff_delay;', '  uint8_t q, p;\n  uint8_t iff_delay;')
    (game / 'runtime_reference.h').write_text(header, encoding='utf-8')
    source = (original / 'z80.c').read_text(encoding='utf-8')
    source = replace(source, '#include "z80.h"', '#include "runtime_reference.h"')
    source = replace(source, '  z->cyc = 0;', '  z->cyc = 0; z->q = z->p = 0;')
    source = replace(source, 'case 0x18: z->pc += (int8_t) nextb(z); break;',
                     'case 0x18: { int8_t d = (int8_t)nextb(z); jr(z, d); } break;')
    source = replace(source, 'z->mem_ptr = (a << 8) | (z->a + 1);',
                     'z->mem_ptr = (uint16_t)((a << 8) + port + 1);')
    source = replace(source, 'z->mem_ptr = (port + 1) | (z->a << 8);',
                     'z->mem_ptr = ((port + 1) & 255) | (z->a << 8);')
    source = replace(source, '  *r = z->port_in(z, z->c);',
                     '  z->mem_ptr = get_bc(z) + 1;\n  *r = z->port_in(z, z->c);\n'
                     '  z->xf = GET_BIT(3, *r); z->yf = GET_BIT(5, *r);')
    for op, value in ((0x41, 'z->b'), (0x49, 'z->c'), (0x51, 'z->d'), (0x59, 'z->e'),
                      (0x61, 'z->h'), (0x69, 'z->l'), (0x71, '0')):
        text = f'case 0x{op:02X}: z->port_out(z, z->c, {value}); break;'
        source = replace(source, text, text.replace('z->port_out', 'z->mem_ptr = get_bc(z) + 1; z->port_out'))
    for comment in ('ld a,i', 'ld a,r'):
        source = replace(source, f'    break; // {comment}',
            f'    z->xf = GET_BIT(3, z->a); z->yf = GET_BIT(5, z->a);\n    break; // {comment}')
    source = replace(source, 'case 0x4D: ret(z); break;', 'case 0x4D: z->iff1 = z->iff2; ret(z); break;')
    source = replace(source, 'case 0xE9: jump(z, *iz); break;', 'case 0xE9: z->pc = *iz; break;')
    source = replace(source, 'case 0x2A: *iz = rw(z, nextw(z)); break;',
                     'case 0x2A: { uint16_t a = nextw(z); *iz = rw(z, a); z->mem_ptr = a + 1; } break;')
    source = replace(source, 'case 0x22: ww(z, nextw(z), *iz); break;',
                     'case 0x22: { uint16_t a = nextw(z); ww(z, a, *iz); z->mem_ptr = a + 1; } break;')
    source = replace(source, '  case 0x66: z->interrupt_mode = 0;',
                     '  case 0x4E: case 0x6E:\n  case 0x66: z->interrupt_mode = 0;')
    source = replace(source, '  } break; // otdr', '      z->cyc += z->b ? 5 : 0;\n  } break; // otdr')
    source = replace(source, 'default: fprintf(stderr, "unknown ED opcode: %02X\\n", opcode); break;',
                     'default: break; /* NMOS undocumented ED encodings are two-byte NOPs. */')
    for function in ('ini', 'ind'):
        start = source.index(f'static void {function}(')
        end = source.index('\n}', start) + 2
        body = source[start:end].replace('z->mem_ptr = get_bc(z)', 'z->mem_ptr = get_bc(z) + 0x100')
        source = source[:start] + body + source[end:]
    # CPI/CPD already move WZ. Repeat forms must not move it a second time.
    for opcode in ('0xB1', '0xB9'):
        start = source.index(f'  case {opcode}: {{', source.index('void exec_opcode_ed(' , source.index('// executes a ED opcode')))
        end = source.index('break;', start)
        body = source[start:end].replace('    } else {\n      z->mem_ptr += 1;\n', '    } else {\n')
        source = source[:start] + body + source[end:]
    for opcode in ('0x37', '0x3F'):
        start = source.index(f'  case {opcode}:')
        end = source.index('break;', start)
        body = source[start:end]
        body = body.replace(f'  case {opcode}:', f'  case {opcode}: {{\n    uint8_t xy = z->a | (get_f(z) & ~z->q);')
        body = body.replace('GET_BIT(3, z->a)', 'GET_BIT(3, xy)').replace('GET_BIT(5, z->a)', 'GET_BIT(5, xy)')
        source = source[:start] + body + '} ' + source[end:]
    source = replace(source, 'case 0xFB: z->iff_delay = 1; break;',
                     'case 0xFB: z->iff1 = z->iff2 = 1; z->iff_delay = 1; break;')
    start = source.index('  if (z->iff_delay > 0) {')
    end = source.index('\n  if (z->nmi_pending)', start)
    source = source[:start] + '  if (z->iff_delay) return;\n' + source[end:]
    source = replace(source, '    z->int_pending = 0;\n    z->halted = 0;',
        '    z->int_pending = 0;\n    if (z->p) z->pf = 0;\n    z->q = z->p = 0;\n    z->halted = 0;')
    # A floating SMS interrupt bus supplies FF (RST 38): 13 T-states total.
    source = replace(source, '      z->cyc += 11;\n      exec_opcode(z, z->int_data);',
        '      z->cyc += 2;\n      exec_opcode(z, z->int_data);\n'
        '      z->r = (z->r & 0x80) | ((z->r - 1) & 0x7f);')
    start = source.index('void z80_step(z80* const z) {')
    end = source.index('\n// outputs to stdout', start)
    source = source[:start] + '''void z80_step(z80* const z) {
  uint8_t op = z->halted ? 0 : rb(z, z->pc), family = 0;
  z->iff_delay = 0;
  /* Discard redundant index prefixes iteratively, without host recursion. */
  unsigned fragments = 0;
  while (!z->halted && (op == 0xDD || op == 0xFD)) {
    z->q = 0;
    uint8_t next = rb(z, (uint16_t)(z->pc + 1));
    if (next != 0xDD && next != 0xFD && next != 0xED) break;
    z->pc++; z->cyc += 4; inc_r(z); op = next;
    if (++fragments == 65536) return;
  }
  uint8_t decoded = op;
  if (op == 0xDD || op == 0xFD) {
    decoded = rb(z, (uint16_t)(z->pc + 1));
    if (decoded == 0xCB) { family = 1; decoded = rb(z, (uint16_t)(z->pc + 3)); }
  } else if (op == 0xCB || op == 0xED) {
    family = op == 0xCB ? 1 : 2; decoded = rb(z, (uint16_t)(z->pc + 1));
  }
  bool flags = family == 1 ? decoded < 0x80 : family == 2 ?
    ((decoded & 0xC7) == 0x40 || (decoded & 0xC7) == 0x42 || (decoded & 0xC7) == 0x44 ||
     decoded == 0x57 || decoded == 0x5F || decoded == 0x67 || decoded == 0x6F || (decoded & 0xE4) == 0xA0) :
    ((decoded >= 0x80 && decoded < 0xC0) || (decoded & 0xC7) == 0xC6 ||
     (decoded < 0x40 && ((decoded & 7) == 4 || (decoded & 7) == 5 || (decoded & 7) == 7 || (decoded & 0xCF) == 9)));
  if (z->halted) exec_opcode(z, 0); else exec_opcode(z, nextb(z));
  if (family == 2 && (decoded & 0xF4) == 0xB0) {
    unsigned group = decoded & 3;
    bool repeat = group == 0 ? get_bc(z) != 0 : group == 1 ? get_bc(z) != 0 && !z->zf : z->b != 0;
    if (repeat) {
      z->mem_ptr = z->pc + 1;
      z->xf = (z->pc >> 11) & 1; z->yf = (z->pc >> 13) & 1;
      if (group >= 2) {
        uint8_t b = z->b;
        if (z->cf) {
          z->hf = (b & 15) == (z->nf ? 0 : 15);
          b += z->nf ? -1 : 1;
        }
        z->pf ^= !parity(b & 7);
      }
    }
  }
  z->q = flags ? get_f(z) : 0;
  z->p = family == 2 && (decoded == 0x57 || decoded == 0x5F);
  process_interrupts(z);
}
''' + source[end:]
    (game / 'runtime_reference.c').write_text(source, encoding='utf-8')
