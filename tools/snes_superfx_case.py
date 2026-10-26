"""Authored GSU jobs (cases) as the S-CPU drives them, and their C table."""
from tools.snes_superfx_model import (Gsu, ModelError, ROM_SIZE, RAM_SIZE, M16, ram_crc)

# R0-R13 start as recognisable fillers so a stray register write shows up.
BACKGROUND = [(0x0A01 + n * 0x0313) & M16 for n in range(14)]
MODES = {'cold': 0, 'warm': 1, 'rom': 2}


def rom_index(bank, addr):
    """GSU view of the Game Pak ROM: 00-3F LoROM 32K chunks, 40-5F linear 64K banks."""
    if bank < 0x40:
        return (((bank & 0x3F) << 15) | (addr & 0x7FFF)) & (ROM_SIZE - 1)
    return (((bank - 0x40) << 16) | addr) & (ROM_SIZE - 1)


class Case:
    """One authored job.

    mode 'cold': code runs through the cold code cache (fills from ROM);
    mode 'warm': the S-CPU preloads all 32 cache lines first (documented: writing the
                 last byte of a line validates it), so every fetch is a cache hit;
    mode 'rom' : code sits outside the 512-byte cache window, every fetch is a ROM read.
    ``timed`` asks for an exact stop-clock check (only built from documented prices).
    ``ares`` marks expectations that rest on ares semantics where fullsnes is silent.
    ``finding`` ties the case to a recorded documentation/core difference.
    """

    def __init__(self, name, code, *, start=0, regs=None, sfr=0, scmr=0x18, scbr=0, cfgr=0,
                 clsr=0, pbr=0, mode='cold', rom=(), ram=(), cache=None, timed=False,
                 ares=False, finding=0, resume=(), jobs=(), cache_check=(), sfr_mask=0xFFFF,
                 irq_masked_flag=True, background=True, base=None, cycles=None, no_ram=False):
        self.name = name
        self.start, self.sfr, self.scmr, self.scbr, self.cfgr = start, sfr, scmr, scbr, cfgr
        self.clsr, self.pbr, self.mode, self.timed = clsr, pbr, mode, timed
        self.ares, self.finding, self.resume = ares, finding, tuple(resume)
        self.sfr_mask, self.cache_check = sfr_mask, tuple(cache_check)
        self.irq_masked_flag = irq_masked_flag
        self.base, self.cycles, self.no_ram = base, cycles, no_ram
        base = {n: BACKGROUND[n] for n in range(14)} if background else {}
        base.update(regs or {})
        self.regs = base
        self.jobs = [dict(j) for j in jobs]
        self.rom_patches = list(rom)
        self.ram_patches = list(ram)
        if pbr <= 0x5F:
            self.rom_patches.insert(0, (rom_index(pbr, start), bytes(code)))
        else:
            self.ram_patches.insert(0, ((((pbr & 1) << 16) | start) & (RAM_SIZE - 1), bytes(code)))
        self.cache = cache
        self.cache_used = None
        self.exp = None
        self.job_values = []

    def rom_image(self):
        rom = bytearray(ROM_SIZE)
        for idx, data in self.rom_patches:
            rom[idx:idx + len(data)] = data
        return rom

    def ram_image(self):
        ram = bytearray(RAM_SIZE)
        for idx, data in self.ram_patches:
            ram[idx:idx + len(data)] = data
        return ram

    def expect(self):
        rom, ram = self.rom_image(), self.ram_image()
        m = Gsu(bytes(rom), ram)
        m.irq_masked_flag_rule = self.irq_masked_flag
        m.cfgr, m.clsr, m.scmr, m.scbr = self.cfgr & 0xA0, self.clsr & 1, self.scmr & 0x3F, self.scbr
        m.pbr = self.pbr & 0x7F
        m.flush_cache()
        m.set_sfr_flags(self.sfr)
        if self.mode == 'warm':
            data = self.cache
            if data is None:
                data = bytes(m.memory_byte(m.pbr, a) for a in range(512))
            self.cache_used = bytes(data)
            m.cpu_cache_fill(data)
        jobs = self.jobs or [{}]
        self.job_values = []
        for number, job in enumerate(jobs):
            values = dict(self.regs) if number == 0 else {}
            values.update(job)
            if number == 0:
                values[15] = self.start
            self.job_values.append(values)
            for n in sorted(values):
                if n < 15:
                    m.cpu_write_reg(n, values[n])
            if 15 in values:
                m.r[15] = values[15] & M16
            m.fetch_count = m.hits = m.direct = m.fills = 0
            m.mult_extra = 0
            m.r14_written = False
            m.fetched = []
            m.untimed = set()
            m.start()
            m.run()
        if self.timed:
            self.check_timed(m, len(jobs))
        self.ares = self.ares or bool(m.ares_rules)
        self.exp = m
        return m

    def check_timed(self, m, njobs):
        """timed=1: only prices fullsnes states (all fetches cache hits, or all plain ROM reads);
        timed=2: also the cold cache fill, whose cost fullsnes does not give (self-consistency only)."""
        if njobs != 1 or m.untimed or m.r14_written or self.pbr > 0x5F:
            raise ModelError('%s: no price for %s' % (self.name, sorted(m.untimed) or 'this job'))
        if self.timed == 1 and (m.fills or (m.hits and m.direct)):
            raise ModelError('%s: documented timing needs a single fetch regime' % self.name)


def c_bytes(data):
    return ','.join('%d' % b for b in data) if data else '0'


def ranges(items):
    """Group (index, byte) pairs into contiguous (start, bytes) runs."""
    out = []
    for idx, byte in sorted(items):
        if out and out[-1][0] + len(out[-1][1]) == idx:
            out[-1][1].append(byte)
        else:
            out.append((idx, [byte]))
    return [(i, bytes(b)) for i, b in out]


def emit_case(case, serial, base_index=-1):
    """Return (declarations, table row) for one case."""
    m = case.exp
    out = []
    p = 'c%d' % serial

    def patches(label, items):
        for k, (idx, data) in enumerate(items):
            out.append('static const uint8_t %s_%s%d[]={%s};' % (p, label, k, c_bytes(data)))
        rows = ','.join('{%d,%d,%s_%s%d}' % (idx, len(data), p, label, k) for k, (idx, data) in enumerate(items))
        out.append('static const RrGsuPatch %s_%s[]={%s};' % (p, label, rows if items else '{0,0,0}'))
        return len(items)

    nrom = patches('rom', [(i, bytes(d)) for i, d in case.rom_patches])
    nram = patches('ram', [(i, bytes(d)) for i, d in case.ram_patches])
    nexp = patches('exp', [] if case.no_ram else ranges([(i, m.ram[i]) for i in m.dirty]))
    rom = case.rom_image()
    check = [(addr & 0x1FF, bytes(rom[rom_index(case.pbr, addr + k)] for k in range(length)))
             for addr, length in case.cache_check]
    ncache = patches('cc', check)
    jobs = []
    for values in case.job_values:
        mask, regs = 0, [0] * 16
        for n, v in values.items():
            mask |= 1 << n
            regs[n] = v & M16
        jobs.append('{%d,{%s}}' % (mask, ','.join(str(r) for r in regs)))
    out.append('static const RrGsuJob %s_jobs[]={%s};' % (p, ','.join(jobs)))
    cache_ref = '0'
    if case.cache_used is not None:
        out.append('static const uint8_t %s_cache[512]={%s};' % (p, c_bytes(case.cache_used)))
        cache_ref = '%s_cache' % p
    out.append('static const uint32_t %s_resume[]={%s};' % (p, ','.join(str(t) for t in case.resume) or '0'))
    row = ('{.name="%s",.mode=%d,.clsr=%d,.cfgr=%d,.scmr=%d,.scbr=%d,.pbr=%d,.sfr_init=%d,.timed=%d,'
           '.finding=%d,.ares=%d,.njobs=%d,.jobs=%s_jobs,.nrom=%d,.rom=%s_rom,.nram=%d,.ram=%s_ram,'
           '.cache=%s,.nresume=%d,.resume=%s_resume,.r={%s},.sfr=%d,.sfr_mask=%d,.rombr=%d,.rambr=%d,'
           '.exp_pbr=%d,.cbr=%d,.ram_crc=%uu,.nexp=%d,.exp=%s_exp,.ncache=%d,.cc=%s_cc,'
           '.hits=%d,.direct=%d,.fills=%d,.extra=%d,.base=%d,.cyc_lo=%d,.cyc_hi=%d,.no_ram=%d}') % (
        case.name, MODES[case.mode], case.clsr & 1, case.cfgr & 0xA0, case.scmr & 0x3F, case.scbr & 0xFF,
        case.pbr & 0x7F, case.sfr, int(case.timed), case.finding, 1 if case.ares else 0,
        len(case.job_values), p, nrom, p, nram, p, cache_ref, len(case.resume), p,
        ','.join(str(v) for v in m.r), m.sfr() & case.sfr_mask, case.sfr_mask, m.rombr, m.rambr,
        m.pbr, m.cbr, ram_crc(m.ram), nexp, p, ncache, p,
        m.hits if case.timed else 0, m.direct if case.timed else 0, m.fills if case.timed else 0,
        m.mult_extra if case.timed else 0,
        base_index, case.cycles[0] if case.cycles else 0, case.cycles[1] if case.cycles else 0,
        1 if case.no_ram else 0)
    return '\n'.join(out), row
