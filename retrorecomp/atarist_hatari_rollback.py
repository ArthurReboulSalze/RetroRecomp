"""The adapted Hatari's lean in-memory snapshot, for multiplayer rollback (MIT; the C text below is added to Hatari's files, GPL-2.0-or-later like them).

Hatari's own snapshot is made for a rare quick save: it goes through a (virtual) file, carries the static data of the machine every time (the 2 MiB ROM aperture,
the whole image of each drive, for an IPF the decoded flux of every track: 18.7 MB measured on Bomb Jack), restores by a cold reset first and does it inside the next
frame. A rollback saves a state every frame and loads one for every correction, and the host's F9 asks for the digest or a new snapshot right after a load: it needs
a snapshot of the mutable state only, into a buffer the caller owns, restored at once in place.

`rr_snap_save` / `rr_snap_load` (memorySnapShot.c) walk the same subsystem functions as Hatari's own capture, in its order, with `MemorySnapShot_Store` copying to or from
the buffer, and skip what never changes in a game: the configuration, the TOS and cartridge ROM, the drive images, the IPF flux. What the subsystems keep as plain
variables is stored by their own function; what Hatari restores by a cold reset (the CPU's tables, the memory map, the floppy images) is left as it is, since a snapshot
is loaded in the process that saved it (nothing leaves the process: pointers into static data are kept as they are). `rr_snap_digest` is the machine's state as named
fields in a fixed order (never a raw structure). The C library's rand() is replaced by a small generator of ours whose state is part of the snapshot and of the digest:
the same on every PC, and replayed exactly (weak bits of an IPF, the index pulse after a reset, the MFP's jitter use it).
"""
from __future__ import annotations

RESTORE_DONE_MARK = '/* the lean snapshot of retrorecomp/atarist_hatari_rollback.py */'

_STORE_OLD = 'void MemorySnapShot_Store(void *pData, int Size)\n{\n\tlong nBytes;\n\n'
_STORE_NEW = '''/* While rr_snap_lean is set, MemorySnapShot_Store copies to (rr_snap_saving) or from the caller's buffer instead of the snapshot file; a NULL buffer only counts. */
void MemorySnapShot_Store(void *pData, int Size)
{
	long nBytes;

	if (rr_snap_lean)
	{
		if (Size < 0 || (rr_snap_buf && rr_snap_pos + (size_t)Size > rr_snap_cap))
			rr_snap_error = 1;
		else
		{
			if (rr_snap_buf)
			{
				if (rr_snap_saving)
					memcpy(rr_snap_buf + rr_snap_pos, pData, (size_t)Size);
				else
					memcpy(pData, rr_snap_buf + rr_snap_pos, (size_t)Size);
			}
			rr_snap_pos += (size_t)Size;
		}
		return;
	}

'''

_SKIP_OLD = 'void MemorySnapShot_Skip(int Nb)\n{\n\tint res;\n'
_SKIP_NEW = 'void MemorySnapShot_Skip(int Nb)\n{\n\tint res;\n\n\tif (rr_snap_lean)\n\t{\n\t\trr_snap_pos += (size_t)Nb;\n\t\treturn;\n\t}\n'

# `rr_snap_lean` and the counters are defined after MemorySnapShot_Skip in the file, so the Skip patch needs the declaration first.
_DECL_OLD = 'static MSS_File CaptureFile;\n'
_DECL_NEW = ('static MSS_File CaptureFile;\n'
             '/* Retro-Recomp modification (GPL-2.0, like this file): the lean in-memory snapshot (retrorecomp/atarist_hatari_rollback.py). */\n'
             'int rr_snap_lean;\nstatic int rr_snap_saving, rr_snap_error;\nstatic uint8_t *rr_snap_buf;\nstatic size_t rr_snap_cap, rr_snap_pos;\n')

_API_OLD = '#include <savestate.h>\n'
_API_NEW = '''#include <savestate.h>

/* ---- Retro-Recomp modification (GPL-2.0, like this file): the lean in-memory snapshot of the machine (multiplayer rollback) ---- */
extern void STMemory_RrSnap(bool bSave);
extern int Floppy_RrSnap(bool bSave);
extern void IPF_RrSnap(bool bSave);
extern uint64_t FDC_RrDigest(uint64_t h);
extern void rr_cpu_finish(void);
extern uint32_t rr_rand_get(void);
extern void Hatari_rand_MemorySnapShot_Capture(int bSave);

uint64_t rr_digest_mix(uint64_t h, uint64_t value)
{
	h ^= value;
	h *= 0x100000001b3ull;
	h ^= h >> 29;
	return h;
}

static uint64_t rr_digest_bytes(uint64_t h, const uint8_t *p, size_t n)
{
	size_t i;
	for (i = 0; i + 8 <= n; i += 8)
	{
		uint64_t w;
		memcpy(&w, p + i, 8);			/* both PCs are little endian */
		h = (h ^ w) * 0x100000001b3ull;
		h ^= h >> 31;
	}
	for (; i < n; i++)
		h = rr_digest_mix(h, p[i]);
	return h;
}

/* The state the next frames depend on, as named fields in a fixed order (the 68000, the RAM, the I/O area, the cycle and video counters, the MFP, the PSG, the keyboard, the
 * floppy controller, the generator), the same on Windows and Linux. */
uint64_t rr_snap_digest(void)
{
	uint64_t h = 0xcbf29ce484222325ull;
	int i;
	for (i = 0; i < 16; i++)
		h = rr_digest_mix(h, (uint32_t)regs.regs[i]);
	h = rr_digest_mix(h, (uint32_t)m68k_getpc());
	h = rr_digest_mix(h, (uint32_t)M68000_GetSR());
	h = rr_digest_mix(h, (uint32_t)(!regs.s ? regs.regs[15] : regs.usp));		/* the stack pointer of the mode not running is the saved one; the one running is A7 (the other copy is stale) */
	h = rr_digest_mix(h, (uint32_t)(regs.s ? regs.regs[15] : regs.isp));
	h = rr_digest_bytes(h, STRam, STRamEnd);
	h = rr_digest_bytes(h, IOmemory, 0x10000);
	h = rr_digest_mix(h, (uint64_t)CyclesGlobalClockCounter);
	h = rr_digest_mix(h, (uint32_t)nCyclesMainCounter);
	h = rr_digest_mix(h, (uint32_t)nVBLs);
	h = rr_digest_mix(h, (uint32_t)nHBL);
	{
		const MFP_STRUCT *m = &MFP_Array[0];
		h = rr_digest_mix(h, m->GPIP);  h = rr_digest_mix(h, m->AER);  h = rr_digest_mix(h, m->DDR);
		h = rr_digest_mix(h, m->IERA);  h = rr_digest_mix(h, m->IERB); h = rr_digest_mix(h, m->IPRA); h = rr_digest_mix(h, m->IPRB);
		h = rr_digest_mix(h, m->ISRA);  h = rr_digest_mix(h, m->ISRB); h = rr_digest_mix(h, m->IMRA); h = rr_digest_mix(h, m->IMRB);
		h = rr_digest_mix(h, m->VR);    h = rr_digest_mix(h, m->TACR); h = rr_digest_mix(h, m->TBCR); h = rr_digest_mix(h, m->TCDCR);
		h = rr_digest_mix(h, m->TADR);  h = rr_digest_mix(h, m->TBDR); h = rr_digest_mix(h, m->TCDR); h = rr_digest_mix(h, m->TDDR);
		h = rr_digest_mix(h, (uint32_t)m->TA_MAINCOUNTER); h = rr_digest_mix(h, (uint32_t)m->TB_MAINCOUNTER);
		h = rr_digest_mix(h, (uint32_t)m->TC_MAINCOUNTER); h = rr_digest_mix(h, (uint32_t)m->TD_MAINCOUNTER);
	}
	h = rr_digest_bytes(h, PSGRegisters, MAX_PSG_REGISTERS);
	h = rr_digest_mix(h, Keyboard.NbBytesInOutputBuffer);
	h = rr_digest_mix(h, KeyboardProcessor.MouseMode);
	h = rr_digest_mix(h, KeyboardProcessor.JoystickMode);
	h = rr_digest_mix(h, KeyboardProcessor.Joy.JoyData[0]);
	h = rr_digest_mix(h, KeyboardProcessor.Joy.JoyData[1]);
	h = FDC_RrDigest(h);
	h = rr_digest_mix(h, rr_rand_get());
	return h;
}

/* What a game does not change is not in the snapshot: the configuration, the TOS and cartridge ROM, the images of the drives and the flux of the IPF tracks. The order is Hatari's. */
static int rr_snap_sequence(bool bSave)
{
	int drive;
	for (drive = 0; drive < MAX_FLOPPYDRIVES; drive++)		/* the dynamic state of STX, SCP and Kryoflux images is not kept: such a game stays on the delay tier */
		if (EmulationDrives[drive].ImageType == FLOPPY_IMAGE_TYPE_STX || EmulationDrives[drive].ImageType == FLOPPY_IMAGE_TYPE_SCP ||
		    EmulationDrives[drive].ImageType == FLOPPY_IMAGE_TYPE_KFS)
			return 1;
	STMemory_RrSnap(bSave);
	Cycles_MemorySnapShot_Capture(bSave);				/* before the controller (CyclesGlobalClockCounter) */
	FDC_MemorySnapShot_Capture(bSave);
	if (Floppy_RrSnap(bSave))
		return 1;
	IPF_RrSnap(bSave);
	ACIA_MemorySnapShot_Capture(bSave);
	IKBD_MemorySnapShot_Capture(bSave);
	MIDI_MemorySnapShot_Capture(bSave);
	CycInt_MemorySnapShot_Capture(bSave);
	M68000_MemorySnapShot_Capture(bSave);
	MFP_MemorySnapShot_Capture(bSave);
	PSG_MemorySnapShot_Capture(bSave);
	Sound_MemorySnapShot_Capture(bSave);
	Video_MemorySnapShot_Capture(bSave);
	Blitter_MemorySnapShot_Capture(bSave);
	IoMem_MemorySnapShot_Capture(bSave);
	Hatari_rand_MemorySnapShot_Capture(bSave);
	return rr_snap_error;
}

/* The size of a snapshot: the same for the whole run, counted once. 0: this machine cannot be saved this way. */
size_t rr_snap_size(void)
{
	static size_t size;
	if (!size)
	{
		rr_snap_buf = NULL; rr_snap_cap = 0; rr_snap_pos = 0; rr_snap_error = 0; rr_snap_saving = 1; rr_snap_lean = 1;
		rr_snap_sequence(true);
		rr_snap_lean = 0;
		size = rr_snap_error ? 0 : rr_snap_pos;
	}
	return size;
}

/* The bytes written, 0 when the buffer is too small or the machine cannot be saved. Valid after any frame (the CPU is between two instructions). */
size_t rr_snap_save(void *buffer, size_t capacity)
{
	size_t used;
	if (!buffer || capacity < rr_snap_size())
		return 0;
	rr_snap_buf = (uint8_t *)buffer; rr_snap_cap = capacity; rr_snap_pos = 0; rr_snap_error = 0; rr_snap_saving = 1; rr_snap_lean = 1;
	rr_snap_sequence(true);
	rr_snap_lean = 0;
	used = rr_snap_error ? 0 : rr_snap_pos;
	rr_snap_buf = NULL;
	return used;
}

/* Back to the saved state at once, in place: 1, or 0 when the size is not a snapshot's (nothing was touched). */
int rr_snap_load(const void *buffer, size_t size)
{
	int failed;
	if (!buffer || !rr_snap_size() || size != rr_snap_size())
		return 0;
	rr_snap_buf = (uint8_t *)buffer; rr_snap_cap = size; rr_snap_pos = 0; rr_snap_error = 0; rr_snap_saving = 0; rr_snap_lean = 1;
	rr_snap_sequence(false);
	rr_snap_lean = 0;
	failed = rr_snap_error || rr_snap_pos != size;
	rr_snap_buf = NULL;
	if (failed)
		return 0;
	rr_cpu_finish();
	return 1;
}
'''

_FLOPPY_OLD = 'void Floppy_GetBootDrive(void)\n{\n'
_FLOPPY_NEW = '''/* Retro-Recomp modification (GPL-2.0, like this file): the lean snapshot keeps what a drive changes while a game runs (its disk-change states); the image is static. */
int Floppy_RrSnap(bool bSave)
{
	int i;
	(void)bSave;
	for (i = 0; i < MAX_FLOPPYDRIVES; i++)
	{
		MemorySnapShot_Store(&EmulationDrives[i].bContentsChanged, sizeof(EmulationDrives[i].bContentsChanged));
		MemorySnapShot_Store(&EmulationDrives[i].bOKToSave, sizeof(EmulationDrives[i].bOKToSave));
		MemorySnapShot_Store(&EmulationDrives[i].TransitionState1, sizeof(EmulationDrives[i].TransitionState1));
		MemorySnapShot_Store(&EmulationDrives[i].TransitionState1_VBL, sizeof(EmulationDrives[i].TransitionState1_VBL));
		MemorySnapShot_Store(&EmulationDrives[i].TransitionState2, sizeof(EmulationDrives[i].TransitionState2));
		MemorySnapShot_Store(&EmulationDrives[i].TransitionState2_VBL, sizeof(EmulationDrives[i].TransitionState2_VBL));
	}
	return 0;
}

void Floppy_GetBootDrive(void)
{
'''

_IPF_OLD = 'int FDC_GetBytesPerTrack_IPF(uint8_t Drive, uint8_t Track, uint8_t Side)\n{\n'
_IPF_NEW = '''/* Retro-Recomp modification (GPL-2.0, like this file): the lean snapshot keeps the position in the track a drive reads (the decoded flux is static, and the pointers into it
 * are valid in the process that saved the state). */
void IPF_RrSnap(bool bSave)
{
	int drive;
	(void)bSave;
	for (drive = 0; drive < MAX_FLOPPYDRIVES; drive++)
		MemorySnapShot_Store(&IPF_State[drive].stream, sizeof(IPF_State[drive].stream));
}

int FDC_GetBytesPerTrack_IPF(uint8_t Drive, uint8_t Track, uint8_t Side)
{
'''

_STMEM_OLD = 'void STMemory_SetDefaultConfig(void)\n{\n'
_STMEM_NEW = '''/* Retro-Recomp modification (GPL-2.0, like this file): the lean snapshot keeps the RAM and the I/O area; the TOS and the cartridge area do not change. */
void STMemory_RrSnap(bool bSave)
{
	(void)bSave;
	MemorySnapShot_Store(STRam, STRamEnd);
	MemorySnapShot_Store(IOmemory, 0x10000);
}

void STMemory_SetDefaultConfig(void)
{
'''

_FDC_OLD = 'void\tFDC_MemorySnapShot_Capture(bool bSave)\n'
_FDC_NEW = '''/* Retro-Recomp modification (GPL-2.0, like this file): the controller's part of the multiplayer digest, as named fields. */
extern uint64_t rr_digest_mix(uint64_t h, uint64_t value);
uint64_t FDC_RrDigest(uint64_t h)
{
	int d;
	h = rr_digest_mix(h, (uint32_t)FDC.Command);
	h = rr_digest_mix(h, (uint32_t)FDC.CommandState);
	h = rr_digest_mix(h, FDC.CommandType);
	h = rr_digest_mix(h, FDC.StatusTypeI);
	h = rr_digest_mix(h, (uint32_t)FDC.IndexPulse_Counter);
	h = rr_digest_mix(h, FDC.CommandComplete_ClockCounter);
	h = rr_digest_mix(h, FDC.FD_DR_time);
	h = rr_digest_mix(h, FDC.DPLL_Window_State_Pos);
	h = rr_digest_mix(h, FDC.DPLL_Last_Bit);
	for (d = 0; d < MAX_FLOPPYDRIVES; d++)
		h = rr_digest_mix(h, ((uint64_t)MFM_STREAMS[d].RevolutionsNbr << 32) ^ (uint64_t)FDC_DRIVES[d].HeadTrack);
	return h;
}

void\tFDC_MemorySnapShot_Capture(bool bSave)
'''

_CPU_OLD = 'void restore_cpu_finish (void)\n{\n'
_CPU_NEW = '''/* Retro-Recomp modification (GPL-2.0, like this file): what restore_cpu_finish does for a state loaded in place: the program counter and the interrupt level; the CPU's tables are not built again. */
void rr_cpu_finish (void)
{
	/* the prefetch queue (ir, irc, ird) is restored as it was saved: fill_prefetch_quick is for state files without it, and it would read memory (bus side effects) and change ird */
	m68k_setpc_normal (regs.pc);
	doint ();
}

void restore_cpu_finish (void)
{
'''

_RAND_OLD = 'void\tHatari_rand_MemorySnapShot_Capture ( int bSave )\n{\n'
_RAND_NEW = ('/* Retro-Recomp modification (GPL-2.0, like this file): the state of the generator, for the multiplayer digest. */\n'
             'uint32_t rr_rand_get ( void ) { return Hatari_rand_state; }\n\n'
             'void\tHatari_rand_MemorySnapShot_Capture ( int bSave )\n{\n')

_M68000_OLD = '\t\tsave_fpu (&len,chunk);\n'
_M68000_NEW = '\t\t{ extern int rr_snap_lean; if (!rr_snap_lean) save_fpu (&len,chunk); }	/* Retro-Recomp modification (GPL-2.0, like this file): the lean snapshot leaves out the FPU, which no ST has (the FPU helpers are not set before the first frame) */\n'
_M68000_OLD2 = '\t\trestore_fpu (chunk);\n'
_M68000_NEW2 = '\t\t{ extern int rr_snap_lean; if (!rr_snap_lean) restore_fpu (chunk); }\n'

_M68000_OLD3 = '\t\tsave_cpu_extra (&len,chunk);\n'
_M68000_NEW3 = '\t\t{ extern int rr_snap_lean; if (!rr_snap_lean) save_cpu_extra (&len,chunk); }	/* its fields are the configuration (and loading them back writes it) */\n'
_M68000_OLD4 = '\t\trestore_cpu_extra (chunk);\n'
_M68000_NEW4 = '\t\t{ extern int rr_snap_lean; if (!rr_snap_lean) restore_cpu_extra (chunk); }\n'

_RTC_OLD = 'static struct tm* get_localtime(void)\n{\n\t/* Get system time */\n\ttime_t nTimeTicks = time(NULL);\n\treturn localtime(&nTimeTicks);\n}\n'
_RTC_NEW = '''/* Retro-Recomp modification (GPL-2.0, like this file): in a multiplayer match every seat's clock reads the same time (UTC, not this PC's zone); 0 is this PC's time. */
static int64_t rr_rtc_seconds;
void rr_rtc_session_clock(int64_t seconds) { rr_rtc_seconds = seconds; }

static struct tm* get_localtime(void)
{
	/* Get system time */
	time_t nTimeTicks = rr_rtc_seconds ? (time_t)rr_rtc_seconds : time(NULL);
	return rr_rtc_seconds ? gmtime(&nTimeTicks) : localtime(&nTimeTicks);
}
'''

ROLLBACK_REPLACEMENTS = [
    ('src/memorySnapShot.c', _DECL_OLD, _DECL_NEW),
    ('src/memorySnapShot.c', _SKIP_OLD, _SKIP_NEW),
    ('src/memorySnapShot.c', _STORE_OLD, _STORE_NEW),
    ('src/memorySnapShot.c', _API_OLD, _API_NEW),
    ('src/floppy.c', _FLOPPY_OLD, _FLOPPY_NEW),
    ('src/floppies/ipf_dsk.c', _IPF_OLD, _IPF_NEW),
    ('src/stMemory.c', _STMEM_OLD, _STMEM_NEW),
    ('src/fdc.c', _FDC_OLD, _FDC_NEW),
    ('src/cpu/newcpu.c', _CPU_OLD, _CPU_NEW),
    ('src/utils.c', _RAND_OLD, _RAND_NEW),
    ('src/m68000.c', _M68000_OLD, _M68000_NEW),
    ('src/m68000.c', _M68000_OLD2, _M68000_NEW2),
    ('src/m68000.c', _M68000_OLD3, _M68000_NEW3),
    ('src/m68000.c', _M68000_OLD4, _M68000_NEW4),
    ('src/rtc.c', _RTC_OLD, _RTC_NEW),
]
