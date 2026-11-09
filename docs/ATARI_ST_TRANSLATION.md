# Atari ST: really translated 68000 code on Hatari, a plan

Written on 9 November 2026 to prepare a decision of the owner. **No translation exists and none starts before that decision.** The machine stays emulated on Hatari whichever route is taken; the window title and the note "not fully recompiled" do not change. This page is about the 68000 only; it says nothing of hardware fidelity, gameplay or latency.

Sources: a sampling profile of the current tree, three games, on a PC that was not quiet, so shares and ratios only, about +/- 3 to 5 % on a ratio; a reading of `retrorecomp/amiga_translate.py`, of Hatari's `gencpu.c` and of what it generates. Measured figures and estimates are labelled.

## 1. Where the time goes now

Native code since 1.7.3 is Hatari's handlers compiled again per opcode and chained ([ATARI_ST.md](ATARI_ST.md#2-how-the-conversion-works)). Percent of the main thread's host cycles, native path, 5 runs merged per column, the same windows of play as the first profile:

| Component | Bomb Jack | Turrican II | Indiana Jones |
| --- | ---: | ---: | ---: |
| Way in and chain: hook, look-up, instruction, test of what is due, next | 12.8 | 13.7 | 19.5 |
| The 68000 loop | 6.0 | 1.4 | 7.8 |
| The handlers' own work (registers, flags, addresses) | 7.1 | 9.3 | 8.9 |
| Bus: memory, wait states, prefetch | 25.2 | 32.6 | 15.0 |
| Cycle accounting | 1.7 | 2.5 | 1.9 |
| Interrupt and flag checks between instructions | 11.1 | 5.3 | 14.9 |
| **68000 in all** | **63.9** | **64.7** | **68.1** |
| Clock events and MFP | 19.1 | 3.2 | 17.9 |
| Video | 9.6 | 21.7 | 6.6 |
| Sound, keyboard, copies | 7.4 | 10.0 | 7.3 |

So the most a perfect translation could gain, the whole 68000 costing nothing, is 2.8, 2.8 and 3.1 times against today's native path. It is a ceiling, not a target: the bus, the slot waits and the interrupt sampling stay.

**The handlers' own work, the only part a translation of the semantics removes by itself, is 7 to 9 %.** The bus is three times that, and inlining it gains nothing measurable (below): its cost is what it does, not how it is called.

## 2. A finding that comes first: the timer D

TOS programs the MFP's timer D at a very high rate and leaves its interrupt off. Hatari still runs an event for it, one every 1.6 instructions on Bomb Jack (4,212 per frame; measured, the same with TOS 1.04 and EmuTOS, so not EmuTOS's doing). 70 to 97 % of the chains stop because of an event due, which is why a chain is 1.5 to 1.9 instructions long on these games, and any translated block would stop there too.

Hatari has its own option for this, off today (`hatari_timerd`): when TOS itself starts the timer, it starts it far slower. Its source says the rate halves the frame rate. Tried on one tree, not shipped; each game's fresh reference has the patch too, every route equal to it, the compressed copy and the state too (Standard level):

| Game | Host cycles, today over patched (5 alternated runs: median, min) | Mean chain, today, patched |
| --- | ---: | ---: |
| Bomb Jack | 1.49, 1.50 | 1.52, 3.51 |
| Indiana Jones | 1.52, 1.51 | 1.74, 4.05 |
| Kick Off 2 | 1.52, 1.56 | 1.86, 4.87 |

Turrican II, on TOS 1.04, stops the timer itself in play: little to gain there. **This is about as much as a translation is estimated to give, for one line.** But it changes the machine, not the code: a game that uses the timer as TOS left it sees another rate, and a game reading its data register gets Hatari's fake value. Hatari names two games that use the timer without setting it up (Paradroid, Speedball) and calls the patch compatible; we have checked neither. It would be a named limit of hardware fidelity, and the panel would run again. The native counts move a little (a game's course changes with the timing): the reference changes with it, so the frame comparison does not see the difference from an unpatched machine, and a check of that kind would have to be added.

## 3. Compiling what exists better (measured, no translation)

On private copies of Bomb Jack, Turrican II and Indiana Jones, 6 to 8 alternated rounds, the trace of each game's main route equal to its reference. Cycles of the variant over today's, lower is better; noise about +/- 3 to 5 %:

| Change | Bomb Jack | Turrican II | Indiana Jones |
| --- | ---: | ---: | ---: |
| Link-time optimisation of the steps | 0.950 | 0.944 | 0.971 |
| Test of what is due inline in each instruction | 0.985 | 0.946 | 0.995 |
| Fault exits marked cold | 0.989 | 0.962 | 0.984 |
| Shift and A7 tables local | 1.001 | 0.980 | 1.000 |
| Bus inline in each form | 1.017 | 0.967 | 0.994 |
| Those last four together | 0.965 | 0.895 to 0.929 | 0.986 |

The programs grow by 10 to 21 %. LTO was not tried on Linux, and these variants did not run the vectors. **Removing `OpcodeFamily` is not valid**: Hatari reads it on the cycle-exact path (`ioMem.c`, `psg.c`, for MOVEM to I/O registers), and Turrican II's trace differs without it.

## 4. What a translator would be

**What carries over from the Amiga's `amiga_translate.py`** (593 lines, 50 of Moira's handlers, 140 in all): about a quarter of it as knowledge, the effective-address decode, the condition table, the operand selection, the flag formulas, the shape of the work, and the decision that extension words are read live so a form depends only on its opcode. **None of its text, and not its bus order.** It emits Moira's templates, C++ exceptions and flag booleans. Hatari follows the vectors where Moira does not (JSR fetches the target before it pushes; a long read-modify-write writes the low word first; so does MOVEM.L to -(An)), so each order comes from Hatari's text. Interrupts are sampled at explicit points of each handler (`ipl_fetch_now`, `ipl_fetch_next`, `ipl_fetch_next_pre`), not by a flag on the last access; a fault is a test after each access with its own PC and flag repair; flags live in an x86-shaped word.

**Hatari's handlers are not an interpreter's.** With the opcode a literal, the compiler has already removed the decoding. What remains in a handler is memory traffic on global state across calls: `regs.ir`, `irc`, `db`, buffers and PC stored at each step, a test of `hardware_bus_error` after each access, `CurrentInstrCycles` and `OpcodeFamily` kept for the devices that read them. A translator earns its gain by keeping that state in locals along a chain and flushing it on exit, not by rewriting the arithmetic.

Two routes:

| | Pass over gencpu's text | Translator as on the Amiga |
| --- | --- | --- |
| What it is | A Python pass over the generated handlers: fields made literal, exits moved out of the hot path, accesses numbered, state held in locals along a chain | Own C for 60 to 80 code shapes behind Hatari's 1,540 handlers, written from them |
| Size (estimate) | 300 to 600 lines, tests and proof additions | 1,000 to 1,600 lines, 250 to 400 of tests, the same proof additions |
| AI time (estimate) | 1 to 2 days; bottleneck: the state flushed before each device access | 2 to 4 days; bottleneck: matching orders and interrupt points, found one by one by the differential run |
| Coverage | All 45,814 forms from the start | About 99 % of what games execute; the rest stays as it is |
| What the report may say | **Hatari's code specialised**, as today: its statements remain | **Translated**, counted apart from the specialised forms, per form |
| Licence | GPL-2.0, Hatari's text | Written from GPL handlers, so GPL-2.0 too; an exported ST game is GPL either way |

Staying as they are, in both routes: DIVU, DIVS, MULU, MULS, TAS, CHK, TRAP, TRAPV, RTE, RTR, STOP, RESET, MOVEP, the BCD group, moves and logic on SR and CCR, line A and F, illegal opcodes, and every fault exit. A mask, a displacement or an immediate stays read on the bus: the guard is the opcode only, so MOVEM cannot be unrolled and immediates cannot be folded.

**Gain, an estimate on the profile above, not a measurement.** Assuming a translated instruction pays half of today's way in, chain and loop, 40 % of the handlers' work, 80 % of the bus, 30 % of the cycle accounting and 60 % of the checks: **1.32, 1.30 and 1.41 times** against today's native path, before section 2 and with chains as short as today. The bus term matters most, 10 points of it being about 0.03 to 0.05 on the factor. With the timer D patched the estimate is not additive: the shares must be measured again. A rough product with section 2 is near 2 times on the games it helps (not measured).

## 5. The proof

Nothing ships unless it equals its fresh interpreted reference, frame by frame, on picture, sound, RAM and registers, on every route. Per form, `tools/atarist_vector_selftest.py --all-forms` already compares every form with Hatari's table handler: registers, flags, clock in each slot position, 834,101 bus accesses in order and clock, an interrupt line changing during the instruction, prefetch and buffers, RAM, through a device bank and on direct RAM; the 6,764 fixtures go on the same way. It finds no difference on today's forms, and without `-fwrapv` it finds the ADDX.L family. With code written by hand it would become the main gate. To add before a translator: an injected bus error (no fixture and no run reaches those exits), the hidden fault state (`last_addr_for_exception_3` and its kin), `extra_cycle`, the raw flag words, and the fixtures' own transaction lists compared with Hatari's order. Estimate: 150 to 250 lines. Any form can stay on Hatari's text, form by form.

## 6. Recommendation and choices

1. **Compile better first** (section 3): LTO, the inline test, cold exits. Hours, no change to any behaviour, the same proof. Not a decision for the owner unless it should be.
2. **Timer D: the owner's decision.** It is the largest gain seen, measured, but a change to the machine. Recommended **with** the limit written down and a first read on the panel, since a game that needs it can be recognised only by trying.
3. **Then measure again, and only then decide on a translator.** Recommended order if the goal is *the share that is really translated*: the translator of the Amiga's kind, since a pass over Hatari's text would not change what the report may honestly say. If the goal is speed alone, the pass, or nothing: after 1 and 2 the games on the panel may have no need of more.

Not studied here: a sweep outward from observed code as on the Amiga (Turrican II's window of play is now 99.99 % native, so the need is less clear than on 8 November); saving more than the 68000, since the chips stay Hatari's in every route; Linux for LTO.
