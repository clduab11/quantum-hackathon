# SPDX-License-Identifier: Apache-2.0
"""Promote stage-3-verified elites from an OpenEvolve checkpoint into hand-off folders.

    uv run python search/promote.py --checkpoint search/runs/<run>/checkpoints/checkpoint_40 \
        [--top 3] [--min-ratio 1.0] [--out search/handoff] [--dry-run]

Selection: among programs whose full official verification passed with ratio above --min-ratio, the
(T_total, Q_total) Pareto front plus the --top best ratios, one hand-off per distinct program. For each:

  1. rebuild the family from a clean `git worktree` of this repository at HEAD, with VQCC_DATA pointing at a
     staging directory that holds only the declared factor file (ledger.benchmark_health.stage_inputs, the
     G5 recipe) and PYTHONHASHSEED=0;
  2. check the rebuilt files are byte-identical to what the evaluator hashed during the search;
  3. run the full official verifier again (64 shots per address, the fixed public salt);
  4. write search/handoff/<id>/ with program.py, outputs/dfthcsos/*, verifier.json, rebuild.json, metrics.json,
     artifacts.json, sha256s.json, a draft candidate manifest built with ledger/run_manifest.py (salt label
     from configs/gates/default.yaml) and HANDOFF.md.

It also prints ``DISCOVERY:`` lines, the verified rows for READY hand-offs and at most three negative
results (the most promising programs the official verifier rejected, one per distinct rejection), and
appends them to ``<run>/discovery_lines.md``. search/DISCOVERY.md itself stays hand-curated: paste from there.

promote.py touches no register, queue or manifest directory and commits nothing: shipping stays with
Paperclip and the board (AGENTS.md). Hand-off folders hold .kmb/.npz binaries and are git-ignored.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

SEARCH_DIR = Path(__file__).resolve().parent
REPO_ROOT = SEARCH_DIR.parent
for path in (str(REPO_ROOT), str(SEARCH_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import evaluator  # noqa: E402  (sibling module: verifier wrapper, factor config, constants)
from ledger.benchmark_health import diff_hashes, stage_inputs  # noqa: E402
from ledger.gates.runner import DEFAULT_CONFIG, load_config as load_gate_config  # noqa: E402
from ledger.run_manifest import (  # noqa: E402
    Provenance, TaskRecord, create_manifest, kickmix_build_id, sha256_file, write_manifest,
)


# --- selection -----------------------------------------------------------------------------------


def load_checkpoint(checkpoint: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    metadata = json.loads((checkpoint / "metadata.json").read_text(encoding="utf-8"))
    programs = []
    for path in sorted((checkpoint / "programs").glob("*.json")):
        try:
            program = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        program["_checkpoint"] = str(checkpoint)  # lets family_key find artifact files stored beside the program
        programs.append(program)
    return metadata, programs


def pareto_front(points: list[dict[str, Any]], keys: tuple[str, str] = ("t", "q")) -> list[dict[str, Any]]:
    """Programs not dominated on the two metrics named by ``keys`` (both minimised)."""
    front = []
    for candidate in points:
        cm = candidate["metrics"]
        dominated = False
        for other in points:
            if other is candidate:
                continue
            om = other["metrics"]
            if all(om[k] <= cm[k] for k in keys) and any(om[k] < cm[k] for k in keys):
                dominated = True
                break
        if not dominated:
            front.append(candidate)
    return front


def family_key(program: dict[str, Any]) -> str:
    """One hand-off per verified family: same ratio, T_total, Q_total, J and brot.

    OpenEvolve's island migration copies a program under a new id without its artifacts, and the model
    rewrites NOTES on every iteration, so neither output hashes nor code identify a family reliably; the
    verified result does, and two programs that tie on all of it would be redundant hand-offs anyway.
    """
    m = program.get("metrics") or {}
    return json.dumps([round(float(m.get("ratio", 0.0)), 9), m.get("t"), m.get("q"), m.get("batch_size"), m.get("brot")])


def select_elites(programs: list[dict[str, Any]], top: int = 3, min_ratio: float = 1.0) -> list[dict[str, Any]]:
    """Stage-3-verified programs above ``min_ratio``: the best ratios first, then the rest of the front.

    One hand-off per distinct family (``family_key``); the earliest program found wins a tie.
    """
    verified: dict[str, dict[str, Any]] = {}
    for program in sorted(programs, key=lambda p: (p.get("iteration_found") or 0, p.get("id", ""))):
        metrics = program.get("metrics") or {}
        if metrics.get("stage3_passed", 0) < 1 or metrics.get("ratio", 0) <= min_ratio:
            continue
        key = family_key(program)
        if key not in verified or metrics["ratio"] > verified[key]["metrics"]["ratio"]:
            verified[key] = program
    pool = sorted(verified.values(), key=lambda p: -p["metrics"]["ratio"])
    chosen = pool[:top]
    for program in pareto_front(pool):
        if program not in chosen:
            chosen.append(program)
    return chosen


# --- rebuild -------------------------------------------------------------------------------------


def git_head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()


def clean_rebuild(code: str, expected: dict[str, str], factor: dict[str, Any], *, timeout: float = 900.0) -> dict[str, Any]:
    """Run ``code`` in a detached worktree at HEAD against the staged declared input; compare hashes.

    Returns the rebuild record; ``record["out_dir"]`` holds the rebuilt files until ``cleanup(record)``.
    """
    commit = git_head()
    tmp = Path(tempfile.mkdtemp(prefix="search-promote-"))
    worktree, staging, out = tmp / "worktree", tmp / "package", tmp / "out"
    record: dict[str, Any] = {"status": "FAIL: not run", "commit": commit, "tmp": str(tmp), "out_dir": str(out)}
    try:
        staging.mkdir()
        rel = factor["package_relative_path"]
        staged = stage_inputs({"dfthcsos": [{"path": rel, "sha256": factor["sha256"]}]}, staging,
                              package_root=Path(os.environ.get("VQCC_DATA", evaluator.DEFAULT_DATA)))
        subprocess.run(["git", "worktree", "add", "--detach", str(worktree), commit], cwd=REPO_ROOT,
                       capture_output=True, text=True, check=True)
        program = tmp / "program.py"
        program.write_text(code, encoding="utf-8")
        out.mkdir()
        argv = [sys.executable, str(program), "--out", str(out), "--factorization", str(staging / rel),
                "--source-brot", str(factor["source_brot"])]
        proc = subprocess.run(argv, cwd=worktree, capture_output=True, text=True, timeout=timeout,
                              env={**os.environ, "PYTHONPATH": str(worktree), "QH_REPO_ROOT": str(worktree),
                                   "VQCC_DATA": str(staging), "PYTHONHASHSEED": "0"})
        actual = {p.relative_to(out).as_posix(): sha256_file(p) for p in sorted(out.rglob("*")) if p.is_file()}
        diffs = diff_hashes(expected, actual)
        copied = {rel_path: staged[digest] for rel_path, digest in actual.items() if digest in staged}
        identical = proc.returncode == 0 and not any(diffs.values())
        record.update(identical=identical, returncode=proc.returncode, argv=argv, diffs=diffs, copied=copied,
                      inputs=staged, files=actual, stderr_tail=proc.stderr[-2000:],
                      status="PASS" if identical else "FAIL: rebuilt files differ from the search evaluation")
        if proc.returncode == 0 and not expected:
            record["status"] = "FAIL: the checkpoint recorded no file hashes for this program"
    except Exception as exc:  # noqa: BLE001 - recorded, not raised: the hand-off says what failed
        record["status"] = f"FAIL: {type(exc).__name__}: {exc}"
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=REPO_ROOT,
                       capture_output=True, text=True, check=False)
        subprocess.run(["git", "worktree", "prune"], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    return record


def cleanup(record: dict[str, Any]) -> None:
    shutil.rmtree(record.get("tmp", ""), ignore_errors=True)


# --- hand-off ------------------------------------------------------------------------------------


def program_artifacts(program: dict[str, Any], checkpoint: Path) -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    if program.get("artifacts_json"):
        try:
            artifacts.update(json.loads(program["artifacts_json"]))
        except ValueError:
            pass
    artifact_dir = program.get("artifact_dir")
    if artifact_dir:
        for candidate in (Path(artifact_dir), checkpoint / "artifacts" / program["id"]):
            if candidate.is_dir():
                for path in sorted(candidate.iterdir()):
                    if path.is_file() and path.stat().st_size < 1 << 20:
                        artifacts.setdefault(path.name, path.read_text(encoding="utf-8", errors="replace"))
                break
    return artifacts


def expected_files(artifacts: dict[str, Any]) -> dict[str, str]:
    files = artifacts.get("files")
    if isinstance(files, str):
        try:
            files = json.loads(files)
        except ValueError:
            files = {}
    return {str(k): str(v) for k, v in (files or {}).items()}


def _last_note(code: str) -> str:
    notes = [line.strip() for line in evaluator.extract_notes(code).splitlines() if line.strip()]
    last = notes[-1] if notes else "(no NOTES line)"
    last = re.sub(r"^\d{4}-\d{2}-\d{2}:?\s*", "", last)  # the row carries its own date
    if len(last) > 140:
        last = last[:140].rsplit(" ", 1)[0] + " ..."
    return last


def discovery_entry(handoff_id: str, verifier: dict[str, Any], program: dict[str, Any]) -> str:
    return (f"| {time.strftime('%Y-%m-%d')} | search {handoff_id}: {_last_note(program['code'])} | "
            f"{verifier['toffoli_count']:,.0f} | {verifier['num_qubits']} | {verifier['ratio']:.6f} | "
            "search/promote.py, full verifier |")


# --- negative results ----------------------------------------------------------------------------


NEGATIVE_LINES_MAX = 3


def failure_reason(program: dict[str, Any]) -> str:
    """The verifier's rejection text for a program that reached stage 2 or 3 without passing."""
    artifacts: dict[str, Any] = {}
    raw = program.get("artifacts_json") or program.get("artifacts")
    if isinstance(raw, str):
        try:
            artifacts = json.loads(raw)
        except ValueError:
            artifacts = {}
    elif isinstance(raw, dict):
        artifacts = raw
    summary = str(artifacts.get("summary") or "")
    fails = [line.strip() for line in summary.splitlines() if "FAIL" in line]
    if fails:
        return fails[-1]
    metrics = program.get("metrics") or {}
    return f"stage {int(metrics.get('stage_reached') or 0)} reached without a pass"


def negative_candidates(programs: list[dict[str, Any]], limit: int = NEGATIVE_LINES_MAX) -> list[dict[str, Any]]:
    """Programs the official verifier rejected: stage 2 or 3 reached, stage 3 not passed.

    The most promising first (highest predicted ratio), one per distinct rejection text, at most
    ``limit``. These are the negatives worth a DISCOVERY line: layouts the model should not retry
    under the same assumptions.
    """
    chosen: list[dict[str, Any]] = []
    seen: set[str] = set()
    ordered = sorted(programs, key=lambda p: (-float((p.get("metrics") or {}).get("predicted_ratio") or 0.0),
                                              p.get("iteration_found") or 0, str(p.get("id", ""))))
    for program in ordered:
        metrics = program.get("metrics") or {}
        if metrics.get("stage_reached", 0) < 2 or metrics.get("stage3_passed", 0) >= 1:
            continue
        reason = failure_reason(program)
        if reason in seen:
            continue
        seen.add(reason)
        chosen.append(program)
        if len(chosen) >= limit:
            break
    return chosen


def negative_entry(program: dict[str, Any], run_name: str, checkpoint_name: str) -> str:
    """A negative-result line in the form of DISCOVERY.md's 'Negatives' section, with its assumption."""
    metrics = program.get("metrics") or {}
    reason = failure_reason(program)
    if len(reason) > 160:
        reason = reason[:160].rsplit(" ", 1)[0] + " ..."
    tag = f"search {run_name}-{checkpoint_name}-{str(program.get('id', ''))[:8]}"
    return (f"DISCOVERY: - {time.strftime('%Y-%m-%d')} {_last_note(program.get('code', ''))}: {reason} ({tag}; "
            f"predicted ratio {float(metrics.get('predicted_ratio') or 0.0):.4f}, J {int(metrics.get('batch_size') or 0)}, "
            f"brot {int(metrics.get('brot') or 0)}). Assumes this run's declared factor, fixed salt and shot counts; "
            "the full official verifier is the judge.")


def emit_discovery_lines(run_dir: Path, checkpoint_name: str, lines: list[str]) -> Path | None:
    """Print ``DISCOVERY:`` lines and append them to ``<run>/discovery_lines.md``.

    search/DISCOVERY.md is never written here: it stays hand-curated.
    """
    for line in lines:
        print(line)
    if not lines:
        return None
    target = Path(run_dir) / "discovery_lines.md"
    try:
        with target.open("a", encoding="utf-8") as stream:
            stream.write(f"\n## {time.strftime('%Y-%m-%d %H:%M')} search/promote.py {checkpoint_name}\n\n")
            stream.write("\n".join(lines) + "\n")
    except OSError:
        return None
    return target


def write_handoff(program: dict[str, Any], checkpoint: Path, out_root: Path, factor: dict[str, Any],
                  *, force: bool = False) -> dict[str, Any]:
    run_name = checkpoint.parents[1].name if len(checkpoint.parents) > 1 else "run"
    handoff_id = f"{run_name}-{checkpoint.name}-{program['id'][:8]}"
    folder = out_root / handoff_id
    if folder.exists():
        if not force:
            return {"id": handoff_id, "status": "SKIP: hand-off folder exists (use --force)", "folder": str(folder)}
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    artifacts = program_artifacts(program, checkpoint)
    expected = expected_files(artifacts)
    (folder / "program.py").write_text(program["code"], encoding="utf-8")
    (folder / "program.sha256").write_text(sha256_file(folder / "program.py") + "\n", encoding="utf-8")
    (folder / "metrics.json").write_text(json.dumps({
        "program_id": program["id"], "parent_id": program.get("parent_id"), "generation": program.get("generation"),
        "iteration_found": program.get("iteration_found"), "metrics": program.get("metrics"),
        "metadata": program.get("metadata"), "checkpoint": str(checkpoint),
    }, indent=1, default=str) + "\n", encoding="utf-8")
    (folder / "artifacts.json").write_text(json.dumps(artifacts, indent=1, default=str) + "\n", encoding="utf-8")

    rebuild = clean_rebuild(program["code"], expected, factor)
    result: dict[str, Any] = {"id": handoff_id, "folder": str(folder), "rebuild": rebuild["status"]}
    verifier: dict[str, Any] | None = None
    try:
        out_dir = Path(rebuild["out_dir"])
        if (out_dir / "dfthcsos").is_dir() and any((out_dir / "dfthcsos").iterdir()):
            shutil.copytree(out_dir / "dfthcsos", folder / "outputs" / "dfthcsos")
            verifier = evaluator.verify_family(folder / "outputs" / "dfthcsos", evaluator.FULL_SHOTS)
            (folder / "verifier.json").write_text(json.dumps(verifier, indent=1, default=str) + "\n", encoding="utf-8")
    finally:
        cleanup(rebuild)
    rebuild = {k: v for k, v in rebuild.items() if k not in ("tmp", "out_dir")}
    (folder / "rebuild.json").write_text(json.dumps(rebuild, indent=1, default=str) + "\n", encoding="utf-8")

    verified = bool(verifier and verifier.get("status") == "PASS")
    recorded_ratio = float((program.get("metrics") or {}).get("ratio") or 0.0)
    matches = verified and abs(verifier["ratio"] - recorded_ratio) < 1e-9
    result.update(verifier=(verifier or {}).get("status", "not run"), ratio=(verifier or {}).get("ratio"),
                  matches_search_ratio=matches)

    status = "READY" if (rebuild["status"] == "PASS" and matches) else "NOT READY"
    manifest_path = None
    if verified:
        manifest_path = write_draft_manifest(folder, handoff_id, verifier, factor)
    sha256s = {p.relative_to(folder).as_posix(): {"sha256": sha256_file(p), "size": p.stat().st_size}
               for p in sorted(folder.rglob("*")) if p.is_file() and p.name != "sha256s.json"}
    (folder / "sha256s.json").write_text(json.dumps(sha256s, indent=1) + "\n", encoding="utf-8")
    (folder / "HANDOFF.md").write_text(handoff_text(handoff_id, status, program, checkpoint, rebuild, verifier,
                                                    recorded_ratio, manifest_path, factor), encoding="utf-8")
    result["status"] = status
    if verified:
        result["discovery_entry"] = discovery_entry(handoff_id, verifier, program)
    return result


def write_draft_manifest(folder: Path, handoff_id: str, verifier: dict[str, Any], factor: dict[str, Any]) -> Path:
    import dfthcsos.verify as official
    import kickmix
    gate_config = load_gate_config(DEFAULT_CONFIG)
    outputs = folder / "outputs"
    files = {p.relative_to(outputs).as_posix(): sha256_file(p) for p in sorted(outputs.rglob("*")) if p.is_file()}
    metrics = dict(verifier.get("metrics") or {})
    resources = verifier.get("resources") or {}
    metrics.update({k: resources[k] for k in ("angles_qubits", "persistent_qubits", "temporary_qubits") if k in resources})
    task = TaskRecord(
        task="dfthcsos",
        provenance=Provenance(licence="own", notes=(
            f"search/promote.py hand-off {handoff_id}: program.py (own, Apache-2.0) built from the declared "
            f"input {factor['package_relative_path']} sha256 {factor['sha256']}, shipped as a recorded copy "
            "when the circuits load the source precision (D-PRA211-05)")),
        files=files, verifier_sha256=sha256_file(Path(official.__file__)), shots=evaluator.FULL_VERIFIED_SHOTS,
        failures=None, num_qubits=int(verifier["num_qubits"]), toffoli_count=float(verifier["toffoli_count"]),
        cost=float(verifier["score"]), baseline_cost=evaluator.BASELINE_COST, measured=True, metrics=metrics,
        evidence=[sha256_file(folder / "verifier.json")],
    )
    manifest = create_manifest(
        candidate_id=f"search-{handoff_id}", tasks={"dfthcsos": task},
        kickmix_build_id=kickmix_build_id(Path(kickmix.__file__)), salt_label=gate_config.salt_label,
        repo=REPO_ROOT,
        notes=("DRAFT written by search/promote.py. Not a register entry: no zip, no G0-G5 record, invsqrt and "
               "dqi absent. A shipping agent copies program.py into tasks/dfthcsos/candidates/, declares it as the "
               "dfthcsos generator in a configs/gates/<candidate>.yaml and runs the gates on a full three-task zip."),
    )
    return write_manifest(manifest, folder / "manifest.draft.json")


def handoff_text(handoff_id: str, status: str, program: dict[str, Any], checkpoint: Path, rebuild: dict[str, Any],
                 verifier: dict[str, Any] | None, recorded_ratio: float, manifest_path: Path | None,
                 factor: dict[str, Any]) -> str:
    lines = [f"# Hand-off {handoff_id}", "", f"Status: **{status}**", "",
             f"- source: checkpoint `{checkpoint}`, program `{program['id']}` (iteration {program.get('iteration_found')}, "
             f"generation {program.get('generation')}, parent `{program.get('parent_id')}`)",
             f"- search-time full verification: ratio {recorded_ratio:.6f}",
             f"- clean rebuild at commit `{rebuild.get('commit')}`: {rebuild.get('status')}; copied declared inputs: "
             f"{json.dumps(rebuild.get('copied', {}))}"]
    if verifier and verifier.get("status") == "PASS":
        lines.append(f"- re-verified here: ratio {verifier['ratio']:.6f}, T_total {verifier['toffoli_count']:.0f}, "
                     f"Q_total {verifier['num_qubits']}, lambda_eff {verifier['lambda_eff']:.6f}, "
                     f"{verifier['verified_shots']} shots, salt {verifier['salt']}")
    elif verifier:
        lines.append(f"- re-verification FAILED: {verifier.get('error')}")
    else:
        lines.append("- re-verification not run (rebuild produced no files)")
    lines += ["", "## Contents", "",
              "- `program.py` the evolved generator (own code); `program.sha256`",
              "- `outputs/dfthcsos/angle_k_*.kmb`, `outputs/dfthcsos/submission.npz` the clean rebuild",
              "- `verifier.json` full official verifier result; `rebuild.json` the worktree rebuild record",
              "- `metrics.json`, `artifacts.json` what the search loop recorded",
              "- `sha256s.json` every file above",
              f"- `{manifest_path.name}` draft candidate manifest (ledger schema v1; dfthcsos only)" if manifest_path else
              "- no manifest draft (verification did not pass)",
              "", "## How a shipping agent consumes this", "",
              "1. Copy `program.py` to `tasks/dfthcsos/candidates/<candidate>.py` on an `op-vqcc/<topic>` branch "
              "cut from `main`; keep the EVOLVE markers and the NOTES docstring.",
              f"2. Declare it as the dfthcsos generator in `configs/gates/<candidate>.yaml` with the declared input "
              f"`{factor['package_relative_path']}` (sha256 `{factor['sha256']}`).",
              "3. Build the full three-task zip with the chosen invsqrt and dqi generators, then `python -m "
              "ledger.gates.runner new/run` for G0-G5. G4 must beat the parent candidate; G5 repeats this rebuild.",
              "4. One candidate, one pull request, merge-gate report in the body (AGENTS.md). The board merges; "
              "john-wick uploads.", "",
              "Nothing here is a register entry. This folder is git-ignored and may be deleted once consumed."]
    return "\n".join(lines) + "\n"


# --- CLI -----------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--checkpoint", type=Path, required=True, help="OpenEvolve checkpoint directory")
    parser.add_argument("--top", type=int, default=3, help="best ratios to promote besides the Pareto front")
    parser.add_argument("--min-ratio", type=float, default=1.0, help="promote only ratios above this")
    parser.add_argument("--out", type=Path, default=SEARCH_DIR / "handoff")
    parser.add_argument("--force", action="store_true", help="overwrite an existing hand-off folder")
    parser.add_argument("--dry-run", action="store_true", help="print the selection and stop")
    args = parser.parse_args(argv)
    checkpoint = args.checkpoint.resolve()
    if not (checkpoint / "metadata.json").is_file():
        print(f"not a checkpoint directory: {checkpoint}", file=sys.stderr)
        return 2
    metadata, programs = load_checkpoint(checkpoint)
    elites = select_elites(programs, top=args.top, min_ratio=args.min_ratio)
    print(f"{checkpoint}: {len(programs)} programs, last iteration {metadata.get('last_iteration')}, "
          f"{len(elites)} elite(s) above ratio {args.min_ratio}")
    for program in elites:
        m = program["metrics"]
        print(f"  {program['id'][:8]} ratio {m['ratio']:.6f} T {m['t']:.0f} Q {m['q']:.0f} iteration {program.get('iteration_found')}")
    run_dir = checkpoint.parents[1] if len(checkpoint.parents) > 1 else checkpoint.parent
    negatives = negative_candidates(programs)
    negative_lines = [negative_entry(p, run_dir.name, checkpoint.name) for p in negatives]
    print(f"{len(negative_lines)} negative result(s) for the run's discovery_lines.md (max {NEGATIVE_LINES_MAX})")
    if args.dry_run or not elites:
        emit_discovery_lines(run_dir, checkpoint.name, negative_lines)  # negatives need no rebuild
        return 0
    factor = evaluator.factor_config()
    results = []
    for program in elites:
        try:
            results.append(write_handoff(program, checkpoint, args.out, factor, force=args.force))
        except Exception as exc:  # noqa: BLE001 - one broken hand-off must not abort the others
            results.append({"id": program["id"][:8], "status": f"ERROR: {type(exc).__name__}: {exc}"})
    print(json.dumps(results, indent=1, default=str))
    ready = [r for r in results if r.get("status") == "READY"]
    if ready:
        print("\nDISCOVERY.md entries (paste under 'Verified results'):")
        for r in ready:
            print(r["discovery_entry"])
    print()
    emit_discovery_lines(run_dir, checkpoint.name,
                         [f"DISCOVERY: {r['discovery_entry']}" for r in ready] + negative_lines)
    failed = [r for r in results if not str(r.get("status", "")).startswith(("READY", "SKIP"))]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
