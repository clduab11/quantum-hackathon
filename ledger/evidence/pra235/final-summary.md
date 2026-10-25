# PRA-235 final experiment verdict

The scheduled Google-only factor experiment matrix is complete. The (65,60,30),
12-bit floor passes the 19 mHa requirement. The (32,60,30), 10-bit target, both
public-style shapes at 10–11 bits, and all compressed points below 12 bits miss
accuracy at the tested budgets. No passing factor reaches the 4x stretch.
These are measured negatives, not infeasibility results.

## Leading passing checkpoints

| Selection | Shape / bits | error1 / error2 mHa | Lambda | E_gap | lambda_eff | predicted T / Q | modeled ratio |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Best margin, Adam 300 + rounded-U weights 200 | (65,60,30) / 12 | 3.383503314 / 17.459501285 | 332.668541726 | 4.083043259867 | 51.960839599 | 88874 / 727 | 0.999505x |
| Best accepted modeled cost, penalty 2e-4 | (65,60,30) / 12 | 3.224421669 / 18.299842110 | 325.285029352 | 4.067613184750 | 51.280813872 | 88874 / 727 | 1.012759x |

Adam encoded SHA-256:
`ec864ac608d42a5e0a3c816aff353ccf8383e6472e3a4ddf88f35f45ce24c371`.
High-penalty encoded SHA-256:
`44e55a6b70d3da5618e9006b27350cd197e16f18aa256024c90cb19c3bfae4f1`.
Both passed unmodified evaluate_words, independent saved-file proxy reloads and
fresh byte repeats in the same source/environment. Both were already handed to
PRA-237 with downloadable archives. No circuit or submission is produced here.
Resource estimates include ordinary-QROM ANGLE lookups; they are not measured
circuit performance. The cost gain is only about 1.3%, far short of 4x.

## Lever verdicts

| Lever | Measured result | Evidence |
| --- | --- | --- |
| Long structural budget | 1,000-step continuous floor passes at 18.668749 mHa; old 20-step regression remains 20.363453 mHa with identical cc7dd377 hash | floor-long-complete-01.json; pra235-v2-regression-01.json |
| Larger L-BFGS memory and rounded-U fitting | maxcor20 / 500 structural + weights 200 floor passes 17.628403 mHa, freshly byte-repeated; selected width fits independently | gradual-complete-01.json; floor-repeat-comparison-01.json |
| Gradual pruning | R64 passes competition20 mHa at 19.567859 but misses 19 mHa margin; R60 through R32 fail; final 10-bit R32 is 243.531672 mHa | gradual-complete-01.json |
| D(w) sweep | 0/2e-6/2e-5/2e-4 pass at 17.743563/17.743778/17.729283/18.299842 mHa; high penalty gives best accepted modeled cost | penalty-*-complete-01.json |
| Adam / trust-ncg | Adam 300 reaches 17.459501 mHa; trust 300 reaches 18.050079 mHa; caps exhausted, no optimizer convergence claim | optimizer-adam-complete-01.json; trust-ncg-complete-01.json |
| Offset refinement | lambda_eff objectives and iteration outcomes recorded before/after rounded-U fitting; Lambda and gap acceptance enforced by verifier checks; best high-penalty final offset converges at 57 steps | complete reports, stages and quantized_offsets |
| Larger-shape initialization | Google-only regrouping supports larger B/C; R6 and R1 accuracy misses at all target widths after 1000 structural + 500 weight steps per width | public-r6-complete-01.json; public-r1-complete-01.json |
| Below 12-bit encoding | No compressed point passes; fixed rounded-U fits optimize weights, not discrete angles | all complete reports |

## Final target precision matrix

| Shape | 12-bit error2 mHa | 11-bit | 10-bit | 9-bit | 8-bit |
| --- | ---: | ---: | ---: | ---: | ---: |
| (32,60,30) | 241.536870 | 245.062173 | 243.531672 | 257.016123 | 290.042650 |
| (6,144,127) | 277.081853 | 275.480077 | 277.529710 | 285.552127 | 313.274957 |
| (1,496,384) | 132.791028 | 132.788108 | 137.904962 | 156.802953 | 205.156343 |

R32 uses 500 structural/maxcor20/D(w)=2e-5, offsets 100, independent 12/10-bit
weight fits 200 and offsets 100; 11/9/8 are continuous encodings. R6/R1 use 1000
structural and independent 11/10/9/8-bit weight fits 500. All structural fits hit
caps. The final R32 10-bit offsets converge at 53 steps; structural-plus-offset 402.204s.
Gradual pipeline total 12271.408s; child exit 3 is the expected completed numerical
miss, not an operational failure.

## Evidence, provenance and verification

`final-integrity-01.json` audits all 10 primary runs (145 measured rows, including
repeated controls): 290 actual raw/encoded file hash comparisons pass. Repeated
raw references count separately. Every report's numerical source hashes match
both committed source 961357b and the current worktree. All untouched control raw
and 12-bit encoded hashes match the prior reference. The historical cc7dd377 hash
belongs to the 20-step compressed checkpoint, not the untouched control.

Full settings, versions, point/stage runtimes, predictions, optimizer diagnostics,
input pins and every raw/encoded hash are retained in the 10 complete reports
listed by the audit. Python 3.13.13, NumPy 2.5.4, SciPy 1.18.1, one BLAS thread.
Exact plans and launch commands are committed. Binaries remain outside Git.
Google input manifest is `ledger/manifests/inputs/pra198-google-v4.json`;
method parents and licences are in `notices/30-dfthcsos.txt`. No forbidden public
factor file was loaded. New helpers are own NumPy/SciPy code extending the
already attributed methods. No new notebook method was imported in this run.

Unchanged numerical implementation has recorded validation in verification-02.md:
uv sync passed; full suite with explicit pinned kickmix PYTHONPATH 269 passed / 1 skipped;
focused factor tests 20 passed; zero-gradient mutation failed as expected.
The final evidence/doc-only changes use fresh file-integrity, register and merge
checks; these do not claim a new full-suite run. All required experiment levers
have measured outcomes. No experiments remain running or awaiting collection.
