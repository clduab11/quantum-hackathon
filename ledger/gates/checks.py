"""The G0–G5 checks the runner calls. Each takes a GateContext and returns a dict whose `status`
is "PASS" or "FAIL: <reason>".

G0–G3 delegate to hooks owned by other work units and named in `configs/gates/*.yaml`:

- G0 `ledger.gates.g0_preflight:preflight(submission_dir)` — P0-4 (PRA-174), metric-only checks.
- G1 / G2 `tasks.<task>.gates:g1_smoke(submission_dir)` / `g2_proxy(submission_dir)` — the
  generator owners (P0-6 invsqrt numpy mirror, P0-7 dqi and dfthcsos).
- G3 `harness.score_local:score_submission(submission_dir, salt_label=, shot_divisor=1)` — P0-4.

G4 (strict improvement) and G5 (clean rebuild + provenance) are implemented here.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

from ledger.archive import build_zip
from ledger.benchmark_health import rebuild_in_clean_worktree
from ledger.evidence import classify_submission, collect_verifier_evidence
from ledger.gates.runner import GateContext, resolve
from ledger.run_manifest import SHIPPABLE_LICENCES, TASKS, load_manifests, sha256_file
from ledger.scorecard import best_geometric_mean


def _status_ok(result: Any) -> bool:
    return isinstance(result, dict) and result.get("status") == "PASS"


def g0_preflight(ctx: GateContext) -> dict[str, Any]:
    """P0-4's `preflight(root)` raises ValueError on rejection and returns the parsed circuits on
    success; a hook may instead return a status dict. Both forms are accepted. Parsed circuits
    are not stored (they are not JSON and can be large)."""
    result = resolve(ctx.params["hook"])(ctx.submission_dir)
    if isinstance(result, dict) and "status" in result:
        return result
    return {"status": "PASS"}


def per_task(ctx: GateContext) -> dict[str, Any]:
    """Run one hook per task; every task must PASS. A task with no hook configured fails."""
    hooks: dict[str, str] = ctx.params.get("hooks", {})
    results: dict[str, Any] = {}
    for task in TASKS:
        if task not in hooks:
            results[task] = {"status": f"FAIL: no {ctx.spec.id} hook configured for {task}"}
            continue
        try:
            results[task] = resolve(hooks[task])(ctx.submission_dir)
        except Exception as exc:
            results[task] = {"status": f"FAIL: {type(exc).__name__}: {exc}"}
    failed = [t for t in TASKS if not _status_ok(results[t])]
    if failed:
        reasons = "; ".join(f"{t}: {results[t].get('status')}" for t in failed)
        return {"status": f"FAIL: {reasons}", "tasks": results}
    return {"status": "PASS", "tasks": results}


def g3_full_verifier(ctx: GateContext) -> dict[str, Any]:
    """Full local verification at full shot counts; folds the results into the manifest."""
    result = resolve(ctx.params["hook"])(
        ctx.submission_dir, salt_label=ctx.config.salt_label, shot_divisor=1
    )
    if not _status_ok(result):
        return {"status": result.get("status", "FAIL: verifier returned no status"),
                "result": result}
    summaries = result.get("tasks", {})
    expected = ctx.params.get("expected_shots", {})
    problems = []
    for task in TASKS:
        summary = summaries.get(task)
        if not _status_ok(summary):
            problems.append(f"{task}: {summary.get('status') if summary else 'missing'}")
        elif task in expected and summary.get("verified_shots") != expected[task]:
            problems.append(
                f"{task}: {summary.get('verified_shots')} shots, expected {expected[task]}"
            )
    if problems:
        return {"status": "FAIL: " + "; ".join(problems), "result": result}
    manifest = ctx.manifest
    manifest.kickmix_build_id = result.get("kickmix_build_id") or manifest.kickmix_build_id
    manifest.qualtran_pin = result.get("qualtran_pin") or manifest.qualtran_pin
    manifest.salt_label = ctx.config.salt_label
    digest = collect_verifier_evidence(
        manifest,
        ctx.spec.id,
        {t: summaries[t] for t in TASKS},
        verifier_hashes=result.get("verifier_hashes"),
        baseline_costs=result.get("baseline_costs"),
        commands=result.get("commands", []),
        root=ctx.evidence_root,
    )
    return {"status": "PASS", "evidence_sha256": digest,
            "geometric_mean": manifest.geometric_mean}


def g4_strict_improvement(ctx: GateContext) -> dict[str, Any]:
    """The measured geometric mean must beat the parent's and the best archived candidate's."""
    manifest = ctx.manifest
    gm = manifest.geometric_mean
    if not manifest.is_measured() or gm is None:
        return {"status": "FAIL: candidate has no measured geometric mean (run G3 first)"}
    archive = [m for m in load_manifests(ctx.manifests_root) if m.kind == "candidate"]
    details: dict[str, Any] = {"geometric_mean": gm}
    if manifest.parent_candidate_id:
        parent = next((m for m in archive if m.candidate_id == manifest.parent_candidate_id), None)
        if parent is None or parent.geometric_mean is None or not parent.is_measured():
            return {"status": f"FAIL: parent {manifest.parent_candidate_id} has no measured "
                              "geometric mean in the ledger"}
        details["parent"] = parent.geometric_mean
        if not gm > parent.geometric_mean:
            return {"status": f"FAIL: {gm:.6f} does not beat parent "
                              f"{parent.geometric_mean:.6f}", **details}
    best = best_geometric_mean(archive, exclude=manifest.candidate_id)
    if best is not None:
        details["archive_best"] = {"candidate_id": best[0], "geometric_mean": best[1]}
        if not gm > best[1]:
            return {"status": f"FAIL: {gm:.6f} does not beat archive best {best[1]:.6f} "
                              f"({best[0]})", **details}
    return {"status": "PASS", **details}


def provenance_problems(ctx: GateContext) -> list[str]:
    manifest = ctx.manifest
    problems = []
    commit = manifest.generator_commit
    if not re.fullmatch(r"[0-9a-f]{40}", commit or ""):
        problems.append(f"generator commit {commit!r} is not a clean 40-hex commit")
    for task in TASKS:
        record = manifest.tasks.get(task)
        if record is None:
            problems.append(f"{task}: no task record")
            continue
        licence = record.provenance.licence
        if licence not in SHIPPABLE_LICENCES:
            problems.append(f"{task}: licence {licence!r} cannot be shipped (R10)")
        if licence != "own" and not record.provenance.parent_url:
            problems.append(f"{task}: {licence} parent has no URL")
    return problems


def g5_rebuild_and_provenance(ctx: GateContext) -> dict[str, Any]:
    """R10: provenance is shippable, the zip holds exactly the manifest's files, the zip is the
    deterministic build of those files, and a clean worktree at `generator_commit` regenerates
    every file byte for byte. The generators see only the config's declared `inputs` (staged
    into an otherwise empty VQCC_DATA); an output that is a byte copy of a declared input is
    recorded as `copied`: a copied circuit fails the gate, a copied non-circuit input (the
    declared dfthcsos factorization) is accepted (PRA-211; D-PRA211-01, D-PRA211-05)."""
    manifest = ctx.manifest
    problems = provenance_problems(ctx)
    expected = {t: manifest.tasks[t].files for t in TASKS if t in manifest.tasks}
    if classify_submission(ctx.submission_dir) != expected:
        problems.append("zip contents differ from the manifest's file hashes")
    with tempfile.TemporaryDirectory(prefix="ledger-g5-") as tmp:
        rebuilt_zip = build_zip(ctx.submission_dir, Path(tmp) / "rebuilt.zip")
        if sha256_file(rebuilt_zip) != manifest.zip_sha256:
            problems.append("zip is not the deterministic build of its files "
                            "(build it with ledger.archive.build_zip)")
    rebuild: dict[str, Any] = {}
    if not problems:
        rebuild = rebuild_in_clean_worktree(
            manifest.generator_commit, ctx.config.generators, expected, repo=ctx.repo,
            timeout_seconds=ctx.params.get("timeout_seconds"), inputs=ctx.config.inputs,
            package_root=ctx.package_root,
        )
        if rebuild["status"] != "PASS":
            problems.append(rebuild["status"].removeprefix("FAIL: "))
    if problems:
        return {"status": "FAIL: " + "; ".join(problems), "rebuild": rebuild}
    return {"status": "PASS", "rebuild": rebuild}
