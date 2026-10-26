# SPDX-License-Identifier: Apache-2.0
"""Summarise a search run: iterations, stage pass rates, best ratio, tokens and dollars per iteration.

    uv run python search/stats.py search/runs/<run> [--json]

Reads <run>/evals/*.json (one per evaluation, written by search/evaluator.py), <run>/llm_calls.jsonl
(one per LLM call, written by search/providers.py), <run>/launches.jsonl and the newest checkpoint.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def latest_checkpoint(run: Path) -> Path | None:
    checkpoints = [p for p in (run / "checkpoints").glob("checkpoint_*") if p.name.rsplit("_", 1)[-1].isdigit()]
    return max(checkpoints, key=lambda p: int(p.name.rsplit("_", 1)[-1])) if checkpoints else None


def summarise(run: Path) -> dict[str, Any]:
    evals = []
    for path in sorted((run / "evals").glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(record, dict) and isinstance(record.get("metrics"), dict) and "timestamp" in record:
            evals.append(record)
    calls = read_jsonl(run / "llm_calls.jsonl")
    launches = read_jsonl(run / "launches.jsonl")
    checkpoint = latest_checkpoint(run)
    summary: dict[str, Any] = {"run": str(run), "launches": launches, "checkpoint": str(checkpoint) if checkpoint else None}

    iterations = None
    programs: list[dict[str, Any]] = []
    if checkpoint:
        try:
            metadata = json.loads((checkpoint / "metadata.json").read_text(encoding="utf-8"))
            iterations = int(metadata.get("last_iteration") or 0)
        except (OSError, ValueError):
            pass
        for path in (checkpoint / "programs").glob("*.json"):
            try:
                programs.append(json.loads(path.read_text(encoding="utf-8")))
            except ValueError:
                continue
    summary["iterations_completed"] = iterations
    summary["programs_in_checkpoint"] = len(programs)

    n = len(evals)
    stage1 = [e for e in evals if e["metrics"].get("stage1_passed", 0) >= 1]
    reached2 = [e for e in evals if e["metrics"].get("stage_reached", 0) >= 2]
    stage2 = [e for e in evals if e["metrics"].get("stage2_passed", 0) >= 1]
    reached3 = [e for e in evals if e["metrics"].get("stage_reached", 0) >= 3]
    stage3 = [e for e in evals if e["metrics"].get("stage3_passed", 0) >= 1]

    def rate(part: list, whole: list) -> float | None:
        return round(len(part) / len(whole), 3) if whole else None

    summary["evaluations"] = {
        "count": n,
        "stage1_build_pass": {"passed": len(stage1), "of": n, "rate": rate(stage1, evals)},
        "stage2_reduced_verifier_pass": {"passed": len(stage2), "of": len(reached2), "rate": rate(stage2, reached2)},
        "stage3_full_verifier_pass": {"passed": len(stage3), "of": len(reached3), "rate": rate(stage3, reached3)},
        "fully_verified_rate_overall": rate(stage3, evals),
        "mean_build_seconds": round(statistics.fmean(e.get("build_seconds", 0) for e in evals), 1) if evals else None,
        "wall_seconds": round(max(e["timestamp"] for e in evals) - min(e["timestamp"] for e in evals), 0) if n > 1 else 0,
    }
    verified = sorted(stage3, key=lambda e: -e["metrics"]["ratio"])
    if verified:
        best = verified[0]
        summary["best_verified"] = {"ratio": best["metrics"]["ratio"], "t": best["metrics"]["t"],
                                    "q": best["metrics"]["q"], "program_sha256": best.get("program_sha256"),
                                    "summary": best.get("summary", "").splitlines()[-1:]}
        summary["distinct_verified_ratios"] = sorted({round(e["metrics"]["ratio"], 6) for e in stage3}, reverse=True)[:10]
    else:
        summary["best_verified"] = None
    failure_reasons: dict[str, int] = defaultdict(int)
    for e in evals:
        for problem in e.get("problems") or []:
            failure_reasons[problem.split(":")[0][:80]] += 1
    summary["stage1_failure_reasons"] = dict(sorted(failure_reasons.items(), key=lambda kv: -kv[1])[:10])

    by_model: dict[str, dict[str, Any]] = {}
    for call in calls:
        key = f"{call.get('provider')}/{call.get('model')}"
        row = by_model.setdefault(key, {"calls": 0, "ok": 0, "rate_limited": 0, "prompt_tokens": 0,
                                        "completion_tokens": 0, "total_tokens": 0, "cost_usd": 0.0, "seconds": []})
        row["calls"] += 1
        row["ok"] += 1 if call.get("ok") else 0
        row["rate_limited"] += 1 if call.get("rate_limited") else 0
        row["prompt_tokens"] += int(call.get("prompt_tokens") or 0)
        row["completion_tokens"] += int(call.get("completion_tokens") or 0)
        row["total_tokens"] += int(call.get("total_tokens") or 0)
        row["cost_usd"] += float(call.get("cost_usd") or 0.0)
        if call.get("seconds") is not None:
            row["seconds"].append(float(call["seconds"]))
        if call.get("rate_limit_used_percent") is not None:
            row["last_rate_limit_used_percent"] = call["rate_limit_used_percent"]
    for row in by_model.values():
        row["mean_seconds"] = round(statistics.fmean(row["seconds"]), 1) if row["seconds"] else None
        row["mean_prompt_tokens"] = round(row["prompt_tokens"] / row["calls"]) if row["calls"] else None
        row["mean_completion_tokens"] = round(row["completion_tokens"] / row["calls"]) if row["calls"] else None
        row["cost_usd"] = round(row["cost_usd"], 4)
        del row["seconds"]
    summary["llm_calls_by_model"] = by_model
    total_tokens = sum(r["total_tokens"] for r in by_model.values())
    total_cost = sum(r["cost_usd"] for r in by_model.values())
    # One generation attempt per iteration: first attempts count iterations the checkpoint has not recorded yet.
    attempted = sum(1 for c in calls if int(c.get("attempt") or 1) == 1)
    denominator = max(iterations or 0, attempted, 1)
    summary["per_iteration"] = {"iterations": denominator, "total_tokens": round(total_tokens / denominator),
                                "cost_usd_list_price": round(total_cost / denominator, 4),
                                "llm_calls": round(len(calls) / denominator, 2)}
    return summary


def render(summary: dict[str, Any]) -> str:
    ev = summary["evaluations"]
    lines = [f"run: {summary['run']}", f"checkpoint: {summary['checkpoint']}",
             f"iterations completed: {summary['iterations_completed']}  programs in checkpoint: {summary['programs_in_checkpoint']}",
             f"evaluations: {ev['count']}  wall {ev['wall_seconds']} s  mean build {ev['mean_build_seconds']} s", "",
             "| stage | passed | of | rate |", "|---|---:|---:|---:|"]
    for name in ("stage1_build_pass", "stage2_reduced_verifier_pass", "stage3_full_verifier_pass"):
        row = ev[name]
        lines.append(f"| {name} | {row['passed']} | {row['of']} | {row['rate']} |")
    lines.append(f"\nfully verified overall: {ev['fully_verified_rate_overall']}")
    best = summary.get("best_verified")
    lines.append(f"best verified ratio: {best['ratio']:.6f} (T {best['t']:.0f}, Q {best['q']:.0f})" if best
                 else "best verified ratio: none yet")
    if summary.get("distinct_verified_ratios"):
        lines.append("verified ratios: " + ", ".join(f"{r:.6f}" for r in summary["distinct_verified_ratios"]))
    if summary["stage1_failure_reasons"]:
        lines.append("stage-1 failure reasons: " + json.dumps(summary["stage1_failure_reasons"]))
    lines += ["", "| provider/model | calls | ok | throttled | mean prompt tok | mean completion tok | total tok | cost USD (list) | mean s |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for key, row in summary["llm_calls_by_model"].items():
        lines.append(f"| {key} | {row['calls']} | {row['ok']} | {row['rate_limited']} | {row['mean_prompt_tokens']} | "
                     f"{row['mean_completion_tokens']} | {row['total_tokens']} | {row['cost_usd']} | {row['mean_seconds']} |")
    per = summary["per_iteration"]
    lines.append(f"\nper iteration ({per['iterations']} iterations): {per['total_tokens']} tokens, "
                 f"{per['llm_calls']} LLM calls, ${per['cost_usd_list_price']} list price")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    summary = summarise(args.run)
    print(json.dumps(summary, indent=1, default=str) if args.json else render(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
