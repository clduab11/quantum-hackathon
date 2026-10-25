from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import ledger_fakes
import pytest
import yaml

from ledger.archive import build_zip
from ledger.gates.runner import DEFAULT_CONFIG, GateConfig, load_config, start_candidate
from ledger.run_manifest import Provenance, RunManifest

# A toy generator: writes deterministic bytes for one task at the manifest's relative paths.
GENERATOR = '''\
import sys
from pathlib import Path
task, out = sys.argv[1], Path(sys.argv[2])
files = {
    "invsqrt": ["invsqrt.kmb"],
    "dqi": ["dqi.kmb"],
    "dfthcsos": ["dfthcsos/angle_k_0.kmb", "dfthcsos/angle_k_1.kmb", "dfthcsos/submission.npz"],
}[task]
for name in files:
    path = out / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("generated " + name).encode() * 64)
'''
# A toy generator that reads a declared package input: it copies the dfthcsos factorization from
# $VQCC_DATA into the output (a copied declared input) and derives the two ANGLE circuits from
# its bytes. With --derive-only it writes a derived factorization instead of a copy. With
# --copy-as-circuit it also writes angle_k_0.kmb as a byte copy of the input (a copied circuit).
COPIER = '''\
import os, shutil, sys
from pathlib import Path
task, out = sys.argv[1], Path(sys.argv[2])
derive_only = "--derive-only" in sys.argv
copy_as_circuit = "--copy-as-circuit" in sys.argv
if task != "dfthcsos":
    path = out / f"{task}.kmb"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("generated " + path.name).encode() * 64)
    raise SystemExit(0)
source = Path(os.environ["VQCC_DATA"]) / "sample_submission" / "dfthcsos" / "submission.npz"
(out / "dfthcsos").mkdir(parents=True, exist_ok=True)
words = source.read_bytes()
if derive_only:
    (out / "dfthcsos" / "submission.npz").write_bytes(words[::-1])
else:
    shutil.copyfile(source, out / "dfthcsos" / "submission.npz")
for k in range(2):
    (out / "dfthcsos" / f"angle_k_{k}.kmb").write_bytes(bytes(b ^ k for b in words) * 4)
if copy_as_circuit:
    shutil.copyfile(source, out / "dfthcsos" / "angle_k_0.kmb")
'''
TASKS = ("invsqrt", "dqi", "dfthcsos")
PACKAGE_INPUT = "sample_submission/dfthcsos/submission.npz"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=ledger-test", "-c", "user.email=ledger-test@example.invalid",
         *args],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()


@dataclass
class Workspace:
    root: Path
    repo: Path
    zip_path: Path
    config: GateConfig
    manifests_root: Path
    evidence_root: Path
    queue_dir: Path
    package_root: Path

    def candidate(self, candidate_id: str = "cand-001", licence: str = "own",
                  parent: str | None = None) -> RunManifest:
        provenance = {
            t: Provenance(licence=licence,
                          parent_url=None if licence == "own" else "https://example.invalid/p")
            for t in TASKS
        }
        return start_candidate(self.zip_path, candidate_id, provenance,
                               parent_candidate_id=parent, salt_label=self.config.salt_label,
                               repo=self.repo)

    def context(self) -> dict:
        return {"repo": self.repo, "manifests_root": self.manifests_root,
                "evidence_root": self.evidence_root, "package_root": self.package_root}

    def copier_zip(self, name: str, *, derive_only: bool = False,
                   copy_as_circuit: bool = False) -> Path:
        """A candidate zip built by `copier.py` against this workspace's fake package."""
        built = self.root / name
        extra = self._copier_flags(derive_only, copy_as_circuit)
        for task in TASKS:
            subprocess.run([sys.executable, "copier.py", task, str(built), *extra], cwd=self.repo,
                           check=True, env={**os.environ, "VQCC_DATA": str(self.package_root)})
        return build_zip(built, self.root / f"{name}.zip")

    @staticmethod
    def _copier_flags(derive_only: bool, copy_as_circuit: bool) -> list[str]:
        return ((["--derive-only"] if derive_only else [])
                + (["--copy-as-circuit"] if copy_as_circuit else []))

    def copier_config(self, *, inputs: bool = True, sha256: str | None = None,
                      derive_only: bool = False, copy_as_circuit: bool = False) -> GateConfig:
        """The workspace config with copier.py as the dfthcsos generator and, by default, the
        package factorization declared as its input."""
        raw = yaml.safe_load(self.config.path.read_text())
        extra = self._copier_flags(derive_only, copy_as_circuit)
        raw["generators"]["dfthcsos"] = ["{python}", "copier.py", "dfthcsos", "{out}", *extra]
        if inputs:
            digest = sha256 or hashlib.sha256(
                (self.package_root / PACKAGE_INPUT).read_bytes()).hexdigest()
            raw["inputs"] = {"dfthcsos": [{"path": PACKAGE_INPUT, "sha256": digest}]}
        path = self.root / "copier-gates.yaml"
        path.write_text(yaml.safe_dump(raw, sort_keys=False))
        return load_config(path)


@pytest.fixture
def fakes():
    ledger_fakes.reset()
    yield ledger_fakes
    ledger_fakes.reset()


@pytest.fixture
def workspace(tmp_path: Path, fakes) -> Workspace:
    """A tiny generator repo, a candidate zip built from it, and a gate config whose G0–G3
    hooks are the fakes. G4 and G5 are the real checks."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "gen.py").write_text(GENERATOR)
    (repo / "copier.py").write_text(COPIER)
    git(repo, "add", "gen.py", "copier.py")
    git(repo, "commit", "-q", "-m", "toy generators")

    # A fake competition package holding one declared input.
    package = tmp_path / "package"
    (package / PACKAGE_INPUT).parent.mkdir(parents=True)
    (package / PACKAGE_INPUT).write_bytes(b"factorization words " * 32)

    built = tmp_path / "built"
    for task in TASKS:
        subprocess.run([sys.executable, "gen.py", task, str(built)], cwd=repo, check=True)
    zip_path = build_zip(built, tmp_path / "candidate.zip")

    raw = yaml.safe_load(DEFAULT_CONFIG.read_text())
    hooks = {"G0": "ledger_fakes:g0", "G1": "ledger_fakes:g1", "G2": "ledger_fakes:g2"}
    for gate in raw["gates"]:
        if gate["id"] == "G0":
            gate["params"]["hook"] = hooks["G0"]
        elif gate["id"] in ("G1", "G2"):
            gate["params"]["hooks"] = {t: hooks[gate["id"]] for t in TASKS}
        elif gate["id"] == "G3":
            gate["params"]["hook"] = "ledger_fakes:g3"
    raw["generators"] = {t: ["{python}", "gen.py", t, "{out}"] for t in TASKS}
    raw.pop("inputs", None)  # the toy generators read nothing; copier_config declares inputs
    config_path = tmp_path / "gates.yaml"
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False))

    return Workspace(
        root=tmp_path, repo=repo, zip_path=zip_path, config=load_config(config_path),
        manifests_root=tmp_path / "manifests", evidence_root=tmp_path / "evidence",
        queue_dir=tmp_path / "queue", package_root=package,
    )
