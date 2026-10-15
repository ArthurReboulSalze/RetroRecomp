"""Native ELF resources, linked directly as bytes rather than compiled C arrays."""
from pathlib import Path
import json
import os
from .paths import ASSETS


def embed_resources(project: Path, resources: dict[int, Path]) -> None:
    if os.name == 'nt':
        return
    from PIL import Image
    icon=project/'game-icon.png'
    if not icon.is_file():icon=ASSETS/'assets/Retro-Recomp-icon-256.png'
    bitmap=project/'embedded-window-icon.bmp'
    with Image.open(icon) as image:image.convert('RGBA').save(bitmap,format='BMP')
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
    (project/'embedded_resources.S').write_text('\n'.join(assembly)+'\n',encoding='utf-8')
    (project/'embedded_resources.c').write_text('\n'.join(source)+'\n',encoding='utf-8')
