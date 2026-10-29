# SPDX-License-Identifier: Apache-2.0
"""Shared adapter contract for the staged search evaluator."""
from __future__ import annotations

import ast
import hashlib
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SEARCH_DIR = REPO_ROOT / "search"
DEFAULT_DATA = Path(
    os.environ.get(
        "VQCC_DATA",
        "/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation",
    )
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass
class StageTimings:
    stage0: float = 0.0
    stage1: float = 0.0
    stage2: float = 0.0
    stage3: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "stage0": round(self.stage0, 4),
            "stage1": round(self.stage1, 4),
            "stage2": round(self.stage2, 4),
            "stage3": round(self.stage3, 4),
        }


@dataclass
class CandidateBundle:
    """Artifacts produced by stage 0 for later stages."""

    task: str
    program_path: Path
    outdir: Path
    circuit_bytes: dict[str, bytes] = field(default_factory=dict)
    report: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""


class TaskAdapter:
    """One evolvable program + staged checks for a single VQCC task."""

    name: str = "base"
    initial_program: Path = SEARCH_DIR / "initial_program.py"

    def __init__(self, task: str | None = None, generation: int = 0) -> None:
        self.task = task or self.name
        self.generation = int(generation)

    def program_path(self) -> Path:
        return self.initial_program

    def stage0_parse(self, program_path: Path) -> list[str]:
        """Parse the program AST and return structural problems."""
        problems: list[str] = []
        try:
            tree = ast.parse(program_path.read_text(encoding="utf-8"), filename=str(program_path))
        except SyntaxError as exc:
            return [f"syntax error: {exc}"]
        if not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Assign))
                   for node in tree.body):
            problems.append("program has no top-level definitions")
        return problems

    def build_command(self, program_path: Path, outdir: Path) -> list[str]:
        raise NotImplementedError

    def stage0_build(self, program_path: Path, outdir: Path | None = None,
                     timeout: float = 420.0) -> CandidateBundle:
        """Run the candidate program and collect circuit artifacts."""
        out = Path(outdir or tempfile.mkdtemp(prefix=f"{self.task}-eval-"))
        bundle = CandidateBundle(task=self.task, program_path=program_path, outdir=out)
        bundle.problems.extend(self.stage0_parse(program_path))
        if bundle.problems:
            return bundle
        cmd = self.build_command(program_path, out)
        env = {
            **os.environ,
            "PYTHONPATH": str(REPO_ROOT),
            "QH_REPO_ROOT": str(REPO_ROOT),
            "PYTHONHASHSEED": "0",
            "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS", "2"),
        }
        try:
            proc = subprocess.run(
                cmd, cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            bundle.problems.append(f"build timed out after {timeout:.0f} s")
            partial = exc.stderr or b""
            bundle.stderr = (partial.decode("utf-8", "replace") if isinstance(partial, bytes) else partial)[-3000:]
            return bundle
        bundle.stdout = proc.stdout
        bundle.stderr = (proc.stderr or "")[-3000:]
        if proc.returncode != 0:
            tail = (proc.stderr or "").strip().splitlines()
            bundle.problems.append(f"program exited {proc.returncode}: {tail[-1] if tail else 'no stderr'}")
            return bundle
        try:
            bundle.report = self.parse_build_report(proc.stdout, out)
        except Exception as exc:  # noqa: BLE001
            bundle.problems.append(f"bad build report: {type(exc).__name__}: {exc}")
            return bundle
        bundle.circuit_bytes = self.collect_circuit_bytes(out)
        bundle.problems.extend(self.static_checks(bundle))
        return bundle

    def parse_build_report(self, stdout: str, outdir: Path) -> dict[str, Any]:
        del stdout, outdir
        return {}

    def collect_circuit_bytes(self, outdir: Path) -> dict[str, bytes]:
        """Read ``.kmb``/``.kmx`` files under ``outdir`` into memory."""
        found: dict[str, bytes] = {}
        for path in sorted(outdir.rglob("*")):
            if path.is_file() and path.suffix in {".kmb", ".kmx"}:
                found[path.relative_to(outdir).as_posix()] = path.read_bytes()
        return found

    def static_checks(self, bundle: CandidateBundle) -> list[str]:
        """Reject empty or text-looking circuit dumps before verification."""
        problems: list[str] = []
        if not bundle.circuit_bytes:
            problems.append("no .kmb/.kmx circuits written")
            return problems
        for name, data in bundle.circuit_bytes.items():
            head = data[:256]
            if not head:
                problems.append(f"{name} is empty")
                continue
            # Textual / JSON dumps are rejected; kickmix binaries contain NULs.
            if b"\x00" not in head and (head[:1] in (b"{", b"[", b"#") or head.startswith(b"qubit")):
                problems.append(f"{name} looks like text, not a .kmb binary")
            elif b"\x00" not in head:
                try:
                    head.decode("utf-8")
                except UnicodeDecodeError:
                    pass
                else:
                    if head.isascii() and any(ch in head.lower() for ch in (b"register", b"circuit", b"toffoli")):
                        problems.append(f"{name} looks like text, not a .kmb binary")
        return problems

    def stage1_sample(self, bundle: CandidateBundle, seed: int) -> dict[str, Any]:
        """Bit-parallel / cheap sample. Never sets ``feasible``."""
        raise NotImplementedError

    def stage2_verify(self, bundle: CandidateBundle) -> dict[str, Any]:
        """Official verifier. Sets ``feasible`` only on PASS."""
        raise NotImplementedError

    def cost_fields(self, bundle: CandidateBundle, sample: dict[str, Any],
                    verified: dict[str, Any] | None) -> dict[str, Any]:
        """Resource fields used by ``combined_score`` / rich metrics."""
        raise NotImplementedError

    def fingerprint(self, bundle: CandidateBundle) -> bytes:
        """Digest every file under ``bundle.outdir`` for the memo key.

        Relative path + content hash for each file. ``DqiAdapter`` overrides this
        for its large ``.kmb`` so it hashes on disk without loading the whole file.
        """
        parts: list[bytes] = []
        outdir = Path(bundle.outdir)
        if outdir.is_dir():
            for path in sorted(outdir.rglob("*")):
                if path.is_file():
                    rel = path.relative_to(outdir).as_posix()
                    parts.append(rel.encode("utf-8"))
                    parts.append(sha256_file(path).encode("ascii"))
        if parts:
            return b"\0".join(parts)
        # Fallback when the build wrote nothing on disk yet.
        for name in sorted(bundle.circuit_bytes):
            parts.append(name.encode("utf-8"))
            parts.append(sha256_bytes(bundle.circuit_bytes[name]).encode("ascii"))
        return b"\0".join(parts)

    def submission_identity(self, bundle: CandidateBundle) -> str:
        """Task-specific submission identity bound into the verifier memo key."""
        del bundle
        return ""

    def verifier_settings(self) -> dict[str, Any]:
        """Settings that can change a verification result (salt, workers, …)."""
        return {}

    def stage2_verify_reduced(self, bundle: CandidateBundle) -> dict[str, Any]:
        """Cheap / reduced-shot proxy. Must never set ``feasible`` True."""
        result = self.stage2_verify(bundle)
        result = dict(result)
        result["feasible"] = False
        result["verification_stage"] = "reduced"
        return result

    def stage2_verify_full(self, bundle: CandidateBundle) -> dict[str, Any]:
        """Full official verification. Sole path that may set ``feasible``."""
        result = self.stage2_verify(bundle)
        result = dict(result)
        result["verification_stage"] = "full"
        return result
