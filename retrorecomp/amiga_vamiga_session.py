"""The multiplayer session's changes to the adapted vAmiga Core (MIT script; the files it changes stay MPL-2.0).

`amiga_vamiga` adapts the pinned Core and is one of the Amiga's generator sources (`amiga_knowledge.GENERATOR_SOURCES`): an edit there
makes every qualified path wait again. The in-process snapshot of a multiplayer session (rollback: `rr_amiga_snap_*` in
native/amiga_machine/amiga_session.cpp) needs three things a path cannot notice, because nothing they add runs unless the session
saves or loads a snapshot: a save and a load of vAmiga's state without its per-component checksums and without an allocation, the
sound path's own state written into a buffer the session already holds, and the keyboard's held keys, which no vAmiga snapshot keeps.
They are kept here, outside the generator pins, as `amiga_vamiga_display` keeps the display's, and may only add to the files of
`SESSION_FILES`. `tests/test_amiga_rollback.py` holds that line.

The build stamp moves with them (`adaptation_digest`, chained after the display's).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import amiga_vamiga_display

# The only files a replacement of this module may change: new members only, nothing the machine runs by itself.
SESSION_FILES = ('Infrastructure/CoreComponent.h', 'Infrastructure/CoreComponent.cpp', 'Ports/AudioPort.h', 'Peripherals/Keyboard/Keyboard.h')

REPLACEMENTS = [
    # The in-process snapshot (rollback, one per frame): the walk and the bytes of save() and load(), without the
    # per-component checksums (a hash of every RAM byte, at each save and each load: the buffer never leaves the process), into a
    # buffer the session holds (`capacity` bytes, 0: it does not fit). rrLoad checks every component's size against the machine's
    # before it reads a byte, so a buffer that does not fit is refused with the machine untouched.
    ('Infrastructure/CoreComponent.h',
     '    // Saves the internal state to a memory buffer\n    isize save(u8 *buf);\n    virtual void _didSave() { }\n',
     '    // Saves the internal state to a memory buffer\n    isize save(u8 *buf);\n    virtual void _didSave() { }\n\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): the in-process snapshot, without checksums (CoreComponent.cpp).\n'
     '    isize rrSave(u8 *buf, isize capacity);\n'
     '    isize rrLoad(const u8 *buf, isize size);\n'
     '    void rrPostorder(const std::function<void(CoreComponent *)> &func);\n'),
    # postorderWalk takes its function by value at every level (a copy, and an allocation when the function does not fit
    # std::function's own room): the snapshot walks by reference, with functions that hold one pointer.
    ('Infrastructure/CoreComponent.cpp',
     '    postorderWalk([](CoreComponent *c) { c->_didSave(); });\n\n    return result;\n}\n',
     '    postorderWalk([](CoreComponent *c) { c->_didSave(); });\n\n    return result;\n}\n\n'
     '// Retro-Recomp modification (MPL-2.0, like this file): save() and load() for a buffer that never leaves the process (a\n'
     '// multiplayer session\'s rollback): the same bytes, the checksum fields left at zero and not verified; no allocation.\n'
     'void\nCoreComponent::rrPostorder(const std::function<void(CoreComponent *)> &func)\n{\n'
     '    for (auto &c : subComponents) c->rrPostorder(func);\n'
     '    func(this);\n}\n\n'
     'namespace { struct RrWalk { u8 *out; const u8 *in; isize limit, at; bool fits; }; }\n\n'
     'isize\nCoreComponent::rrSave(u8 *buffer, isize capacity)\n{\n'
     '    RrWalk w { buffer, nullptr, capacity, 0, true };\n'
     '    RrWalk *p = &w;\n'
     '    rrPostorder([p](CoreComponent *c) {\n'
     '        if (!p->fits) return;\n'
     '        const isize expected = c->size(false);\n'
     '        if (p->at + expected > p->limit) { p->fits = false; return; }\n'
     '        u8 *ptr = p->out + p->at;\n'
     '        write64(ptr, u64(expected));\n'
     '        write64(ptr, 0);\n'
     '        SerWriter writer(ptr); *c << writer;\n'
     '        if (isize(writer.ptr - (p->out + p->at)) != expected) { p->fits = false; return; }\n'
     '        p->at += expected;\n'
     '    });\n'
     '    if (!w.fits) return 0;\n'
     '    rrPostorder([](CoreComponent *c) { c->_didSave(); });\n'
     '    return w.at;\n}\n\n'
     'isize\nCoreComponent::rrLoad(const u8 *buffer, isize size)\n{\n'
     '    RrWalk w { nullptr, buffer, size, 0, true };\n'
     '    RrWalk *p = &w;\n'
     '    rrPostorder([p](CoreComponent *c) {\n'
     '        if (!p->fits) return;\n'
     '        const isize expected = c->size(false);\n'
     '        const u8 *ptr = p->in + p->at;\n'
     '        if (p->at + 16 > p->limit || isize(read64(ptr)) != expected || p->at + expected > p->limit) { p->fits = false; return; }\n'
     '        p->at += expected;\n'
     '    });\n'
     '    if (!w.fits || w.at != size) return 0;\n'
     '    w.at = 0;\n'
     '    rrPostorder([p](CoreComponent *c) {\n'
     '        const u8 *ptr = p->in + p->at + 16;\n'
     '        SerReader reader(ptr); *c << reader;\n'
     '        p->at = isize(reader.ptr - p->in);\n'
     '    });\n'
     '    rrPostorder([](CoreComponent *c) { c->_didLoad(); });\n'
     '    return w.at;\n}\n'),
    # The sound path's state (amiga_vamiga's rrSaveAudio) written into a buffer the session holds already, never more than rrAudioBound:
    # the same bytes, no allocation. rrSaveAudio keeps its use for the quick states and goes through it.
    ('Ports/AudioPort.h',
     '    void rrSaveAudio(std::vector<u8> &o) const\n'
     '    {\n'
     '        auto put = [&](const void *p, size_t n) { o.insert(o.end(), (const u8 *)p, (const u8 *)p + n); };\n',
     '    size_t rrAudioBound() const\n'
     '    {\n'
     '        size_t n = 16 + 6 * 8 + 2 * 5 * 8 + 6 * 8 + sizeof filter.ledFilter.tmpL + sizeof filter.ledFilter.tmpR + 1;\n'
     '        for (const auto &s : sampler) n += 8 + (size_t)s.cap() * (sizeof(i16) + 8);\n'
     '        return n;\n'
     '    }\n'
     '    void rrSaveAudio(std::vector<u8> &o) const\n'
     '    {\n'
     '        o.resize(rrAudioBound());\n'
     '        o.resize(rrSaveAudioTo(o.data(), o.size()));\n'
     '    }\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): the bytes written into `o` (`capacity` bytes), 0 when they do not fit.\n'
     '    size_t rrSaveAudioTo(u8 *o, size_t capacity) const\n'
     '    {\n'
     '        size_t at = 0;\n'
     '        bool fits = true;\n'
     '        auto put = [&](const void *p, size_t n) { if (at + n > capacity) { fits = false; return; } memcpy(o + at, p, n); at += n; };\n'),
    ('Ports/AudioPort.h',
     '        u8 m = wasMuted ? 1 : 0; put(&m, 1);\n    }\n',
     '        u8 m = wasMuted ? 1 : 0; put(&m, 1);\n        return fits ? at : 0;\n    }\n'),
    # The keys the keyboard holds down, which a snapshot does not keep (a load would leave those of the timeline left, and a press of a
    # key it takes for held would be lost: a Start, the guest's Return, swallowed on one seat after a rollback): read and set around the
    # in-process snapshot and a quick state.
    ('Peripherals/Keyboard/Keyboard.h',
     '    void rrHandshakeOver();\n\n',
     '    void rrHandshakeOver();\n'
     '    // Retro-Recomp modification (MPL-2.0, like this file): the held keys, around a snapshot (amiga_vamiga_session.py).\n'
     '    void rrKeysDown(u8 out[128]) const { for (int k = 0; k < 128; k++) out[k] = keyDown[k] ? 1 : 0; }\n'
     '    void rrSetKeysDown(const u8 in[128]) { for (int k = 0; k < 128; k++) keyDown[k] = in[k] != 0; }\n\n'),
]

MARKER = 'rr-session.json'      # inside Core/, so it goes when `amiga_vamiga.adapt` makes the folder again


def adaptation_digest() -> str:
    """What the adapted tree depends on: the display layer's digest (which holds `amiga_vamiga`'s) and the replacements of this module."""
    value = hashlib.sha256(b'amiga-vamiga-session\0' + amiga_vamiga_display.adaptation_digest().encode())
    for rel, old, new in REPLACEMENTS:
        value.update(b'\0' + rel.encode() + b'\0' + old.encode() + b'\0' + new.encode())
    return value.hexdigest()


def adapt(checkout: Path, target: Path) -> Path:
    """`amiga_vamiga_display.adapt`, then the replacements of this module; returns the adapted Core folder. Done once per digest: a tree
    made for another digest is made again from the checkout, never patched twice."""
    digest = adaptation_digest()
    core = target / 'Core'
    try:
        if json.loads((core / MARKER).read_text(encoding='utf-8')).get('adaptation') == digest:
            return core
    except (OSError, ValueError):
        pass
    (core / amiga_vamiga_display.MARKER).unlink(missing_ok=True)      # the layers below are made again too
    (target / 'ready.json').unlink(missing_ok=True)
    core = amiga_vamiga_display.adapt(checkout, target)
    for rel, old, new in REPLACEMENTS:
        path = core / rel
        text = path.read_text(encoding='utf-8')
        if text.count(old) != 1:
            raise ValueError(f'vAmiga {rel}: the pinned text was not found exactly once.')
        path.write_text(text.replace(old, new), encoding='utf-8', newline='\n')
    (core / MARKER).write_text(json.dumps({'adaptation': digest, 'replacements': len(REPLACEMENTS)}) + '\n', encoding='utf-8')
    return core
