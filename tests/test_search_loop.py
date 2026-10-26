"""search/: the dfthcsos OpenEvolve loop. No LLM calls and no full verifier runs in this file."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
SEARCH = REPO / "search"
DEFAULT_DATA = Path("/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation")


def load(name: str):
    if str(SEARCH) not in sys.path:
        sys.path.insert(0, str(SEARCH))
    spec = importlib.util.spec_from_file_location(name, SEARCH / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def package_root() -> Path | None:
    root = Path(os.environ.get("VQCC_DATA", DEFAULT_DATA))
    return root if (root / "sample_submission" / "dfthcsos" / "submission.npz").is_file() else None


@pytest.mark.parametrize("provider,name,parallel", [("claude", "claude_code", 2), ("codex", "codex_app_server", 4)])
def test_configs_load_and_install_our_providers(provider, name, parallel):
    from openevolve.config import Config
    config = Config.from_yaml(SEARCH / f"config_{provider}.yaml")
    assert config.llm.provider == name
    assert config.llm.models and all(m.provider == name for m in config.llm.models)
    assert sum(m.weight for m in config.llm.models) == pytest.approx(1.0)
    assert config.database.feature_dimensions == ["q_bin", "t_bin"]
    assert config.database.num_islands == 3 and config.database.migration_interval == 20
    assert config.database.population_size == 200
    assert config.evaluator.cascade_evaluation and config.evaluator.enable_artifacts
    assert config.evaluator.parallel_evaluations == parallel
    assert config.enforce_evolve_blocks and config.diff_based_evolution
    evaluator = load("evaluator")
    assert config.evaluator.cascade_thresholds == [evaluator.STAGE1_THRESHOLD, evaluator.STAGE2_THRESHOLD]
    providers = load("providers")
    installed = providers.install(config)
    assert installed and all(m.init_client is not None for m in config.llm.models)


def test_codex_config_names_a_catalog_model():
    from openevolve.config import Config
    config = Config.from_yaml(SEARCH / "config_codex.yaml")
    assert [m.name for m in config.llm.models] == ["gpt-6-sol", "gpt-6-astra"]
    assert config.llm.reasoning_effort == "medium"


def test_initial_program_has_one_evolve_block_and_notes():
    from openevolve.utils.code_utils import parse_evolve_blocks
    code = (SEARCH / "initial_program.py").read_text(encoding="utf-8")
    assert len(parse_evolve_blocks(code)) == 1
    evaluator = load("evaluator")
    assert evaluator.extract_notes(code).startswith("seed:")


def test_system_message_embeds_discovery_notes():
    run = load("run")
    message = run.compose_system_message()
    assert "{discovery_notes}" not in message
    assert "Verified results" in message and "EVOLVE-BLOCK-START" in message


def test_score_policy_keeps_verified_programs_on_top():
    ev = load("evaluator")
    assert ev.score_policy(False, None, None, None) == 0.0
    static_only = ev.score_policy(True, 1.1, None, None)
    assert ev.STAGE1_THRESHOLD <= static_only < ev.STAGE2_THRESHOLD
    assert ev.score_policy(True, 1.1, {"status": "FAIL"}, None) < ev.STAGE1_THRESHOLD
    reduced = ev.score_policy(True, 1.1, {"status": "PASS", "ratio": 1.1}, None)
    assert ev.STAGE2_THRESHOLD <= reduced < 0.7
    full = ev.score_policy(True, 1.1, {"status": "PASS", "ratio": 1.1}, {"status": "PASS", "ratio": 1.077784})
    assert full == pytest.approx(1.077784)
    assert ev.score_policy(True, 1.1, {"status": "PASS", "ratio": 1.1}, {"status": "FAIL"}) < ev.STAGE1_THRESHOLD
    # the worst verified program still beats the best unverified one down to ratio 0.7
    assert ev.score_policy(True, 2.0, {"status": "PASS", "ratio": 2.0}, {"status": "PASS", "ratio": 0.7}) > reduced


def test_promote_selects_best_and_pareto_front():
    promote = load("promote")

    def program(pid, ratio, t, q, passed=1.0, code=None):
        return {"id": pid, "code": code or pid, "metrics": {"ratio": ratio, "t": t, "q": q, "stage3_passed": passed}}

    programs = [
        program("best", 1.08, 85109, 742),
        program("lowq", 1.06, 93965, 682),      # on the front: fewer qubits
        program("dominated", 1.05, 94000, 700),  # dominated by lowq on both axes? no: q 700 > 682, t 94000 > 93965 -> dominated
        program("seed", 1.0, 93237, 730),       # not above min_ratio
        program("unverified", 1.3, 70000, 700, passed=0.0),
        program("dup", 1.08, 85109, 742, code="best"),
    ]
    chosen = promote.select_elites(programs, top=1, min_ratio=1.0)
    assert [p["id"] for p in chosen] == ["best", "lowq"]
    front = promote.pareto_front([p for p in programs if p["id"] in ("best", "lowq", "dominated")])
    assert {p["id"] for p in front} == {"best", "lowq"}


def test_providers_classify_errors_and_parse_cli_json():
    providers = load("providers")
    assert providers.looks_rate_limited("Error: usage limit reached, resets at 3pm")
    assert not providers.looks_rate_limited("SyntaxError: invalid diff")
    assert providers._last_json_object('noise\n{"result": "OK", "usage": {"output_tokens": 4}}')["result"] == "OK"
    llm = providers.LeanClaudeCodeLLM(SimpleNamespace(name="sonnet", timeout=10, retries=0, retry_delay=1,
                                                       weight=1.0, max_budget_usd=0.5, system_message=None))
    command = llm.command("system text")
    assert command[:3] == ["claude", "-p", "--model"] and "--tools" in command and "--setting-sources" in command
    assert command[command.index("--system-prompt") + 1] == "system text"
    codex = providers.CodexAppServerLLM(SimpleNamespace(name="gpt-6-sol", timeout=10, retries=0, retry_delay=1,
                                                         weight=1.0, reasoning_effort="medium", system_message=None))
    assert codex.model == "gpt-6-sol" and codex.reasoning_effort == "medium"


@pytest.mark.skipif(package_root() is None, reason="competition package not present")
def test_seed_program_reproduces_the_reference_family(tmp_path):
    npz = package_root() / "sample_submission" / "dfthcsos" / "submission.npz"
    proc = subprocess.run(
        [sys.executable, str(SEARCH / "initial_program.py"), "--out", str(tmp_path), "--factorization", str(npz),
         "--source-brot", "12"],
        cwd=REPO, env={**os.environ, "PYTHONPATH": str(REPO)}, capture_output=True, text=True, check=True)
    report = json.loads(proc.stdout)
    from tasks.dfthcsos.generate import REFERENCE_ANGLE_SHA256, REFERENCE_NPZ_SHA256
    assert (report["num_circuits"], report["batch_size"], report["brot"]) == (10, 8, 12)
    assert report["npz_is_byte_copy"] and report["max_qubits"] <= 128
    assert report["files"]["dfthcsos/submission.npz"]["sha256"] == REFERENCE_NPZ_SHA256
    for k, digest in REFERENCE_ANGLE_SHA256.items():
        assert report["files"][f"dfthcsos/angle_k_{k}.kmb"]["sha256"] == digest


def test_run_checkpoint_helpers_ignore_partial_directories(tmp_path):
    run = load("run")
    (tmp_path / "checkpoints" / "checkpoint_5").mkdir(parents=True)
    (tmp_path / "checkpoints" / "checkpoint_10").mkdir()
    (tmp_path / "checkpoints" / "checkpoint_12.partial").mkdir()
    assert run.latest_checkpoint(tmp_path).name == "checkpoint_10"
    assert [p.name for p in run.list_checkpoints(tmp_path)] == ["checkpoint_5", "checkpoint_10"]
    assert [p.name for p in run.prune_checkpoints(tmp_path, keep=1)] == ["checkpoint_5"]
    assert run.latest_checkpoint(tmp_path).name == "checkpoint_10"


def test_stats_summarises_an_empty_run_directory(tmp_path):
    stats = load("stats")
    summary = stats.summarise(tmp_path)
    assert summary["evaluations"]["count"] == 0 and summary["best_verified"] is None
    assert "per iteration" in stats.render(summary)


@pytest.mark.skipif(package_root() is None, reason="competition package not present")
def test_evaluator_stage1_scores_the_seed_without_simulating(tmp_path, monkeypatch):
    monkeypatch.setenv("SEARCH_SCRATCH", str(tmp_path))
    monkeypatch.setenv("SEARCH_RUN_DIR", str(tmp_path / "run"))
    monkeypatch.delenv("SEARCH_KEEP_OUTPUTS", raising=False)
    ev = load("evaluator")
    result = ev.evaluate_stage1(str(SEARCH / "initial_program.py"))
    metrics = result.metrics
    assert metrics["stage1_passed"] == 1.0 and metrics["stage_reached"] == 1.0
    assert (metrics["q"], metrics["t"]) == (730.0, 93237.0) == (metrics["q_bin"], metrics["t_bin"])
    assert metrics["predicted_ratio"] == pytest.approx(1.0, abs=1e-9)
    assert ev.STAGE1_THRESHOLD <= metrics["combined_score"] < ev.STAGE2_THRESHOLD
    assert "summary" in result.artifacts and "files" in result.artifacts and "g2_proxy" in result.artifacts
    build = ev._BUILDS[str(SEARCH / "initial_program.py")]
    assert build.outdir.exists()
    ev.discard(build)
    assert not build.outdir.exists()


def test_evaluator_reports_a_crashing_program(tmp_path, monkeypatch):
    monkeypatch.setenv("SEARCH_SCRATCH", str(tmp_path))
    monkeypatch.setenv("SEARCH_RUN_DIR", str(tmp_path / "run"))
    monkeypatch.delenv("SEARCH_KEEP_OUTPUTS", raising=False)
    broken = tmp_path / "broken.py"
    broken.write_text("import sys\nprint('boom', file=sys.stderr)\nraise SystemExit(3)\n", encoding="utf-8")
    ev = load("evaluator")
    # no competition package needed: the program never reads the factor file
    (tmp_path / "factor.npz").write_bytes(b"not an npz")
    monkeypatch.setattr(ev, "factor_config", lambda path=None: {
        "path": tmp_path / "factor.npz", "sha256": "0" * 64, "source_brot": 12, "package_relative_path": "x"})
    result = ev.evaluate_stage1(str(broken))
    assert result.metrics["combined_score"] == 0.0 and result.metrics["stage1_passed"] == 0.0
    assert "exited 3" in result.artifacts["summary"] and "boom" in result.artifacts["stderr"]
    assert list((tmp_path / "run" / "evals").glob("*.json")), "a failed evaluation is still recorded"
    assert not list(tmp_path.glob("dfthcsos-eval-*")), "the build directory is removed after a stage-1 failure"
