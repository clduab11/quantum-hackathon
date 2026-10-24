# DQI design note: Berlekamp–Massey + Forney (P1)

This note is the P1 plan for replacing the reference Reed–Solomon decoder in `tasks/dqi/generate.py`. It does not change the P0 generator. The P0 generator is the competition package's extended-Euclidean decoder, rebuilt in this repository. The k256.dev decoder is not a parent and is not shipped.

Sources checked for this note:

- Gu et al., arXiv:2610.22367, and the Apache-2.0 circuit note `andigu/uncompute` `tasks/dqi-reed-solomon/circuits/discovered/README.md` (retrieved 2026-10-24).
- The same repository's task README for the field and the TQ-cost definition.
- PRA-171 inventory: verifier quotes for Q, executed Toffolis, and `R(ε⁺)`.
- `kickmix.GF2Field(12).modulus` on the shipped binary, read in this run.

## Register plan

The competition instance is RS(4095, 4025, 71) over GF(2¹²). The reference generator allocates:

- Quantum syndrome registers `S0`..`S69`: 70 registers, 12 qubits each, 840 qubits.
- Classical record `E0`..`E4094`: 4,095 registers, 12 bits each, 49,140 bits. Each shot's X-basis record is written here. The phase is the popcount of `error[j] AND E[j]` over positions.

Gu's decoder does not build the 4,095-symbol error word. It keeps the syndrome, a locator, a template, discrepancies, and a short workspace, and it kicks one phase bit. Their register names are not `S0`..`S69`. A port has to use the verifier's names and widths. Workspace qubits must be allocated and freed. Competition Q is the largest qubit id ever referenced, plus one. A freed qubit reduces Q only when its id is reused. Resetting a high id does not reduce Q (PRA-171, Qualtran `Circuit::compute_num_qubits`).

## Where the qubits and Toffolis go

Gu's certified circuit, in their own accounting:

| Phase | Toffolis | What it does |
| --- | ---: | --- |
| `bm` | 141,071 | 70 Berlekamp–Massey rounds. One shared inversion and one shared multiply serve both the retain path and the replace path. |
| `monicize` | 1,583 | Scale the locator so the constant term is 1. |
| `omega` | 15,246 | Write the error evaluator into the low syndrome words. |
| `euclid` | 44,470 | One half-degree Euclidean pass builds Ψ = 1/σ′. This pass sets the peak of 1,837 qubits. |
| `sweep` | 92,552 | 4,024 field points, 23 Toffolis each. Interpolation drops 71 points. |
| `euclid_inv` | 44,470 | Reverse the Euclidean pass. |
| `omega_restore` | 15,246 | Restore the syndrome words. |
| `unmonicize` | 1,583 | Undo the scale. |
| `reverse` | 86,176 | Replay 69 locator updates backward. Measurement drops values that do not need a reverse multiply. |

Total: 442,397 Toffolis, peak 1,837 qubits, 124,823,679 Clifford gates. The task's "440k Toffolis / 1,837 qubits" is this circuit. `init`, `zlin`, and `cleanup` add no Toffolis. `zlin` applies the syndrome-linear part of the phase with Z gates.

The reference circuit we rebuilt is larger: static count 5,725,461 Toffoli-like gates and Q = 1,893. Most of that cost is the synchronized Euclidean algorithm, run forward and then uncomputed, plus a Chien/Forney scan over all 4,095 positions.

## Failure budget

The verifier draws 102,400 shots. `δ = 2⁻¹²⁸`. Cost is `R(ε⁺) × Q² × T`, with `T` the mean executed Toffoli-like count and

`R(ε) = ln 2 / (−ln(½ + 2√ε))`.

`ε⁺` is the one-sided Clopper–Pearson bound. Zero failures is not `ε = 0`. On this shot count the bound is `ε⁺ = 8.6606×10⁻⁴` and `R = 1.19126`. One failure moves the bound to `9.1042×10⁻⁴` and `R` to `1.19673`, a **+0.459%** increase. The brief's "+0.45%" is that increase, rounded. Seven failures on the same 102,400 shots give `R = 1.21985`, about **+2.40%**.

Q is squared. A cut from 1,893 to 1,837 qubits, if the competition counted the same qubits Gu counts, would cut the cost by about 5.8% before Toffolis. The Toffoli cut from 5,725,461 to 442,397 is about 12.9×. Together, using Gu's Q and T and seven failures on 102,400 shots, the formula gives about **13.4×** versus the zero-failure reference arithmetic `2.444×10¹³`. That figure is a spreadsheet check. It is not a kickmix measurement.

Gu report 7 wrong signs in 100,000 tests, inside an allowance of 100 wrong signs. Their README also quotes a modelled total failure near `1.4×10⁻⁴` from truncated windows, a one-entry stack, and a second zero pivot. Failing shots still restore the syndrome. They can apply a wrong phase, or, on some stack overflows, free a qubit that is not zero. A nonzero freed qubit is a competition failure as well as a phase failure.

## What Gu claim, and what this competition counts

| Item | Gu et al. | This competition (PRA-171) |
| --- | --- | --- |
| Cost | Executed Toffolis × peak live qubits. A classically controlled gate is priced at the arity it promotes to. Cliffords are free. | `R(ε⁺) × Q² × T`. `T` is the mean executed Toffoli-like count, including cleanup. `Q` is max qubit id + 1, not peak live qubits. |
| Field | `x¹²+x⁷+x⁶+x⁵+x³+x+1` (integer 4331). | Shipped `kickmix.GF2Field(12)` modulus is **4179**, which is `x¹²+x⁶+x⁴+x+1`. Same polynomial as the competition paper. Not Gu's polynomial. |
| Syndrome | `S_i = e(γ^i)`, `γ = x`, index 1..70. | `s_i = Σ e_j α^{(i+1)j}`, registers `S0`..`S69`. Exponents match. Names and basis do not. |
| Phase | Fixed SHA-256 mask. | Fresh classical record `E0`..`E4094` on every shot. |
| Failures | Allowance about `10⁻³`, scored as pass/fail. | Every failure raises `R(ε⁺)`. There is no free allowance. `ε⁺ ≥ 1/16` rejects the task. |
| Builder | `uncompute.Builder` op stream. | kickmix `CircuitBuilder`, file `.kmb`. |

Because Q is squared and ids are not lifetime-tracked, a port that copies Gu's "peak 1,837" into a kickmix circuit can score a higher Q than 1,837. The port has to reuse cleaned ids. Because T is an executed count, a classically controlled Toffoli that does not fire is cheaper than Gu's promoted-arity price. The random record `E` may therefore be cheaper here than Gu's fixed mask, if kickmix drops idle classical controls. PRA-171 did not measure that. Do not assume it.

## Open questions

1. After a kickmix port, what Q does the verifier report? Gu's 1,837 is peak live qubits. The competition number is max id + 1.
2. Do kickmix's classical controls make the per-shot record `E0`..`E4094` cost only the Toffolis that fire? This needs one instrumented stage, not a guess.
3. What failure count minimises `R(ε⁺) × Q² × T` on 102,400 shots once the real Q and T are known? Seven failures is Gu's measurement on their sampler, not an optimum for this cost.
4. Do Gu's truncation windows keep the same failure rate on the competition weight law? Their field and mask differ, so the windows have to be remeasured here.
5. The reference generator's `GF2Field(12)` is modulus 4179. Every Gu constant (multipliers, inverses, the Itoh–Tsujii chain) has to be regenerated for 4179. Confirm the primitive element stays `2` after that change. This run saw `primitive_element = 2` for modulus 4179.
6. A nonzero qubit at `free` fails the competition even when the phase is the only intended output. The port has to prove ancilla cleanup on the failure paths, not only on the common path.
7. Thread 752010 was unanswered on 2026-10-23. This plan does not use a compiled k256 input. If a later shortcut loads such an input, stop. R10 still applies.
