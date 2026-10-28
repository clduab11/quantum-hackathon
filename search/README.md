# search/: evaluator-driven search loop (invsqrt, dfthcsos, dqi)

An [OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve) loop that evolves one Python
program per task. Fitness is the Deb-layered `combined_score` from research report §6.2 (infeasible band
`[0, 0.5)`, feasible band `[0.5, 1]` on log cost). MAP-Elites features are `log_toffoli` and `log_qubits`.
The staged evaluator (§6.4) runs parse/build → seeded sample → memoised official verify → cost score.
Nothing here ships: `promote.py` writes hand-off folders and Paperclip plus the board take it from there
(AGENTS.md).

```bash
uv run python -m search.run --task invsqrt --smoke
uv run python -m search.run --task dfthcsos --smoke
uv run python -m search.run --task dqi --smoke
uv run python -m search.run --task dfthcsos --provider codex --iterations 40
```

The design follows Gu, Kemeny, Yelin and Lukin (arXiv:2610.22367): islands, MAP-Elites over (T, Q),
a fresh model session per iteration with the parent program and the evaluator's feedback, archive elites in
the prompt, and discovery notes.

## Files

| file | role |
|---|---|
| `initial_program.py` | the seed program (Google's reference layout, ratio 1.0). Only the `EVOLVE-BLOCK` is evolvable: `BROT`, `BATCH_SIZE` and `build_family()`. The wrapper, the register contract and the output format are fixed |
| `evaluator.py` | OpenEvolve cascade: stage 1 build + static checks + G2 proxy, stage 2 verifier at 2 shots per address, stage 3 full verifier (64 shots per address, 254,464 shots), fixed public salt |
| `factor.yaml` | the declared factor input (path, SHA-256, precision). Swap in a better declared factor here |
| `config_claude.yaml` | OpenEvolve config for Claude Max via `claude -p` (sonnet 0.8 / opus 0.2, 2 concurrent calls) |
| `config_codex.yaml` | OpenEvolve config for the ChatGPT/Codex subscription via `codex app-server` (gpt-6-sol 0.8 / gpt-6-astra 0.2, medium effort, 4 concurrent calls) |
| `providers.py` | the two subscription providers (lean `claude -p`; a JSON-RPC client for `codex app-server`) |
| `prompts/` | system message and user template; `run.py` pastes `DISCOVERY.md` into the system message |
| `DISCOVERY.md` | append-only notes: facts, verified results, negatives with their assumptions, open directions |
| `run.py` | launcher: installs the providers, composes the prompt, runs or resumes the loop, checkpoints on exit |
| `promote.py` | takes stage-3-verified elites from a checkpoint, rebuilds each in a clean worktree, re-verifies, writes `handoff/<id>/` |
| `stats.py` | iterations, stage pass rates, best ratio, tokens and dollars per iteration per model for one run |

`search/runs/`, `search/handoff/` and `search/scratch/` are git-ignored (checkpoints, prompts, circuit binaries).

## Setup (WSL)

```bash
cd /home/cld-main/work/search/quantum-hackathon
uv sync                      # the `search` dependency group (openevolve 0.4.0) is a default group
uv run python scripts/install_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation
claude auth status           # Claude Max login (Claude Code CLI)
codex login status           # ChatGPT login (Codex CLI)
uv run pytest tests/test_search_loop.py
```

## Running

Codex carries the volume; Claude runs at low concurrency because the Max 5-hour limits bind.

```bash
# one-hour style session on Codex, 40 iterations, 4 concurrent turns and verifier runs
uv run python search/run.py --provider codex --iterations 40 --output search/runs/codex-a

# Claude Max, two concurrent `claude -p` calls (the ceiling the limits allow; do not raise it)
uv run python search/run.py --provider claude --iterations 20 --output search/runs/claude-a

# standing loop: no --iterations (config max_iterations is 100000); stop with Ctrl-C or SIGTERM
uv run python search/run.py --provider codex --output search/runs/codex-standing
```

Run the loop with `nohup ... &` or inside `tmux` for unattended sessions; it logs to
`<run>/logs/` and prints the resume command on exit.

### Knobs

| knob | where | default | note |
|---|---|---|---|
| concurrency (= concurrent LLM calls = concurrent verifier runs) | `evaluator.parallel_evaluations`, or `run.py --parallel N` | claude 2, codex 4 | one worker uses one core for the simulator plus one in-flight model call |
| models and weights | `llm.models` | sonnet 0.8 / opus 0.2; gpt-6-sol 0.8 / gpt-6-astra 0.2 | rewrites vs ideation by weight. The Codex catalog on 2026-10-25 has no `gpt-5.x-codex` slug; `gpt-5.6-*` are listed as older generation |
| per-call budget (Claude) | `max_budget_usd` per model | 2.00 / 6.00 | list-price cap the CLI enforces; Max is not billed per token |
| reasoning effort (Codex) | `llm.reasoning_effort` | medium | low, medium, high, xhigh |
| islands, migration, population | `database.*` | 3 islands, every 20 generations, 200 programs | |
| MAP-Elites features | `database.feature_dimensions` | `log_toffoli`, `log_qubits` | log-spaced (T, Q) cells |
| cascade | `evaluator.cascade_thresholds` | `[0.05, 0.5]` | stage 2 needs a near-feasible sample; feasible floor is 0.5. Mirrored by `STAGE1_THRESHOLD`/`STAGE2_THRESHOLD` in `evaluator.py` |
| stage timeouts | `evaluator.timeout` | 900 s per stage | OpenEvolve's outer limit. Inside it a build has 420 s (`SEARCH_BUILD_TIMEOUT`) and each verifier run, which runs in a child process so it can be killed, 600 s (`SEARCH_VERIFY_TIMEOUT`); the full verifier takes 35-60 s here |
| static size gates | `SEARCH_MAX_INSTRUCTIONS`, `SEARCH_MAX_STATIC_TOFFOLI` | 30M instructions, 400k static Toffolis | ten times the reference family; larger families fail stage 1 instead of occupying a worker for minutes |
| checkpoints | `checkpoint_interval`, `run.py --keep-checkpoints N` | 5, keep all | one more atomic checkpoint on exit; each holds every program with its prompts (about 50 KB per program), so prune on a standing loop |
| rate-limit back-off | `SEARCH_RATE_LIMIT_BACKOFF` (env) | 300 s | sleep when a provider reports a usage limit before retrying |
| declared factor | `factor.yaml` (`SEARCH_FACTOR_CONFIG` to point elsewhere) | Google's packaged `submission.npz` | SHA-256 checked before every build |
| scratch | `SEARCH_SCRATCH` | system temp | build outputs (~27 MB each) live here during an evaluation and are removed afterwards; `SEARCH_KEEP_OUTPUTS=1` keeps them |

### What the model sees

`prompts/system_message.txt` + `DISCOVERY.md` as the system message; the user message carries the parent
program, its metrics, the evaluator artifacts of the parent (summary, program report, G2 proxy, verifier
JSON, stderr), the island's top programs and inspirations from other cells. The reply is SEARCH/REPLACE
edits; edits outside the EVOLVE block are reverted (`enforce_evolve_blocks: true`).

## Resuming

Checkpoints land in `<run>/checkpoints/checkpoint_<iteration>/`. Kill the loop any time (Ctrl-C, SIGTERM,
or a reboot); OpenEvolve checkpoints every five iterations and `run.py` rewrites `checkpoint_<last>` on
exit with signals masked and an atomic rename, so iterations admitted out of order after an interval
checkpoint are kept and a half-written directory is never picked up (a `.partial` directory is ignored).

```bash
uv run python search/run.py --provider codex --output search/runs/codex-a --resume          # newest checkpoint
uv run python search/run.py --provider codex --output search/runs/codex-a --checkpoint search/runs/codex-a/checkpoints/checkpoint_40
```

A resumed run keeps the population, the islands, the archive, the MAP-Elites feature statistics and the
artifacts; the initial program is not re-added. Switching provider on resume is fine: the checkpoint is
provider-neutral.

## Reading a run

```bash
uv run python search/stats.py search/runs/codex-a            # iterations, pass rates, best ratio, tokens/$ per iteration
tail -f search/runs/codex-a/logs/*.log                        # OpenEvolve log
ls search/runs/codex-a/checkpoints/checkpoint_40/programs/    # every program with metrics, prompts and artifacts
```

`<run>/evals/*.json` has one record per evaluation; `<run>/llm_calls.jsonl` one per model call (tokens, cost,
seconds, the Codex account's rate-limit use).

## Hand-off (nothing ships from here)

```bash
uv run python search/promote.py --checkpoint search/runs/codex-a/checkpoints/checkpoint_40 --dry-run   # who would be promoted
uv run python search/promote.py --checkpoint search/runs/codex-a/checkpoints/checkpoint_40 --top 3
```

`promote.py` selects the stage-3-verified programs above ratio 1.0 (the (T, Q) Pareto front plus the best
ratios), rebuilds each one from a detached `git worktree` at `HEAD` with `VQCC_DATA` pointing at a staging
directory that holds only the declared factor file (the G5 recipe), checks the rebuilt files are
byte-identical to what the loop hashed, runs the full official verifier again, and writes
`search/handoff/<run>-<checkpoint>-<program>/` with `program.py`, `outputs/dfthcsos/*`, `verifier.json`,
`rebuild.json`, `metrics.json`, `artifacts.json`, `sha256s.json`, a draft candidate manifest
(`manifest.draft.json`, ledger schema v1, dfthcsos only, salt label from `configs/gates/default.yaml`) and
`HANDOFF.md`. It prints a `DISCOVERY.md` table row for each READY hand-off: paste it under "Verified results".

A shipping agent consumes a hand-off by copying `program.py` into `tasks/dfthcsos/candidates/`, declaring it
as the dfthcsos generator in a `configs/gates/<candidate>.yaml`, building the full three-task zip and running
G0-G5 (`python -m ledger.gates.runner`). One candidate, one pull request, merge-gate report in the body; the
board merges; john-wick uploads. `promote.py` touches no register, queue or manifest directory.

## Rules the loop enforces

- The salt is the fixed public label and the shot counts are fixed: no seed or salt search (AGENTS.md).
- The factor file is a hash-pinned input; the program may only read it. The NPZ ships as a byte copy unless
  the circuits load a lower precision, in which case `angle_words` is requantised the way `tasks/dfthcsos/circuit.py` does.
- Circuit binaries and NPZ files never enter git (`.gitignore`); hand-offs record SHA-256s.
- Model calls run on the two subscriptions only: `claude -p` with tools, settings, hooks and MCP servers
  disabled; `codex app-server` with a read-only sandbox, approvals never, an empty working directory.
