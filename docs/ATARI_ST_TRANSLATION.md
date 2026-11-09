# Atari ST: really translated 68000 code on Hatari, a plan

Written on 9 November 2026 to prepare a decision of the owner. **No translation exists and none starts before that decision.** The machine stays emulated on Hatari whichever route is taken; the window title and the note "not fully recompiled" do not change. This page is about the 68000 only; it says nothing of hardware fidelity, gameplay or latency.

Sources: a sampling profile of the current tree, three games, on a PC that was not quiet, so shares and ratios only, about +/- 3 to 5 % on a ratio; a reading of `retrorecomp/amiga_translate.py`, of Hatari's `gencpu.c` and of what it generates. Measured figures and estimates are labelled.

## 1. Where the time goes now

Native code since 1.7.2 is Hatari's handlers compiled again per opcode and chained, with Hatari's timer D patch on and link-time optimisation ([ATARI_ST.md](ATARI_ST.md#2-how-the-conversion-works), [its limit](ATARI_ST.md#5-known-limits)). Percent of the main thread's host cycles, native path, 5 runs merged per column, windows of play, on a PC that was not quiet:

| Component | Bomb Jack, EmuTOS | Bomb Jack, TOS 1.04 | Indiana Jones, EmuTOS | Indiana Jones, TOS 1.04 |
| --- | ---: | ---: | ---: | ---: |
| Way in and chain: hook, look-up, instruction, test of what is due, next | 11.2 | 10.0 | 21.2 | 20.7 |
| The 68000 loop | 2.0 | 1.6 | 3.3 | 1.6 |
| The handlers' own work (registers, flags, addresses) | 9.8 | 10.5 | 11.2 | 9.2 |
| Bus: memory, wait states, prefetch | 40.6 | 41.0 | 28.5 | 33.7 |
| Cycle accounting | 0.7 | 1.4 | 1.2 | 1.4 |
| Interrupt and flag checks between instructions | 3.9 | 3.7 | 7.0 | 4.7 |
| **68000 in all** | **68.2** | **68.4** | **72.4** | **71.2** |
| Clock events and MFP | 4.6 | 3.9 | 3.8 | 2.7 |
| Video | 13.4 | 12.5 | 11.1 | 11.6 |
| Sound | 9.0 | 7.4 | 8.2 | 9.7 |

Turrican II is left out: that conversion, Standard level from an empty library, ran 7 % of this window natively (past its routes), so the figure would say nothing of native code.

So the most a perfect translation could gain, the whole 68000 costing nothing, is 3.1 to 3.6 times against today's native path. It is a ceiling, not a target: the bus, the slot waits and the interrupt sampling stay.

**The handlers' own work, the only part a translation of the semantics removes by itself, is 9 to 11 %.** The bus is three or four times that, and did not move in host cycles when everything else did. Inlining it gained nothing measurable (section 3): its cost is what it does, not how it is called.

## 2. What was done before this page's decision

On the owner's word of 9 November 2026, the machine now runs Hatari's timer D patch and the native code is compiled better: the test between instructions inline, cold fault exits, LTO. The limit and the gain per TOS are on the [machine page](ATARI_ST.md#5-known-limits). It was the largest gain seen and it was not a translation. A chain is now about 3.5 to 4.9 instructions on EmuTOS over a whole route, 13 to 16 on TOS 1.04; in play 6 to 14. What stops them now is the machine's own events (HBL and end of line 628 per frame, IKBD 156, MIDI 62, of about 974 on EmuTOS) and, on EmuTOS, a STOP in its ROM.

## 3. What did not need a translation

Measured before the patch, on private copies of Bomb Jack, Turrican II and Indiana Jones, 6 to 8 alternated rounds, the trace of each game's main route equal to its reference. Cycles of the variant over the code of then, lower is better; noise about +/- 3 to 5 %:

| Change | Bomb Jack | Turrican II | Indiana Jones |
| --- | ---: | ---: | ---: |
| Link-time optimisation of the steps (kept) | 0.950 | 0.944 | 0.971 |
| Test of what is due inline in each instruction (kept) | 0.985 | 0.946 | 0.995 |
| Fault exits marked cold (kept) | 0.989 | 0.962 | 0.984 |
| Shift and A7 tables local | 1.001 | 0.980 | 1.000 |
| Bus inline in each form | 1.017 | 0.967 | 0.994 |

**Removing `OpcodeFamily` is not valid**: Hatari reads it on the cycle-exact path (`ioMem.c`, `psg.c`, for MOVEM to I/O registers), and Turrican II's trace differs without it.

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

**Gain, an estimate on the profile above, not a measurement.** Assuming a translated instruction pays half of today's way in, chain and loop, 40 % of the handlers' work, 80 % of the bus, 30 % of the cycle accounting and 60 % of the checks: **1.29 and 1.30 times on Bomb Jack, 1.39 and 1.36 on Indiana Jones** (EmuTOS and TOS 1.04), against today's native path, with the patch and LTO in it. The bus term matters most, 10 points of it being about 0.03 to 0.05 on the factor.

## 5. The proof

Nothing ships unless it equals its fresh interpreted reference, frame by frame, on picture, sound, RAM and registers, on every route. Per form, `tools/atarist_vector_selftest.py --all-forms` already compares every form with Hatari's table handler: registers, flags, clock in each slot position, 834,101 bus accesses in order and clock, an interrupt line changing during the instruction, prefetch and buffers, RAM, through a device bank and on direct RAM; the 6,764 fixtures go on the same way. It finds no difference on today's forms, and without `-fwrapv` it finds the ADDX.L family. With code written by hand it would become the main gate. To add before a translator: an injected bus error (no fixture and no run reaches those exits), the hidden fault state (`last_addr_for_exception_3` and its kin), `extra_cycle`, the raw flag words, and the fixtures' own transaction lists compared with Hatari's order. Estimate: 150 to 250 lines. Any form can stay on Hatari's text, form by form.

## 6. Where the decision stands

Done: compiling better, and the timer D patch with its limit. **Still the owner's: a translator.** The figure for that decision is 1.3 to 1.4 times, estimated, against the native path of today, for 2 to 4 days of AI time and the largest proof of the machine.
If the goal is **the share that is really translated**, the translator of the Amiga's kind is the route, since a pass over Hatari's text would not change what the report may honestly say. If the goal is **speed alone**, the bus is the row to attack, and a translator touches it little: a pass, or nothing.

Not studied here: a sweep outward from observed code as on the Amiga. It would address what a first conversion leaves on the interpreter past its routes (Turrican II at 7 % native in a window of play from an empty library), which matters more to a player than any figure on this page. Saving more than the 68000 is not possible on this route: the chips stay Hatari's.
