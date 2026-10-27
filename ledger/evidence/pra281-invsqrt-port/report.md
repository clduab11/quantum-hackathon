# PRA-284: regenerated invsqrt floor candidate on the rustad bundle

The exact candidate zip clears real G0–G5 with no waivers and
`shipping_problems() == []`. The official invsqrt result is
**13.237727705632725×**, Q84, over **200,540,928 shots** at
`PRA171_LOCAL_PUBLIC_FIXED_SALT_0001`. This clears the ≥13.2377× task floor.
Local bundle geometric mean: **16.91319568027347**, against the parent
`pra280-rustad` at 16.88208344372253 (+0.18 %).

The candidate changes only invsqrt from `pra280-rustad`. Schur DQI remains
47.59316876861791× and rustad chemistry remains 7.679252642164734×; their file
maps are byte-identical to the parent. The candidate is local verification
evidence, not a submission or permission to merge. It ships with PRA-285's
result, not on its own.

| Identity | Value |
| --- | --- |
| Branch | `op-vqcc/PRA-281-1-invsqrt-port-candidate` |
| Base | `main` at `33c8f82cde158101615b40057eb039649efbdd66` |
| G5 generator commit | `ab06f050551aefbcf69464b46b5ae9efc52ba0a3` |
| Candidate / parent | `pra281-invsqrt-port` / `pra280-rustad` |
| Zip SHA-256 | `5c8db085d18872b17dc16890a2afd6ea8b3c63d3dc513b853ba0ac20b797cecd` |
| Parent zip SHA-256 | `8e2918400fd033440d350d4af76bc4bdfca3787cdf411dcbb974f03d3b4f8f21` |
| invsqrt SHA-256 | `17fc223d79d3f1f15ef448389072209972b373403dd0a45352f4fe7eaff541ad` |
| Config | `configs/gates/pra281-invsqrt-port.yaml` (copy of `pra280-rustad.yaml`, invsqrt only) |

The binary zip is at `/home/cld-main/work/vqcc-data/pra284/pra281-invsqrt-port.zip`;
`run_candidate.py` builds it from the parent's hash-checked zip with only
`invsqrt.kmb` replaced, then runs the gates. No binary is committed.

## Full official invsqrt verifier

```json
{
  "circuit_sha256": "17fc223d79d3f1f15ef448389072209972b373403dd0a45352f4fe7eaff541ad",
  "max_toffoli_count": 1564,
  "num_ops": 37753,
  "num_qubits": 84,
  "reaction_depth": 214,
  "rotation_count": 44.0,
  "rotation_eps": 3.051847661949807e-13,
  "score": 156882.98474606057,
  "status": "PASS",
  "t_count": 1.0,
  "toffoli_count": 1553.0002254402652,
  "toffoli_equivalent": 1867.654580310245,
  "verified_shots": 200540928,
  "worst_error_over_tolerance": 0.9995943415273103,
  "worst_x": 32
}
```

The ratio is the calibrated reference cost divided by the measured score. The
raw verifier summaries for all three tasks are in `G3.json`; the manifest binds
them to the exact zip by SHA-256.

## Clean rebuilds and real gates

Two independent clean detached worktrees at `6babc95`, each with an empty
declared-input staging directory, refit on CUDA and produced:

```text
rebuild 1: exit 0; 17fc223d79d3f1f15ef448389072209972b373403dd0a45352f4fe7eaff541ad
rebuild 2: exit 0; 17fc223d79d3f1f15ef448389072209972b373403dd0a45352f4fe7eaff541ad
```

Both prove all 3,133,452 integer inputs and the compiled phase match. See
`clean-rebuilds.json` and the two raw rebuild logs. This evidence is about the
circuit alone and does not depend on the bundle base.

The real cascade on the exact zip (`gates.log`, `pipeline.json`), 584.3 s:

```text
G0 PASS
G1 PASS
G2 PASS
G3 PASS
G4 PASS   GM 16.91319568027347 > parent and archive best 16.88208344372253 (pra280-rustad); chemistry 7.679252642164734 ≥ 7.679
G5 PASS   commit ab06f050; invsqrt, dqi, dfthcsos: returncode 0, identical: true
shipping_problems: []
```

G5's third rebuild of the port, now at `ab06f05` through the committed
`--circuit-only` CLI, again produced `17fc223d…`. The only copied input is
`dfthcsos/submission.npz`, the declared, hash-pinned rustad factor
(D-PRA211-05). No circuit or fitted table is an input.

## Superseded first run on the PRA-250 parent

The first exact-zip run used `pra250-hankel` as the parent, because PR #58 had
not merged yet. It also cleared real G0–G5: zip
`72696370e02126c0edf427933718f0ad25cee496cf5db7e56c2f4b08491579d3`, GM
11.304033298686251, same invsqrt verifier JSON, reviewed head `b19064d` on
PRA-289. Its manifest, queue pointer and G3 record are in that commit and in
PRA-284's evidence attachment. The zip is kept at
`/home/cld-main/work/vqcc-data/queue/pra281-invsqrt-port.pra250-base-72696370.zip`.
It was superseded only because the bundle base moved to `pra280-rustad`.

## Change and verification

The G1/G2 hooks follow the existing reference-gate contract. G1 pins the
selected hash and the 22-qubit x register; G2 simulates x=1..1536 once each.
`--circuit-only` suppresses the JSON report in the G5 output directory; it
still refits, proves, compiles and calibrates. No existing coefficient fitter
or other task generator changed. The existing public-port notice in
`notices/10-invsqrt.txt` already covers this source; no notice change or
licence check was needed.

The new tests first reported `2 failed, 3 errors` for the missing hooks/config
and the unsupported CLI flag. Commands and results are in `commands.md` and
`pytest.log`.

## Rollback addendum (answers PRA-289)

This change adds an opt-in config and candidate records. It does not change
the default bundle. **Before merge**, rollback is to leave the PR unmerged.

**After merge**, changing configs alone does not withdraw this candidate:
its manifest stays gated, and its queue pointer still lists it. Uploads only
run through `ledger.scorecard reserve/submit --candidate <manifest> --zip
<archive>`, so the rollback has to do two things. It withdraws the pointer
and names the parent explicitly. One command, run from the checkout:

```sh
PYTHONPATH=. uv run python ledger/evidence/pra281-invsqrt-port/rollback.py --repo .
```

It does the following:

1. **Stops selection.** It deletes `ledger/queue/pra281-invsqrt-port.json` and
   the ignored queue zip copy `ledger/queue/pra281-invsqrt-port.zip`. On `main`,
   that deletion lands as a board-authorized PR with a new superseding decision
   file. Decision rows are append-only.
2. **Selects the parent explicitly.** It reads
   `ledger/manifests/candidates/pra280-rustad.json` (file SHA-256
   `a47374797d491fc02f518ea595bba9ef809a83da614b8e992a3d272717332991`) and
   requires `shipping_problems() == []`. It requires
   `configs/gates/pra280-rustad.yaml`. It requires the archive
   `/home/cld-main/work/vqcc-data/pra280/pra280-rustad.zip` to hash to the
   manifest's `8e2918400fd033440d350d4af76bc4bdfca3787cdf411dcbb974f03d3b4f8f21`.
   It prints the exact `--candidate`/`--zip` arguments that any later
   reservation must use.
3. **Proves only invsqrt changes back.** Between the two manifests, and member
   by member between the two zips, the only difference is `invsqrt.kmb`. The
   port `17fc223d…` (13.2377×) goes back to `75e8a0e2…` (13.1648×). Schur DQI
   and rustad chemistry are byte-identical.

The command never touches decisions, manifests, evidence, configs, notices or
reservations. It makes no reservation, upload or network call. It exits
nonzero, and changes nothing else, if any check fails.

**Recorded check.** `--rehearse` runs the same function on a `git archive` of
a commit in a temporary directory. It adds the ignored queue zip copy and
deletes the directory afterwards. It compares before/after hashes of the
queue and of every watched record.

```text
$ PYTHONPATH=. uv run --no-sync python ledger/evidence/pra281-invsqrt-port/rollback.py --rehearse --ref 8acc1196aad130e3500d6965352db95a77c3d95e
exit 0
withdrawn: ledger/queue/pra281-invsqrt-port.json (2dbb7977…), ledger/queue/pra281-invsqrt-port.zip (5c8db085…)
other 9 queue entries: before == after
selected: pra280-rustad, manifest a4737479…, archive 8e291840…, shipping_problems []
invsqrt: 17fc223d… → 75e8a0e2…; dqi unchanged: true; dfthcsos unchanged: true
preserved: 573 files byte-identical before/after (listing SHA-256 871dd188…),
  incl. D-PRA281-01.md 238e7528…, candidate manifest 13cb6705…, 11 reservation files
reservation_or_upload: none
```

The full output is `rollback-check.json`. Outside staging, during the same run,
this worktree's reservation files and live queue pointer/zip hashes were
unchanged. Source commit `8acc119` is the candidate-record commit. The commit
that follows adds only this addendum, `rollback-check.json`, and a key rename and
the documented `PYTHONPATH=.` in `rollback.py`. Anyone can rerun the rehearsal at
any later head with `--ref <head>`.

Not checked: Kaggle hidden salts, public score, or deployment behaviour. No
reservation, upload, merge, push to main, forbidden-source read, licence
check, or live-stack action occurred.
