"""The merge-order gate (PRA-210): candidate branches cut from one main squash in any order.

The positive case builds three candidate branches on the new register layout, each doing what a
real candidate PR does (new manifest, new decisions, a rewritten notice entry), and squashes them
in every order. The negative control does the same on the old single-file layout and must
conflict, so a regression to shared register files is caught.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import merge_gate
from scripts.merge_gate import Head, Simulator, orders_for, register_check

REPO_ROOT = Path(__file__).resolve().parent.parent
FILES = ["NOTICE", "notices", "docs/DECISIONS.md", "docs/decisions", ".gitignore",
         "ledger/__init__.py", "ledger/registers.py", "ledger/manifests/index-legacy.csv",
         "ledger/manifests/candidates"]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env={**merge_gate.os.environ, **merge_gate.GIT_ENV}
                          ).stdout.strip()


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for rel in FILES:
        src = REPO_ROOT / rel
        if src.is_dir():
            shutil.copytree(src, root / rel)
        else:
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, root / rel)
    git(root.parent, "init", "-q", "-b", "main", str(root))
    commit_all(root, "main")
    return root


def branch(repo: Path, name: str, edits: dict[str, str | None]) -> Head:
    git(repo, "checkout", "-q", "-b", name, "main")
    for rel, text in edits.items():
        path = repo / rel
        if text is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    sha = commit_all(repo, name)
    git(repo, "checkout", "-q", "main")
    return Head(name, f"refs/heads/{name}", sha=sha)


def candidate(repo: Path, cid: str) -> str:
    data = json.loads((repo / "ledger/manifests/candidates/reference-001.json").read_text())
    data["candidate_id"], data["manifest_id"] = cid, f"00000000-0000-0000-0000-{cid[-12:]:0>12}"
    return json.dumps(data, indent=2) + "\n"


def row(ident: str) -> str:
    return f"| 2026-10-25 | {ident} | synthetic decision | test | accepted |\n"


def squash_all(repo: Path, heads: list[Head]):
    sim = Simulator(repo, git(repo, "rev-parse", "main"), {h.label: h for h in heads})
    return [sim.run(order) for order in orders_for([h.label for h in heads], 720)]


def test_candidate_branches_on_the_new_layout_squash_in_every_order(repo: Path):
    notices = repo / "notices"
    heads = [
        branch(repo, "invsqrt", {
            "ledger/manifests/candidates/cand-invsqrt.json": candidate(repo, "cand-invsqrt"),
            "docs/decisions/D-T1-01.md": row("D-T1-01"),
            "docs/decisions/D-T1-02.md": row("D-T1-02"),
            # Rewrites the existing invsqrt bullet and adds one: the case naive union got wrong.
            "notices/10-invsqrt.txt": "- invsqrt is a port (rewritten).\n- schedule parent.\n",
        }),
        branch(repo, "dqi", {
            "ledger/manifests/candidates/cand-dqi.json": candidate(repo, "cand-dqi"),
            "docs/decisions/D-T2-01.md": row("D-T2-01"),
            "notices/20-dqi.txt": (notices / "20-dqi.txt").read_text() + "- Gu port.\n",
        }),
        branch(repo, "tools", {
            "docs/decisions/D-T3-01.md": row("D-T3-01"),
            "notices/40-tools.txt": "- A new tool parent, Apache-2.0.\n",
        }),
    ]
    results = squash_all(repo, heads)
    assert len(results) == 6
    assert [r.conflict_at for r in results] == [None] * 6
    trees = {r.tree for r in results}
    assert len(trees) == 1  # every order lands the same registers
    status, out = register_check(repo, trees.pop())
    assert status == "PASS", out
    assert "decisions" in out


def test_old_single_file_layout_conflicts(repo: Path):
    """Negative control: two branches appending to one shared register conflict after the
    first squash, which is the failure PRA-210 removes."""
    closed = (repo / "docs/DECISIONS.md").read_text()
    heads = [branch(repo, n, {"docs/DECISIONS.md": closed + row(f"D-{n}-01")})
             for n in ("A", "B")]
    results = squash_all(repo, heads)
    assert all(r.conflict_at and r.files == ["docs/DECISIONS.md"] for r in results)


def test_same_decision_id_twice_conflicts_or_fails_the_check(repo: Path):
    heads = [branch(repo, n, {"docs/decisions/D-DUP-01.md": row("D-DUP-01").replace(
        "synthetic", n)}) for n in ("A", "B")]
    assert all(r.conflict_at for r in squash_all(repo, heads))  # add/add on one file


def test_register_check_fails_a_merged_tree_that_appends_to_the_closed_register(repo: Path):
    closed = (repo / "docs/DECISIONS.md").read_text()
    head = branch(repo, "late", {"docs/DECISIONS.md": closed + row("D-LATE-01")})
    (result,) = squash_all(repo, [head])
    status, out = register_check(repo, result.tree)
    assert status == "FAIL" and "closed" in out


def test_orders_cover_every_pair_both_ways_when_not_exhaustive():
    labels = [f"#{n}" for n in range(1, 9)]
    orders = orders_for(labels, 720)
    assert len(orders) == 16
    for a in labels:
        for b in labels:
            if a != b:
                assert any(o.index(a) < o.index(b) for o in orders)
    assert {o[0] for o in orders} == set(labels) == {o[-1] for o in orders}
    assert len(orders_for(labels[:3], 720)) == 6


def test_gate_end_to_end_on_local_refs(repo: Path, monkeypatch: pytest.MonkeyPatch,
                                       capsys: pytest.CaptureFixture[str]):
    branch(repo, "one", {"docs/decisions/D-E1-01.md": row("D-E1-01")})
    branch(repo, "two", {"docs/decisions/D-E2-01.md": row("D-E2-01")})
    monkeypatch.chdir(repo)
    code = merge_gate.main(["--repo", "x/y", "--source", str(repo), "--no-open-prs",
                            "--ref", "one=one", "--ref", "two=two"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "Merge-order gate: PASS" in out and "clean 2, conflicting 0" in out
    assert "already in the base (they prove nothing): none" in out


def test_gate_names_a_head_that_is_already_in_the_base(repo: Path, monkeypatch: pytest.MonkeyPatch,
                                                      capsys: pytest.CaptureFixture[str]):
    monkeypatch.chdir(repo)
    assert merge_gate.main(["--repo", "x/y", "--source", str(repo), "--no-open-prs",
                            "--ref", "stale=main"]) == 0
    assert "already in the base (they prove nothing): stale" in capsys.readouterr().out
