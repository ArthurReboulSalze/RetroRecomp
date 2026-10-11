"""Work RAM decoding in private copies of the pinned Mega Drive runtime.

The 64 KiB RAM is mirrored across $E00000-$FFFFFF. Bus addresses select the
same bytes, but CPU PCs/address registers must retain their original value.
"""
from .core import ConversionError

RAM_START = 0xe00000


def runtime_source(source: str, kind: str) -> str:
    counts = {'bus': 4, 'interpreter': 2, 'glue': 2}
    old = '>= 0xFF0000u'
    if source.count(old) != counts[kind]:
        raise ConversionError(f'Pinned Mega Drive {kind} RAM decoding changed; adaptation refused.')
    source = source.replace(old, '>= 0xE00000u')
    if kind == 'glue':
        # RAM_BASE in the pinned header describes its preferred alias. These
        # six dispatch comparisons must accept every alias instead. Absolute
        # short address sign extension ($FF0000 | word) remains untouched.
        if source.count('RAM_BASE') != 6:
            raise ConversionError('Pinned Mega Drive RAM dispatch changed; adaptation refused.')
        source = source.replace('RAM_BASE', '0xE00000u')
    return source
