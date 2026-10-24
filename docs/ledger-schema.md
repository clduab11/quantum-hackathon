# Ledger manifest schema (v1)

The ledger is the proof layer. Every candidate circuit set, every verifier run and every Kaggle submission leaves a
manifest that a stranger can re-check: re-hash the files, re-run the generator at `generator_commit` in a clean
worktree, and re-run the verifiers whose SHA-256 is recorded.

Code: `ledger/run_manifest.py` (record, reader, writer), `ledger/evidence.py`, `ledger/scorecard.py`,
`ledger/benchmark_health.py`, `ledger/archive.py`, `ledger/gates/`. `run_manifest` and `benchmark_health` are ported
from qrc-thresher's `proof/` layer (schema v1.1, Apache-2.0); the rest is new in the same pattern.

Sample: [`ledger/examples/reference-submission.json`](../ledger/examples/reference-submission.json), the reference
submission, rebuilt by `ledger/examples/make_reference_manifest.py`.

## Where things live

| Path | Content | Committed |
| --- | --- | --- |
| `ledger/manifests/candidates/<candidate_id>.json` | One manifest per candidate; rewritten after each gate | yes |
| `ledger/manifests/submissions/submission-NNN.json` | One manifest per Kaggle submission; never rewritten | yes |
| `ledger/evidence/<candidate_id>/<gate>.json` | Evidence record: verifier summaries, log hashes, commands | yes |
| `ledger/manifests/index.csv` | Append-only index: one row per new candidate (`runner new`) and per submission | yes |
| `ledger/queue/<candidate_id>.json` | Queue pointer for a G5-passed zip | yes |
| `ledger/queue/<candidate_id>.zip`, `.kmb`, `.npz`, data | Binaries | **no** (SHA-256 only) |

Manifests are JSON with sorted keys, written atomically (fsynced `.tmp` file, then rename). `runner new` and every
`submission-NNN.json` are created exclusively: an existing file is never overwritten. Derived values (`ratio`,
`geometric_mean`) are written for human readers and **recomputed on load**, so a hand-edited ratio cannot drift from
its cost and baseline.

## Manifest fields

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | str | `"1"` |
| `manifest_id` | str | UUID4 of this record |
| `kind` | str | `candidate` or `submission` |
| `candidate_id` | str | Candidate name, or `submission-NNN` for submissions |
| `parent_candidate_id` | str \| null | Lineage parent; G4 must beat it |
| `source_candidate_id` | str \| null | Submissions only: the candidate that was submitted |
| `timestamp_utc` | str | ISO-8601 with timezone |
| `operator` | str | Paperclip agent id (`PAPERCLIP_AGENT_ID`) or local user |
| `generator_commit` | str | `git rev-parse HEAD` of the generator repo, `-dirty` appended if the worktree was dirty |
| `git_branch` | str | Branch at creation |
| `kickmix_build_id` | str \| null | `sha256:<hex>` of the kickmix binary used. The shipped `kickmix.so` reports only `__version__ == '0.1'` and its source commit is unverified (PRA-171 §2), so its hash is its identity |
| `qualtran_pin` | str \| null | Qualtran commit, if known. The starter notebook pins `c58703d…`; that does not prove the `.so` was built from it |
| `salt_label` | str \| null | Label of the **public local** salt used for verification. Kaggle's salts are secret and never recorded |
| `zip_sha256` | str \| null | SHA-256 of the candidate zip, built with `ledger.archive.build_zip` (deterministic) |
| `tasks` | map | `invsqrt`, `dqi`, `dfthcsos` → task record (below) |
| `geometric_mean` | float \| null | Derived: geometric mean of the three task ratios; null unless all three exist |
| `gates` | list | Gate records (below), in the order they ran |
| `kaggle_submission_id` | str \| null | Kaggle's id; required on `submission` manifests |
| `submitted_at_utc` | str \| null | Submission time (UTC); the day it counts against the cap |
| `python_version`, `platform`, `cli_command` | str | Run provenance |
| `notes` | str | Free text |

### Task record

| Field | Type | Meaning |
| --- | --- | --- |
| `task` | str | `invsqrt`, `dqi` or `dfthcsos` |
| `files` | map | Relative path in the zip → SHA-256 (each `.kmb`/`.kmx`, `submission.npz`). The `.kmb` hash is also the verifier's seed input |
| `verifier_sha256` | str \| null | SHA-256 of the verifier file that produced the numbers |
| `shots` | int \| null | Verified shots: 200,540,928 (invsqrt), 102,400 (dqi), 254,464 (dfthcsos) at full count |
| `failures` | int \| null | invsqrt: always 0 on PASS (any failure rejects). dqi: `value_errors + phase_errors`. dfthcsos: null (accuracy gates, not shot failures) |
| `eps_plus` | float \| null | dqi: one-sided Clopper–Pearson upper bound at δ = 2⁻¹²⁸ (`effective_error_rate`); must be < 1/16 |
| `num_qubits` | int \| null | Q as the verifier counts it (see accounting below) |
| `toffoli_count` | float \| null | **Mean executed Toffoli-like operations per shot** (not the static count) |
| `t_count` | float \| null | invsqrt: directly counted base T-like gates per shot (excludes synthesized rotations) |
| `rotation_count` | float \| null | invsqrt: mean non-Clifford `Z_POW` rotations per shot |
| `cost` | float \| null | The verifier's `score` |
| `baseline_cost` | float \| null | Reference cost **under the same salt label** |
| `ratio` | float \| null | Derived: `baseline_cost / cost` |
| `measured` | bool | True only when the numbers come from a captured verifier run (`ledger.evidence`). Unmeasured numbers never count as best-per-task or archive |
| `metrics` | map | Task-specific extras: invsqrt `toffoli_equivalent`, `rotation_eps`, `worst_error_over_tolerance`; dqi `repetition_factor`, `empirical_error_rate`; dfthcsos `lambda_eff`, `Lambda`, `E_gap`, `error_1`, `error_2`, `angles_qubits`, `persistent_qubits`, `temporary_qubits` |
| `evidence` | list | SHA-256 of each evidence record that fed this task |
| `provenance.licence` | str | `Apache-2.0`, `CC-BY-4.0`, `own` (Praxen code under the repo's Apache-2.0) or `reference-only` |
| `provenance.parent_url` | str \| null | Required unless `own` |
| `provenance.notes` | str | Free text |

`reference-only` parents (for example the k256.dev dqi artifact) may inform work; G5 refuses to ship them (R10).

### Gate record

| Field | Meaning |
| --- | --- |
| `gate` | `G0` … `G5` |
| `status` | `PASS`, `FAIL` or `WAIVED` |
| `timestamp_utc` | When it ran |
| `zip_sha256` | The zip it ran on. A gate counts only if this equals the manifest's current `zip_sha256` |
| `reason` | Failure text, or the waiver's written reason |
| `evidence_sha256` | Evidence record written by the gate (G3) |
| `details` | JSON-safe detail from the check (per-task hook results, rebuild diffs, archive comparison) |

## Accounting (from the PRA-171 inventory, quoting the verifier source)

- **Toffolis are per executed shot.** All three verifiers divide the simulator's executed count by shots. A
  classically conditioned fixup pays only on the shots where it runs. `max_toffoli_count` (static) is kept in
  `metrics` for reference.
- **Q for invsqrt and dqi** is the largest referenced qubit id + 1, including register declarations; there is no
  lifetime tracking. Sparse ids cost space; reusing cleaned ids can reduce Q.
- **Q for dfthcsos** is `persistent + max(temporary)` over the ANGLE circuits and the heuristic stage model, not one
  global max id.
- **Costs:** invsqrt `Q × (Toffoli + T_total/4)` with rotations at `0.56·log2(1/ε) + 5.3` T; dqi
  `R(ε⁺) × Q² × Toffoli` with `R(ε) = ln2 / −ln(½ + 2√ε)`; dfthcsos `λ_eff × T_total × Q_total` with
  `λ_eff = √(E_gap(2Λ − E_gap))`, rejected unless error ≤ 20 mHa, Λ > 49.0, E_gap > 3.914898 Ha.
- **Score:** geometric mean of the three `baseline_cost / cost`. Any failing task rejects the whole zip.

## Gates (`configs/gates/default.yaml`, run by `ledger/gates/runner.py`)

| Gate | Check | Waivable | Owner of the hook |
| --- | --- | --- | --- |
| G0 | Pre-flight: metric-only file checks, no simulation (`ledger.gates.g0_preflight:preflight`) | no | P0-4 |
| G1 | Smoke on small instances (`tasks.<task>.gates:g1_smoke`) | yes, with reason | generator owner |
| G2 | Fast proxy: invsqrt exhaustive numpy mirror; dqi subsampled shots; dfthcsos `heuristic_costs` + error/Λ/E_gap (`tasks.<task>.gates:g2_proxy`) | yes, with reason | generator owner |
| G3 | Full local verifier at full shots (`harness.score_local:score_submission`); folds results into the manifest as evidence | no | P0-4 |
| G4 | Measured geometric mean strictly beats the parent and the best measured archived candidate | yes, with reason | ledger |
| G5 | Provenance shippable; clean 40-hex generator commit; zip holds exactly the manifest's files and is their deterministic build; clean `git worktree` at `generator_commit` regenerates every file byte for byte | no | ledger |

Rules enforced by the runner:

- Order is fixed. A gate runs only when every earlier gate is cleared **on the same zip SHA-256**: a candidate cannot
  reach G3 without G2 passing, and a changed zip starts again from G0.
- A hook that raises or is not installed is a **FAIL**, never a skip.
- A gate's results are folded into the manifest all or nothing: a G3 that fails part-way leaves no task `measured`.
- An unsafe, corrupt, encrypted or unsupported zip is a G0 FAIL.
- **Shipping rule** (`RunManifest.shipping_problems`, used by the queue and by `record_submission`): every gate G0–G5
  cleared on the current zip, G0/G3/G5 real PASS records (never WAIVED, even in a hand-edited manifest), and every
  task measured. Only zips that meet it enter `ledger/queue/`.

Hook contracts:

- G0 `preflight(submission_dir)`: raise (or return `{"status": "FAIL: …"}`) to reject; any other return is a pass.
- G1/G2 `fn(submission_dir) -> {"status": "PASS" | "FAIL: …", …}`.
- G3 `score_submission(submission_dir, *, salt_label, shot_divisor=1) -> {"status", "tasks": {task: <verifier JSON
  summary, unchanged>}, "baseline_costs": {task: float}, "verifier_hashes": {task: sha256}, "kickmix_build_id",
  "qualtran_pin", "commands"}`.
- G5 generator command per task (`generators:` in the config), run from the worktree root; `{out}` is an empty output
  directory, `{python}` this interpreter. Outputs use the manifest's relative paths.

## Submissions (R6)

Only john-wick submits. Hard cap **3 per UTC day**. Procedure:

1. `uv run python -m ledger.scorecard --check-slot` — exits 1 if today's cap is used up.
2. Submit the queued zip (`ledger/queue/<candidate_id>.zip`).
3. `ledger.scorecard.record_submission(candidate, kaggle_submission_id)` writes `submission-NNN.json` and its index
   row. It refuses a fourth submission on the same UTC day, a candidate that fails the shipping rule, and a duplicate
   Kaggle id.

Known limit: the ledger cannot stop an upload made without step 1, and it does not lock across processes (the
exclusive create makes a racing second writer fail rather than overwrite). Only john-wick submits, one at a time.

`uv run python -m ledger.scorecard` prints the table: ratio per task, geometric mean, measured flag, last gate,
best measured ratio per task, and submissions per UTC day.

## Health and reproducibility

`uv run python -m ledger.benchmark_health` runs the self-checks (manifest round trip, cap logic, gate config,
examples). With `--manifest <candidate.json>` it also rebuilds the candidate in a clean worktree and compares hashes.
