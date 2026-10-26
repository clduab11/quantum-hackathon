# PRA-250 recovered source audit — proceed to port

The missing-source obstacle is resolved. This supersedes the earlier availability finding, not its historical observations. This read was posted to the task before implementation.

SomeJoint / Agniv Banerjee, kernel 140675727, notebook v7: https://www.kaggle.com/code/somejoint/quantum-circuits-13-54-local-gm-cost-gains . UTF-8 API source SHA-256 `3b0df548f40676117fb6f53cd7c9ab0fc5ca29b7ed56f90581921e443e92d7eb`. Captured archive SHA-256 `7fc342ab0c04c2001dc2b13f424da4d2dd3d4acbabc0fc09e789182084092923` verified against the attachment. The archive also contains unrelated Schur material; only the SomeJoint notebook/API content was inspected, and the unrelated files were excluded from the audit workspace.

Cell indices are zero-based. Cell 0 and 13 state submission 10 retains submission 9's dqi. Cell 102 selects `hankel_half.forney` and `cyclic_gold.extract`, builds from source, and checks published hash `c1a4763847f594587f83588eddf437f2bb6957806f1277e6c98b0aac21c003b9`, Q 883 and static T 996829. These remain author claims until our verification. Cell 13 explicitly reports rare residual phase exceptions (one directly observed in 307200 local shots plus two inferred from Kaggle), not exact correctness.

## Licence and lineage

Cell 34 explicitly identifies the new Bezout/Hankel/cyclic-cube work and licenses the DQI source Apache-2.0. Cell 90 provides the Apache text; cell 91 preserves the upstream NOTICE. Contrary to the recovery summary's shorthand, the extracted DQI modules generally do not contain SPDX headers; the author grant is the explicit cell-34 declaration, with embedded licence and notices. Cell 92 records predecessor file pins. All 42 `upstream/` files match the independently audited anazemcev v6 capture byte-for-byte, including the 20 SomeJoint and 21 Manwithacat upstream matches. Earlier notebook versions, scriptVersionIds and UTF-8 hashes remain in the prior document revision and committed `tasks/dqi/jfraction/PROVENANCE.md`.

The inherited Manwithacat projection is unchanged. We retain our already committed Lagrange/trace implementation and do not copy that file. The existing fallback stays untouched. No new licence obstacle identified in the selected author-owned additions. This is source provenance, not legal sign-off.

## Selected changes and input closure

New phase path: `hankel_half` → central/border repair, recursive LDU scaling, in-place polynomial maps, root-only Forney scan. New extraction: cyclic middle-cube interpolation → Gold cube/vector routines and the existing paired-v6 extraction. Runtime keeps fixed threshold 14 and borrowed zero metadata. The exact fixed 26-AND Boolean tensor is embedded in cell 89, a small source JSON table owned by this notebook; no heuristic/search is executed and no circuit is declared as input.

Port only production functions needed by these two selected paths. Remove notebook sys.path manipulation, runtime monkey-patch bootstrap, profiling CLIs and independent microcheck harnesses. Reuse existing jfraction package modules; preserve its new projection and direct norm-recycle inverse call. Scoped extraction patches must restore the inherited arithmetic functions after use. No selectable variant or salt is added to the generator.

DQI generation needs only committed Python/JSON source and hash-pinned Kickmix. Original common.py points at competition reference Python and verifier modules; the port uses committed reference_circuit.py through existing jfraction.common instead. No DQI `.kmb`, `decoder_input.kmb`, toolbox `dqi/*.npz`, package circuit, notebook output, downloaded coefficient file, external source loader, network call, fit or seed search is needed. The enclosing notebook's invsqrt/chemistry output copies are excluded. The missing `ldu_scale` import occurs only in an unused microcheck CLI and is excluded with that CLI. Phuc EXP-250a is not merged: the earlier public wrapper has no generator to assess.

## All 58 embedded files

The 42 inherited files are exact matches of the earlier source audit. The 16 added files are listed below (includes the build/runtime wrappers and tensor). Exact per-file sizes and hashes for all 58 are saved in files.json. Source extraction used AST literal parsing only, never notebook execution.

| Cell | New path | SHA-256 |
| --- | --- | --- |
| 35 | `build.py` | `affe27084a69ec798bda984b9377dbde058e9886f2226bf549bdb07b28a34b95` |
| 36 | `runtime.py` | `b951b201efba438544f6b2a1daad6332d9342e54a5d8443541a4f53a2beff4b8` |
| 37 | `hankel_half.py` | `3fe84f046436cae04ba1cbad764e4d3b099cce4af52713bee3e7aa71893fbeaa` |
| 38 | `cyclic_gold.py` | `d51ab45ef43ec66f1dc38fc30986f6df638aedcd8f99ad752cca827f302b8cbb` |
| 39 | `gold_extraction.py` | `6bb93d17c742449666d9e7d6185dba4cd79815b02423cf6cd019640cc6221afb` |
| 40 | `central2/bezout_model.py` | `2ceef384e912c035857288270e8231f096717b45d856ec195d869f9c4a805b1a` |
| 41 | `central2/border_circuit.py` | `f0c34d0634f660f733863d51af9efa3bd97d31d89980541fa1756a3c42ef9dc5` |
| 42 | `central2/central_circuit.py` | `d952a3c1a45e540bc6a82068cc8d7b4be0ddeacb7483d04e3136dffff73e7443` |
| 43 | `central2/forney_bezout.py` | `c134a55ad41cfc8b5a7e13a8ac1dbfb0f06cb3397d01360a51ee3e84ca48bee3` |
| 44 | `central2/half_circuit.py` | `046c851ea477c7a773296dfafcec9bb0abedb4cb071b3f88b3def4953776a289` |
| 45 | `central2/inplace_poly.py` | `0554cbca7a160ea1dee83eae492ddd91ad184e4894203e5a3a4b762703f5b68a` |
| 46 | `central2/recursive_ldu.py` | `df9cd8845bbe26295901b9a3ef6d0b9bb298d0dd477dca7de5546fb2ec57272d` |
| 47 | `central2/retry_circuit.py` | `0cb44f6632ca588ff6d70fc0146fd2857ab2c23fc9d44d28a7c25d26c75ee7d6` |
| 48 | `gold26/gold_cube.py` | `4f6d10b4a7e548b8d81a631a1298ae32ca320506d788703ed8a407aec7fd4fef` |
| 49 | `gold26/gold_forms.py` | `0554cbca7a160ea1dee83eae492ddd91ad184e4894203e5a3a4b762703f5b68a` |
| 89 | `gold26/hermitian12-search-check.json` | `a10ce67df5bab5a089a12debea5342045e0ef17ce7ab66bfd2b5b162662cf001` |

All Python files parse. Input/side-effect paths were inspected statically. Verification results are recorded separately in docs/reports/pra250-dqi.md. New task branch is based on current origin/main `9db5f61785d41636cff13a9116d26aa13c57aeb1`; no task commits were rewritten.

## Port mechanics

SOURCE_MAP.json pins every imported source file and its modified port. EMBEDDED_FILES.json records all 58 audited embedded files. Production imports point to the existing jfraction package. The border inverse explicitly calls norm recycling, matching upstream runtime substitution. The original mask projection is not copied; our existing trace/Lagrange implementation changes circuit bytes and Clifford operation counts. The extraction context temporarily installs the two source hooks and restores both even on exceptions; it does not modify fallback source. Generator inputs are source-only; the Gold tensor is committed Apache-2.0 source data.
