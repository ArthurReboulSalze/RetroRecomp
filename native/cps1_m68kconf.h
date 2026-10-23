/* Musashi configuration for the CPS-1 reference 68000 (copied over the
 * pinned Geolith m68kconf.h in the build tree): plain MC68000, interrupt
 * acknowledge through the board, everything else off. */
#ifndef M68KCONF__HEADER
#define M68KCONF__HEADER

#define OPT_OFF             0
#define OPT_ON              1
#define OPT_SPECIFY_HANDLER 2

#define M68K_COMPILE_FOR_MAME      OPT_OFF
#define M68K_EMULATE_010            OPT_OFF
#define M68K_EMULATE_EC020          OPT_OFF
#define M68K_EMULATE_020            OPT_OFF
#define M68K_EMULATE_030            OPT_OFF
#define M68K_EMULATE_040            OPT_OFF
#define M68K_SEPARATE_READS         OPT_OFF
#define M68K_SIMULATE_PD_WRITES     OPT_OFF

int cps1_m68k_int_ack(int level);
#define M68K_EMULATE_INT_ACK        OPT_SPECIFY_HANDLER
#define M68K_INT_ACK_CALLBACK(A)    cps1_m68k_int_ack(A)

#define M68K_EMULATE_BKPT_ACK       OPT_OFF
#define M68K_BKPT_ACK_CALLBACK()    0
#define M68K_EMULATE_TRACE          OPT_OFF
#define M68K_EMULATE_RESET          OPT_OFF
#define M68K_RESET_CALLBACK()
#define M68K_CMPILD_HAS_CALLBACK    OPT_OFF
#define M68K_CMPILD_CALLBACK(v,r)
#define M68K_RTE_HAS_CALLBACK       OPT_OFF
#define M68K_RTE_CALLBACK()
#define M68K_TAS_HAS_CALLBACK       OPT_OFF
#define M68K_TAS_CALLBACK()         1
#define M68K_ILLG_HAS_CALLBACK      OPT_OFF
#define M68K_ILLG_CALLBACK(opcode)  0
#define M68K_EMULATE_FC             OPT_OFF
#define M68K_SET_FC_CALLBACK(A)
#define M68K_MONITOR_PC             OPT_OFF
#define M68K_SET_PC_CALLBACK(A)
#ifdef CPS1_TRACE   /* diagnostic build only: every instruction with its cycle */
void cps1_trace_instruction(unsigned pc);
#define M68K_INSTRUCTION_HOOK       OPT_SPECIFY_HANDLER
#define M68K_INSTRUCTION_CALLBACK(pc) cps1_trace_instruction(pc)
#else
#define M68K_INSTRUCTION_HOOK       OPT_OFF
#define M68K_INSTRUCTION_CALLBACK(pc)
#endif
#define M68K_EMULATE_PREFETCH       OPT_OFF
#define M68K_EMULATE_ADDRESS_ERROR  OPT_OFF
#define M68K_LOG_ENABLE             OPT_OFF
#define M68K_LOG_1010_1111          OPT_OFF
#define M68K_LOG_FILEHANDLE         stderr
#define M68K_EMULATE_PMMU           OPT_OFF

#if defined(__x86_64__) || defined(_M_X64) || __SIZEOF_LONG__+0 == 8
#define M68K_USE_64_BIT  OPT_ON
#else
#define M68K_USE_64_BIT  OPT_OFF
#endif

#endif /* M68KCONF__HEADER */
