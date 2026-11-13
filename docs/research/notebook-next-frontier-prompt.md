Using this notebook's sources, identify implementable improvements for Kaggle Verifiable Quantum Circuit Compilation, targeting 29.91-30.0. Cite source sections/code for each claim; label estimates and missing evidence. Do not assume access to our repo.

Measured Syed v12 baseline: Kaggle 27.00209; all three tasks passed G0-G5/full-shot verification.
- invsqrt: Q46, charged Toffoli-equivalent C1742.66859 (includes rotations), cost Q*C=80162.755; worst error/tolerance=0.973576.
- DQI: Q889, mean Toffoli T383156.2876, R1.201388; cost R*Q^2*T=3.6380008e11. Two value errors in 102400 shots; zero errors still gives R~1.19126, not 1.
- Chemistry: aggregate Q427, T14810, lambda_eff46.9073475; cost lambda_eff*Q*T=296635967.6. Errors 0.01961037/0.01999878 must both stay <0.020. Width cap128 applies per ANGLE circuit, not aggregate Q.

If f_i=new/old task cost, score=27.00209/(f1*f2*f3)^(1/3). For 30, product<=0.72917: 27.08% cheaper in one task or ~9.99% in all three. Never add overlapping gains.

Already explored: staged invsqrt Q84 (~177631 cost), optimistic Q63 (~112181), both worse; DQI zero-test uncompute already exists; chemistry sign-gauge/low-bit parity already exists; unrefitted b_rot7 (~336.9M) loses. These are not general lower bounds.

Return up to 4 distinct, cited hypotheses: exact algorithm/circuit change; before/after Q,T,rotations,R/lambda and error/phase/ancilla budget; derived cost saving; smallest falsifiable CPU test, pseudocode and numeric stop criterion. Then choose compatible changes toward 29.91/30 with full cost-product arithmetic, and one best next experiment. If sources cannot support the target, say what result or excerpt is missing. No invented savings, salt/seed grinding, relaxed verifiers, uploads or paid compute; require reproducible licensed generators.
