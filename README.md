# quantum-hackathon

Praxen's entry to the Kaggle competition **Google Quantum AI – Verifiable Quantum Circuit Compilation**
(`google-verifiable-quantum-circuit-compilation`, final deadline 2027-01-20).

The competition asks for three `kickmix` circuits (invsqrt, dqi, dfthcsos), each fuzz-verified by Google's
simulator. The score is the geometric mean of `baseline_cost / cost` across the three tasks, so the reference scores 1.0.
Cost is a logical-resource product per task (qubits × non-Clifford count, with task-specific factors). Any failing
task rejects the whole submission.

This repository is public from day one. A full write-up follows after the final deadline (Jan 20).

## Layout

```
tasks/invsqrt/     generator, verifier wrapper and candidates for the invsqrt task
tasks/dqi/         generator, verifier wrapper and candidates for the dqi task
tasks/dfthcsos/    generator, verifier wrapper and candidates for the dfthcsos task
ledger/            submission ledger: run manifests, evidence, scorecard, gates G0–G5
harness/           local verifier wrappers and scoring
search/            evaluator-driven OpenEvolve search loop for dfthcsos (search/README.md); hand-offs, never shipping
notebooks/         public Kaggle notebook source
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
