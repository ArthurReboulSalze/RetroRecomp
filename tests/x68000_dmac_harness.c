/* Authored cases for the HD63450 channel start of the X68000 machine base (x68k/dmac.c, as adapted by
 * tools/x68000_base74.py). No ROM, disk or firmware: the bus is a few authored bytes and the device
 * ready callback is a flag. Each line printed is "name key=value ..."; tests/test_x68000_dmac.py reads them. */
#include <stdio.h>
#include <string.h>

#include "common.h"
#include "dmac.h"
#include "memory.h"

DWORD BusErrFlag = 0;
BYTE Mcry_LRTiming = 0;
static BYTE bus[0x4000];
static int interrupts;
static int device_ready;

BYTE FASTCALL dma_readmem24(DWORD adr) { return bus[adr & 0x3fff]; }
WORD FASTCALL dma_readmem24_word(DWORD adr) { return (WORD)(bus[adr & 0x3fff] << 8 | bus[(adr + 1) & 0x3fff]); }
DWORD FASTCALL dma_readmem24_dword(DWORD adr) { return (DWORD)dma_readmem24_word(adr) << 16 | dma_readmem24_word(adr + 2); }
void FASTCALL dma_writemem24(DWORD adr, BYTE data) { bus[adr & 0x3fff] = data; }
void FASTCALL dma_writemem24_word(DWORD adr, WORD data) { dma_writemem24(adr, (BYTE)(data >> 8)); dma_writemem24(adr + 1, (BYTE)data); }
void FASTCALL dma_writemem24_dword(DWORD adr, DWORD data) { dma_writemem24_word(adr, (WORD)(data >> 16)); dma_writemem24_word(adr + 2, (WORD)data); }
void IRQH_IRQCallBack(BYTE irq) { (void)irq; }
void IRQH_Int(BYTE irq, void *handler) { (void)irq; (void)handler; ++interrupts; }
int FDC_IsDataReady(void) { return 0; }
int SASI_IsReady(void) { return 0; }
int ADPCM_IsReady(void) { return 0; }
static int ready(void) { return device_ready; }

#define CH 2
#define BASE (0xe84000 + CH * 0x40)

static void reg(unsigned offset, unsigned value) { DMA_Write(BASE + offset, (BYTE)value); }
static void reg16(unsigned offset, unsigned value) { reg(offset, value >> 8); reg(offset + 1, value); }
static void reg32(unsigned offset, unsigned value) { reg16(offset, value >> 16); reg16(offset + 2, value); }

/* Device to memory, byte operands, external request: one byte moves each time the device is ready. */
static void program(unsigned count)
{
   reg(0x04, 0x00);
   reg(0x05, 0x82);
   reg(0x06, 0x04);
   reg(0x25, 0x41);
   reg(0x27, 0x42);
   reg16(0x0a, count);
   reg32(0x0c, 0x1000);
   reg32(0x14, 0x2000);
}

static void report(const char *name)
{
   printf("%s csr=%02x cer=%02x ccr=%02x mtc=%u mar=%05x interrupts=%d\n", name, DMA[CH].CSR, DMA[CH].CER,
          DMA[CH].CCR, DMA[CH].MTC, DMA[CH].MAR & 0xfffff, interrupts);
}

static void reset(void)
{
   DMA_Init();
   DMA_SetReadyCB(CH, ready);
   memset(bus, 0, sizeof bus);
   interrupts = 0;
   device_ready = 0;
}

int main(void)
{
   /* A channel that waits for its device is active; the device then becomes ready and the game starts it again. */
   reset();
   program(4);
   reg(0x07, 0x88);
   report("armed");
   device_ready = 1;
   reg(0x07, 0x88);
   report("restart_on_active_channel");

   /* A finished transfer leaves COC set; the next start must not need the game to acknowledge it first. */
   reset();
   device_ready = 1;
   program(1);
   reg(0x07, 0x88);
   report("first_transfer");
   program(1);
   reg(0x07, 0x88);
   report("start_with_completion_not_acknowledged");

   /* Errors that are not about the channel being busy are untouched. */
   reset();
   device_ready = 1;
   program(0);
   reg(0x07, 0x88);
   report("zero_count");
   reset();
   program(4);
   reg(0x07, 0x88);
   reg(0x07, 0x10);
   report("software_abort");
   return 0;
}
