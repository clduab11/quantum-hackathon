# PRA-242 measured results

Neither bounded CPU run produced a passing point. Both remained above the source driver’s
30 mHa continuous gate. These results do not establish convergence, shape infeasibility,
or failure of the full public training method. No integration candidate is handed off.

| Shape | Stage | Error (mHa) | Completed work |
|---|---|---:|---|
| [6, 144, 127] | merge | 1443.083789 | 8 PSD sweeps |
| [6, 144, 127] | structural | 395.986423 | 500 iterations, 516 evaluations |
| [6, 144, 127] | gauss-newton | 86.796484 | 30 iterations, 787 CG iterations |
| [6, 144, 127] | offsets | 86.796484 | 33 iterations |
| [1, 496, 384] | merge | 403.702841 | 8 PSD sweeps |
| [1, 496, 384] | structural | 89.401508 | 500 iterations, 517 evaluations |
| [1, 496, 384] | gauss-newton | 35.160044 | 30 iterations, 900 CG iterations |
| [1, 496, 384] | offsets | 35.160044 | 46 iterations |

All rows below are direct-rounding diagnostics from the unmodified evaluator.
Ratios are ordinary-ANGLE cost predictions for **failing** factors, not score gains.

| Shape | bits | error1 mHa | error2 mHa | Lambda | gap | lambda_eff | T | Q | ratio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| [6, 144, 127] | 10 | 13.150122 | 102.232209 | 769.846874 | 4.141770 | 79.749001 | 27282 | 773 | 1.995213 |
| [6, 144, 127] | 11 | 6.701725 | 90.532258 | 769.746672 | 4.041568 | 78.775840 | 27582 | 781 | 1.977426 |
| [6, 144, 127] | 12 | 3.165939 | 87.709208 | 769.701192 | 3.996088 | 78.330191 | 27882 | 789 | 1.947332 |
| [1, 496, 384] | 10 | 12.561760 | 73.796475 | 1593.082635 | 4.448984 | 118.976484 | 22410 | 803 | 1.567298 |
| [1, 496, 384] | 11 | 6.126401 | 47.093993 | 1592.747533 | 4.113882 | 114.402041 | 22710 | 811 | 1.592569 |
| [1, 496, 384] | 12 | 3.295739 | 38.568975 | 1592.758503 | 4.124852 | 114.554671 | 23010 | 819 | 1.554379 |

## Reproduction boundary

Reimplemented: balanced similarity merging of every Google group; simultaneous OMP;
full-target PSD sweeps; scaled residual plus D(w) structural objective; analytic tangent
Gauss–Newton/PCG with source damping/backtracking. Existing offset fitting supplies
lambda_eff and strict-floor soft penalties for diagnostic encoding.

Changed: Google replaces banned Ahmed R26; direct B144 replaces the B157-to-B144
Schur-pruning curriculum; SciPy L-BFGS-B/float64 replaces Torch L-BFGS/float32;
fixed limits of 500 structural / 30 GN / 30 CG replace larger time-limited GPU schedules.
The final structural iterate is retained; canonical eigenvector signs and the initial
PSD floor also differ. Neither run uses randomness, verifier seeds, GPU or foreign factors.

Not reached/reimplemented: progressive sensitivity freezing, discrete repair, fixed-word QR
weight fitting, column-gauge rotations, coupled error/gap/Lambda barrier and one-body
word polishing. The failed 30 mHa gate means no 8/9-bit stretch experiment was justified.
The THC-shaped run is our method; Gluzdov’s training schedule is unavailable.

Both training stages exhausted their 500-iteration budgets; these are not convergence claims.
See FIT_V3.md for commands, optimizer settings, exact source provenance and failure semantics.
The reports retain every stage and independently measured row; checkpoints.json lists all
saved NPZ hashes. Binary factors remain outside git.

## Final factor hashes

- r6 final factors: `88791b9449270b2572aa9adb6818d5d356ee86648c90fc45e482f692866f79f5` (`offsets.npz`).
- r6, 10 bits: `2d57a24f9d5c2f1a6255ab9d3263d7badb95cde5dad4cc227370e4c06bd10151` (`rounded-diagnostic-b10.npz`).
- r6, 11 bits: `4d45cc15c4eb537f229660791cd16a4891d4ad3be5345da1522ae94b942fbefc` (`rounded-diagnostic-b11.npz`).
- r6, 12 bits: `aa5e7b33fabdb4647b0775785b180b2306299bfb90a173ea50b1fba97d5a18fa` (`rounded-diagnostic-b12.npz`).
- thc final factors: `2315a25a2b20883362630b0e5dca6a1bfea4b3be647cf250497617e618689a9b` (`offsets.npz`).
- thc, 10 bits: `6b4b14f836ce41c155ec664afc15be3d3c245e04e56148fcab2e082f6ab8e268` (`rounded-diagnostic-b10.npz`).
- thc, 11 bits: `d269afd68c5cdb61b93e5578789a95e2c56ae2a4dd6133d9439d2c13cac5e460` (`rounded-diagnostic-b11.npz`).
- thc, 12 bits: `832b07485229e055223dd3df1c064b47f88db1097ecf8d9e1f1946918dfca887` (`rounded-diagnostic-b12.npz`).
