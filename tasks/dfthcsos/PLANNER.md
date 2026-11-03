# Our own full-XOR J=5 planner (PRA-359)

`tasks/dfthcsos/full_xor/plans.json` replays SomeJoint's search. The published notebook does not contain
that search, so any new word table broke the replay. `tasks.dfthcsos.full_xor.planner` is our search: it takes
a delta table (addresses x 5 words) and returns the `Plan` and the cache schedule that
`emitter.build_staged` turns into an exact XOR oracle. It builds no circuit and writes no data file.

```sh
uv run python -m tasks.dfthcsos.full_xor.search_plans --workers 14 --emit-check --out /tmp/pra359/b143.json
uv run python -m tasks.dfthcsos.full_xor.search_plans --requantize 7 --workers 14 --out /tmp/pra359/b7raw.json
uv run python -m tasks.dfthcsos.full_xor.search_plans --requantize 7 --clamp-canonical --workers 14 --out /tmp/pra359/b7clamp.json
```

The rows in `--out` have the layout of `plans.json` (`batch`, `delta_sha256`, `plan`, `schedule`), so
`b143.compile_batch` replays them. `planio.plan_from_dict` now accepts `brot` 7 as well as 8.

## Method

1. **Tensor.** Split the 11 address bits into 4 low and 7 high bits. Each output bit is a polynomial in the
   address. Its monomials that mix low and high bits form `T[l][h][o]`: 15 low monomials `l`, up to 76 high
   monomials `h`, and `F` independent output polynomials `o` (35 for 8-bit words: the two sign bits of a word
   agree, so 5 x 7). Pure-low and pure-high monomials are free corrections on cached wires.
2. **Products.** One Toffoli is one product `(L1+R2)(L2+R1)` with a fanout `f`. Its mixed part is
   `(x1 r1^T + x2 r2^T) (x) f`: a rank-2 matrix times a fanout. A plan is a set of pairs `(X, f)`, `X` a
   2-dim subspace of the low monomials, whose spans `X (x) f` contain the span `S` of the high slices.
   The count of products is the count of pairs.
3. **Blocks.** The low monomials are grouped by the outputs their slices touch (in the coded batches the
   multi-bit monomials touch only 25 or 30 of the 35) and each group is cut into blocks of 3 or 4. A block
   is solved alone. Block sizes 2, 5 and 6 cost more per monomial on these tensors.
4. **One block.** Draw `n0` random pairs `W0`, let `E = S + W0`, and add pairs that lie inside `E` until
   they span it. Then the block costs `dim E / 2` pairs. `x f^T` lies in `E` exactly when `x^T Y f = 0` for
   every `Y` in the annihilator of `E`, which is linear in `f`; `BlockSolver.inside` computes those spaces and
   `complete` picks pairs with two new dimensions each. The search takes the smallest `n0` that completes.
   The threshold is sharp (on a random tensor of that shape, 299 of 300 draws at `n0` = 8 and 0 of 300 at
   `n0` = 7 for a block of 3 over 35 outputs), so restarts below it do not help.
5. **Exact plan.** The slice coefficients `r` come from a Gaussian elimination that tracks combinations. The
   pure corrections are the remaining coefficients; `assemble` raises if any mixed monomial is left, and
   `validation.assert_independent` re-checks the whole truth table from the plan alone.
6. **Cache schedule** (`phasing.py`). `scheduler.make_schedule` appends every pure-low correction at the end,
   so a monomial dropped earlier is computed again (14 low computations per circuit). Pure-low corrections
   are CNOT fanouts that commute with the products, so the phased schedule orders the requirement masks by
   local search, runs the exact retention DP, and puts each correction in a phase that holds its monomial.
   All 15 circuits reach the floor of 11, the committed count.
7. **Width gate** (`planner.py`). `peak_width = selection + 5 brot + high cache + low slots`, the same sum the
   emitter checks. It is enforced at four points before anything is emitted: `precheck_width` (selection and
   words alone must leave a slot), `candidate_blocks` (a block that needs more slots than remain is not
   offered), `schedule_within_width` (the capacity range is cut at the cap), and `check_width` on the
   returned plan. Each raises `WidthGateError` and returns no plan.

## Results

Published (8,143,60) factor (SHA-256 `aef36d39...f6395b`), 15 circuits, one pass:

| table | products | low | Toffolis / pass | peak qubits | note |
|---|---:|---:|---:|---:|---|
| committed `plans.json` (SomeJoint) | 3,018 | 165 | 4,218 | 128 | replayed |
| `paired_anf.make_plan` rank split | 3,960 (3,722 with `share_odd`) | | | | the notebook's earlier planner; not emitted |
| **this planner, 8-bit** | **3,127** | **165** | **4,327** | **128** | exact; +109 over committed |
| this planner, 7-bit half-up, as is | 3,439 | 165 | 4,639 | 123 | 1,860 words leave the sign range; the emitter refuses |
| this planner, 7-bit half-up, one-step clamp | 2,995 | 165 | 4,195 | 122 | measurement only, not shippable |

All 15 circuits of the 8-bit and clamped 7-bit rows were built with `build_staged`, simulated on dirty
targets (two passes, four copies of the 1,220 addresses) and read back through the official
`recover_words_from_circuits`, which returns the submitted words and counts 8,654 / 8,390 Toffolis over both
passes. The search takes 5 s on 14 workers.

## The gap to 4,218

The planner is 109 Toffolis (2.6 %) above the committed plans. The products are the whole gap; the low
computations are equal. The reason is structural, not a bug:

* For a generic tensor a block of `ell` coordinates over `F` outputs cannot be spanned by pairs once the
  annihilator of `E` has more than about `F/2` dimensions per coordinate, which gives 46 pairs for 3
  coordinates, 62 for 4 and 79 for 5 at `F` = 35. Five blocks of 3 cost 230 products; the committed plan
  has 225.
* The committed blocks of 5 cost 75 pairs, not 79. Their annihilator `Q` has 25 dimensions; inside it
  there are sub-spaces of 2 to 6 dimensions supported on 3 of the 5 coordinates, and the pairs on two unit
  vectors have `N_X` spaces of 7 to 12 dimensions (a random annihilator of that size gives about 5). We do
  not know how they found it.

## Negative results

* **Relation design.** Choose the annihilator `Q` as relations of the slices on 3 coordinates (4 for 25
  outputs) and hill-climb which relations. By the loose measure (the span of all pairs inside `E`) it
  reaches `E` of 117 dimensions for 4 coordinates (`c` = 23) and 150 for 5 (`c` = 25, the committed
  size), but the pairs inside `E` overlap so much that covering `E` takes 82 pairs, not 59. Scored by the
  pairs that really add two dimensions each, the climb reaches `c` = 18 and 61 pairs against 62 from the
  first-phase search. Run time went from 5 s to 170 s for 14 products fewer. It was not kept.
* **Hill-climbing the first phase** (3 coordinates, `n0` = 7): the deficiency falls from 19 to 9 and stalls.
* **Coordinate-pair pairs only** (X = two unit vectors) never complete a block of 6, and weight-2 subspaces
  add no pairs to a designed `E` over 15 coordinates (random tensors).
* **Block sizes** 2, 5 and 6 cost more per monomial than 3 or 4 on batches 0, 4 and 5 (measured per
  group: 17.5, 15.3, 15.5, 15.8, 16.0 pairs per monomial for 35 outputs at sizes 2 to 6).
* **Low-bit split 3** instead of 4 would cache 144 high monomials: 11 + 40 + 144 = 195 qubits. Not run.
* **brot 7 loses the coded batches.** At 7 bits (clamped) no batch has a reduced output set, so all 15
  circuits cost 199 to 200 products; the coded 8-bit batches cost 187 to 210.

## Open leads

* The generic limit above is the cost of independent blocks. Overlapping blocks that split a coordinate's
  slice between them could share first-phase pairs; untested.
* The committed annihilators are structured. A search that builds `Q` from relations *and* checks the
  pairing efficiency incrementally (rather than the span) might reach 75 for blocks of 5.
* Half-up 7-bit words leave the sign range at one value (63 -> 32). A gauge that moves it back without
  changing the angle needs the projector-preserving fold of `paired_anf.signed_gauge`; that is the refit's
  decision (PRA-314), not the planner's.

## Not checked

The official score of any of these circuits, G5 byte-for-byte rebuild of a planner plan (no plan file is
committed here; `b143` still replays `plans.json`), the OpenEvolve loop (`search/run.py --provider local`
needs a gateway key that this seat does not have), and any brot-7 refit (PRA-314) other than the naive
half-up image of the published words.
