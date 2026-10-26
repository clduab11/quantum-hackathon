# Schur decoder source audit and port

The source audit was recorded on PRA-261 before the port. Parent:
https://github.com/jday96314/QuantumAI/tree/2b9227095bf2c76f9f64a572645d7dce54998298/initial_experiments/6/agent14 .
`source-pins.json` records the exact upstream path, Git blob SHA-1 and SHA-256 of
each selected file. The parent has **no repository licence**. Use is under board
ruling D-PRA269-01, card `aba6c540`, extending D-PRA228-01. This attribution does
not claim an Apache licence for the parent's additions.

The notebook was renamed to
https://www.kaggle.com/code/alexchilton/toffolis-go-15-05-verified-portfolio-llm-gauge .
The actual source inspected was scriptVersionId **362573669**, changelog v36,
SHA-256 `28e0f08476df85323f9d25589f3cf781f13b5df105233193edfe8a5d1cff149c`.
Cell indices are zero-based. Cell 8 describes the decoder lineage and three
width reductions. Copying code in cells 1, 5 and 6 is excluded. The requested v33
was unavailable anonymously. No v33 audit or independent licence is claimed.

## Selected construction

Port `build_raw_cf_destructive.py`'s composition: raw quadratic-node Schur
extraction, destructive continued-fraction synthesis, derivative-inverse
conversion, runtime-mask amplitude scan, inverse synthesis and extraction.
Dependencies include earlier experiment arithmetic; exact paths are pinned.
The package uses relative imports and removes upstream test/CLI drivers. The
composer is rewritten in Python to stream explicit component output. Generation
runs in an isolated temporary working directory; only `dqi.kmb` is delivered.

The upstream loader's vendor tree and circuit capture/replay are excluded.
The port instead uses our committed Apache-2.0 Gu arithmetic ancestor in
`tasks/dqi/bm_forney`: andigu/uncompute commit
`64b5a13aa249f1360846657392e6c66817b26d0f`. It derives field formulas for the
official modulus 4179 in memory. The exact source substitution removes the
`DQI_CONSTANTS` environment input. Existing committed windows load only to
initialize the ancestor module; the Schur schedule does not use BM windows.

The absent upstream `parameters/cubic_joint_quadratic_16.txt` is **not** a
runtime input. Our replacement derives a 17-AND cover: nine products for GF16
multiplication and four products for each of two cubes. All 256 inputs are
checked against the independent field formula. This is algebraic construction,
not a salt/seed search. The original source's inspection-based transformations
of committed emitter functions remain checked for exact replacement targets.

No circuit, notebook, downloaded coefficients, captured operation tape,
credentials or network call is a generator input. Old tape-export drivers and
the Boolean network file parser are removed. All arithmetic input data is
committed source or deterministically derived from the official field.

## Limits and comparison

This first candidate ports the available **892-qubit** construction. The
notebook author's 883-qubit modifications are in an inaccessible attached
dataset, and are not claimed as ported. Its public circuit SHA-256
`26369ae8dfaa62dd5963e4ce16c5bb6b3ba6dd1fa090ee322810a0bb78803d3e` is a
measurement-only comparison artifact, never an input or submitted file.
John Wick measured it at Q883, mean T536797.78, R1.213105, 5 value and 0 phase
errors in 102400 fixed-public-salt shots: 48.135×. Those measurements are not
verification of this generator. Each candidate requires its own full verifier
and byte-identical clean rebuild.
