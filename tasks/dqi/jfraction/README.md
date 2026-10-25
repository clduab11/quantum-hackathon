# Paired J-fraction DQI

Build from the repository's CPython 3.13 + Kickmix environment:

```sh
uv run python tasks/dqi/generate_jfraction.py --out /tmp/dqi-paired
```

The command writes only `dqi.kmb`; JSON resource and per-phase allocation
snapshots go to stdout. `peak_qubits` is the cumulative referenced-ID highwater;
`live_qubits` is the allocation count at the boundary, not the within-phase peak. No verifier or public binary is used to generate it.
Use `configs/gates/pra236-jfraction.yaml` for exact-zip G0–G5. The fixed salt is
`PRA171_LOCAL_PUBLIC_FIXED_SALT_0001`; the full DQI verifier uses 102,400 shots.

The decoder preserves all 35 levels while storing two first-order gap pointers.
Three-gap overflow and higher-order gaps are approximation limits inherited
from the source, not proven impossible events. A sampled pass does not prove
zero true error. See `PROVENANCE.md` for accepted source and reuse boundaries.

New mathematical projection tests cover every position and bit basis in the
full field, plus a small emitted circuit with dirty classical scratch. Small
inverse tests check zero, nonzero inputs, retained values and HMR cleanup phase.
