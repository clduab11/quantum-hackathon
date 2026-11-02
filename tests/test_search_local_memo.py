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
    b.clear()  # in-memory only: the next miss re-reads the file and nothing is written twice
    assert b.get(b"k1")["who"] == "a" and b.hits == 1
    b.set(b"k1", {"status": "PASS", "who": "b"})
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_memo_set_keeps_the_first_writer_in_process_and_on_disk(tmp_path):
    path = tmp_path / "memo.jsonl"
    a, b = VerifierMemo(path), VerifierMemo(path)
    a.set(b"k", {"status": "PASS", "who": "a"})
    assert b.set(b"k", {"status": "FAIL", "who": "b"}) == {"status": "PASS", "who": "a"}  # a's line was already on disk
    assert b.get(b"k")["who"] == "a" and b.negative_hits == 0
    memo = VerifierMemo()  # in-process only: the same rule
    assert memo.set(b"k", {"who": 1}) == {"who": 1} and memo.set(b"k", {"who": 2}) == {"who": 1}


def test_memo_first_writer_is_atomic_across_processes(tmp_path):
    """Four real worker processes race on the same keys; every key ends with exactly one line on disk and
    every worker returns the committed winner (the interprocess file lock makes refresh-then-append atomic)."""
    import time
    import warnings

    path = tmp_path / "memo.jsonl"
    worker = (
        "import json, sys, time\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from search.memo import VerifierMemo\n"
        "memo = VerifierMemo(sys.argv[2]); who = sys.argv[3]\n"
        "print('ready', flush=True)  # readiness barrier: imports are done, the parent now picks the start\n"
        "start = float(sys.stdin.readline())\n"
        "time.sleep(max(0.0, start - time.time()))  # release every worker at the same instant\n"
        "out = {}\n"
        "for i in range(150):\n"
        "    out[str(i)] = memo.set(f'key-{i}'.encode(), {'who': who, 'i': i})\n"
        "print(json.dumps(out), flush=True)\n"
    )
    procs = [subprocess.Popen([sys.executable, "-c", worker, str(REPO), str(path), f"w{n}"],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) for n in range(4)]
    for p in procs:
        assert p.stdout.readline().strip() == "ready"  # wait for all four before setting the start time
    start = time.time() + 0.2
    returned = [json.loads(p.communicate(input=f"{start}\n", timeout=120)[0]) for p in procs]
    assert all(p.returncode == 0 for p in procs)
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 150, "every key was persisted exactly once"
    on_disk = {record["value"]["i"]: record["value"] for record in lines}
    for out in returned:
        for i, value in out.items():
            assert value == on_disk[int(i)], "each worker returned the committed winner"
    assert (tmp_path / "memo.jsonl.lock").exists()
    winners = {v["who"] for v in on_disk.values()}
    if len(winners) < 2:  # best effort: scheduling on a slow runner may let one worker win every key
        warnings.warn(f"memo race test: a single worker ({winners}) won every key; contention was not exercised",
                      stacklevel=1)


def test_program_key_binds_sibling_modules(tmp_path):
    from search.memo import sibling_sources_digest

    alone = tmp_path / "alone"
    alone.mkdir()
    program = alone / "prog.py"
    program.write_text("import helper\n", encoding="utf-8")
    assert sibling_sources_digest(program) == ""  # OpenEvolve's one-file temp directory: nothing to bind
    (alone / "helper.py").write_text("X = 1\n", encoding="utf-8")
    first = sibling_sources_digest(program)
    assert first and first == sibling_sources_digest(program)
    (alone / "helper.py").write_text("X = 2\n", encoding="utf-8")
    assert sibling_sources_digest(program) != first
    assert sibling_sources_digest(tmp_path / "missing" / "prog.py") == ""


def test_code_fingerprint_tracks_files_and_module_sources(tmp_path):
    from search.memo import code_fingerprint

    source = tmp_path / "x.py"
    source.write_text("a = 1\n", encoding="utf-8")
    before = code_fingerprint(files=[source])
    assert before == code_fingerprint(files=[source]) and len(before) == 16
    source.write_text("a = 2\n", encoding="utf-8")
    assert code_fingerprint(files=[source]) != before
    assert code_fingerprint(modules=["search.memo"]) != code_fingerprint(modules=["search.fitness"])
    assert code_fingerprint(modules=["search.memo"]) == code_fingerprint(modules=["search.memo", "no.such.module"])


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
    """One program alone in its own directory, as OpenEvolve lays them out (the memo binds sibling modules)."""
    path = path.parent / path.stem / path.name
    path.parent.mkdir(parents=True, exist_ok=True)
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
    third_path = _crashing_program(tmp_path / "c.py")
    third = ev2.evaluate_stage1(str(third_path))
    assert third.metrics["combined_score"] == first.metrics["combined_score"] and "memo_hit" in third.artifacts
    assert ev2._VERIFY_MEMO.negative_hits == 1  # a stage-1 failure is a negative result
    for stage in (ev2.evaluate_stage2, ev2.evaluate_stage3):  # every stage answers the same way
        assert "memo_hit" in stage(str(third_path)).artifacts
    sibling = third_path.parent / "helper.py"  # a sibling module changes the environment: no reuse
    sibling.write_text("X = 1\n", encoding="utf-8")
    monkeypatch.setattr(ev2, "run_program", real_run2)
    assert "memo_hit" not in ev2.evaluate_stage1(str(third_path)).artifacts

    fourth = ev2.evaluate_stage1(str(_crashing_program(tmp_path / "d.py", code=4)))  # a different source misses
    assert "exited 4" in fourth.artifacts["summary"] and "memo_hit" not in fourth.artifacts


def test_program_memo_binds_the_declared_factor(tmp_path, monkeypatch):
    ev = _evaluator(tmp_path, monkeypatch)
    program = str(_crashing_program(tmp_path / "a.py"))
    key_a = ev.program_memo_key(program)
    monkeypatch.setattr(ev, "BUILD_TIMEOUT", ev.BUILD_TIMEOUT * 2)  # a timed-out build must be retried with more time
    assert ev.program_memo_key(program) != key_a
    monkeypatch.setattr(ev, "BUILD_TIMEOUT", ev.BUILD_TIMEOUT / 2)
    monkeypatch.setattr(ev, "VERIFY_TIMEOUT", ev.VERIFY_TIMEOUT * 2)
    assert ev.program_memo_key(program) != key_a
    monkeypatch.setattr(ev, "VERIFY_TIMEOUT", ev.VERIFY_TIMEOUT / 2)
    assert ev.program_memo_key(program) == key_a
    monkeypatch.setattr(ev, "_evaluator_fingerprint", lambda: "deadbeefdeadbeef")  # scoring/verifier code changed
    assert ev.program_memo_key(program) != key_a
    monkeypatch.setattr(ev, "_evaluator_fingerprint", lambda: ev.code_fingerprint(
        files=(SEARCH / "evaluator.py", SEARCH / "fitness.py"), modules=("tasks.dfthcsos.gates", *ev.VERIFIER_MODULES)))
    assert ev.program_memo_key(program) == key_a
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
    missing = ev.evaluate_stage1(str(tmp_path / "missing.py"))  # unreadable: a stage-0 verdict, not an evaluator fault
    assert "stage 0: cannot read" in missing.artifacts["summary"] and "evaluator_traceback" not in missing.artifacts
    assert missing.metrics["stage1_passed"] == 0.0


def test_factor_digest_is_hashed_once_per_process(tmp_path, monkeypatch):
    import yaml

    ev = load("evaluator")
    factor = tmp_path / "factor.npz"
    factor.write_bytes(b"factor words " * 16)
    import hashlib
    digest = hashlib.sha256(factor.read_bytes()).hexdigest()
    config = tmp_path / "factor.yaml"
    config.write_text(yaml.safe_dump({"factorization": str(factor), "sha256": digest, "source_brot": 12,
                                      "package_relative_path": "x"}), encoding="utf-8")
    monkeypatch.setenv("SEARCH_FACTOR_CONFIG", str(config))
    hashed = {"n": 0}
    real = ev.sha256_file

    def counting(path):
        hashed["n"] += 1
        return real(path)

    monkeypatch.setattr(ev, "sha256_file", counting)
    assert ev.factor_config()["sha256"] == digest and ev.factor_config()["sha256"] == digest
    assert hashed["n"] == 1
    factor.write_bytes(b"other words " * 16)  # a changed file is hashed again and then fails the pin
    with pytest.raises(ValueError):
        ev.factor_config()
    assert hashed["n"] == 2


def test_verifier_memo_key_binds_the_verifier_code(tmp_path, monkeypatch):
    ev = load("evaluator")
    chemistry = _chemistry(tmp_path)
    key = ev._verify_key(chemistry, ev.REDUCED_SHOTS, 1.0)
    assert key == ev._verify_key(chemistry, ev.REDUCED_SHOTS, 1.0)
    monkeypatch.setattr(ev, "_verifier_fingerprint", lambda: "0123456789abcdef")  # dfthcsos.verify changed
    assert ev._verify_key(chemistry, ev.REDUCED_SHOTS, 1.0) != key


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

    monkeypatch.setattr(cascade, "_STATE", {})
    monkeypatch.setattr(cascade, "_MEMO", VerifierMemo())
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


def test_cascade_reduced_pass_requires_the_verifier_verdict():
    from search.adapter_cascade import _reduced_passed

    # DQI: zero failures is the contract; one failed shot out of 1,536 is a FAIL whatever the fraction says
    assert not _reduced_passed({"k_failures": 1.0, "fraction_correct": 1.0 - 1 / 1536, "verification_stage": "reduced"})
    assert _reduced_passed({"k_failures": 0.0, "fraction_correct": 1.0, "verification_stage": "reduced"})
    assert not _reduced_passed({"k_failures": 0.0, "fraction_correct": 1.0, "error": "verify crashed"})
    # invsqrt / dfthcsos: the explicit verdict wins over the fraction either way
    assert not _reduced_passed({"reduced_pass": False, "fraction_correct": 1.0})
    assert _reduced_passed({"reduced_pass": True, "fraction_correct": 0.99})
    # no verdict field at all: only a perfect fraction counts
    assert not _reduced_passed({"fraction_correct": 0.995}) and _reduced_passed({"fraction_correct": 1.0})
    assert not _reduced_passed(None) and not _reduced_passed({})


def test_cascade_stage3_blocks_dqi_with_one_failed_reduced_shot(tmp_path, monkeypatch):
    from search import adapter_cascade as cascade

    monkeypatch.setattr(cascade, "_STATE", {})
    monkeypatch.setattr(cascade, "_MEMO", VerifierMemo())
    program = tmp_path / "prog.py"
    bundle = _cascade_bundle(tmp_path, program)
    bundle.task = "dqi"
    adapter = _cascade_adapter(bundle, reduced_fc=1.0)
    adapter.stage2_verify_reduced.return_value = {  # what DqiAdapter returns for max_k == 1 at 1,536 shots
        **adapter.stage2_verify_reduced.return_value, "fraction_correct": 1.0 - 1 / 1536, "k_failures": 1.0,
        "eps_plus": 1 / 1536, "max_error_over_tol": 100.0 / 1536, "phase_wrong_fraction": 1 / 1536}
    del adapter.stage2_verify_reduced.return_value["reduced_pass"]
    monkeypatch.setattr(cascade, "_adapter_for", lambda t, generation=0: adapter)
    cascade._STATE[cascade._state_key(str(program), "dqi")] = {
        "bundle": bundle, "sample": adapter.stage1_sample.return_value,
        "reduced": adapter.stage2_verify_reduced.return_value, "verified": None, "adapter_task": "dqi"}
    result = cascade.evaluate_stage3(str(program), task="dqi")
    adapter.stage2_verify_full.assert_not_called()
    assert result.metrics["stage3_passed"] == 0.0 and result.metrics["feasible"] == 0.0
    assert result.metrics["stage2_passed"] == 0.0, "a failed reduced verdict is a failed stage 2, not 1.0 from the fraction"
    assert "reduced-stage PASS" in result.artifacts["gated"]
    # the same verdict drives stage 2's own metric
    monkeypatch.setattr(cascade, "_STATE", {})
    cascade.evaluate_stage1(str(program), task="dqi")
    assert cascade.evaluate_stage2(str(program), task="dqi").metrics["stage2_passed"] == 0.0


def test_cascade_circuit_memo_keys_bind_the_verifier_code(tmp_path, monkeypatch):
    from search import adapter_cascade as cascade

    monkeypatch.setattr(cascade, "_STATE", {})
    monkeypatch.setattr(cascade, "_MEMO", VerifierMemo())
    program = tmp_path / "prog.py"
    adapter = _cascade_adapter(_cascade_bundle(tmp_path, program), reduced_fc=1.0)
    monkeypatch.setattr(cascade, "_adapter_for", lambda t, generation=0: adapter)
    cascade.evaluate_stage1(str(program), task="invsqrt")
    cascade.evaluate_stage2(str(program), task="invsqrt")
    cascade.evaluate_stage2(str(program), task="invsqrt")  # same circuits, same code: memoised
    assert adapter.stage2_verify_reduced.call_count == 1
    monkeypatch.setattr(cascade, "_cascade_fingerprint", lambda: "0123456789abcdef")  # verifier/proxy code changed
    cascade.evaluate_stage2(str(program), task="invsqrt")
    assert adapter.stage2_verify_reduced.call_count == 2
    cascade.evaluate_stage3(str(program), task="invsqrt")
    assert adapter.stage2_verify_full.call_count == 1
    monkeypatch.setattr(cascade, "_STATE", {})
    monkeypatch.setattr(cascade, "_cascade_fingerprint", lambda: "fedcba9876543210")
    adapter.stage0_build.return_value = _cascade_bundle(tmp_path, tmp_path / "again.py")
    cascade.evaluate(str(program), task="invsqrt")  # a rebuilt program with identical circuit bytes
    assert adapter.stage2_verify_reduced.call_count == 3 and adapter.stage2_verify_full.call_count == 2


def test_cascade_answers_identical_program_sources_from_the_memo(tmp_path, monkeypatch):
    from search import adapter_cascade as cascade

    monkeypatch.delenv("SEARCH_MEMO_DISABLE", raising=False)
    monkeypatch.delenv("SEARCH_SMOKE", raising=False)
    monkeypatch.setattr(cascade, "_STATE", {})
    monkeypatch.setattr(cascade, "_MEMO", VerifierMemo(tmp_path / "memo.jsonl"))
    prog_a, prog_b = tmp_path / "a" / "a.py", tmp_path / "b" / "b.py"  # one program per directory, as OpenEvolve does
    for program in (prog_a, prog_b):
        program.parent.mkdir()
        program.write_text("x = 1\n", encoding="utf-8")
    adapter = _cascade_adapter(_cascade_bundle(tmp_path, prog_a), reduced_fc=0.0)
    monkeypatch.setattr(cascade, "_adapter_for", lambda t, generation=0: adapter)

    first = cascade.evaluate(str(prog_a), task="invsqrt")
    assert adapter.stage0_build.call_count == 1 and first.metrics["stage_reached"] == 2.0
    assert cascade._STATE == {}
    second = cascade.evaluate(str(prog_b), task="invsqrt")  # the same source under another path
    assert adapter.stage0_build.call_count == 1 and "memo_hit" in second.artifacts
    assert second.metrics == first.metrics

    monkeypatch.setattr(cascade, "_MEMO", VerifierMemo(tmp_path / "memo.jsonl"))  # a new worker process
    third = cascade.evaluate_stage1(str(prog_b), task="invsqrt")
    assert adapter.stage0_build.call_count == 1 and "memo_hit" in third.artifacts
    assert cascade._MEMO.negative_hits == 1 and cascade._STATE == {}

    prog_c = tmp_path / "c" / "c.py"
    prog_c.parent.mkdir()
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
    assert _local_llm(providers, api_base="http://cfg.test/v1").base_url == "http://cfg.test/v1"
    monkeypatch.setenv("SEARCH_LOCAL_BASE_URL", "http://other.test:1234/v1")
    assert _local_llm(providers).base_url == "http://other.test:1234/v1"
    assert _local_llm(providers, api_base="http://cfg.test/v1").base_url == "http://other.test:1234/v1"  # env wins
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
    respond(302, {})  # a redirect is never followed: the key and the prompt stay on the configured origin
    with pytest.raises(providers.NoRetry, match="redirect"):
        llm._call("s", "u", 5)


def test_local_provider_refuses_cleartext_keys_off_loopback_and_redirects(monkeypatch):
    monkeypatch.delenv("SEARCH_LOCAL_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    providers = load("providers")
    assert providers.check_gateway_url("http://127.0.0.1:4000/v1", credentialed=True) is None
    assert providers.check_gateway_url("http://127.1.2.3:4000/v1", credentialed=True) is None
    assert providers.check_gateway_url("http://[::1]:4000/v1", credentialed=True) is None
    assert providers.check_gateway_url("http://localhost:4000/v1", credentialed=True) is None
    assert "cleartext" in providers.check_gateway_url("http://127.example.test/v1", credentialed=True)  # a DNS name
    assert not providers.is_loopback_host("127.example.test") and not providers.is_loopback_host("")
    # regression: a DNS name that merely starts with "127." is remote; with a key set it is refused over plain http,
    # while the literal loopback forms (IPv4, bracketed IPv6, localhost) are accepted
    with pytest.raises(providers.NoRetry, match="cleartext"):
        _local_llm(providers, api_base="http://127.example.com", api_key="k").request("s", "u")
    for accepted in ("http://127.0.0.1:4000", "http://[::1]:4000", "http://localhost:4000"):
        assert _local_llm(providers, api_base=accepted, api_key="k").request("s", "u")[0] == accepted + "/chat/completions"
    # a loopback gateway bypasses http_proxy; any other host keeps urllib's proxy handling
    monkeypatch.setenv("http_proxy", "http://proxy.test:3128")
    monkeypatch.delenv("no_proxy", raising=False)
    import urllib.request
    # an empty ProxyHandler defines no *_open method, so urllib keeps it out of .handlers: no proxy at all
    local = [h for h in providers._opener_for("http://127.0.0.1:4000/v1/chat/completions").handlers
             if isinstance(h, urllib.request.ProxyHandler)]
    assert local == []
    remote = [h for h in providers._opener_for("https://gateway.test/v1/chat/completions").handlers
              if isinstance(h, urllib.request.ProxyHandler)]
    assert remote and any(h.proxies.get("http") == "http://proxy.test:3128" for h in remote)
    assert all(any(isinstance(h, providers._NoRedirect) for h in providers._opener_for(u).handlers)
               for u in ("http://127.0.0.1:4000/v1/x", "https://gateway.test/v1/x"))
    assert providers.check_gateway_url("https://gateway.test/v1", credentialed=True) is None
    assert providers.check_gateway_url("http://gateway.test/v1", credentialed=False) is None
    assert "cleartext" in providers.check_gateway_url("http://gateway.test/v1", credentialed=True)
    assert "http(s)" in providers.check_gateway_url("ftp://gateway.test/v1", credentialed=False)
    with pytest.raises(providers.NoRetry, match="cleartext"):
        _local_llm(providers, api_base="http://gateway.test/v1", api_key="k").request("s", "u")
    assert _local_llm(providers, api_base="https://gateway.test/v1", api_key="k").request("s", "u")[0] == \
        "https://gateway.test/v1/chat/completions"
    with pytest.raises(providers.NoRetry, match="http"):
        _local_llm(providers, api_base="file:///etc/passwd").request("s", "u")
    # the opener used by _post_json refuses redirects outright
    assert providers._NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://elsewhere.test/") is None


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
    assert providers.install(config) == ["local:local-ornith-35b"]
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
        # execution errors are not verdicts: never a DISCOVERY negative
        program("slow", stage=3, passed=0.0, predicted=1.40,
                summary="stage 3 (full verifier, 64 shots/address) FAIL: verifier exceeded 600 s (too slow)"),
        program("crash", stage=2, passed=0.0, predicted=1.35,
                summary="stage 2 (verifier, 2 shots/address) FAIL: verifier child exited 1 without a result: boom"),
        {**program("fault", stage=2, passed=0.0, predicted=1.33, summary="stage 2: the evaluator failed (x)"),
         "artifacts_json": json.dumps({"summary": "stage 2: the evaluator failed (KeyError: 'y'); this is not the "
                                                  "program's fault", "evaluator_traceback": "Traceback ..."})},
    ]
    assert [p["id"] for p in programs if promote.is_execution_error(p)] == ["slow", "crash", "fault"]
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
    unwritable = tmp_path / "not-a-directory"
    unwritable.write_text("x", encoding="utf-8")
    assert promote.emit_discovery_lines(unwritable, "checkpoint_40", lines) is None  # reported, lines still printed
    err = capsys.readouterr()
    assert err.out.count("DISCOVERY: - ") == 3 and "could not append 3 DISCOVERY line(s)" in err.err


def test_promote_reads_rejection_reasons_from_disk_artifacts(tmp_path):
    promote = load("promote")
    checkpoint = tmp_path / "run" / "checkpoints" / "checkpoint_5"
    artifact_dir = checkpoint / "artifacts" / "big1"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "summary").write_text("stage 2 PASS\nstage 3 (full verifier, 64 shots/address) FAIL: rejected: gap",
                                          encoding="utf-8")
    program = {"id": "big1", "code": "", "_checkpoint": str(checkpoint), "artifact_dir": str(artifact_dir),
               "metrics": {"stage_reached": 3, "stage3_passed": 0.0, "predicted_ratio": 1.2}}
    assert promote.failure_reason(program).endswith("FAIL: rejected: gap")
    assert not promote.is_execution_error(program)
    assert [p["id"] for p in promote.negative_candidates([program])] == ["big1"]
    (artifact_dir / "evaluator_traceback").write_text("Traceback", encoding="utf-8")
    assert promote.is_execution_error(program) and promote.negative_candidates([program]) == []
