"""Reproducibility and ledger health checks.

Ported from qrc-thresher `src/qrc_thresher/proof/benchmark_health.py` (Apache-2.0,
https://github.com/clduab11/qrc-thresher). Kept: one function per check, each returning a dict
whose `status` is `"PASS"` or `"FAIL: <reason>"`, and an aggregate with an overall status.
Replaced: the reservoir-computing checks, with ledger checks and the R10 reproducibility check.

The reproducibility check (`rebuild_in_clean_worktree`) is the core of G5: it checks out
`generator_commit` into a fresh `git worktree`, runs each task's generator there, and compares
the SHA-256 of every output file with the hashes recorded in the manifest.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ledger.run_manifest import (
    GATE_IDS,
    REPO_ROOT,
    TASKS,
    GateRecord,
    Provenance,
    RunManifest,
    TaskRecord,
    create_manifest,
    read_manifest,
    sha256_file,
    write_manifest,
)

EXAMPLES_DIR = Path(__file__).resolve().parent / "examples"


def _hash_tree(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): sha256_file(p)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _expand(argv: list[str], **values: str) -> list[str]:
    return [arg.format(**values) for arg in argv]


def diff_hashes(expected: dict[str, str], actual: dict[str, str]) -> dict[str, list[str]]:
    return {
        "missing": sorted(set(expected) - set(actual)),
        "extra": sorted(set(actual) - set(expected)),
        "changed": sorted(k for k in set(expected) & set(actual) if expected[k] != actual[k]),
    }


def rebuild_in_clean_worktree(
    commit: str,
    generators: dict[str, list[str]],
    expected: dict[str, dict[str, str]],
    *,
    repo: Path = REPO_ROOT,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Re-run each task's generator at `commit` in a fresh worktree and compare file hashes.

    `generators[task]` is an argv list run from the worktree root; `{out}` expands to an empty
    output directory for that task, `{python}` to this interpreter and `{worktree}` to the
    worktree root. Output paths are compared relative to `{out}`, so a generator must write the
    same relative paths that appear in the manifest's `files` (for example `dfthcsos/angle_k_0.kmb`).
    """
    if not re.fullmatch(r"[0-9a-f]{40}", commit or ""):
        return {"status": f"FAIL: generator commit {commit!r} is not a clean 40-hex commit"}
    missing = sorted(set(expected) - set(generators))
    if missing:
        return {"status": f"FAIL: no generator configured for {', '.join(missing)}"}
    tmp = Path(tempfile.mkdtemp(prefix="ledger-rebuild-"))
    worktree = tmp / "worktree"
    tasks: dict[str, Any] = {}
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), commit],
            cwd=repo, capture_output=True, text=True, check=True,
        )
        for task in expected:
            out = tmp / "out" / task
            out.mkdir(parents=True)
            argv = _expand(generators[task], out=str(out), python=sys.executable,
                           worktree=str(worktree))
            proc = subprocess.run(
                argv, cwd=worktree, capture_output=True, text=True, timeout=timeout_seconds,
                env={**os.environ, "PYTHONHASHSEED": "0"}, check=False,
            )
            actual = _hash_tree(out)
            diffs = diff_hashes(expected[task], actual)
            identical = proc.returncode == 0 and not any(diffs.values())
            tasks[task] = {
                "identical": identical,
                "returncode": proc.returncode,
                "argv": argv,
                "diffs": diffs,
                "stderr_tail": proc.stderr[-2000:],
            }
    except (OSError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", "") or ""
        return {"status": f"FAIL: {exc} {detail}".strip(), "commit": commit, "tasks": tasks}
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(worktree)],
                       cwd=repo, capture_output=True, text=True, check=False)
        shutil.rmtree(tmp, ignore_errors=True)
        # If the remove failed, drop the stale .git/worktrees entry too.
        subprocess.run(["git", "worktree", "prune"], cwd=repo, capture_output=True, text=True,
                       check=False)
    bad = [t for t, r in tasks.items() if not r["identical"]]
    status = "PASS" if not bad else f"FAIL: rebuild differs for {', '.join(bad)}"
    return {"status": status, "commit": commit, "tasks": tasks}


# --- Ledger self-checks -----------------------------------------------------------------------


def _sample_tasks() -> dict[str, TaskRecord]:
    return {
        t: TaskRecord(task=t, provenance=Provenance(licence="own"), files={f"{t}.kmb": "0" * 64},
                      cost=2.0, baseline_cost=4.0, measured=True)
        for t in TASKS
    }


def check_manifest_roundtrip() -> dict[str, Any]:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = create_manifest(candidate_id="health-check", tasks=_sample_tasks())
            path = write_manifest(manifest, Path(tmp) / "m.json")
            ok = read_manifest(path) == manifest and manifest.geometric_mean == 2.0
            return {"status": "PASS" if ok else "FAIL: round trip changed the manifest"}
    except Exception as exc:
        return {"status": f"FAIL: {exc}"}


def check_scorecard_cap() -> dict[str, Any]:
    from ledger.scorecard import DAILY_CAP, SubmissionCapExceeded, record_submission

    try:
        with tempfile.TemporaryDirectory() as tmp:
            candidate = create_manifest(candidate_id="health-check", tasks=_sample_tasks(),
                                        zip_sha256="0" * 64)
            candidate.gates += [GateRecord(gate=g, status="PASS", timestamp_utc="",
                                           zip_sha256=candidate.zip_sha256) for g in GATE_IDS]
            now = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
            for i in range(DAILY_CAP):
                record_submission(candidate, f"k{i}", root=Path(tmp), now=now)
            try:
                record_submission(candidate, "k-over", root=Path(tmp), now=now)
                return {"status": "FAIL: a fourth submission was recorded"}
            except SubmissionCapExceeded:
                pass
            record_submission(candidate, "k-next-day", root=Path(tmp), now=now + timedelta(days=1))
            return {"status": "PASS"}
    except Exception as exc:
        return {"status": f"FAIL: {exc}"}


def check_gate_config() -> dict[str, Any]:
    try:
        from ledger.gates.runner import DEFAULT_CONFIG, load_config

        config = load_config(DEFAULT_CONFIG)
        return {"status": "PASS", "gates": [g.id for g in config.gates]}
    except Exception as exc:
        return {"status": f"FAIL: {exc}"}


def check_examples() -> dict[str, Any]:
    try:
        paths = sorted(EXAMPLES_DIR.glob("*.json"))
        if not paths:
            return {"status": "FAIL: no example manifests"}
        for path in paths:
            read_manifest(path)
        return {"status": "PASS", "examples": [p.name for p in paths]}
    except Exception as exc:
        return {"status": f"FAIL: {exc}"}


def run_benchmark_health(
    manifest: RunManifest | None = None,
    generators: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Run every check; with a manifest and generator commands, also the rebuild check."""
    checks: dict[str, Any] = {
        "manifest_roundtrip": check_manifest_roundtrip(),
        "scorecard_cap": check_scorecard_cap(),
        "gate_config": check_gate_config(),
        "examples": check_examples(),
    }
    if manifest is not None and generators is not None:
        checks["reproducibility"] = rebuild_in_clean_worktree(
            manifest.generator_commit, generators, {t: r.files for t, r in manifest.tasks.items()}
        )
    overall = all(v.get("status") == "PASS" for v in checks.values())
    return {
        "checks": {k: v.get("status", "FAIL") for k, v in checks.items()},
        "details": checks,
        "overall": "PASS" if overall else "FAIL",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ledger health and reproducibility checks")
    parser.add_argument("--manifest", type=Path, help="candidate manifest to rebuild")
    parser.add_argument("--config", type=Path, help="gate config with the generator commands")
    args = parser.parse_args(argv)
    manifest = generators = None
    if args.manifest:
        from ledger.gates.runner import DEFAULT_CONFIG, load_config

        manifest = read_manifest(args.manifest)
        generators = load_config(args.config or DEFAULT_CONFIG).generators
    report = run_benchmark_health(manifest, generators)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
