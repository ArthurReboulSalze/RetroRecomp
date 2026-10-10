"""Build-only reductions for the pinned Game Boy emitter's generated C.

Keep every compiled (bank, PC) entry and every fallback reason. The original
native bodies, optimization level and validation budgets are unchanged.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re


@contextmanager
def preserve_unchanged_sources(project: Path):
    """Let the emitter overwrite files, but don't recompile identical output.

    Hash the *final adapted* contents, including all runtime headers. Never
    reuse a qualification result; the caller still builds and runs all tests.
    """
    def sources():
        yield from (p for p in project.iterdir() if p.is_file() and
                    (p.suffix in {'.c', '.h', '.rc', '.md', '.ico', '.gb'} or
                     p.name == 'CMakeLists.txt'))
        runtime = project / 'runtime'
        if runtime.is_dir():
            yield from (p for p in runtime.rglob('*') if p.is_file())

    previous = {}
    for path in sources():
        stat = path.stat()
        previous[path] = (stat.st_mtime_ns, stat.st_size,
                          hashlib.sha256(path.read_bytes()).digest())
    yield
    for path, (mtime, size, digest) in previous.items():
        if path.is_file() and path.stat().st_size == size and \
                hashlib.sha256(path.read_bytes()).digest() == digest:
            os.utime(path, ns=(path.stat().st_atime_ns, mtime))


_PAGE = re.compile(r'void (game_dispatch_[0-9a-f]+)\(GBContext\* ctx, uint16_t addr, uint16_t bank\) \{\n(.*?)\n\}', re.S)
_ADDRESS = re.compile(r'        case (0x[0-9a-f]+):\n            switch \(bank\) \{\n(.*?)            \}\n            break;', re.S)
_BANK = re.compile(r'                case (\d+): (\w+)\(ctx\); break;\n')
_BANK_DEFAULT = re.compile(r'                default: gbrt_execute_dispatch_fallback\(ctx, bank, addr, GB_DISPATCH_FALLBACK_BANK_NOT_COMPILED, (\d+)\); break;\n')


def compact_dispatch(source: str) -> tuple[str, int]:
    """Replace regular nested switches by immutable native-function tables.

    Leave unusual/inlined pages untouched. Parse the complete page grammar
    before rewriting so a future emitter cannot silently lose native entries.
    """
    converted = 0

    def page(match):
        nonlocal converted
        name, body = match.groups()
        rows: dict[int, dict[int, str]] = {}
        counts = [0] * 256
        matches = list(_ADDRESS.finditer(body))
        for entry in matches:
            address, banks = entry.groups()
            offset = int(address, 16) & 255
            if int(address, 16) >> 8 != int(name.rsplit('_', 1)[1], 16):
                return match.group()
            bindings = list(_BANK.finditer(banks))
            default = _BANK_DEFAULT.search(banks)
            if not default or int(default[1]) != len(bindings) or not bindings:
                return match.group()
            if _BANK_DEFAULT.sub('', _BANK.sub('', banks)).strip():
                return match.group()
            if counts[offset]:
                return match.group()
            counts[offset] = len(bindings)
            for binding in bindings:
                bank, function = binding.groups()
                bank = int(bank)
                if bank > 511 or offset in rows.get(bank, {}):
                    return match.group()
                rows.setdefault(bank, {})[offset] = function
        expected = ('switch (addr) {\n\n'
                    '        default: gbrt_execute_dispatch_fallback(ctx, bank, addr, '
                    'GB_DISPATCH_FALLBACK_ADDRESS_NOT_COMPILED, 0); break;\n    }')
        if ''.join(_ADDRESS.sub('', body).split()) != ''.join(expected.split()) or not rows:
            return match.group()
        converted += 1
        lines = []
        for bank, entries in sorted(rows.items()):
            lines.append(f'static void (*const {name}_bank_{bank}[256])(GBContext*) = {{')
            for start in range(0, 256, 8):
                lines.append('    ' + ', '.join(entries.get(i, '0') for i in range(start, start + 8)) + ',')
            lines.append('};')
        lines.append(f'static const uint16_t {name}_counts[256] = {{' + ','.join(map(str, counts)) + '};')
        lines.append(f'void {name}(GBContext* ctx, uint16_t addr, uint16_t bank) {{')
        lines.append('    void (*const* row)(GBContext*) = 0;')
        lines.append('    switch (bank) {')
        for bank in sorted(rows):
            lines.append(f'        case {bank}: row = {name}_bank_{bank}; break;')
        lines.append('        default: break;\n    }')
        lines.append('    const unsigned offset = addr & 255u;')
        lines.append('    if (row && row[offset]) { row[offset](ctx); return; }')
        lines.append(f'    const unsigned count = {name}_counts[offset];')
        lines.append('    gbrt_execute_dispatch_fallback(ctx, bank, addr, count ? '
                     'GB_DISPATCH_FALLBACK_BANK_NOT_COMPILED : '
                     'GB_DISPATCH_FALLBACK_ADDRESS_NOT_COMPILED, count);\n}')
        return '\n'.join(lines)

    return _PAGE.sub(page, source), converted


def compact_generated_dispatch(project: Path) -> dict:
    before = after = pages = 0
    for path in project.glob('game_dispatch_chunk_*.c'):
        source = path.read_text(encoding='utf-8')
        compact, count = compact_dispatch(source)
        before += len(source.encode('utf-8'))
        after += len(compact.encode('utf-8'))
        pages += count
        path.write_text(compact, encoding='utf-8')
    result = dict(pages=pages, source_bytes_before=before, source_bytes_after=after)
    return result


_WRAPPER = re.compile(r'^void (\w+)\(GBContext\* ctx\) \{\n    (body_\w+)\(ctx\);\n\}\n', re.M)
_BODY_ENTRY = re.compile(
    r'((?:static )?void body_\w+\(GBContext\* ctx\) \{\n'
    r'    gbrt_note_generated_direct_transition\(ctx\);\n)'
    r'    switch \(ctx->pc\) \{\n((?:        case 0x[0-9a-f]+: goto \w+;\n)+)'
    r'        default: break;\n    \}')


def safe_body_entries(source: str) -> tuple[str, int]:
    """Preserve entry labels without the problematic MSVC switch/goto CFG.

    MSVC 19.44 /O2 emitted a write through an uninitialized nonvolatile
    register when entering a later label in one shared body. Explicit tests
    preserve every entry and the default fallthrough, without disabling
    optimization or changing guest instructions. Only the pinned grammar is
    rewritten; regular guest switches remain untouched.
    """
    def replace(match):
        entries = re.findall(r'case (0x[0-9a-f]+): goto (\w+);', match[2])
        if len(entries) <= 16:
            return match[1] + ''.join(f'    if (ctx->pc == {pc}) goto {label};\n'
                                     for pc, label in entries)
        # Some shared bodies have over ten thousand entry labels. A linear
        # ladder would make dispatch and CPU validation much slower. Split
        # the immutable entry set so at most log2(N) tests plus a small leaf
        # are needed; missing PCs still reach the original default path.
        entries.sort(key=lambda item: int(item[0], 16))
        def tree(items, indent):
            if len(items) <= 8:
                return ''.join(f'{indent}if (rr_entry_pc == {pc}) goto {label};\n'
                               for pc, label in items)
            middle = len(items) // 2
            return (f'{indent}if (rr_entry_pc < {items[middle][0]}) {{\n' +
                    tree(items[:middle], indent + '    ') + f'{indent}}} else {{\n' +
                    tree(items[middle:], indent + '    ') + f'{indent}}}\n')
        return match[1] + '    const uint16_t rr_entry_pc = ctx->pc;\n' + tree(entries, '    ')
    return _BODY_ENTRY.subn(replace, source)


def share_native_bodies(project: Path) -> dict:
    """Route entries directly to their existing shared body, without a thunk.

    Only exact, side-effect-free wrappers qualify. Native replacement hooks or
    other custom functions stay in place. Exported bodies retain the same PC
    switch, safepoints and generated-code counters.
    """
    aliases = {}
    safe_entries = 0
    paths = list(project.glob('game_funcs_*.c'))
    for path in paths:
        source, count = safe_body_entries(path.read_text(encoding='utf-8'))
        safe_entries += count
        if count:
            path.write_text(source, encoding='utf-8')
        for wrapper, body in _WRAPPER.findall(source):
            if wrapper in aliases and aliases[wrapper] != body:
                raise ValueError(f'Ambiguous Game Boy generated wrapper: {wrapper}')
            aliases[wrapper] = body
    if not aliases:
        return dict(wrappers_removed=0, shared_bodies=0, safe_entry_tables=safe_entries)
    bodies = set(aliases.values())
    identifier = re.compile(r'\b(?:func_\w+|rst_\w+|int_\w+|gb_main)\b')
    for path in paths + list(project.glob('game_dispatch_chunk_*.c')) + [project / 'game_internal.h', project / 'game.c', project / 'game_main.c']:
        source = path.read_text(encoding='utf-8')
        if path in paths:
            source = _WRAPPER.sub('', source)
            source = re.sub(r'^static void (body_\w+)\(',
                            lambda m: ('void ' if m[1] in bodies else 'static void ') + m[1] + '(',
                            source, flags=re.M)
        source = identifier.sub(lambda m: aliases.get(m[0], m[0]), source)
        if path.name == 'game_internal.h':
            seen = set()
            lines = []
            for line in source.splitlines(keepends=True):
                if line.startswith('void body_'):
                    if line in seen:
                        continue
                    seen.add(line)
                lines.append(line)
            source = ''.join(lines)
        path.write_text(source, encoding='utf-8')
    # Keep the common header stable between discovery passes. A newly found
    # entry should not invalidate every unrelated C object through a giant
    # global list of function declarations.
    header = project / 'game_internal.h'
    source = header.read_text(encoding='utf-8')
    declarations = set(re.findall(r'^void (body_\w+)\(GBContext\* ctx\);$', source, re.M))
    source = re.sub(r'^void body_\w+\(GBContext\* ctx\);\n', '', source, flags=re.M)
    header.write_text(source, encoding='utf-8')
    for path in paths + list(project.glob('game_dispatch_chunk_*.c')) + [project / 'game.c', project / 'game_main.c']:
        source = path.read_text(encoding='utf-8')
        used = sorted(set(re.findall(r'\bbody_\w+\b', source)) & declarations)
        if used:
            source = '#include "game_internal.h"\n' + ''.join(
                f'void {name}(GBContext* ctx);\n' for name in used) + source
            path.write_text(source, encoding='utf-8')
    return dict(wrappers_removed=len(aliases), shared_bodies=len(bodies), safe_entry_tables=safe_entries)
