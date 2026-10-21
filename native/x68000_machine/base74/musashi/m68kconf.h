/* Retro-Recomp X68000: Musashi build configuration for the X68000 (MC68000).
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * Option names follow Musashi's documented configuration interface. Used
 * with Geolith's Musashi copy (src/m68k, MIT) for the 2014 machine base.
 */
#ifndef M68KCONF__HEADER
#define M68KCONF__HEADER

#ifdef __cplusplus
extern "C" {
#endif
int my_irqh_callback(int level);
#ifdef __cplusplus
}
#endif

#define OPT_OFF             0
#define OPT_ON              1
#define OPT_SPECIFY_HANDLER 2

#define M68K_COMPILE_FOR_MAME       OPT_OFF

/* MC68000 only. */
#define M68K_EMULATE_010            OPT_OFF
#define M68K_EMULATE_EC020          OPT_OFF
#define M68K_EMULATE_020            OPT_OFF
#define M68K_EMULATE_030            OPT_OFF
#define M68K_EMULATE_040            OPT_OFF

#define M68K_SEPARATE_READS         OPT_OFF
#define M68K_SIMULATE_PD_WRITES     OPT_OFF

/* The X68000 interrupt controller supplies vectors (irqh.c callbacks). */
#define M68K_EMULATE_INT_ACK        OPT_SPECIFY_HANDLER
#define M68K_INT_ACK_CALLBACK(A)    my_irqh_callback(A)

#define M68K_EMULATE_BKPT_ACK       OPT_OFF
#define M68K_BKPT_ACK_CALLBACK()    unused_bkpt_ack()
#define M68K_EMULATE_TRACE          OPT_ON
#define M68K_EMULATE_RESET          OPT_OFF
#define M68K_RESET_CALLBACK()       unused_reset()
#define M68K_CMPILD_HAS_CALLBACK    OPT_OFF
#define M68K_CMPILD_CALLBACK(v,r)   unused_cmpild(v,r)
#define M68K_RTE_HAS_CALLBACK       OPT_OFF
#define M68K_RTE_CALLBACK()         unused_rte()
#define M68K_TAS_HAS_CALLBACK       OPT_OFF
#define M68K_TAS_CALLBACK()         unused_tas()
#define M68K_ILLG_HAS_CALLBACK      OPT_OFF
#define M68K_ILLG_CALLBACK(opcode)  unused_illg(opcode)
#define M68K_EMULATE_FC             OPT_OFF
#define M68K_SET_FC_CALLBACK(A)     unused_set_fc(A)
#define M68K_MONITOR_PC             OPT_OFF
#define M68K_SET_PC_CALLBACK(A)     unused_set_pc(A)
#define M68K_INSTRUCTION_HOOK       OPT_OFF
#define M68K_INSTRUCTION_CALLBACK(pc) unused_instruction_hook(pc)
#define M68K_EMULATE_PREFETCH       OPT_OFF
#define M68K_EMULATE_ADDRESS_ERROR  OPT_ON

#define M68K_LOG_ENABLE             OPT_OFF
#define M68K_LOG_1010_1111          OPT_OFF
#define M68K_LOG_FILEHANDLE         unused_log_file

#define M68K_EMULATE_PMMU           OPT_OFF

#if defined(__x86_64__) || defined(_M_X64) || __SIZEOF_LONG__+0 == 8
#define M68K_USE_64_BIT  OPT_ON
#else
#define M68K_USE_64_BIT  OPT_OFF
#endif

#endif /* M68KCONF__HEADER */
