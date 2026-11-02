# SPDX-License-Identifier: Apache-2.0
"""Persistent verifier/program memo, stage-0 short-circuit, the reduced-before-full gate, the `local`
provider and promote.py's negative DISCOVERY lines. No LLM calls, no network, no verifier runs."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from search.memo import VerifierMemo, program_key, program_sha256, verification_key

REPO = Path(__file__).resolve().parents[1]
SEARCH = REPO / "search"


def load(name: str):
    """A fresh module object for search/<name>.py (test_search_loop.load): one process's view of the memo."""
    if str(SEARCH) not in sys.path:
        sys.path.insert(0, str(SEARCH))
    spec = importlib.util.spec_from_file_location(name, SEARCH / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# --- memo persistence ----------------------------------------------------------------------------


def test_memo_hits_after_a_process_restart(tmp_path):
    path = tmp_path / "memo.jsonl"
    key = verification_key(task="dfthcsos", mode="full", circuit_fingerprint=b"family-a", shots=64)
    first = VerifierMemo(path)
    first.set(key, {"status": "PASS", "ratio": 1.1, "seconds": 2.0})
    assert path.is_file()
    restarted = VerifierMemo(path)  # a new process: nothing in memory
    assert restarted.get(key) == {"status": "PASS", "ratio": 1.1, "seconds": 2.0}
    assert restarted.hits == 1 and restarted.negative_hits == 0
    other = verification_key(task="dfthcsos", mode="full", circuit_fingerprint=b"family-b", shots=64)
    assert restarted.get(other) is None


def test_memo_default_path_follows_the_run_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("SEARCH_MEMO_PATH", raising=False)
    monkeypatch.delenv("SEARCH_MEMO_DISABLE", raising=False)
    monkeypatch.setenv("SEARCH_RUN_DIR", str(tmp_path / "run"))
    memo = VerifierMemo()  # created before the run directory is known, like the evaluator's module memo
    assert memo.path == tmp_path / "run" / "verifier_memo.jsonl"
    memo.set(b"k", {"status": "PASS"})
    assert memo.path.is_file()
    assert VerifierMemo().get(b"k") == {"status": "PASS"}
    monkeypatch.setenv("SEARCH_MEMO_PATH", str(tmp_path / "explicit.jsonl"))
    assert VerifierMemo().path == tmp_path / "explicit.jsonl"
    monkeypatch.setenv("SEARCH_MEMO_DISABLE", "1")
    assert VerifierMemo().get(b"k") is None and VerifierMemo().path is None
    monkeypatch.delenv("SEARCH_MEMO_DISABLE")
    monkeypatch.delenv("SEARCH_MEMO_PATH")
    monkeypatch.delenv("SEARCH_RUN_DIR")
    assert VerifierMemo().path is None  # in-process only, as before


def test_memo_negative_results_are_never_rerun(tmp_path):
    path = tmp_path / "memo.jsonl"
    key = verification_key(task="dfthcsos", mode="full", circuit_fingerprint=b"slow-family", shots=2)
    VerifierMemo(path).set(key, {"status": "FAIL", "error": "verifier exceeded 600 s"})
    memo = VerifierMemo(path)
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        return {"status": "PASS"}

    assert memo.get_or_set(key, factory)["status"] == "FAIL"
    assert calls["n"] == 0 and memo.negative_hits == 1 and memo.hits == 1
    record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert record["negative"] is True and record["value"]["status"] == "FAIL"


def test_memo_sees_lines_another_worker_appended(tmp_path):
    path = tmp_path / "memo.jsonl"
    a, b = VerifierMemo(path), VerifierMemo(path)
    assert b.get(b"k1") is None
    a.set(b"k1", {"status": "PASS", "who": "a"})
    assert b.get(b"k1") == {"status": "PASS", "who": "a"}
    b.set(b"k1", {"status": "PASS", "who": "b"})  # a second writer never duplicates the line
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1
    assert VerifierMemo(path).get(b"k1")["who"] == "a"  # the first writer wins on disk


def test_program_key_binds_source_task_mode_and_settings(tmp_path):
    p1, p2, p3 = tmp_path / "a.py", tmp_path / "b.py", tmp_path / "c.py"
    p1.write_text("x = 1\n", encoding="utf-8")
    p2.write_text("x = 1\n", encoding="utf-8")
    p3.write_text("x = 2\n", encoding="utf-8")
    assert program_sha256(p1) == program_sha256(p2) != program_sha256(p3)
    assert program_sha256(tmp_path / "missing.py") is None
    base = dict(task="dfthcsos", mode="full", program_sha256=program_sha256(p1), settings="s1")
    assert program_key(**base) == program_key(**base)
    assert program_key(**{**base, "mode": "smoke"}) != program_key(**base)
    assert program_key(**{**base, "task": "dqi"}) != program_key(**base)
    assert program_key(**{**base, "settings": "s2"}) != program_key(**base)
    assert program_key(**base).startswith(b"kind=program")
    with pytest.raises(ValueError):
        program_key(task="dfthcsos", mode="full", program_sha256="")


# --- the dfthcsos evaluator ----------------------------------------------------------------------


def _crashing_program(path: Path, code: int = 3) -> Path:
    path.write_text(f"import sys\nprint('boom', file=sys.stderr)\nraise SystemExit({code})\n", encoding="utf-8")
    return path


def _fake_factor(ev, monkeypatch, tmp_path):
    (tmp_path / "factor.npz").write_bytes(b"not an npz")
    monkeypatch.setattr(ev, "factor_config", lambda path=None: {
        "path": tmp_path / "factor.npz", "sha256": "0" * 64, "source_brot": 12, "package_relative_path": "x"})


def _evaluator(tmp_path, monkeypatch):
    monkeypatch.setenv("SEARCH_SCRATCH", str(tmp_path / "scratch"))
    monkeypatch.setenv("SEARCH_RUN_DIR", str(tmp_path / "run"))
    monkeypatch.delenv("SEARCH_MEMO_PATH", raising=False)
    monkeypatch.delenv("SEARCH_MEMO_DISABLE", raising=False)
    monkeypatch.delenv("SEARCH_KEEP_OUTPUTS", raising=False)
    monkeypatch.delenv("SEARCH_SMOKE", raising=False)
    ev = load("evaluator")
    _fake_factor(ev, monkeypatch, tmp_path)
    return ev


def test_identical_program_sources_are_not_rebuilt(tmp_path, monkeypatch):
    ev = _evaluator(tmp_path, monkeypatch)
    builds = {"n": 0}
    real_run = ev.run_program

    def counting_run(program_path):
        builds["n"] += 1
        return real_run(program_path)

    monkeypatch.setattr(ev, "run_program", counting_run)
    first = ev.evaluate_stage1(str(_crashing_program(tmp_path / "a.py")))
    assert builds["n"] == 1 and "exited 3" in first.artifacts["summary"]
    second = ev.evaluate_stage1(str(_crashing_program(tmp_path / "b.py")))  # the same bytes under another path
    assert builds["n"] == 1
    assert second.metrics == first.metrics and "memo_hit" in second.artifacts
    assert (tmp_path / "run" / "verifier_memo.jsonl").is_file()

    # A new worker process (fresh module, empty memory) with the same run directory answers from the file.
    ev2 = _evaluator(tmp_path, monkeypatch)
    real_run2 = ev2.run_program
    monkeypatch.setattr(ev2, "run_program", lambda p: pytest.fail("the memo should answer without a build"))
    third = ev2.evaluate_stage1(str(_crashing_program(tmp_path / "c.py")))
    assert third.metrics["combined_score"] == first.metrics["combined_score"] and "memo_hit" in third.artifacts
    assert ev2._VERIFY_MEMO.negative_hits == 1  # a stage-1 failure is a negative result
    for stage in (ev2.evaluate_stage2, ev2.evaluate_stage3):  # every stage answers the same way
        assert "memo_hit" in stage(str(tmp_path / "c.py")).artifacts

    monkeypatch.setattr(ev2, "run_program", real_run2)
    fourth = ev2.evaluate_stage1(str(_crashing_program(tmp_path / "d.py", code=4)))  # a different source misses
    assert "exited 4" in fourth.artifacts["summary"] and "memo_hit" not in fourth.artifacts


def test_program_memo_binds_the_declared_factor(tmp_path, monkeypatch):
    ev = _evaluator(tmp_path, monkeypatch)
    program = str(_crashing_program(tmp_path / "a.py"))
    key_a = ev.program_memo_key(program)
    monkeypatch.setattr(ev, "factor_config", lambda path=None: {
        "path": tmp_path / "factor.npz", "sha256": "1" * 64, "source_brot": 12, "package_relative_path": "x"})
    assert ev.program_memo_key(program) != key_a
    monkeypatch.setattr(ev, "factor_config", lambda path=None: (_ for _ in ()).throw(FileNotFoundError("gone")))
    assert ev.program_memo_key(program) is None  # a misconfigured evaluator caches nothing
    assert ev.program_memo_key(str(tmp_path / "missing.py")) is None


def test_stage0_syntax_error_short_circuits_before_the_build(tmp_path, monkeypatch):
    ev = _evaluator(tmp_path, monkeypatch)
    monkeypatch.setattr(ev.subprocess, "run",
                        lambda *a, **k: pytest.fail("a program that does not parse must never be executed"))
    broken = tmp_path / "broken.py"
    broken.write_text("def main(:\n    pass\n", encoding="utf-8")
    problems = ev.stage0_checks(broken)
    assert problems and "syntax error" in problems[0]
    result = ev.evaluate_stage1(str(broken))
    assert result.metrics["combined_score"] < ev.STAGE1_THRESHOLD and result.metrics["stage1_passed"] == 0.0
    assert "stage 0" in result.artifacts["summary"] and "syntax error" in result.artifacts["summary"]
    assert list((tmp_path / "run" / "evals").glob("*.json")), "a stage-0 failure is still recorded"
    assert ev.stage0_checks(SEARCH / "initial_program.py") == []
    assert ev.stage0_checks(tmp_path / "missing.py")[0].startswith("stage 0: cannot read")


def _chemistry(root: Path, name: str = "dfthcsos") -> Path:
    chemistry = root / name
    chemistry.mkdir()
    (chemistry / "angle_k_0.kmb").write_bytes(b"\x00circuit-" + name.encode())
    (chemistry / "submission.npz").write_bytes(b"\x00npz-" + name.encode())
    return chemistry


def test_verifier_timeout_is_memoised_and_gates_the_full_verifier(tmp_path, monkeypatch):
    monkeypatch.setenv("SEARCH_MEMO_PATH", str(tmp_path / "memo.jsonl"))
    monkeypatch.delenv("SEARCH_MEMO_DISABLE", raising=False)
    monkeypatch.delenv("SEARCH_SMOKE", raising=False)
    ev = load("evaluator")
    chemistry = _chemistry(tmp_path)
    spawned = {"n": 0}

    def fake_run(cmd, **kwargs):
        spawned["n"] += 1
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))

    monkeypatch.setattr(ev.subprocess, "run", fake_run)
    first = ev.verify_family_isolated(chemistry, ev.REDUCED_SHOTS, timeout=1.0)
    assert first["status"] == "FAIL" and "exceeded" in first["error"] and spawned["n"] == 1
    again = ev.verify_family_isolated(chemistry, ev.REDUCED_SHOTS, timeout=1.0)
    assert again["memo_hit"] is True and spawned["n"] == 1
    full = ev.verify_family_isolated(chemistry, ev.FULL_SHOTS, timeout=1.0)  # never spawns: reduced did not pass
    assert full["status"] == "FAIL" and "reduced PASS" in full["gated"] and spawned["n"] == 1

    ev2 = load("evaluator")  # a fresh process sees the negative result too
    monkeypatch.setattr(ev2.subprocess, "run", fake_run)
    assert ev2.verify_family_isolated(chemistry, ev.REDUCED_SHOTS, timeout=1.0)["memo_hit"] is True
    assert spawned["n"] == 1 and ev2._VERIFY_MEMO.negative_hits == 1


def test_verify_json_child_uses_the_memo_and_the_reduced_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("SEARCH_MEMO_PATH", str(tmp_path / "memo.jsonl"))
    monkeypatch.delenv("SEARCH_MEMO_DISABLE", raising=False)
    monkeypatch.delenv("SEARCH_SMOKE", raising=False)
    ev = load("evaluator")
    calls: list[int] = []

    def rejecting(path, shots):
        calls.append(shots)
        return {"status": "FAIL", "shots_per_address": shots, "salt": ev.SALT, "error": "rejected: accuracy"}

    monkeypatch.setattr(ev, "verify_family", rejecting)
    bad = _chemistry(tmp_path, "bad")
    full = ev.verify_json_child(bad, ev.FULL_SHOTS)
    assert calls == [ev.REDUCED_SHOTS], "the reduced stage ran first and failed; the full verifier was never reached"
    assert full["status"] == "FAIL" and "reduced PASS" in full["gated"]
    assert ev.verify_json_child(bad, ev.REDUCED_SHOTS)["memo_hit"] is True and calls == [ev.REDUCED_SHOTS]

    def passing(path, shots):
        calls.append(shots)
        return {"status": "PASS", "shots_per_address": shots, "salt": ev.SALT, "ratio": 1.0}

    monkeypatch.setattr(ev, "verify_family", passing)
    calls.clear()
    good = _chemistry(tmp_path, "good")
    assert ev.verify_json_child(good, ev.FULL_SHOTS)["status"] == "PASS"
    assert calls == [ev.REDUCED_SHOTS, ev.FULL_SHOTS]
    assert ev.verify_json_child(good, ev.FULL_SHOTS)["memo_hit"] is True and len(calls) == 2
    # the parent side recalls the child's result from the shared file without spawning anything
    monkeypatch.setattr(ev.subprocess, "run", lambda *a, **k: pytest.fail("memoised: no child should be spawned"))
    assert ev.verify_family_isolated(good, ev.FULL_SHOTS)["memo_hit"] is True


def _absent(monkeypatch, *names: str) -> None:
    """Remove environment variables so that monkeypatch restores them even when the code under test sets them."""
    for name in names:
        monkeypatch.setenv(name, "placeholder")  # records the original (absent) value
        monkeypatch.delenv(name)


def test_evaluator_cli_accepts_no_memo_and_a_verify_json_timeout(tmp_path, monkeypatch, capsys):
    import os

    _absent(monkeypatch, "SEARCH_RUN_DIR", "SEARCH_MEMO_PATH", "SEARCH_MEMO_DISABLE")
    monkeypatch.setenv("SEARCH_SCRATCH", str(tmp_path / "scratch"))
    ev = load("evaluator")
    monkeypatch.setattr(ev, "verify_family", lambda path, shots: {"status": "FAIL", "shots_per_address": shots,
                                                                    "salt": ev.SALT, "error": "rejected"})
    assert ev.main(["--verify-json", str(_chemistry(tmp_path)), str(ev.REDUCED_SHOTS), "12.5"]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["status"] == "FAIL"
    monkeypatch.setattr(ev, "evaluate", lambda program: ev.EvaluationResult(metrics={"stage3_passed": 0.0}, artifacts={}))
    assert ev.main([str(tmp_path / "prog.py")]) == 1
    scratch_memo = tmp_path / "scratch" / "verifier_memo.jsonl"
    assert os.environ["SEARCH_MEMO_PATH"] == str(scratch_memo)  # outside a run the child shares the scratch memo
    assert ev._VERIFY_MEMO.path == scratch_memo
    assert ev.main([str(tmp_path / "prog.py"), "--no-memo"]) == 1
    assert os.environ["SEARCH_MEMO_DISABLE"] == "1" and ev._VERIFY_MEMO.path is None


# --- the adapter cascade -------------------------------------------------------------------------


def _cascade_adapter(bundle, *, reduced_fc: float) -> MagicMock:
    from search.adapters.base import TaskAdapter

    adapter = MagicMock(spec=TaskAdapter)
    adapter.task = adapter.name = bundle.task
    adapter.stage0_build.return_value = bundle
    sample = {"feasible": False, "fraction_correct": 1.0, "max_error_over_tol": 0.0, "ancilla_dirty_fraction": 0.0,
              "phase_wrong_fraction": 0.0, "toffoli_count": 100.0, "qubit_count": 10.0, "cost_c": 100.0,
              "r_eps": 1.0, "k_failures": 0.0, "eps_plus": 0.0}
    adapter.stage1_sample.return_value = dict(sample)
    adapter.stage2_verify_reduced.return_value = {
        **sample, "fraction_correct": reduced_fc, "max_error_over_tol": 0.0 if reduced_fc >= 1.0 else 9.0,
        "verification_stage": "reduced", "reduced_pass": reduced_fc >= 1.0}
    adapter.stage2_verify_full.return_value = {**sample, "feasible": True, "verification_stage": "full"}

    def cost_fields(bundle, sample, verified):
        source = verified if verified else sample
        keys = ("toffoli_count", "qubit_count", "cost_c", "r_eps", "k_failures", "eps_plus", "fraction_correct",
                "max_error_over_tol", "ancilla_dirty_fraction", "phase_wrong_fraction")
        return {"task": bundle.task, **{k: source.get(k, 0.0) for k in keys},
                "feasible": bool(verified and verified.get("feasible"))}

    adapter.cost_fields.side_effect = cost_fields
    adapter.fingerprint.return_value = b"fp"
    adapter.verifier_settings.return_value = {}
    adapter.submission_identity.return_value = ""
    adapter.reduced_shots.return_value = None
    adapter.full_shots.return_value = None
    return adapter


def _cascade_bundle(tmp_path: Path, program: Path):
    from search.adapters.base import CandidateBundle

    out = tmp_path / f"out-{program.stem}"
    out.mkdir()
    (out / "marker").write_text("alive", encoding="utf-8")
    return CandidateBundle(task="invsqrt", program_path=program, outdir=out, circuit_bytes={"a.kmb": b"\x00"})


def test_cascade_stage3_refuses_the_full_verifier_without_a_reduced_pass(tmp_path, monkeypatch):
    from search import adapter_cascade as cascade

    cascade._STATE.clear()
    cascade._MEMO = VerifierMemo()
    program = tmp_path / "prog.py"
    bundle = _cascade_bundle(tmp_path, program)
    adapter = _cascade_adapter(bundle, reduced_fc=0.0)
    monkeypatch.setattr(cascade, "_adapter_for", lambda t, generation=0: adapter)
    # Stage 2 kept its state with a reduced result that did not pass; a direct stage-3 call must not verify.
    cascade._STATE[cascade._state_key(str(program), "invsqrt")] = {
        "bundle": bundle, "sample": adapter.stage1_sample.return_value,
        "reduced": adapter.stage2_verify_reduced.return_value, "verified": None, "adapter_task": "invsqrt"}
    result = cascade.evaluate_stage3(str(program), task="invsqrt")
    adapter.stage2_verify_full.assert_not_called()
    assert result.metrics["stage3_passed"] == 0.0 and result.metrics["feasible"] == 0.0
    assert result.metrics["stage_reached"] == 2.0 and "reduced-stage PASS" in result.artifacts["gated"]
    assert cascade._STATE == {} and not bundle.outdir.exists()


def test_cascade_answers_identical_program_sources_from_the_memo(tmp_path, monkeypatch):
    from search import adapter_cascade as cascade

    monkeypatch.delenv("SEARCH_MEMO_DISABLE", raising=False)
    monkeypatch.delenv("SEARCH_SMOKE", raising=False)
    cascade._STATE.clear()
    cascade._MEMO = VerifierMemo(tmp_path / "memo.jsonl")
    prog_a, prog_b = tmp_path / "a.py", tmp_path / "b.py"
    prog_a.write_text("x = 1\n", encoding="utf-8")
    prog_b.write_text("x = 1\n", encoding="utf-8")
    adapter = _cascade_adapter(_cascade_bundle(tmp_path, prog_a), reduced_fc=0.0)
    monkeypatch.setattr(cascade, "_adapter_for", lambda t, generation=0: adapter)

    first = cascade.evaluate(str(prog_a), task="invsqrt")
    assert adapter.stage0_build.call_count == 1 and first.metrics["stage_reached"] == 2.0
    assert cascade._STATE == {}
    second = cascade.evaluate(str(prog_b), task="invsqrt")  # the same source under another path
    assert adapter.stage0_build.call_count == 1 and "memo_hit" in second.artifacts
    assert second.metrics == first.metrics

    cascade._MEMO = VerifierMemo(tmp_path / "memo.jsonl")  # a new worker process
    third = cascade.evaluate_stage1(str(prog_b), task="invsqrt")
    assert adapter.stage0_build.call_count == 1 and "memo_hit" in third.artifacts
    assert cascade._MEMO.negative_hits == 1 and cascade._STATE == {}

    prog_c = tmp_path / "c.py"
    prog_c.write_text("x = 2\n", encoding="utf-8")
    adapter.stage0_build.return_value = _cascade_bundle(tmp_path, prog_c)
    assert "memo_hit" not in cascade.evaluate(str(prog_c), task="invsqrt").artifacts
    assert adapter.stage0_build.call_count == 2


# --- the local provider --------------------------------------------------------------------------


def _local_llm(providers, **overrides):
    cfg = SimpleNamespace(name="local-coder", timeout=10, retries=0, retry_delay=1, weight=1.0, system_message=None,
                          api_base=None, api_key=None, max_tokens=512, temperature=0.2, top_p=None,
                          reasoning_effort=None, max_budget_usd=0)
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return providers.LocalOpenAILLM(cfg)


def test_local_provider_shapes_an_openai_chat_request(monkeypatch):
    monkeypatch.delenv("SEARCH_LOCAL_BASE_URL", raising=False)
    monkeypatch.delenv("SEARCH_RUN_DIR", raising=False)
    monkeypatch.setenv("SEARCH_LOCAL_API_KEY", "test-key-not-a-secret")
    providers = load("providers")
    seen: dict = {}
    reply = "<<<<<<< SEARCH\na = 1\n=======\na = 2\n>>>>>>> REPLACE"

    def fake_post(url, headers, body, timeout):
        seen.update(url=url, headers=headers, body=json.loads(body), timeout=timeout)
        return 200, json.dumps({
            "id": "x", "model": "qwen-served",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": reply}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
        }).encode("utf-8")

    monkeypatch.setattr(providers, "_post_json", fake_post)
    llm = _local_llm(providers)
    assert llm.provider == "local" and llm.base_url == "http://127.0.0.1:4000/v1"
    text = asyncio.run(llm.generate_with_context("SYSTEM RULES", [{"role": "user", "content": "rewrite the block"}]))
    assert text == reply  # the diff comes back untouched for OpenEvolve's SEARCH/REPLACE parser
    assert seen["url"] == "http://127.0.0.1:4000/v1/chat/completions" and seen["timeout"] == 10
    assert seen["headers"]["Authorization"] == "Bearer test-key-not-a-secret"
    assert seen["headers"]["Content-Type"] == "application/json"
    body = seen["body"]
    assert body["model"] == "local-coder" and body["stream"] is False
    assert body["max_tokens"] == 512 and body["temperature"] == pytest.approx(0.2) and "top_p" not in body
    assert body["messages"] == [{"role": "system", "content": "SYSTEM RULES"},
                                {"role": "user", "content": "rewrite the block"}]
    assert llm.last_usage["prompt_tokens"] == 120 and llm.last_usage["completion_tokens"] == 30
    assert llm.last_usage["total_tokens"] == 150 and llm.last_usage["cost_usd"] == 0.0
    assert llm.last_usage["model"] == "qwen-served"


def test_local_provider_takes_the_base_url_from_config_and_never_forwards_the_openai_key(monkeypatch):
    monkeypatch.delenv("SEARCH_LOCAL_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("SEARCH_LOCAL_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-must-not-be-forwarded")
    providers = load("providers")
    llm = _local_llm(providers, api_base="http://gateway.test:8080/v1/", api_key="sk-must-not-be-forwarded")
    url, headers, body = llm.request("s", "u")
    assert url == "http://gateway.test:8080/v1/chat/completions"
    assert "Authorization" not in headers
    assert json.loads(body)["messages"][0] == {"role": "system", "content": "s"}
    assert _local_llm(providers, api_key="from-yaml").request("s", "u")[1]["Authorization"] == "Bearer from-yaml"
    monkeypatch.setenv("SEARCH_LOCAL_BASE_URL", "http://other.test:1234/v1")
    assert _local_llm(providers).base_url == "http://other.test:1234/v1"
    assert _local_llm(providers, api_base="http://cfg.test/v1").base_url == "http://cfg.test/v1"
    assert json.loads(_local_llm(providers).request("", "u")[2])["messages"] == [{"role": "user", "content": "u"}]


def test_local_provider_classifies_gateway_errors(monkeypatch):
    monkeypatch.delenv("SEARCH_LOCAL_API_KEY", raising=False)
    providers = load("providers")
    llm = _local_llm(providers)

    def respond(status, payload):
        monkeypatch.setattr(providers, "_post_json",
                            lambda url, headers, body, timeout: (status, json.dumps(payload).encode("utf-8")))

    respond(429, {"error": {"message": "rate limit"}})
    with pytest.raises(providers.RateLimited):
        llm._call("s", "u", 5)
    respond(404, {"error": {"message": "model not found"}})
    with pytest.raises(providers.NoRetry):
        llm._call("s", "u", 5)
    respond(401, {"error": {"message": "auth"}})
    with pytest.raises(providers.NoRetry):
        llm._call("s", "u", 5)
    respond(500, {"error": {"message": "boom"}})
    with pytest.raises(RuntimeError):
        llm._call("s", "u", 5)
    respond(200, {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]})
    with pytest.raises(RuntimeError, match="empty completion"):
        llm._call("s", "u", 5)
    respond(200, {"choices": [{"message": {"content": [{"type": "text", "text": "parts "}, {"type": "text", "text": "ok"}]}}]})
    assert llm._call("s", "u", 5)[0] == "parts ok"


def test_local_config_loads_and_installs_the_local_provider():
    from openevolve.config import Config

    config = Config.from_yaml(SEARCH / "config_local.yaml")
    assert config.llm.provider == "local" and all(m.provider == "local" for m in config.llm.models)
    assert config.llm.api_base == "http://127.0.0.1:4000/v1"
    assert all(m.api_base == config.llm.api_base and m.api_key is None for m in config.llm.models)
    assert all(m.max_budget_usd == 0 for m in config.llm.models)
    assert sum(m.weight for m in config.llm.models) == pytest.approx(1.0)
    codex = Config.from_yaml(SEARCH / "config_codex.yaml")
    assert config.evaluator.cascade_thresholds == codex.evaluator.cascade_thresholds == [0.05, 0.49]
    assert config.evaluator.cascade_evaluation and config.enforce_evolve_blocks and config.diff_based_evolution
    assert config.database.feature_dimensions == codex.database.feature_dimensions
    assert config.database.population_size == codex.database.population_size
    providers = load("providers")
    assert providers.install(config) == ["local:local-coder"]
    assert all(m.init_client is providers.init_local_client for m in config.llm.models)
    run = load("run")
    assert run.build_parser().parse_args(["--provider", "local"]).provider == "local"


# --- promote.py negative DISCOVERY lines ---------------------------------------------------------


def test_promote_emits_at_most_three_negative_discovery_lines_to_the_run_output(tmp_path, capsys):
    promote = load("promote")

    def program(pid, *, stage, passed, predicted, summary):
        return {"id": pid, "code": 'NOTES = """2026-11-01: tried J 6 bank 1"""\n',
                "metrics": {"stage_reached": stage, "stage3_passed": passed, "predicted_ratio": predicted,
                            "ratio": 1.0 if passed else 0.0, "batch_size": 6.0, "brot": 12.0, "t": 1.0, "q": 1.0},
                "artifacts_json": json.dumps({"summary": summary})}

    fail3 = "stage 3 (full verifier, 64 shots/address) FAIL: rejected: error_1 76.9 mHa > 20 mHa"
    programs = [
        program("ok", stage=3, passed=1.0, predicted=1.1, summary="stage 3 PASS"),
        program("s1", stage=1, passed=0.0, predicted=0.0, summary="stage 1 FAILED: report lists no circuits"),
        program("n1", stage=3, passed=0.0, predicted=1.30, summary="stage 2 PASS\n" + fail3),
        program("n2", stage=2, passed=0.0, predicted=1.20,
                summary="stage 2 (verifier, 2 shots/address) FAIL: InvalidCircuits: words differ"),
        program("n3", stage=3, passed=0.0, predicted=1.10,
                summary="stage 3 (full verifier, 64 shots/address) FAIL: rejected: gap"),
        program("n4", stage=3, passed=0.0, predicted=1.05,
                summary="stage 3 (full verifier, 64 shots/address) FAIL: rejected: floor"),
        program("dup", stage=3, passed=0.0, predicted=1.25, summary=fail3),
    ]
    negatives = promote.negative_candidates(programs)
    assert [p["id"] for p in negatives] == ["n1", "n2", "n3"]  # best predicted first, one per reason, max 3
    assert promote.failure_reason(programs[2]) == fail3
    lines = [promote.negative_entry(p, "codex-a", "checkpoint_40") for p in negatives]
    assert all(line.startswith("DISCOVERY: - ") and "Assumes" in line for line in lines)
    assert "error_1 76.9 mHa" in lines[0] and "codex-a-checkpoint_40-n1" in lines[0]
    assert "tried J 6 bank 1" in lines[0] and "predicted ratio 1.3000, J 6, brot 12" in lines[0]

    before = (SEARCH / "DISCOVERY.md").read_bytes()
    run_dir = tmp_path / "codex-a"
    run_dir.mkdir()
    written = promote.emit_discovery_lines(run_dir, "checkpoint_40", lines)
    assert written == run_dir / "discovery_lines.md"
    assert written.read_text(encoding="utf-8").count("DISCOVERY: - ") == 3
    assert capsys.readouterr().out.count("DISCOVERY: - ") == 3
    assert (SEARCH / "DISCOVERY.md").read_bytes() == before, "DISCOVERY.md stays hand-curated"
    assert promote.emit_discovery_lines(run_dir, "checkpoint_40", []) is None
