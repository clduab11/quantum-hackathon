# Public source experiment

This is a separate invsqrt generator ported from Dmitrii Gluzdov's v7 notebook.
It does not replace `tasks/invsqrt/generate.py` or select a submission candidate.
See [provenance](../PROVENANCE.md) and the [research report](../../../docs/research/PRA-249-invsqrt-public-port.md).

```sh
uv sync --group gpu
uv run --group gpu python scripts/install_kickmix.py "$VQCC_DATA"
uv run --group gpu python -m tasks.invsqrt.public_port.generate --out /tmp/invsqrt-public-experiment
```

The generator fits its own coefficients on CUDA, checks all 3,133,452 integer
inputs before circuit construction, builds the circuit, proves its unconditional
phase matches that arithmetic, and fits new rotation angles. The small cutting-plane
LP uses HiGHS on the host; exhaustive constraint evaluation runs on CUDA. A positive
arithmetic certificate does not replace the official full-shot circuit verifier.

No saved public tables, angles, patches or binaries are generator inputs. The
output directory holds the experimental `invsqrt.kmb` and a build report. It is
not a queue entry or a shipping receipt. The default ledger gate configuration
still uses the existing fallback generator.

The PRA-284 floor-candidate config is `configs/gates/pra281-invsqrt-port.yaml`.
It uses `--circuit-only` for G5 so the output directory contains only
`invsqrt.kmb`. This flag suppresses the diagnostic JSON file; it does not skip
the CUDA fit, arithmetic proof, compilation, or angle calibration. Without the
flag the CLI retains its build report. The port's G1 pins the selected circuit
hash and register schema; G2 simulates 1,536 inputs, once each. G3 still requires
the full official verifier, and G5 refits from the committed generator.

The normalized fitter uses groups of eight, three fractional slope bits and
configuration `(9, 19, 26, 2, drop2=(5,))`. It recursively subdivides a group when
the best reachable-domain relative error exceeds `0.95 * 2^-24`. It enforces
even anchors for the virtual low bit. Tie breaking follows ascending enumeration.
The rotation experiment tests the full set and one smallest-angle drop; it does
not claim a global minimum over all schedules or all angle subsets.
