# PRA-293 evidence: fused DQI decoder on submission-008's bundle

> **Superseded first run.** #62 merged into `main` while this ran. On the board's instruction (PRA-293 comment
> `af27be22`, 2026-10-27 17:23 UTC), the candidate that ships in this pull request is `pra293-fused-invsqrt`: #62's
> `pra281-invsqrt-port` with only `dqi.kmb` changed to the same fused bytes. See `../pra293-fused-invsqrt/`. This
> run's manifest and queue pointer were removed from the tree, following "one candidate, one pull request" and #62's
> handling of its PRA-250-based run. They remain in the published commit `2b91cee15463456e1c0e1637dbccdc2edb5bd434`
> (`ledger/manifests/candidates/pra293-fused.json`, `ledger/queue/pra293-fused.json`). The records below are kept as
> evidence for the fused dqi bytes, the G5 rebuild of `tasks/dqi/generate_fused.py` and the rollback to submission-008.

Candidate `pra293-fused`: submission-008 (`pra280-rustad`, zip `8e291840…8f21`) with **only `dqi.kmb` changed**, to
SomeJoint's fused confluent decoder built from the source vendored under `tasks/dqi/fused/` (see its
`PROVENANCE.md`). invsqrt is submission-008's file (13.165×); #62's 13.238× invsqrt was not on `main` when this branch
was cut from `33c8f82`.

## Result

| | submission-008 | pra293-fused |
|---|---:|---:|
| dqi.kmb | `1a1c60ae…8f48` (Schur) | `7beea291…55f6` (fused) |
| dqi Q / mean Toffolis | 892 / 535,327.78 | 889 / 474,307.73 |
| dqi value / phase errors (102,400 shots) | 3 / 0 | 0 / 0 |
| dqi R | 1.20558 | 1.19126 |
| dqi ratio | 47.5932 | **54.7295** |
| invsqrt ratio | 13.1648 | 13.1648 |
| chemistry ratio | 7.6793 | 7.6793 |
| local GM (salt `PRA171_LOCAL_PUBLIC_FIXED_SALT_0001`) | 16.8821 | **17.6869** (+4.77 %) |

Zip `/home/cld-main/work/vqcc-data/pra293-fused/pra293-fused.zip`, SHA-256
`7a6489cd7504ad937ddada926c017b8fc70825d433082c83902993973125eba0`, 31,969,333 bytes (not committed). One fixed salt;
no salt or seed search.

## Gates

`OPENBLAS_NUM_THREADS=1 PYTHONPATH=. uv run python ledger/evidence/pra293-fused/run_candidate.py`, config
`configs/gates/pra293-fused.yaml`, no waivers. 16:17–16:24 UTC, exit 0 (`gates.log`, `pipeline.json`, `G3.json`,
manifest `ledger/manifests/candidates/pra293-fused.json`, queue `ledger/queue/pra293-fused.json`).

- **G0** PASS.
- **G1** PASS. dqi: all 62 vendored files match their pins; the vendored GF(2¹²) multiplier (42 Toffolis) and
  inverse (66 Toffolis) are exact on all 4,096 inputs, inputs and scratch restored, no phase.
- **G2** PASS.
- **G3** PASS: the full verifiers, numbers above.
- **G4** PASS: beats parent and archive best `pra280-rustad` (16.8821); chemistry 7.6793 ≥ 7.679; dqi.kmb is
  `7beea291…55f6` and its ratio 54.7295 ≥ 54.7 (the PRA-293 floor).
- **G5** PASS: a clean worktree at generator commit `3b4e342644706772f3db64fe6b0c5084fe0437f1` regenerated all three
  tasks byte for byte. dqi copied nothing; chemistry's only copy is the declared non-circuit factor
  `submission.npz` (D-PRA211-05). `shipping_problems()` is empty.

## Builds

- `build-dqi.json`, `build-dqi.time.txt`: `uv run python tasks/dqi/generate_fused.py --out …`, exit 0, 1:34 wall,
  2.19 GB peak RSS, `7beea291…55f6`, 546,664,050 bytes, Q 889, static Toffoli-like 487,331.
- The same hash came from the upstream `build.py` run directly in scratch (the closure trace), and from the PRA-202
  source check (comment `3dca70e1`).

## Rollback

`rollback/`: exact dqi-only rollback to submission-008, rehearsed with exit 0. See `rollback/README.md`.

## Publication

Local `git push` has no credentials on this seat, so the branch was published through the governed GitHub connection
as a series of file commits. The published commit `666b659d4611cc2bcf5d89101eba555e55f1791a` has tree
`842032c6cf2517e170c5b001484f6abb0ecc0202`, the same tree as the G5 generator commit `3b4e342` (checked with
`git fetch` and `git rev-parse <commit>^{tree}`). Everything after it is evidence and records only.
