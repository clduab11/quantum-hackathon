# Search fitness: require real feasible cost evidence

Malformed feasible records previously inherited favorable defaults and could score as perfect. The fix validates the selected task cost terms, rejects missing/nonfinite/nonpositive raw evidence and boolean values, and preserves finite explicit log overrides, aliases, numeric strings and the existing positive subunit resource floors. The chemistry evaluator and chemistry/DQI adapters no longer invent missing lambda_eff or repetition evidence. Infeasible proxy records retain their graded lower-band score.

Validation: **143 passed** across `test_search_fitness_validation.py`, `test_search_fitness.py`, `test_search_pra331_fixes.py`, `test_search_pra334_fixes.py` and `test_search_pra336_fixes.py` using the configured native CPython 3.13 environment with kickmix. `uv sync --offline` in this branch succeeds; its fresh environment lacks kickmix because the Windows dependency setup is a separate PR. A run there without that setup had 5 import failures / 138 passes, not a logic regression; the same tests pass with the calibrated interpreter.

This change is separate from the public-portfolio circuit staging and submission-012. It makes no new circuit or score claim. Both branches start at main `b92db3a`, not from each other.
