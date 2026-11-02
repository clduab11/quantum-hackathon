# SPDX-License-Identifier: Apache-2.0
"""OpenEvolve evaluator for the dfthcsos search programs (see search/README.md).

Cascade. OpenEvolve calls the stages in order and stops at the first one whose ``combined_score``
falls below ``evaluator.cascade_thresholds`` ([0.05, 0.3] in the configs):

  evaluate_stage1  build: run the program in a subprocess, check that every circuit parses, uses at
                   most 128 qubits and carries no Z_POW rotation, then run the static G2 proxy
                   (tasks.dfthcsos.gates:g2_proxy) for predicted T and Q.
  evaluate_stage2  reduced official verifier: dfthcsos.verify.verify with 2 shots per address.
  evaluate_stage3  full official verifier: 64 shots per address (254,464 shots), same fixed salt.

``combined_score`` is the verified cost ratio (3,355,599,588.3155365 / cost) only when stage 3 passes.
Before that it is a small penalised proxy (below 0.7), so no unverified program can outrank a verified
one. Metrics also carry ``q``, ``t``, ``lambda_eff``, ``error1``, ``error2`` and the raw MAP-Elites features
``q_bin`` and ``t_bin`` (OpenEvolve min-max bins them). Artifacts carry the program report, the proxy
result, the verifier JSON and stderr so the model can read why a program failed.

The salt is the fixed public label PRA171_LOCAL_PUBLIC_FIXED_SALT_0001 and the shot counts are fixed;
nothing here searches over seeds or salts (AGENTS.md).

Memo. Verifier results and whole-program results go through search/memo.py, persisted under
$SEARCH_RUN_DIR/verifier_memo.jsonl, so an identical program source (same SHA-256) is answered without a
build and an identical circuit family without a verifier run; negative outcomes (a FAIL, a timeout, a
crashed child) are kept too and never re-run. Stage 0, a syntax check, runs before the build subprocess,
and the full verifier is only reached through a reduced-stage PASS, in-process and in the ``--verify-json``
child alike.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

try:  # OpenEvolve wraps plain dicts too, but artifacts need the dataclass
    from openevolve.evaluation_result import EvaluationResult
except ImportError:  # pragma: no cover - only when run outside the search venv
    @dataclass
    class EvaluationResult:  # type: ignore[no-redef]
        metrics: dict
        artifacts: dict = field(default_factory=dict)

SEARCH_DIR = Path(__file__).resolve().parent
REPO_ROOT = SEARCH_DIR.parent
if str(REPO_ROOT) not in sys.path:  # `tasks.*` imports, whether run as a script or inside an OpenEvolve worker
    sys.path.insert(0, str(REPO_ROOT))
from search.fitness import combined_score as dense_combined_score, log_safe  # noqa: E402
from search.memo import (  # noqa: E402
    MEMO_FILENAME, VerifierMemo, code_fingerprint, program_key, program_sha256, settings_digest, verification_key,
)

DEFAULT_DATA = "/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation"
_VERIFY_MEMO = VerifierMemo()  # persisted under $SEARCH_RUN_DIR (or $SEARCH_MEMO_PATH); in-process without either
_EVALUATOR_FINGERPRINT: str | None = None
_VERIFIER_FINGERPRINT: str | None = None
_FACTOR_DIGESTS: dict[tuple[str, int, int], str] = {}
# The official verifier and the circuit loader it runs on; a change to either misses every verifier memo entry.
VERIFIER_MODULES = ("dfthcsos.verify", "dfthcsos.scoreinfra.circuits", "kickmix")

BASELINE_COST = 3355599588.3155365
SALT = "PRA171_LOCAL_PUBLIC_FIXED_SALT_0001"
REDUCED_SHOTS = int(os.environ.get("SEARCH_REDUCED_SHOTS", "2"))
FULL_SHOTS = 64
FULL_VERIFIED_SHOTS = 254464
NUM_ANGLES = 75
QUBIT_CAP = 128
REFERENCE_T = 93237.0
REFERENCE_Q = 730.0
BUILD_TIMEOUT = float(os.environ.get("SEARCH_BUILD_TIMEOUT", "420"))
# The verifier runs in a child process so a pathological family can be killed; OpenEvolve's own stage
# timeout cannot stop a thread. 600 s is ten times the full verification of the reference family.
VERIFY_TIMEOUT = float(os.environ.get("SEARCH_VERIFY_TIMEOUT", "600"))
# Static size gates before any simulation: ten times the reference family's instruction count and
# static Toffoli count. Larger families would take minutes to simulate and cannot score above 0.1.
MAX_INSTRUCTIONS = int(os.environ.get("SEARCH_MAX_INSTRUCTIONS", str(30_000_000)))
MAX_STATIC_TOFFOLI = int(os.environ.get("SEARCH_MAX_STATIC_TOFFOLI", str(400_000)))
# Mirror of evaluator.cascade_thresholds in config_*.yaml; used only to clean up build outputs when
# OpenEvolve will not call the next stage.
STAGE1_THRESHOLD = 0.05
# Must sit below the reduced-PASS infeasible ceiling (0.5/1.01 ≈ 0.495) so a
# reduced official PASS advances the cascade into stage 3 (full verifier). The
# Deb feasible floor remains 0.5; only the cascade gate is lower.
STAGE2_THRESHOLD = 0.49
STALE_AFTER_SECONDS = 6 * 3600


# --- small helpers -----------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def scratch_root() -> Path:
    """Return the scratch directory for build outputs."""
    root = Path(os.environ.get("SEARCH_SCRATCH", tempfile.gettempdir()))
    root.mkdir(parents=True, exist_ok=True)
    return root


def sweep_stale_outputs(root: Path | None = None, max_age: float = STALE_AFTER_SECONDS) -> int:
    """Delete build directories an earlier crashed evaluation left behind."""
    removed = 0
    try:
        for path in (root or scratch_root()).glob("dfthcsos-eval-*"):
            try:
                if path.is_dir() and time.time() - path.stat().st_mtime > max_age:
                    shutil.rmtree(path, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
    except OSError:
        pass
    return removed


def factor_config(path: Path | None = None) -> dict[str, Any]:
    """The declared factor input: path, SHA-256 (checked now), precision and package path."""
    path = Path(path or os.environ.get("SEARCH_FACTOR_CONFIG", SEARCH_DIR / "factor.yaml"))
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    os.environ.setdefault("VQCC_DATA", DEFAULT_DATA)
    factor = Path(os.path.expandvars(str(raw["factorization"])))
    if not factor.is_file():
        raise FileNotFoundError(f"declared factor file is missing: {factor}")
    stat = factor.stat()
    cache_key = (str(factor), stat.st_size, stat.st_mtime_ns)  # hashed once per process unless the file changes
    digest = _FACTOR_DIGESTS.get(cache_key)
    if digest is None:
        digest = _FACTOR_DIGESTS[cache_key] = sha256_file(factor)
    if digest != str(raw["sha256"]):
        raise ValueError(f"declared factor {factor} has SHA-256 {digest}, pinned {raw['sha256']}")
    return {"path": factor, "sha256": digest, "source_brot": int(raw.get("source_brot", 12)),
            "package_relative_path": raw.get("package_relative_path")}


def _finite(value: Any) -> Any:
    """Replace NaN/inf (a rejected gap gives lambda_eff = nan) so JSON stays valid and binning stays sane."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(v) for v in value]
    return value


def num(value: Any, default: float = 0.0) -> float:
    """A finite float for the metrics dict, or ``default``."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def compact(value: Any, limit: int = 6000) -> str:
    """JSON-or-text truncate a value for OpenEvolve artifacts."""
    text = value if isinstance(value, str) else json.dumps(_finite(value), sort_keys=True, default=str)
    return text if len(text) <= limit else text[:limit] + " ...(truncated)"


def extract_notes(code: str) -> str:
    """Pull the NOTES triple-quoted block from a program."""
    match = re.search(r'NOTES\s*=\s*"""(.*?)"""', code, re.DOTALL)
    return match.group(1).strip() if match else ""


def _verifier_fingerprint() -> str:
    """Short digest of the official verifier and circuit-loader code, bound into every verifier memo key."""
    global _VERIFIER_FINGERPRINT
    if _VERIFIER_FINGERPRINT is None:
        _VERIFIER_FINGERPRINT = code_fingerprint(modules=VERIFIER_MODULES)
    return _VERIFIER_FINGERPRINT


def _evaluator_fingerprint() -> str:
    """Short digest of the scoring, proxy and verifier code, bound into program-memo keys so a change misses."""
    global _EVALUATOR_FINGERPRINT
    if _EVALUATOR_FINGERPRINT is None:
        _EVALUATOR_FINGERPRINT = code_fingerprint(
            files=(SEARCH_DIR / "evaluator.py", SEARCH_DIR / "fitness.py"),
            modules=("tasks.dfthcsos.gates", *VERIFIER_MODULES))
    return _EVALUATOR_FINGERPRINT


# --- stage 0: static checks on the source, before any subprocess -------------------------------


def stage0_checks(program_path: str | Path) -> list[str]:
    """Problems that make running the program pointless: unreadable, empty, or not valid Python."""
    path = Path(program_path)
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"stage 0: cannot read the program: {exc}"]
    if not source.strip():
        return ["stage 0: the program is empty"]
    try:
        ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [f"stage 0: syntax error: {exc.msg} (line {exc.lineno})"]
    except (ValueError, RecursionError) as exc:
        return [f"stage 0: cannot parse the program: {type(exc).__name__}: {exc}"]
    return []


# --- the build (stage 1) -----------------------------------------------------------------------


@dataclass
class Build:
    program_path: str
    program_sha256: str
    outdir: Path
    chemistry: Path
    report: dict | None = None
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    seconds: float = 0.0
    error: str | None = None
    files: dict[str, str] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    proxy: dict | None = None
    reduced: dict | None = None
    full: dict | None = None
    stage_seconds: dict[str, float] = field(default_factory=dict)

    @property
    def static_ok(self) -> bool:
        return not self.problems and self.report is not None


_BUILDS: dict[str, Build] = {}


def run_program(program_path: str) -> Build:
    """Run the candidate program in a subprocess against the declared factor file."""
    program_path = str(program_path)
    outdir = Path(tempfile.mkdtemp(prefix="dfthcsos-eval-", dir=scratch_root()))
    build = Build(program_path=program_path, program_sha256=program_sha256(program_path) or "",
                  outdir=outdir, chemistry=outdir / "dfthcsos")
    started = time.monotonic()
    problems = stage0_checks(program_path)  # stage 0 first: an unreadable or unparsable program is never executed
    build.stage_seconds["stage0"] = round(time.monotonic() - started, 3)
    if problems:
        build.error = "; ".join(problems)
        build.seconds = time.monotonic() - started
        return build
    try:
        cfg = factor_config()
    except Exception as exc:  # a misconfigured factor is an evaluator problem, not the program's
        build.error = f"factor config: {type(exc).__name__}: {exc}"
        build.seconds = time.monotonic() - started
        return build
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT), "QH_REPO_ROOT": str(REPO_ROOT),
           "PYTHONHASHSEED": "0", "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS", "2")}
    cmd = [sys.executable, program_path, "--out", str(outdir), "--factorization", str(cfg["path"]),
           "--source-brot", str(cfg["source_brot"])]
    try:
        proc = subprocess.run(cmd, cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=BUILD_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        build.error = f"build timed out after {BUILD_TIMEOUT:.0f} s"
        partial = exc.stderr or b""  # CPython hands back bytes here even with text=True
        build.stderr = (partial.decode("utf-8", "replace") if isinstance(partial, bytes) else partial)[-3000:]
        build.seconds = time.monotonic() - started
        return build
    build.seconds = time.monotonic() - started
    build.returncode = proc.returncode
    build.stdout = proc.stdout
    build.stderr = proc.stderr[-3000:]
    if proc.returncode != 0:
        tail = proc.stderr.strip().splitlines()
        build.error = f"program exited {proc.returncode}: {tail[-1] if tail else 'no stderr'}"
        return build
    try:
        build.report = json.loads(proc.stdout)
    except ValueError:
        build.error = "program printed no JSON report on stdout"
        return build
    if build.chemistry.is_dir():
        build.files = {p.relative_to(outdir).as_posix(): sha256_file(p)
                       for p in sorted(build.chemistry.rglob("*")) if p.is_file()}
    return build


def static_checks(build: Build) -> None:
    """Fill ``build.problems`` and ``build.proxy``; cheap checks before any simulation."""
    if build.error:
        build.problems.append(build.error)
        return
    report = build.report or {}
    circuits = report.get("circuits") or []
    if not circuits:
        build.problems.append("report lists no circuits")
        return
    batch_size = int(report.get("batch_size") or 0)
    if batch_size < 1:
        build.problems.append("report has no batch_size")
        return
    expected = math.ceil(NUM_ANGLES / batch_size)
    if len(circuits) != expected:
        build.problems.append(f"J={batch_size} needs {expected} circuits, program wrote {len(circuits)}")
    over = [c for c in circuits if int(c.get("num_qubits", 0)) > QUBIT_CAP]
    if over:
        build.problems.append(f"{len(over)} circuit(s) exceed {QUBIT_CAP} qubits "
                              f"(max {max(int(c['num_qubits']) for c in over)})")
    if any(int(c.get("z_pow", 0)) for c in circuits):
        build.problems.append("Z_POW rotations are rejected by the verifier (phases must be multiples of pi)")
    expected_files = {f"dfthcsos/angle_k_{k}.kmb" for k in range(expected)} | {"dfthcsos/submission.npz"}
    missing = sorted(expected_files - set(build.files))
    if missing:
        build.problems.append(f"missing output files: {missing}")
    instructions = sum(int(c.get("num_instructions", 0)) for c in circuits)
    static_toffoli = sum(int(c.get("toffoli_like_static", 0)) for c in circuits)
    if instructions > MAX_INSTRUCTIONS or static_toffoli > MAX_STATIC_TOFFOLI:
        build.problems.append(f"family too large to simulate: {instructions:,} instructions, {static_toffoli:,} static "
                              f"Toffolis (caps {MAX_INSTRUCTIONS:,} and {MAX_STATIC_TOFFOLI:,}; the reference has "
                              "2.8M and 39,740)")
    if build.problems:
        return
    try:
        from dfthcsos.scoreinfra.circuits import load_circuits, register_layout
        family = load_circuits(str(build.chemistry))
        layout = register_layout(family)
        rows = int(report.get("rows") or 3976)
        selection_bits = (rows - 1).bit_length()
        if len(layout.selection) != selection_bits:
            build.problems.append(f"selection register has {len(layout.selection)} qubits, the verifier needs "
                                  f"{selection_bits} for {rows} vectors")
    except Exception as exc:
        build.problems.append(f"circuits do not load: {type(exc).__name__}: {exc}")
        return
    try:
        from tasks.dfthcsos.gates import g2_proxy
        started = time.monotonic()
        proxy = g2_proxy(build.outdir)
        proxy["seconds"] = round(time.monotonic() - started, 2)
    except Exception as exc:
        build.problems.append(f"g2_proxy crashed: {type(exc).__name__}: {exc}")
        return
    if "estimated_cost" in proxy and proxy["estimated_cost"]:
        proxy["predicted_ratio"] = BASELINE_COST / float(proxy["estimated_cost"])
    build.proxy = proxy
    status = str(proxy.get("status", "FAIL: no status"))
    if status != "PASS":
        build.problems.append(f"static proxy: {status}")


# --- the official verifier (stages 2 and 3) ----------------------------------------------------


def _family_fingerprint(chemistry: Path) -> bytes:
    """Stable fingerprint of every file under the chemistry dir."""
    parts = []
    for path in sorted(Path(chemistry).rglob("*")):
        if path.is_file():
            parts.append(path.relative_to(chemistry).as_posix().encode("utf-8"))
            parts.append(sha256_file(path).encode("ascii"))
    return b"\0".join(parts)


def _submission_identity(chemistry: Path) -> str:
    """SHA-256 of ``submission.npz`` when present; empty otherwise."""
    path = Path(chemistry) / "submission.npz"
    if path.is_file():
        return sha256_file(path)
    return ""


def _verify_key(chemistry: Path, shots_per_address: int, timeout: float) -> bytes:
    """Memo key of one official verification of the family under ``chemistry``."""
    mode = "smoke" if os.environ.get("SEARCH_SMOKE") == "1" else "full"
    return verification_key(
        task="dfthcsos",
        mode=mode,
        circuit_fingerprint=_family_fingerprint(chemistry),
        shots=int(shots_per_address),
        verifier_settings=settings_digest({"salt": SALT, "timeout": timeout, "verifier": _verifier_fingerprint()}),
        submission_id=_submission_identity(chemistry),
    )


def _gated_by_reduced(reduced: dict[str, Any], shots_per_address: int) -> dict[str, Any]:
    """The answer to a full-verification request made before the reduced stage of the same family passed."""
    gated = {k: v for k, v in reduced.items() if k != "memo_hit"}
    gated.update(status="FAIL", shots_per_address=shots_per_address, salt=SALT,
                 gated=(f"full verification ({shots_per_address} shots/address) needs a reduced PASS first; the "
                        f"reduced stage ({REDUCED_SHOTS} shots/address) returned {reduced.get('status')}: "
                        f"{reduced.get('error')}"))
    gated.setdefault("error", gated["gated"])
    return gated


def verify_family_isolated(chemistry: Path, shots_per_address: int, timeout: float = VERIFY_TIMEOUT) -> dict[str, Any]:
    """``verify_family`` in a child process with a hard timeout (OpenEvolve cannot cancel a thread).

    Goes through the persistent memo first (a PASS, a FAIL, a timeout and a crashed child are all
    remembered), and never reaches the full verifier unless the reduced stage of the same family
    passed: a request for more than ``REDUCED_SHOTS`` recalls or runs the reduced verification first.
    """
    key = _verify_key(chemistry, shots_per_address, timeout)
    cached = _VERIFY_MEMO.get(key)
    if cached is not None:
        hit = dict(cached)
        hit["memo_hit"] = True
        return hit
    if int(shots_per_address) > REDUCED_SHOTS:
        reduced = verify_family_isolated(chemistry, REDUCED_SHOTS, timeout)
        if reduced.get("status") != "PASS":
            return _gated_by_reduced(reduced, shots_per_address)
    started = time.monotonic()
    cmd = [sys.executable, str(Path(__file__).resolve()), "--verify-json", str(chemistry), str(shots_per_address),
           str(timeout)]
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT), "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS", "2")}
    try:
        proc = subprocess.run(cmd, cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        payload = {"status": "FAIL", "shots_per_address": shots_per_address, "salt": SALT,
                   "error": f"verifier exceeded {timeout:.0f} s (the reference family takes 35 s; this one is too "
                            "slow to simulate)", "seconds": round(time.monotonic() - started, 2)}
        _VERIFY_MEMO.set(key, payload, negative=True)  # a family too slow to simulate is never simulated again
        return payload
    payload = None
    for line in reversed(proc.stdout.strip().splitlines()):
        if line.startswith("{"):
            try:
                payload = json.loads(line)
                break
            except ValueError:
                continue
    if not isinstance(payload, dict) or "status" not in payload:
        payload = {"status": "FAIL", "shots_per_address": shots_per_address, "salt": SALT,
                   "error": f"verifier child exited {proc.returncode} without a result: {proc.stderr.strip()[-800:]}",
                   "seconds": round(time.monotonic() - started, 2)}
        _VERIFY_MEMO.set(key, payload, negative=True)
        return payload
    payload.pop("memo_hit", None)  # the child may have answered from the shared file; this process still missed
    _VERIFY_MEMO.set(key, payload)
    return payload


def verify_json_child(chemistry: Path, shots_per_address: int, timeout: float = VERIFY_TIMEOUT) -> dict[str, Any]:
    """The ``--verify-json`` child: the same memo and the same reduced-before-full gate as the parent."""
    key = _verify_key(chemistry, shots_per_address, timeout)
    cached = _VERIFY_MEMO.get(key)
    if cached is not None:
        return {**cached, "memo_hit": True}
    if int(shots_per_address) > REDUCED_SHOTS:
        reduced_key = _verify_key(chemistry, REDUCED_SHOTS, timeout)
        reduced = _VERIFY_MEMO.get(reduced_key)
        if reduced is None:
            reduced = _VERIFY_MEMO.set(reduced_key, verify_family(chemistry, REDUCED_SHOTS))
        if reduced.get("status") != "PASS":
            return _gated_by_reduced(reduced, shots_per_address)
    return _VERIFY_MEMO.set(key, verify_family(chemistry, shots_per_address))


def verify_family(chemistry: Path, shots_per_address: int) -> dict[str, Any]:
    """Run Google's dfthcsos verifier with the fixed public salt; never raises."""
    from dfthcsos.verify import verify
    started = time.monotonic()
    out: dict[str, Any] = {"shots_per_address": shots_per_address, "salt": SALT}
    try:
        result = verify(str(chemistry), salt=SALT, shots_per_address=shots_per_address)
    except AssertionError as exc:  # accuracy, floor, gap or qubit-cap rejection
        out.update(status="FAIL", error=f"rejected: {exc}")
    except Exception as exc:  # InvalidCircuits (register contract, inconsistent words) and friends
        out.update(status="FAIL", error=f"{type(exc).__name__}: {exc}")
    else:
        resources = result["resources"]
        out.update(
            status="PASS", score=float(result["score"]), ratio=BASELINE_COST / float(result["score"]),
            toffoli_count=float(result["toffoli_count"]), num_qubits=int(result["num_qubits"]),
            lambda_eff=float(result["lambda_eff"]), brot=int(result["brot"]),
            batch_size=int(result["batch_size"]), num_circuits=int(result["num_circuits"]),
            verified_shots=int(result["verified_shots"]), submission_sha256=result["submission_sha256"],
            metrics={k: (float(v) if isinstance(v, (int, float)) else v) for k, v in result["metrics"].items()},
            resources={k: resources[k] for k in (
                "angles_toffoli", "angles_qubits", "angles_persistent_qubits", "angles_temporary_qubits",
                "heuristic_toffoli", "heuristic_persistent_qubits", "heuristic_temporary_qubits",
                "persistent_qubits", "temporary_qubits", "toffoli", "qubits") if k in resources},
        )
    out["seconds"] = round(time.monotonic() - started, 2)
    return out


# --- scoring -----------------------------------------------------------------------------------


def score_policy(static_ok: bool, predicted_ratio: float | None,
                 reduced: dict | None, full: dict | None,
                 *, resources: dict | None = None) -> float:
    """Deb-layered ``combined_score`` (research report §6.2).

    Only a full-verifier PASS enters the feasible band ``[0.5, 1]``. Everything
    earlier stays strictly below 0.5 so an infeasible candidate never outranks a
    feasible one.
    """
    resources = resources or {}
    if full is not None and full.get("status") == "PASS":
        res = {
            "feasible": True,
            "task": "dfthcsos",
            "toffoli_count": num(full.get("toffoli_count"), resources.get("t", REFERENCE_T)),
            "qubit_count": num(full.get("num_qubits"), resources.get("q", REFERENCE_Q)),
            "lambda_eff": num(full.get("lambda_eff"), 1.0),
        }
        return dense_combined_score(res, task="dfthcsos")
    # Graded infeasibility from whatever we know so far.
    if full is not None:
        fraction = 0.0
    elif reduced is not None and reduced.get("status") == "PASS":
        fraction = 0.99
    elif static_ok:
        fraction = 0.5 + 0.4 * min(max(predicted_ratio or 0.0, 0.0), 1.0)
    else:
        fraction = 0.0
    res = {
        "feasible": False,
        "fraction_correct": fraction,
        # Keep max-error at the graded floor (1.0 → violation 0) so fraction_correct
        # can differentiate static-only candidates; a hard 2.0 masked them all.
        "max_error_over_tol": 1.0,
        "ancilla_dirty_fraction": 0.0 if static_ok else 1.0,
        "phase_wrong_fraction": 0.0 if static_ok else 1.0,
    }
    score = dense_combined_score(res, task="dfthcsos")
    # Broken builds must fall below the stage-1 cascade threshold so OpenEvolve
    # records them and cleans up without advancing.
    if not static_ok:
        return min(score, STAGE1_THRESHOLD - 1e-6)
    return score


def assemble(build: Build) -> EvaluationResult:
    """Build metrics and artifacts from a Build across stages 1–3."""
    proxy = build.proxy or {}
    predicted = proxy.get("predicted_ratio")
    source = None
    for candidate in (build.full, build.reduced):
        if candidate and candidate.get("status") == "PASS":
            source = candidate
            break
    if source is not None:
        q, t, lambda_eff = num(source["num_qubits"]), num(source["toffoli_count"]), num(source["lambda_eff"])
        error1 = num(source["metrics"].get("error_1"))
        error2 = num(source["metrics"].get("error_2"))
        e_gap = num(source["metrics"].get("E_gap") or source["metrics"].get("e_gap"))
    elif num(proxy.get("estimated_qubits")) > 0 and num(proxy.get("estimated_toffoli")) > 0:
        q, t = num(proxy["estimated_qubits"]), num(proxy["estimated_toffoli"])
        lambda_eff = num(proxy.get("lambda_eff"))
        error1, error2 = num(proxy.get("error_1")), num(proxy.get("error_2"))
        e_gap = num(proxy.get("E_gap") or proxy.get("e_gap"))
    else:
        q, t, lambda_eff, error1, error2, e_gap = REFERENCE_Q, REFERENCE_T, 0.0, 0.0, 0.0, 0.0
    combined = score_policy(build.static_ok, predicted, build.reduced, build.full,
                            resources={"q": q, "t": t})
    predicted = num(predicted) or None
    report = build.report or {}
    full_pass = bool(build.full and build.full.get("status") == "PASS")
    reduced_pass = bool(build.reduced and build.reduced.get("status") == "PASS")
    if build.full is not None:
        stage_reached = 3
    elif build.reduced is not None:
        stage_reached = 2
    else:
        stage_reached = 1
    metrics = {
        "combined_score": num(combined),
        "ratio": num(build.full["ratio"]) if full_pass else 0.0,
        "predicted_ratio": num(predicted),
        "q": q, "t": t, "lambda_eff": lambda_eff, "error1": error1, "error2": error2,
        "toffoli_count": t, "qubit_count": q,
        "log_toffoli": log_safe(max(t, 1.0)), "log_qubits": log_safe(max(q, 1.0)),
        "fraction_correct": 1.0 if full_pass else (0.99 if reduced_pass else (0.5 if build.static_ok else 0.0)),
        "max_error_over_tol": 0.0 if full_pass else 0.0,
        "error_1": error1, "error_2": error2, "E_gap": e_gap,
        "margin_min": 0.0, "k_failures": 0.0, "eps_plus": 0.0,
        "feasible": 1.0 if full_pass else 0.0,
        "q_bin": q, "t_bin": t,  # kept for older checkpoints; MAP-Elites uses log_* now
        "stage1_passed": 1.0 if build.static_ok else 0.0,
        "stage2_passed": 1.0 if reduced_pass else 0.0,
        "stage3_passed": 1.0 if full_pass else 0.0,
        "stage_reached": float(stage_reached),
        "num_circuits": num(report.get("num_circuits")),
        "batch_size": num(report.get("batch_size")),
        "brot": num(report.get("brot")),
        "angle_qubits_max": num(report.get("max_qubits")),
    }
    lines = [f"stage reached: {stage_reached}/3; combined_score {metrics['combined_score']:.4f}"]
    if build.problems:
        lines.append("stage 1 FAILED: " + "; ".join(build.problems))
    else:
        lines.append(f"stage 1 PASS: {int(metrics['num_circuits'])} circuits, J={int(metrics['batch_size'])}, "
                     f"brot={int(metrics['brot'])}, widest circuit {int(metrics['angle_qubits_max'])} qubits, "
                     f"predicted ratio {predicted:.4f} (static T {proxy.get('estimated_toffoli')}, Q {proxy.get('estimated_qubits')})"
                     if predicted else "stage 1 PASS")
    for label, result in (("stage 2 (verifier, %d shots/address)" % REDUCED_SHOTS, build.reduced),
                          ("stage 3 (full verifier, %d shots/address)" % FULL_SHOTS, build.full)):
        if result is None:
            continue
        if result.get("status") == "PASS":
            lines.append(f"{label} PASS: ratio {result['ratio']:.6f}, T {result['toffoli_count']:.0f}, "
                         f"Q {result['num_qubits']}, lambda_eff {result['lambda_eff']:.4f}, {result['seconds']} s")
        else:
            lines.append(f"{label} FAIL: {result.get('error')}")
    artifacts: dict[str, str] = {"summary": "\n".join(lines)}
    if report:
        artifacts["program_report"] = compact({k: v for k, v in report.items() if k != "files"})
    if build.proxy:
        artifacts["g2_proxy"] = compact(build.proxy)
    if build.reduced:
        artifacts["verifier_reduced"] = compact(build.reduced)
    if build.full:
        artifacts["verifier_full"] = compact(build.full)
    if build.stderr.strip():
        artifacts["stderr"] = build.stderr.strip()[-3000:]
    if build.files:
        artifacts["files"] = compact(build.files)
    return EvaluationResult(metrics=metrics, artifacts=artifacts)


def record_evaluation(build: Build, result: EvaluationResult, final_stage: int) -> None:
    """One JSON record per evaluation under $SEARCH_RUN_DIR/evals (read by search/stats.py), and the
    program-source memo entry that answers an identical program next time."""
    remember_program(build, result, final_stage)
    run_dir = os.environ.get("SEARCH_RUN_DIR")
    if not run_dir:
        return
    try:
        evals = Path(run_dir) / "evals"
        evals.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": time.time(), "program_sha256": build.program_sha256, "final_stage": final_stage,
            "metrics": result.metrics, "summary": result.artifacts.get("summary", ""),
            "problems": build.problems, "build_seconds": round(build.seconds, 2),
            "stage_seconds": build.stage_seconds, "files": build.files,
            "notes": extract_notes(Path(build.program_path).read_text(encoding="utf-8", errors="replace"))
            if Path(build.program_path).is_file() else "",
        }
        (evals / f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}.json").write_text(
            json.dumps(payload, indent=1, default=str) + "\n", encoding="utf-8")
    except OSError:
        pass


def discard(build: Build) -> None:
    _BUILDS.pop(build.program_path, None)
    if os.environ.get("SEARCH_KEEP_OUTPUTS") == "1":
        return
    shutil.rmtree(build.outdir, ignore_errors=True)


def _build_for(program_path: str) -> Build:
    """Return a cached Build for ``program_path``, building if needed."""
    build = _BUILDS.get(str(program_path))
    if build is None or not build.outdir.exists():
        build = run_program(program_path)
        started = time.monotonic()
        static_checks(build)
        build.stage_seconds["stage1"] = round(time.monotonic() - started + build.seconds, 2)
        _BUILDS[str(program_path)] = build
    return build


# --- the program memo: identical sources are never rebuilt ------------------------------------


def _program_mode() -> str:
    return "smoke" if os.environ.get("SEARCH_SMOKE") == "1" else "full"


def program_memo_key(program_path: str) -> bytes | None:
    """Memo key for the whole evaluation of one program source, or ``None`` when it cannot be bound.

    Binds the program text, the declared factor input, shots, salt, size caps and a digest of the
    scoring code. An evaluator misconfiguration (unreadable or mismatched factor) yields no key, so
    it is never cached as the program's own failure.
    """
    digest = program_sha256(program_path)
    if digest is None:
        return None
    try:
        factor = factor_config()
    except Exception:  # noqa: BLE001
        return None
    settings = settings_digest({
        "salt": SALT, "reduced_shots": REDUCED_SHOTS, "full_shots": FULL_SHOTS,
        "factor_sha256": factor["sha256"], "source_brot": factor["source_brot"], "qubit_cap": QUBIT_CAP,
        "max_instructions": MAX_INSTRUCTIONS, "max_static_toffoli": MAX_STATIC_TOFFOLI,
        "evaluator": _evaluator_fingerprint(),
    })
    return program_key(task="dfthcsos", mode=_program_mode(), program_sha256=digest, settings=settings)


def cached_program_result(program_path: str) -> EvaluationResult | None:
    """The recorded result of an identical program source, if the memo holds one: no build, no verifier."""
    if str(program_path) in _BUILDS:  # this path is being evaluated right now; finish that
        return None
    key = program_memo_key(program_path)
    if key is None:
        return None
    cached = _VERIFY_MEMO.get(key)
    if not isinstance(cached, dict) or not isinstance(cached.get("metrics"), dict):
        return None
    artifacts = {str(k): v for k, v in (cached.get("artifacts") or {}).items()}
    artifacts["memo_hit"] = (f"program source sha256 {str(cached.get('program_sha256') or '')[:12]} was evaluated "
                             f"before (final stage {cached.get('final_stage')}); its result is reused without a build")
    return EvaluationResult(metrics=dict(cached["metrics"]), artifacts=artifacts)


def remember_program(build: Build, result: EvaluationResult, final_stage: int) -> None:
    """Store the terminal result of ``build`` under its program-source key (negative unless stage 3 passed)."""
    key = program_memo_key(build.program_path)
    if key is None:
        return
    _VERIFY_MEMO.set(key, {
        "metrics": dict(result.metrics), "artifacts": dict(result.artifacts), "final_stage": int(final_stage),
        "program_sha256": build.program_sha256, "problems": list(build.problems),
    }, negative=not result.metrics.get("stage3_passed"))


# --- OpenEvolve entry points -------------------------------------------------------------------


def _failed_result(program_path: str, stage: int, exc: BaseException) -> EvaluationResult:
    """The evaluator itself broke: score zero with the traceback, never an exception out of a stage."""
    import traceback
    metrics = {"combined_score": 0.0, "ratio": 0.0, "predicted_ratio": 0.0, "q": REFERENCE_Q, "t": REFERENCE_T,
               "lambda_eff": 0.0, "error1": 0.0, "error2": 0.0, "q_bin": REFERENCE_Q, "t_bin": REFERENCE_T,
               "stage1_passed": 0.0, "stage2_passed": 0.0, "stage3_passed": 0.0, "stage_reached": float(stage),
               "num_circuits": 0.0, "batch_size": 0.0, "brot": 0.0, "angle_qubits_max": 0.0}
    build = _BUILDS.get(str(program_path))
    if build is not None:
        discard(build)
    return EvaluationResult(metrics=metrics, artifacts={
        "summary": f"stage {stage}: the evaluator failed ({type(exc).__name__}: {exc}); this is not the program's fault",
        "evaluator_traceback": traceback.format_exc()[-3000:]})


def evaluate_stage1(program_path: str) -> EvaluationResult:
    """OpenEvolve stage 1: stage-0 syntax check, build + static proxy; an identical source answers from the memo."""
    try:
        cached = cached_program_result(program_path)
        if cached is not None:
            return cached
        sweep_stale_outputs()
        build = _build_for(program_path)
        result = assemble(build)
        if result.metrics["combined_score"] < STAGE1_THRESHOLD:
            record_evaluation(build, result, final_stage=1)
            discard(build)
        return result
    except Exception as exc:  # noqa: BLE001
        return _failed_result(program_path, 1, exc)


def evaluate_stage2(program_path: str) -> EvaluationResult:
    """OpenEvolve stage 2: reduced official verifier."""
    try:
        cached = cached_program_result(program_path)
        if cached is not None:
            return cached
        build = _build_for(program_path)
        if not build.static_ok:
            result = assemble(build)
            record_evaluation(build, result, final_stage=1)
            discard(build)
            return result
        build.reduced = verify_family_isolated(build.chemistry, REDUCED_SHOTS)
        build.stage_seconds["stage2"] = build.reduced.get("seconds", 0.0)
        result = assemble(build)
        if result.metrics["combined_score"] < STAGE2_THRESHOLD:
            record_evaluation(build, result, final_stage=2)
            discard(build)
        return result
    except Exception as exc:  # noqa: BLE001
        return _failed_result(program_path, 2, exc)


def evaluate_stage3(program_path: str) -> EvaluationResult:
    """OpenEvolve stage 3: full official verifier, reached only through a reduced PASS."""
    try:
        cached = cached_program_result(program_path)
        if cached is not None:
            return cached
        build = _build_for(program_path)
        if build.static_ok:
            if build.reduced is None:  # direct call without stage 2
                build.reduced = verify_family_isolated(build.chemistry, REDUCED_SHOTS)
                build.stage_seconds["stage2"] = build.reduced.get("seconds", 0.0)
            if build.reduced.get("status") == "PASS":
                build.full = verify_family_isolated(build.chemistry, FULL_SHOTS)
                build.stage_seconds["stage3"] = build.full.get("seconds", 0.0)
        result = assemble(build)
        record_evaluation(build, result, final_stage=3 if build.full is not None else (2 if build.reduced else 1))
        discard(build)
        return result
    except Exception as exc:  # noqa: BLE001
        return _failed_result(program_path, 3, exc)


def evaluate(program_path: str) -> EvaluationResult:
    """Non-cascade entry point: the whole pipeline with the same thresholds."""
    result = evaluate_stage1(program_path)
    if result.metrics["combined_score"] < STAGE1_THRESHOLD:
        return result
    result = evaluate_stage2(program_path)
    if result.metrics["combined_score"] < STAGE2_THRESHOLD:
        return result
    return evaluate_stage3(program_path)


def main(argv: list[str] | None = None) -> int:
    """CLI entry for evaluating one program or a verify-json child."""
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--verify-json"]:  # child process of verify_family_isolated: same memo, same reduced gate
        timeout = float(argv[3]) if len(argv) > 3 else VERIFY_TIMEOUT
        print(json.dumps(verify_json_child(Path(argv[1]), int(argv[2]), timeout), default=str))
        return 0
    parser = argparse.ArgumentParser(description="Evaluate one dfthcsos search program the way the loop does.")
    parser.add_argument("program", type=Path)
    parser.add_argument("--keep", action="store_true", help="keep the build directory (also SEARCH_KEEP_OUTPUTS=1)")
    parser.add_argument("--no-memo", action="store_true",
                        help="neither read nor write the verifier/program memo (also SEARCH_MEMO_DISABLE=1)")
    args = parser.parse_args(argv)
    if args.keep:
        os.environ["SEARCH_KEEP_OUTPUTS"] = "1"
    if args.no_memo:
        os.environ["SEARCH_MEMO_DISABLE"] = "1"
    elif not os.environ.get("SEARCH_RUN_DIR"):  # outside a run the scratch directory holds the memo; the child shares it
        os.environ.setdefault("SEARCH_MEMO_PATH", str(scratch_root() / MEMO_FILENAME))
    result = evaluate(str(args.program))
    print(json.dumps({"metrics": result.metrics, "artifacts": result.artifacts}, indent=1))
    return 0 if result.metrics.get("stage3_passed") else 1


if __name__ == "__main__":
    sys.exit(main())
