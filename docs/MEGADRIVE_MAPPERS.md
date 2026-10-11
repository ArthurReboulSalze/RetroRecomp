# Mega Drive cartridge bank mapping

The Sega 512 KiB bank circuit is supported for declared `SEGA SSF` images and
the original `MK-12056` product. Unknown ROMs larger than 4 MiB do not inherit
this mapper from their filename, title or size. Declared images are bounded to
8 MiB. Other cartridge circuits and extension hardware retain explicit gates.

Register facts follow the [Sega bank-mapping documentation](https://www.plutiedev.com/beyond-4mb).
The CPU sees eight 512 KiB windows in its first 4 MiB. Slot zero retains physical
page zero; odd registers A130F3 through A130FF select the other seven slots.
A word write uses its low byte; an even-byte write does not select a page.
Missing physical bytes read FF in this bounded software model. This behavior
and high register bits have not been measured on an unpopulated physical board.

## Recompilation and shared observations

`megadrive_codegen.py` decodes the entire declared physical ROM. Initial legacy
function discovery uses a local first-4-MiB derivative only; that derivative is
never the final code or a replacement for the source cartridge.

Native bodies are indexed by **physical ROM offset** and guarded by actual
instruction words. The literal operation relocates PC, branches, PC-relative
operands and fall-through to the current **logical guest address**. No runtime
opcode decode is mislabeled native. Banked Z80 reads and VDP DMA use the same
cartridge mapping as the main CPU.

Writing a mapper register preserves the 68000's already fetched words. A guard
can select their old physical image after a bank switch. A hybrid instruction
that matches no physical image uses counted fallback and supplies no misleading
ROM hint. The physical learning key is captured before execution, including an
instruction that changes its own bank. Per-ROM observations never borrow roots
from another cartridge and still need final strict conversion qualification.

## States and evidence

ABI-11 serializes page registers, validates fixed page zero and reconstructs
the mapped ROM view from the immutable supplied ROM after restoring core state.
F8/F9 retains the actual prefetch queue; host ROM pointers are never serialized.
F1 restores initial pages. Malformed mapping is rejected before machine mutation.
Old ordinary-cartridge states migrate; old states cannot invent previously
unsupported mapping history for a banked board.

`tools/megadrive_mapper_selftest.py` links the actual backend, CPU, VDP and bus
with an authored, ROM-free 5 MiB cartridge. Its 939 assertions cover every slot,
all sixteen page values, lanes, word writes, physical code beyond 4 MiB,
BRA/DBcc/PC-relative relocation, old prefetch, hybrid-word rejection, a self-bank
write's learning key, banked Z80 reads, VDP DMA, F1 and fresh-process F8/F9.
These independent fixtures are separate from the supplied original 5 MiB
cartridge's advanced conversion and shared-hardware CPU/reference comparison.
Current evidence is in `.build/md-cartridge-hardware-20261011/`.

The Sega circuit does not establish support for unrelated licensed/unlicensed
mappers, 32X, SVP or other expansion devices. Electrical bus turnaround and
refresh, VPA/E-clock acknowledgement, VDP collision timing and broader real
progression remain separate qualification gates before promoting Mega Drive.
