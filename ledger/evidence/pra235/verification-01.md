# Initial helper verification (incomplete experiment)

- `uv sync`: passed; Python 3.13.13, NumPy 2.5.4, SciPy 1.18.1.
- `uv run pytest tests/test_factor_refit_v2.py -q`: `3 passed in 0.51s`.
- Zero-gradient mutation: `test_quantized_weight_gradient_and_fit` failed with
  all 12 gradient entries mismatching finite differences; exit 1. Restored
  original source before the passing check. No mutation is committed.
- `uv run pytest -q`: `3 failed, 260 passed, 1 skipped in 126.78s`.
  Failures were subprocess imports lacking the competition `kickmix` path.
- `PYTHONPATH=/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation/kickmix uv run pytest -q`:
  `263 passed, 1 skipped in 118.00s`. Full stdout: `pytest-01.txt`.
- `uv run python -m ledger.registers check`: passed before final evidence commit.
- Merge queue at initial local `59d3864`: open #28 plus own branch, both orders
  clean, register checks passed. Exact report is in draft PR #29. Re-run before
  declaring the eventual final PR ready.
- Own 20-iteration real-input refit: exit 3 (expected measured PRA-198 floor miss),
  checkpoint and control archive hashes exactly match PRA-198. See JSON.
- Larger-shape construction probe: exit 0; both requested shapes produced from
  pinned Google baseline, no accuracy verdict. See `regroup-probe.json`.
- Long 1,000-iteration run and fixed-12-bit weight probe still running at this
  checkpoint. No compressed passing output or task completion claimed.
