"""Checked fixes to the pinned GB hardware runtime; leave upstream untouched."""
from pathlib import Path

from .core import replace_once


def adapt_hardware(project: Path) -> None:
    path = project / 'runtime/src/audio.c'
    source = path.read_text(encoding='utf-8')
    # NRx2 holds the *initial* envelope volume. The live envelope can grow from
    # zero without changing that register. enabled already includes DAC gating.
    for channel, register in ((1, 'nr12'), (2, 'nr22'), (4, 'nr42')):
        source = replace_once(source,
            f'if (apu->ch{channel}.enabled && (apu->ch{channel}.{register} & 0xF0)) {{',
            f'if (apu->ch{channel}.enabled) {{ /* Mix the live envelope volume. */')
    # A pulse retrigger reloads the timer, not the duty-step counter. Preserve
    # the phase so repeated notes do not restart the waveform at step zero.
    for channel in (1, 2):
        source = replace_once(source, f'                apu->ch{channel}.wave_pos = 0;',
            '                /* Pulse duty phase survives a retrigger. */')
    # NR43 shifts 14/15 stop the noise clock; they are not very slow tones.
    source = replace_once(source, '        uint8_t s = apu->ch4.nr43 >> 4;',
        '''        uint8_t s = apu->ch4.nr43 >> 4;
        if (s >= 14) return; /* The noise LFSR receives no clocks. */''')
    path.write_text(source, encoding='utf-8')
