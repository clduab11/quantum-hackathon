# quantum-hackathon

Praxen's entry to the Kaggle competition **Google Quantum AI – Verifiable Quantum Circuit Compilation**
(`google-verifiable-quantum-circuit-compilation`, final deadline 2027-01-20).

The competition asks for three `kickmix` circuits (invsqrt, dqi, dfthcsos), each fuzz-verified by Google's
simulator. The score is the geometric mean of `baseline_cost / cost` across the three tasks, so the reference scores 1.0.
Cost is a logical-resource product per task (qubits × non-Clifford count, with task-specific factors). Any failing
task rejects the whole submission.

This repository is public from day one. A full write-up follows after the final deadline (Jan 20).

## The competition in plain English

A short field guide; the full, sourced version is [docs/field-guide.md](docs/field-guide.md).

- **It is a compiler contest with an executable verifier, not a prediction contest.** Google's `kickmix`
  simulator runs each circuit on classical inputs, checks outputs, clean ancillas and phase, prices it, and
  divides the reference cost by ours. Score = geometric mean of the three ratios; the reference scores 1.0.
- **Cost per task:** `invsqrt` Q × (Toffoli + T/4), rotations priced in T; `dqi` R(ε⁺) × Q² × Toffoli with
  R(ε) = ln 2 / (−ln(½ + 2√ε)), so qubits count twice; `dfthcsos` λ_eff × Toffoli × Q with
  λ_eff = √(E_gap(2Λ − E_gap)), charged over the whole block encoding, not only the submitted ANGLE circuits.
- **Hard walls:** one failing task rejects the zip. `invsqrt` allows zero failures over 200,540,928 shots;
  `dqi` prices failures through ε⁺ (102,400 shots); `dfthcsos` is rejected above 20 mHa Hamiltonian error, at
  Λ ≤ 49.0 or E_gap ≤ 3.914898 Ha, and any ANGLE circuit wider than 128 qubits is rejected.
- **Verification is salted** (Fiat–Shamir hash of the submission), so seed or nonce grinding is wasted compute
  and banned here. Official scoring takes about 45 minutes; we upload at most 3 times per UTC day.
- **Strategy follows from the metric:** optimise percentage reductions (halving one task ≈ cutting all three
  by 20.6 %), attack peak qubit count first on `dqi`, and treat the chemistry factorisation, Givens tree and
  QROM layout as one objective because a local circuit win can raise λ_eff.
- **Calendar (23:59 UTC):** 2026-11-20 Mid-Competition Milestone Prize (public notebook required);
  2027-01-04 Longest Leader window closes; 2027-01-13 entry and team-merger deadline; 2027-01-20 final
  submission. Prizes: $150,000 in total, places 1–6 plus $10k milestone, $10k longest leader and three $10k
  single-task prizes, all under the same licensing and reproducibility duties.
- **Where we stand (2026-11-02):** submission-011 measures 19.21 locally at the fixed salt (invsqrt 13.24× at
  Q 84, dqi 54.73× at Q 889, dfthcsos 9.78× at Q 430); latest recorded public score 18.39393 (submission-010),
  rank 848 of 1,501; the last paid place scores 24.74. Reaching it needs the product of the three ratios to grow
  about 2.14×, more than matching the best public invsqrt (20.06×) alone would give (≈ 22.1).

## Layout

```
tasks/invsqrt/     generator, verifier wrapper and candidates for the invsqrt task
tasks/dqi/         generator, verifier wrapper and candidates for the dqi task
tasks/dfthcsos/    generator, verifier wrapper and candidates for the dfthcsos task
ledger/            submission ledger: run manifests, evidence, scorecard, gates G0–G5
harness/           local verifier wrappers and scoring
search/            evaluator-driven OpenEvolve search loop for dfthcsos (search/README.md); hand-offs, never shipping
notebooks/         public Kaggle notebook source
docs/field-guide.md  plain-English field guide: metric, hard constraints, verification, calendar, standing
docs/DECISIONS.md  decision and negative-results register (closed rows; new rows in docs/decisions/)
docs/decisions/    one file per new decision (python -m ledger.registers decisions prints all)
notices/           third-party notices, one file per task area (part of NOTICE)
scripts/merge_gate.py  merge-order gate: squash every open PR in every order (see AGENTS.md)
docs/handoffs/     hand-off notes between work sessions
docs/ledger-schema.md  ledger manifest schema
tests/             pytest suite
```

Circuit binaries (`.kmb`), competition data and zips are never committed. Their SHA-256 hashes go in the ledger.

## Running the tests

Requires [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run pytest
```

## Rules for contributors and agents

See [AGENTS.md](AGENTS.md).

## Licence

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
