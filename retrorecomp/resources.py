"""Native ELF resources, linked directly as bytes rather than compiled C arrays."""
from io import BytesIO
from pathlib import Path
import json
import os
from .conversion_common import write_if_changed
from .paths import ASSETS


def embed_resources(project: Path, resources: dict[int, Path]) -> None:
    if os.name == 'nt':
        return
    write_embedding(project, resources)


def write_embedding(project: Path, resources: dict[int, Path]) -> None:
    """The window icon and the two files that link `resources` into the program. A file that would not change keeps its
    timestamp, so preparing a game again rebuilds and relinks nothing."""
    from PIL import Image
    icon=project/'game-icon.png'
    if not icon.is_file():icon=ASSETS/'assets/Retro-Recomp-icon-256.png'
    bitmap=project/'embedded-window-icon.bmp'
    picture=BytesIO()
    with Image.open(icon) as image:image.convert('RGBA').save(picture,format='BMP')
    write_if_changed(bitmap,picture.getvalue())
    resources={101:bitmap,**resources}
    assembly=['.section .rodata',' .balign 16']
    source=['#include "embedded_resources.h"']
    cases=[]
    for identifier,path in sorted(resources.items()):
        path=path.resolve()
        if not path.is_file():raise FileNotFoundError(path)
        symbol=f'rr_resource_{identifier}'
        assembly += [f'.global {symbol}',f'.hidden {symbol}',symbol+':',
                     '.incbin '+json.dumps(str(path),ensure_ascii=False),
                     f'.global {symbol}_end',f'.hidden {symbol}_end',symbol+'_end:','.balign 16']
        source.append(f'extern const unsigned char {symbol}[],{symbol}_end[];')
        cases.append(f'case {identifier}: *size=(size_t)((uintptr_t){symbol}_end-(uintptr_t){symbol});return {symbol};')
    assembly.append('.section .note.GNU-stack,""')
    source.insert(0,'#include <stdint.h>')
    source += ['const void *rr_resource(unsigned id,size_t *size){switch(id){',*cases,'default:*size=0;return NULL;}}']
    write_if_changed(project/'embedded_resources.S',('\n'.join(assembly)+'\n').encode('utf-8'))
    write_if_changed(project/'embedded_resources.c',('\n'.join(source)+'\n').encode('utf-8'))
