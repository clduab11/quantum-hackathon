# dfthcsos search: discovery notes

Append-only. One dated entry per finding; never edit or delete an earlier entry (supersede it with a new
one). Every negative states the assumption it rests on. search/run.py pastes this file into the system
prompt of every LLM call, so keep entries short and factual. Promoted elites (search/promote.py) print a
ready-made entry; paste it here.

## Fixed facts (verifier, 2026-10-25)

- Score: cost = lambda_eff x T_total x Q_total; reference cost 3,355,599,588.3155365 (ratio 1.0).
  Equivalent: ratio = 68,063,010 / (T_total x Q_total) while the circuits load the 12-bit words.
- T_total = ANGLE Toffoli-like gates executed per shot over the forward AND reverse pass + 13,757
  (outer 846 + inner 9,461 + Givens 3,450 at brot 12). Q_total = 634 + J x brot while the ANGLE circuits
  stay under the 128-qubit cap (inner-prep temporaries, 544, dominate the shared workspace).
- Reference family: ordinary unary-iteration QROM, brot 12, J 8, 10 circuits of 119 qubits (12 selection,
  96 word, 11 ancilla): ANGLE T 79,480 (both passes, 3,974 per circuit per pass), T_total 93,237, Q_total 730.
- Hard limits: 12 selection + J x brot word qubits + ancillas <= 128 per circuit, so J <= 9 at brot 12
  (J = 9 leaves 8 ancillas). K = ceil(75 / J) circuits. Words per address must be identical on every shot.
- Full verification takes 34 s on this machine (254,464 shots); 2 shots per address take 10 s.

## Verified results

| date | layout | T_total | Q_total | ratio | source |
|---|---|---:|---:|---:|---|
| 2026-10-25 | reference: ordinary QROM, J 8, brot 12 | 93,237 | 730 | 1.000000 | seed, full verifier |
| 2026-10-25 | ANF loader (build_qrom), J 9, bank 0, scratch 8, pebble 4 | 85,109 | 742 | 1.077784 | PRA-232 (docs/reports/pra232-dfthcsos.md) |
| 2026-10-25 | ANF loader, J 9, bank 0, scratch 6, pebble 5 | 85,595 | 742 | 1.071665 | PRA-232 |
| 2026-10-25 | ANF loader, J 4, bank 1 (two-address), scratch 6, pebble 5 | 93,965 | 682 | 1.062088 | PRA-232 |
| 2026-10-25 | ANF loader, J 2, bank 2 (four-address), scratch 6, pebble 4 | 97,669 | 658 | 1.059079 | PRA-232 |
| 2026-10-25 | ANF loader, J 2, bank 2, scratch 5, pebble 4 | 98,049 | 658 | 1.054975 | PRA-232 |
| 2026-10-25 | ANF loader, J 4, bank 1, scratch 20, pebble 5 (search run codex-smoke-01, iteration 17) | 93,699 | 682 | 1.065104 | search loop, full verifier; promote.py rebuild |

## Negatives (with the assumption each rests on)

- 2026-10-25 brot 11 or 10 with Google's packaged factor: error_1 76.9 / 133.5 mHa > 20 mHa, rejected
  (PRA-232). Assumes the words are Google's baseline requantised by nearest-even rounding; a refitted
  factor could behave differently, but no such declared factor exists in this repository.
- 2026-10-25 bank 1 at J 5 and bank 2 at J 3 (brot 12) exceed the 128-qubit cap in build_qrom (PRA-232).
  Assumes build_qrom's bank-qubit accounting (one qubit per nonzero difference column).
- 2026-10-25 Banked lookups cut T per circuit but force smaller J, so more circuits and the extra bank
  erasure eat the gain: the best banked point (1.062) loses to direct J 9 (1.078). Assumes brot 12 and the
  cap; a loader whose per-circuit T falls faster than K grows would change this.
- 2026-10-25 The reference J 8 family cannot be improved by changing scratch/pebble alone: with ordinary
  QROM those knobs do not exist, and build_qrom at J 8 direct is dominated by J 9.
- 2026-10-25 Smoke run codex-smoke-01 (60 Codex iterations, 58 evaluations, 54 fully verified): every
  verified program was a build_qrom knob setting. 50 reproduced J 9 direct (1.077784); the only new point
  was J 4 / bank 1 / scratch 20 (1.065104: 14 extra traversal wires save 266 Toffolis over scratch 6, still
  short of J 9). Nothing above 1.077784 appeared. Assumes the model only recombines the two shipped
  loaders; a new loader written against the kickmix API (SELECT-SWAP, structure-aware loading) is untested.

## Open directions (untested; the arithmetic is the hypothesis)

- SELECT-SWAP / QROAM: at J 4 (Q 682, 19 circuits) the cap leaves 128 - 12 - 48 = 68 spare qubits. Beating
  1.0778 needs T_total < 92,600, i.e. under 2,075 Toffolis per circuit per pass against ~3,970 for the
  unary-iteration loader. A 2-way or 4-way swap network over the address space could get there if the
  swap cost (CSWAP counts as Toffoli-like) stays small. Untested.
- Exploit structure in the XOR-difference tables: rows whose delta is zero need no load; repeated rows can
  share a control; the 76 one-body rows (addresses 0..75) are eigenvectors and may be far more regular than
  the 3,900 two-body rows. Nobody has measured the zero/repeat statistics of delta_k yet.
- Measurement-based uncomputation of the whole load (compute with ANDs, erase with HMR + Clifford phase fix)
  halves the reverse-pass Toffolis only if the reverse circuit is counted separately; the verifier applies
  the SAME circuit in reverse, so savings must come inside one circuit.
- kickmix's built-in `init_lookup` / `del_lookup` / `unary_iteration` primitives have unmeasured cost here.
