from __future__ import annotations

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
TASKS = ("invsqrt", "dqi", "dfthcsos")


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
                "evidence_root": self.evidence_root}


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
    git(repo, "add", "gen.py")
    git(repo, "commit", "-q", "-m", "toy generator")

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
    config_path = tmp_path / "gates.yaml"
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False))

    return Workspace(
        root=tmp_path, repo=repo, zip_path=zip_path, config=load_config(config_path),
        manifests_root=tmp_path / "manifests", evidence_root=tmp_path / "evidence",
        queue_dir=tmp_path / "queue",
    )
