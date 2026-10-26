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
| `ledger/manifests/submissions/submission-NNN.json` | One manifest per Kaggle submission; never rewritten, except that a gate re-run ordered by a decision appends a gate record with `uv run python -m ledger.gates.runner rerun --generator-commit <sha>` (PRA-211 re-ran G5 on submission-001, D-PRA211-02 and D-PRA211-05) | yes |
| `ledger/manifests/reservations/<day>-slot<k>.json` | A pending submission-slot reservation (PRA-211); renamed `…-<id>.recorded.json` or `…-<id>.failed.json` once resolved | resolved ones yes; a pending one only if it outlives the session |
| `ledger/evidence/<candidate_id>/<gate>.json` | Evidence record: verifier summaries, log hashes, commands | yes |
| `ledger/manifests/index.csv` | Derived index, one row per manifest, rewritten from the manifests by `runner new`, every submission and `python -m ledger.registers index` (PRA-210) | **no** (derived) |
| `ledger/manifests/index-legacy.csv` | The rows appended before PRA-210, frozen byte for byte | yes |
| `ledger/queue/<candidate_id>.json` | Queue pointer for a G5-passed zip | yes |
| `ledger/queue/<candidate_id>.zip`, `.kmb`, `.npz`, data | Binaries | **no** (SHA-256 only) |
| `ledger/standing.yaml` | Our leaderboard standing and one note per submission, for the status page (PRA-241) | yes |
| `ledger/tracks.yaml` | The four programme tracks and their verified numbers, for the status page (PRA-252) | yes |

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
| `provenance.licence` | str | `Apache-2.0`, `CC-BY-4.0`, `own` (Praxen code under the repo's Apache-2.0), `no-licence` (the author attached none) or `reference-only` |
| `provenance.parent_url` | str \| null | Required unless `own` |
| `provenance.notes` | str | Free text |

The licence is a record for the end-of-hackathon credits and licensure pass; G5 does not gate on it (D-PRA273-01). The one exception: `reference-only` parents (for example the k256.dev dqi artifact) may inform work, and G5 refuses to ship them (AGENTS.md R10).

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
| G5 | No reference-only parent; clean 40-hex generator commit; zip holds exactly the manifest's files and is their deterministic build; clean `git worktree` at `generator_commit` regenerates every file byte for byte with `VQCC_DATA` pointing at a staging directory that holds only the config's declared, SHA-256-pinned `inputs`; an output byte-identical to a declared input is recorded as `copied`: a copied circuit fails and a circuit can never be a declared input, a copied non-circuit input (the declared dfthcsos factorization) is accepted (R10, PRA-211, D-PRA211-05) | no | ledger |

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
  directory, `{python}` this interpreter. Outputs use the manifest's relative paths. The generator's `VQCC_DATA` is a
  staging directory holding only the config's `inputs:` (`{task: [{path, sha256}]}`, paths relative to the package
  root), copied there after a hash check; nothing else from the competition package is visible. A circuit (`.kmb`) can
  never be a declared input. The rebuild record lists per task `identical` (every file matches the manifest) and
  `copied` (outputs whose bytes equal a declared input), and `copied_inputs` overall. A copied circuit is a FAIL even
  when every byte matches the manifest; a copied non-circuit input is accepted and stays visible in the record
  (Chris's ruling on PRA-211; D-PRA211-05). `uv run python -m ledger.gates.runner rerun --generator-commit <sha>` repeats G5 on a recorded
  manifest with the generators at that commit and appends the record; the manifest's `generator_commit` is unchanged.

## Submissions (R6)

Only john-wick submits. Hard cap **3 per UTC day**, enforced *before* the upload (PRA-211, D-PRA211-03). The only
sanctioned upload path is `ledger.scorecard.submit`, or its two halves `reserve` and `record`:

1. `uv run python -m ledger.scorecard --check-slot` — exits 1 if today's cap is used up, counting recorded submissions
   and pending reservations.
2. `uv run python -m ledger.scorecard submit --candidate <manifest> --zip ledger/queue/<id>.zip --upload-command '<cmd>'`
   — `reserve_slot` first: with three slots already recorded or reserved it refuses, writes nothing and the upload
   command never runs. Otherwise it creates `ledger/manifests/reservations/<day>-slot<k>.json` exclusively (a hard-link
   create, so two racing reservers cannot share a slot), runs the command with the zip path appended, takes the Kaggle
   submission id from its last stdout line and records it.
   For an upload made elsewhere (the Composio sandbox route of D-PRA178-03): `reserve --candidate <manifest>` before
   the upload, then `record --candidate <manifest> --kaggle-id <id> --reservation <file>` after it.
3. `record_submission(candidate, kaggle_submission_id, reservation=…)` writes `submission-NNN.json` (exclusive create),
   marks the reservation `.recorded.json` and rewrites the derived index. It refuses a candidate that fails the shipping
   rule and a duplicate Kaggle id. Called without a reservation it also refuses when the day is full.
4. An upload that raised or returned no id leaves its reservation **pending**, with the error written into it. A pending
   reservation keeps counting against the cap until it is reconciled: `record … --reservation` if Kaggle did receive
   the submission, or `reconcile --reservation <file> --failed --reason '<why no submission exists>'`, which renames it
   `.failed.json`. Uncertain attempts are never silently dropped.

`DAILY_CAP` is a constant and no function takes a cap parameter. The day boundary is 00:00 UTC, taken from the
reservation or record time; naive timestamps are rejected. Known limit: an upload made outside `submit`/`reserve` is
invisible to the ledger. AGENTS.md forbids that path; the ledger cannot see it.

`uv run python -m ledger.scorecard` prints the table: ratio per task, geometric mean, measured flag, last gate,
best measured ratio per task, submissions per UTC day and pending reservations.

## Status page inputs (`ledger/status_page.py`)

Vercel builds the public status page from the committed repo on every push (`vercel.json`). Our own numbers come from
the manifests (per-task ratios, gate states) and from `ledger/evidence/<submission>/kaggle-public-score.json`; the
two files below hold what the manifests cannot. Both are read by the status page and nothing else, and a missing
field or a value of the wrong type fails the build rather than showing a wrong page. Their text is shown to readers
who know nothing about the project: plain English, no ticket ids, no ledger words.

`ledger/standing.yaml` (`schema: 1`), updated by john-wick with every leaderboard snapshot:

| Field | Type | Meaning |
| --- | --- | --- |
| `leaderboard.read_at_utc` | ISO 8601 text | When the leaderboard was read |
| `leaderboard.our_score` | number | Our public score at that read; the page says the rank is stale if a newer score differs |
| `leaderboard.rank`, `leaderboard.teams` | integer | Our rank and the number of teams |
| `leaderboard.leader_score` | number | The leader's public score |
| `leaderboard.prize_line_place`, `leaderboard.prize_line_score` | integer, number | The last paid place and its score |
| `best_public_per_task.read_at_utc` | ISO 8601 text | When the per-task figures were read |
| `best_public_per_task.<task>` | number | Best per-task ratio stated in a public notebook, for each of `invsqrt`, `dqi`, `dfthcsos` |
| `submission_notes.<submission_id>` | text | One line per submission; a test fails if a submission manifest has no note |
| `notebook_url` | https URL or `null` | Our public Kaggle notebook; `null` hides the link |

`ledger/tracks.yaml` (`schema: 1`), updated by the engineers and john-wick the day a number is verified:

| Field | Type | Meaning |
| --- | --- | --- |
| `tracks[]` | non-empty list | One entry per programme track, shown in file order |
| `tracks[].id` | text | Short unique id (`A` to `D`) |
| `tracks[].name`, `tracks[].aim` | text | The track's name and one sentence on what it is for |
| `tracks[].updated_at_utc` | ISO 8601 text | When the track's figures were last updated |
| `tracks[].figures[]` | list | The track's numbers; may be empty |
| `figures[].label` | text | What the number is |
| `figures[].state` | `shipped`, `verified` or `in work` | `shipped`: in our latest upload; `verified`: passed Google's verifier, not uploaded; `in work`: no measured number yet |
| `figures[].value` | positive number, or absent | The per-circuit score ratio (reference cost / our cost) measured with Google's verifier, never a model. Required for `shipped` and `verified`, forbidden for `in work` |
| `figures[].note` | text, optional | One plain-English line of context |

A test checks that every `shipped` value equals a per-task ratio of the latest submission manifest (two decimals),
so a new upload that changes a circuit's score must come with a `tracks.yaml` update. Keep a blank line between tracks
so that two edits to different tracks never touch neighbouring lines and squash-merge cleanly.

## Health and reproducibility

`uv run python -m ledger.benchmark_health` runs the self-checks (manifest round trip, cap logic, gate config,
examples). With `--manifest <candidate.json>` it also rebuilds the candidate in a clean worktree and compares hashes.
