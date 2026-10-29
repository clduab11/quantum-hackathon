# SPDX-License-Identifier: Apache-2.0
"""Launch or resume the dfthcsos OpenEvolve search loop (see search/README.md).

    uv run python search/run.py --provider codex --iterations 40
    uv run python search/run.py --provider claude --output search/runs/claude-a --resume

The launcher installs the subscription providers (search/providers.py), composes the system prompt
from prompts/system_message.txt plus the current DISCOVERY.md, and always writes a final checkpoint when
the loop stops (OpenEvolve itself only checkpoints every ``checkpoint_interval`` iterations and skips the
final one on Ctrl-C or SIGTERM).
"""
from __future__ import annotations

import os

# OpenBLAS reads its thread count when numpy loads, so this must precede every import that pulls numpy
# (openevolve does). Two threads per worker keeps four parallel verifier runs from fighting over cores.
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "2")

import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import shutil  # noqa: E402
import signal  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

SEARCH_DIR = Path(__file__).resolve().parent
REPO_ROOT = SEARCH_DIR.parent
DEFAULT_DATA = "/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation"
for _path in (str(REPO_ROOT), str(SEARCH_DIR)):  # `providers` and `tasks` must import here and in the workers
    if _path not in sys.path:
        sys.path.insert(0, _path)

from openevolve import OpenEvolve  # noqa: E402
from openevolve.config import load_config  # noqa: E402

import providers  # noqa: E402


def checkpoint_number(path: Path) -> int | None:
    """Parse the integer suffix of a checkpoint directory name."""
    tail = path.name.rsplit("_", 1)[-1]
    return int(tail) if path.name.startswith("checkpoint_") and tail.isdigit() else None


def list_checkpoints(output: Path) -> list[Path]:
    """Complete checkpoints, oldest first; a ``.partial`` directory from an interrupted save is ignored."""
    found = [(checkpoint_number(p), p) for p in (output / "checkpoints").glob("checkpoint_*") if p.is_dir()]
    return [p for n, p in sorted((n, p) for n, p in found if n is not None)]


def latest_checkpoint(output: Path) -> Path | None:
    checkpoints = list_checkpoints(output)
    return checkpoints[-1] if checkpoints else None


def compose_system_message(prompt_dir: Path = SEARCH_DIR / "prompts",
                           discovery: Path = SEARCH_DIR / "DISCOVERY.md") -> str:
    base = (prompt_dir / "system_message.txt").read_text(encoding="utf-8")
    notes = discovery.read_text(encoding="utf-8").strip() if discovery.is_file() else "(no notes yet)"
    return base.replace("{discovery_notes}", notes)


def git_commit() -> str:
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True,
                               text=True, check=True).stdout.strip()
        return f"{head}-dirty" if dirty else head
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def save_exit_checkpoint(openevolve: OpenEvolve, output: Path) -> Path | None:
    """Write checkpoint_<last_iteration> atomically, replacing an interval checkpoint of the same number.

    OpenEvolve writes checkpoint_N as soon as iteration N completes, so iterations admitted out of order
    after it (N-1, N-2 with four workers) are missing from it; a resume from that directory would drop
    them. Signals are ignored while the save runs, and the directory is built as ``.partial`` and renamed
    into place, so a second Ctrl-C cannot leave a half-written checkpoint for --resume to pick up.
    """
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, signal.SIG_IGN)
    last = int(openevolve.database.last_iteration)
    if last <= 0:
        return None
    checkpoints = output / "checkpoints"
    final = checkpoints / f"checkpoint_{last}"
    partial = checkpoints / f"checkpoint_{last}.partial"
    shutil.rmtree(partial, ignore_errors=True)
    openevolve.database.save(str(partial), last)
    best = openevolve.database.get(openevolve.database.best_program_id) if openevolve.database.best_program_id else None
    best = best or openevolve.database.get_best_program()
    if best is not None:
        (partial / f"best_program{openevolve.file_extension}").write_text(best.code, encoding="utf-8")
        (partial / "best_program_info.json").write_text(json.dumps({
            "id": best.id, "generation": best.generation, "iteration": best.iteration_found,
            "current_iteration": last, "metrics": best.metrics, "language": best.language,
            "timestamp": best.timestamp, "saved_at": time.time()}, indent=2), encoding="utf-8")
    if final.exists():
        shutil.rmtree(final)
    os.replace(partial, final)
    return final


def prune_checkpoints(output: Path, keep: int) -> list[Path]:
    """Delete all but the newest ``keep`` complete checkpoints; returns what was removed."""
    checkpoints = list_checkpoints(output)
    removed = checkpoints[:-keep] if keep > 0 else []
    for path in removed:
        shutil.rmtree(path, ignore_errors=True)
    return removed


INITIAL_PROGRAMS = {
    "dfthcsos": SEARCH_DIR / "initial_program.py",
    "invsqrt": SEARCH_DIR / "initial_invsqrt.py",
    "dqi": SEARCH_DIR / "initial_dqi.py",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", choices=["invsqrt", "dfthcsos", "dqi"], default="dfthcsos",
                        help="which VQCC task adapter to drive (default: dfthcsos)")
    parser.add_argument("--smoke", action="store_true",
                        help="run stages 0/1/3 on the seed once (no LLM, no stage-2 official verify)")
    parser.add_argument("--smoke-repeats", type=int, default=1,
                        help="repeats for the smoke median timing (default: 1)")
    parser.add_argument("--provider", choices=["claude", "codex"], default=None,
                        help="claude = Claude Max via `claude -p`; codex = ChatGPT/Codex via `codex app-server`")
    parser.add_argument("--config", type=Path, help="OpenEvolve YAML (default search/config_<provider>.yaml)")
    parser.add_argument("--iterations", type=int, help="iterations to run now (default: config max_iterations)")
    parser.add_argument("--output", type=Path, help="run directory (default search/runs/<provider>-<timestamp>)")
    parser.add_argument("--checkpoint", type=Path, help="checkpoint directory to resume from")
    parser.add_argument("--resume", action="store_true", help="resume from the newest checkpoint under --output")
    parser.add_argument("--parallel", type=int, help="override evaluator.parallel_evaluations (= concurrent LLM calls)")
    parser.add_argument("--target-score", type=float, help="stop once combined_score reaches this ratio")
    parser.add_argument("--keep-checkpoints", type=int, default=None,
                        help="after the run, keep only the newest N checkpoints (default: keep all)")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default=None)
    return parser


def run_smoke(task: str, repeats: int = 1) -> int:
    """End-to-end smoke without providers: stages 0, 1, 3 on the seed program."""
    os.environ["SEARCH_SMOKE"] = "1"
    os.environ.setdefault("VQCC_DATA", DEFAULT_DATA)
    from search.staged import smoke_evaluate

    result = smoke_evaluate(task, repeats=repeats)
    med = result["median_seconds"]
    print(json.dumps(result, indent=1, default=str))
    print("\nTiming table (median seconds)")
    print("| task | stage0 | stage1 | stage3 | 0+1+3 | combined_score |")
    print("|---|---:|---:|---:|---:|---:|")
    print(
        f"| {task} | {med['stage0']:.3f} | {med['stage1']:.3f} | {med['stage3']:.3f} | "
        f"{med['stages_0_1_3']:.3f} | {result['combined_score']:.6f} |"
    )
    if med["stages_0_1_3"] >= 60.0:
        print(f"SMOKE FAIL: median stages 0+1+3 = {med['stages_0_1_3']:.3f}s >= 60s", file=sys.stderr)
        return 1
    if result["problems"]:
        print(f"SMOKE FAIL: problems={result['problems']}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse argv and either smoke-evaluate or launch OpenEvolve."""
    args = build_parser().parse_args(argv)
    os.environ["SEARCH_TASK"] = args.task
    if args.smoke:
        return run_smoke(args.task, repeats=args.smoke_repeats)
    if not args.provider:
        print("--provider is required unless --smoke is set", file=sys.stderr)
        return 2
    config_path = args.config or SEARCH_DIR / f"config_{args.provider}.yaml"
    config = load_config(str(config_path))
    installed = providers.install(config)
    if not installed:
        print(f"no supported provider in {config_path}: set llm.provider to claude_code or codex_app_server",
              file=sys.stderr)
        return 2
    if args.parallel:
        config.evaluator.parallel_evaluations = args.parallel
    if not config.prompt.template_dir or not Path(config.prompt.template_dir).is_dir():
        config.prompt.template_dir = str(SEARCH_DIR / "prompts")  # a copied YAML elsewhere still gets our templates
    config.prompt.system_message = compose_system_message()

    output = args.output or SEARCH_DIR / "runs" / f"{args.provider}-{time.strftime('%Y%m%d-%H%M%S')}"
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = args.checkpoint
    if args.resume and checkpoint is None:
        checkpoint = latest_checkpoint(output)
        if checkpoint is None:
            print(f"--resume: no checkpoint under {output}; starting fresh", file=sys.stderr)
    if checkpoint is not None and not checkpoint.is_dir():
        print(f"checkpoint directory not found: {checkpoint}", file=sys.stderr)
        return 2

    os.environ["SEARCH_RUN_DIR"] = str(output)
    os.environ["SEARCH_PROVIDER"] = args.provider
    os.environ.setdefault("VQCC_DATA", DEFAULT_DATA)

    launch = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "provider": args.provider, "config": str(config_path),
        "models": [{"name": m.name, "weight": m.weight, "provider": m.provider,
                    "reasoning_effort": m.reasoning_effort, "max_budget_usd": m.max_budget_usd}
                   for m in config.llm.models],
        "parallel_evaluations": config.evaluator.parallel_evaluations, "iterations": args.iterations,
        "checkpoint": str(checkpoint) if checkpoint else None, "generator_commit": git_commit(),
        "argv": sys.argv,
    }
    with (output / "launches.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(launch) + "\n")
    print(json.dumps(launch, indent=1))

    initial = INITIAL_PROGRAMS[args.task]
    # Route live OpenEvolve stages to the task-specific evaluator (dfthcsos
    # chemistry cascade, or invsqrt/dqi adapter cascade). Smoke uses staged.py.
    openevolve = OpenEvolve(initial_program_path=str(initial),
                            evaluation_file=str(SEARCH_DIR / "evaluate_entry.py"),
                            config=config, output_dir=str(output))
    if args.log_level:
        logging.getLogger().setLevel(getattr(logging, args.log_level))
    best = None
    try:
        best = asyncio.run(openevolve.run(iterations=args.iterations, target_score=args.target_score,
                                          checkpoint_path=str(checkpoint) if checkpoint else None))
    finally:
        final = save_exit_checkpoint(openevolve, output)
        if final is not None:
            print(f"exit checkpoint: {final}")
        if args.keep_checkpoints:
            for removed in prune_checkpoints(output, args.keep_checkpoints):
                print(f"pruned {removed}")
    newest = latest_checkpoint(output)
    print("\nsearch loop finished")
    if best is not None:
        print("best program metrics: " + json.dumps({k: v for k, v in best.metrics.items()
                                                    if k in ("combined_score", "ratio", "q", "t", "stage3_passed")}))
    if newest is not None:
        print(f"latest checkpoint: {newest}")
        print(f"resume with: uv run python search/run.py --provider {args.provider} --output {output} --resume")
    return 0


if __name__ == "__main__":
    sys.exit(main())
