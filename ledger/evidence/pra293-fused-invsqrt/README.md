# PRA-293 evidence: fused DQI decoder on #62's invsqrt-port bundle (shipping candidate)

Candidate `pra293-fused-invsqrt`: #62's `pra281-invsqrt-port` (zip `5c8db085…cecd`) with **only `dqi.kmb` changed**,
to SomeJoint's fused confluent decoder built from the source vendored under `tasks/dqi/fused/` (see its
`PROVENANCE.md`). The board asked for this bundle on PRA-293 (comment `af27be22`, 2026-10-27 17:23 UTC) after #62
merged. It supersedes the first run `pra293-fused` (submission-008 + the same fused dqi, `../pra293-fused/`).

## Result

| | submission-008 | pra281-invsqrt-port (#62) | pra293-fused (first run) | **pra293-fused-invsqrt** |
|---|---:|---:|---:|---:|
| invsqrt.kmb | `75e8a0e2…` | `17fc223d…41ad` | `75e8a0e2…` | `17fc223d…41ad` |
| dqi.kmb | `1a1c60ae…8f48` (Schur) | `1a1c60ae…8f48` (Schur) | `7beea291…55f6` (fused) | `7beea291…55f6` (fused) |
| invsqrt ratio | 13.1648 | 13.2377 | 13.1648 | **13.2377** |
| dqi ratio | 47.5932 | 47.5932 | 54.7295 | **54.7295** |
| chemistry ratio | 7.6793 | 7.6793 | 7.6793 | 7.6793 |
| local GM (salt `PRA171_LOCAL_PUBLIC_FIXED_SALT_0001`) | 16.8821 | 16.9132 | 17.6869 | **17.7195** |

17.719490035438174 is +4.96 % over submission-008, +4.77 % over the parent and +0.18 % over the first run.

- dqi (G3, 102,400 shots): **0 value / 0 phase errors**, Q 889, mean Toffolis 474,307.73, ratio 54.72947182918558.
  These are the same bytes and the same salt as the first run, and they give the same result.
- invsqrt (G3, 200,540,928 shots): PASS, Q 84, Toffoli 1,553.0, worst error/tolerance 0.99959, ratio
  13.237727705632725. These are #62's numbers, reproduced.
- chemistry (G3, 87,424 shots): PASS, ratio 7.679252642164734.

Zip `/home/cld-main/work/vqcc-data/pra293-fused-invsqrt/pra293-fused-invsqrt.zip`, SHA-256
`22258bb57f1a711336567cb8771c7f88936d903af7727ab0bbd993fb72e5f27d`, 31,967,085 bytes (not committed). One fixed
salt; no salt or seed search.

## Gates

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 UV_NO_SYNC=1 \
  PYTHONPATH=. uv run python -u ledger/evidence/pra293-fused-invsqrt/run_candidate.py
```

Run from a clean tree at `c5309550c5395515931ce63f471f5523eedf8ae7`, in a venv synced with `uv sync --group gpu`
(torch 2.8.0+cu128, one CUDA device: RTX 4060 Ti). Config `configs/gates/pra293-fused-invsqrt.yaml` is a copy of
`pra281-invsqrt-port.yaml` with only the dqi G1 hook, the dqi generator and G4 changed (pinned by
`tests/test_dqi_fused.py`). No waivers. 17:32:40–17:39:24 UTC, 390.9 s, exit 0 (`gates.log`, `pipeline.json`,
`G3.json`, manifest `ledger/manifests/candidates/pra293-fused-invsqrt.json`, queue
`ledger/queue/pra293-fused-invsqrt.json`).

The runner checks the parent zip against the `pra281-invsqrt-port` manifest. It takes `dqi.kmb` from the first run's
`generate_fused.py` output, checked against `7beea291…`. It builds the zip with `ledger.archive.build_zip` and refuses
it unless the invsqrt and chemistry file maps equal the parent's.

- **G0** PASS.
- **G1** PASS. dqi: all 62 vendored files match their pins. The GF(2¹²) multiplier (42 Toffolis) and inverse (66) are
  exact on all 4,096 inputs. invsqrt: the pinned port bytes, Q 84, register `x` of 22 qubits. Chemistry: PASS.
- **G2** PASS (fast proxies; not parity).
- **G3** PASS: the full verifiers, numbers above.
- **G4** PASS (`tasks.dqi.fused.gates:g4_floor_on_port`). GM 17.7195 beats the parent `pra281-invsqrt-port`
  (16.9132) and the archive best, which at gate time was the first run `pra293-fused` (17.6869). Chemistry is
  7.6793 ≥ 7.679. dqi.kmb is `7beea291…55f6` at 54.7295 ≥ 54.7. invsqrt.kmb is `17fc223d…41ad` at 13.2377 ≥ 13.2377.
- **G5** PASS: a clean worktree at `c5309550` regenerated all three tasks byte for byte. invsqrt came from
  `tasks.invsqrt.public_port.generate --circuit-only` (refit on CUDA), dqi from `tasks.dqi.generate_fused` and
  chemistry from `tasks.dfthcsos.rustad`. dqi and invsqrt copied nothing. Chemistry's only copy is the declared
  non-circuit factor `submission.npz` (D-PRA211-05). `shipping_problems()` is empty.

## Tests

- `uv sync --group gpu`, then `UV_NO_SYNC=1 uv run pytest -q -rs`: **427 passed, 3 skipped** (`pytest-gpu.log`). The
  skips are the existing opt-in conditions (nbformat, pinned JAX integration, JAX smoke).
- `uv sync`, then `uv run pytest -q -rs`: **403 passed, 11 skipped** (`pytest.log`). The skips are optional
  dependencies (jax, torch, nbformat, the gpu group).
- `uv run python -m ledger.registers check`: OK, 279 decisions, 7 notice files.

## Rollback

`rollback/`: an exact dqi-only rollback to `pra281-invsqrt-port`, rehearsed with exit 0. #62's invsqrt-only rollback
continues from there to submission-008. See `rollback/README.md`.
