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
    source = adapt_post_boot_apu(source)
    source = adapt_power_off(source)
    source = adapt_length_clock(source)
    source = adapt_sweep_calculation(source)
    path.write_text(source, encoding='utf-8')


def adapt_sweep_calculation(source: str) -> str:
    """With a sweep shift of 0 the console still calculates the next frequency at every sweep clock (the divided frequency is the frequency
    itself) and a result above $7FF turns the channel off, but the frequency is not written back (blargg dmg_sound 04). The pinned runtime
    skipped the whole calculation when the shift was 0. The check at the trigger stays as it was: it needs a shift."""
    source = replace_once(source,
        '    if (shift > 0) {\n        uint16_t delta = new_freq >> shift;\n        if (sub) new_freq -= delta;\n        else     new_freq += delta;\n    }\n    return new_freq;',
        '    uint16_t delta = new_freq >> shift;\n    if (sub) new_freq -= delta;\n    else     new_freq += delta;\n    return new_freq;')
    source = replace_once(source,
        '                if (period > 0 && (ch1->nr10 & 0x07) > 0) {\n'
        '                    uint16_t new_freq = calc_sweep(ch1);\n'
        '                    if (new_freq <= 2047) {\n',
        '                if (period > 0) {\n'
        '                    uint16_t new_freq = calc_sweep(ch1);\n'
        '                    if (new_freq <= 2047 && (ch1->nr10 & 0x07) == 0) {\n'
        '                        /* Shift 0: nothing is written back. */\n'
        '                    } else if (new_freq <= 2047) {\n')
    # Leaving negate mode after a calculation made in it turns the channel off (blargg dmg_sound 05). The unused `freq` field of the
    # channel holds "negate mode was used since the trigger" so that the saved state keeps its size.
    source = replace_once(source, '    bool sub = (ch->nr10 & 0x08) != 0;\n',
        '    bool sub = (ch->nr10 & 0x08) != 0;\n    if (sub) ch->freq = 1; /* negate mode used since the trigger */\n')
    source = replace_once(source, '        case 0xFF10: apu->ch1.nr10 = value; break;',
        '        case 0xFF10:\n            if ((apu->ch1.nr10 & 0x08) && !(value & 0x08) && apu->ch1.freq) apu->ch1.enabled = false;\n'
        '            apu->ch1.nr10 = value;\n            break;')
    return replace_once(source, '                apu->ch1.enabled = (apu->ch1.nr12 & 0xF8) != 0;\n',
        '                apu->ch1.enabled = (apu->ch1.nr12 & 0xF8) != 0;\n                apu->ch1.freq = 0;\n')


def adapt_post_boot_apu(source: str) -> str:
    """The runtime starts where the boot ROM leaves the console. The boot ROM has just played its two notes on channel 1: NR52 reads $F1
    (the status bit of channel 1 is set), the length counter holds the 64 that NR11 = $80 wrote and the length is not enabled, so the
    channel stays on, at a volume the envelope has run down to zero by the time a game starts (silent: the mix is unchanged). The
    pinned reset left channel 1 off, so $FF26 read $F0 (Mooneye's boot_hwio)."""
    return replace_once(source, '    apu->nr52 = 0xF1; /* Audio ON */',
        '    apu->nr52 = 0xF1; /* Audio ON */\n'
        '    /* Left by the boot ROM: channel 1 on at volume zero, frequency of its second note, length 64 not enabled. */\n'
        '    apu->ch1.enabled = true;\n    apu->ch1.volume = 0;\n    apu->ch1.length_counter = 64;\n'
        '    apu->ch1.nr13 = 0xC1;\n    apu->ch1.nr14 = 0x07;\n    apu->ch1.env_timer = 1;')


def adapt_power_off(source: str) -> str:
    """On the original console the length counters and the wave RAM survive the power switch of NR52, and the length part of NR11, NR21,
    NR31 and NR41 can be written while the unit is off (blargg dmg_sound 01, 08 and 11). The pinned runtime cleared the four channels
    whole and ignored every write while off."""
    source = replace_once(source,
        '            memset(&apu->ch1, 0, sizeof(Channel1));\n            memset(&apu->ch2, 0, sizeof(Channel2));\n'
        '            memset(&apu->ch3, 0, sizeof(Channel3));\n            memset(&apu->ch4, 0, sizeof(Channel4));\n',
        '            const int kept_length[4] = { apu->ch1.length_counter, apu->ch2.length_counter, apu->ch3.length_counter, apu->ch4.length_counter };\n'
        '            uint8_t kept_wave[16];\n            memcpy(kept_wave, apu->ch3.wave_ram, sizeof(kept_wave));\n'
        '            memset(&apu->ch1, 0, sizeof(Channel1));\n            memset(&apu->ch2, 0, sizeof(Channel2));\n'
        '            memset(&apu->ch3, 0, sizeof(Channel3));\n            memset(&apu->ch4, 0, sizeof(Channel4));\n'
        '            apu->ch1.length_counter = kept_length[0];\n            apu->ch2.length_counter = kept_length[1];\n'
        '            apu->ch3.length_counter = kept_length[2];\n            apu->ch4.length_counter = kept_length[3];\n'
        '            memcpy(apu->ch3.wave_ram, kept_wave, sizeof(kept_wave));\n')
    return replace_once(source,
        '    if (!power_on && addr != 0xFF26 && !(addr >= 0xFF30 && addr <= 0xFF3F)) {',
        '    if (!power_on) {\n'
        '        /* The length part of NRx1 is writable while the unit is off (the duty bits are not). */\n'
        '        if (addr == 0xFF11) apu->ch1.length_counter = 64 - (value & 0x3F);\n'
        '        else if (addr == 0xFF16) apu->ch2.length_counter = 64 - (value & 0x3F);\n'
        '        else if (addr == 0xFF1B) apu->ch3.length_counter = 256 - value;\n'
        '        else if (addr == 0xFF20) apu->ch4.length_counter = 64 - (value & 0x3F);\n'
        '    }\n'
        '    if (!power_on && addr != 0xFF26 && !(addr >= 0xFF30 && addr <= 0xFF3F)) {')


def adapt_length_clock(source: str) -> str:
    """Length-counter edge cases of the original console (Pan Docs, "Obscure Behavior"; blargg dmg_sound 03): when the next frame-sequencer
    step is not one that clocks length (the first half of a length period), enabling the length of a running counter clocks it once
    (and may turn the channel off), and a trigger that reloads an empty counter loads one less when the length is enabled."""
    source = replace_once(source, 'void gb_audio_write(GBContext* ctx, uint16_t addr, uint8_t value) {',
        'static bool audio_next_step_clocks_length(const GBAudio* apu) {\n'
        '    return (((apu->fs_step + 1) & 1) == 0);\n}\n\n'
        'void gb_audio_write(GBContext* ctx, uint16_t addr, uint8_t value) {')
    for channel, maximum in ((1, 64), (2, 64), (3, 256), (4, 64)):
        source = replace_once(source,
            f'            apu->ch{channel}.length_enabled = (value & 0x40) != 0;\n',
            f'            {{\n                const bool length_on = (value & 0x40) != 0;\n'
            f'                if (length_on && !apu->ch{channel}.length_enabled && apu->ch{channel}.length_counter > 0 && !audio_next_step_clocks_length(apu)) {{\n'
            f'                    if (--apu->ch{channel}.length_counter == 0 && !(value & 0x80)) apu->ch{channel}.enabled = false;\n'
            f'                }}\n                apu->ch{channel}.length_enabled = length_on;\n            }}\n')
        source = replace_once(source,
            f'if (apu->ch{channel}.length_counter == 0) apu->ch{channel}.length_counter = {maximum};',
            f'if (apu->ch{channel}.length_counter == 0) {{\n'
            f'                    apu->ch{channel}.length_counter = {maximum};\n'
            f'                    if (apu->ch{channel}.length_enabled && !audio_next_step_clocks_length(apu)) apu->ch{channel}.length_counter--;\n'
            f'                }}')
    return source
