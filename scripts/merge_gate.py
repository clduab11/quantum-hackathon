"""Merge-order gate: squash every open pull request onto main in many orders, offline (PRA-210).

The board squash-merges pull requests one after another. Each one can be clean against `main`
and still conflict once an earlier one has landed. This gate replays that in a throwaway bare
repository, never touching the caller's checkout or any remote:

1. fetch `main` and every open pull request head (`refs/pull/N/head`), plus any `--ref`;
2. for each order, squash the heads onto `main` one at a time, the way GitHub's squash button
   does: a three-way merge of the head into the current tip (`git merge-tree`, merge base found
   automatically), committed as one new commit on the tip;
3. on every order that merges cleanly, run `python -m ledger.registers check` on the final tree,
   so duplicated decision ids or a changed closed register also fail.

Orders: every permutation when there are at most `--max-orders` of them (6 heads = 720), else
every rotation of the ascending and the descending order, which puts each head first and last
and each pair in both relative orders. Exit 0 when every order is clean and every check passes,
1 when any fails, 2 when the gate itself could not run. The report is markdown, for the PR body.

    python scripts/merge_gate.py                       # open PRs of the origin GitHub repo
    python scripts/merge_gate.py --ref mine=HEAD       # plus a local branch not yet opened
    python scripts/merge_gate.py --pr 12 --pr 13       # only these PRs (no GitHub API call)

Needs git 2.38 or newer (`merge-tree --write-tree`). Standard library only. Set GITHUB_TOKEN to
lift the anonymous API rate limit; the token is only sent to api.github.com.
"""

from __future__ import annotations

import argparse
import io
import itertools
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

GIT_ENV = {
    "GIT_AUTHOR_NAME": "merge-gate", "GIT_AUTHOR_EMAIL": "merge-gate@invalid",
    "GIT_COMMITTER_NAME": "merge-gate", "GIT_COMMITTER_EMAIL": "merge-gate@invalid",
    "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
    "GIT_TERMINAL_PROMPT": "0",
}


class GateError(RuntimeError):
    """The gate could not run (fetch, API or git failure). Not a merge result."""


@dataclass
class Head:
    label: str          # "#12" or the --ref label
    ref: str            # local ref inside the throwaway repository
    sha: str = ""
    title: str = ""
    draft: bool = False
    base: str = ""      # the PR's base branch, when it is not the gate's base (stacked PR)


@dataclass
class OrderResult:
    order: tuple[str, ...]
    conflict_at: str | None = None        # label of the head that conflicted
    after: tuple[str, ...] = ()           # heads already squashed when it conflicted
    files: list[str] = field(default_factory=list)
    tree: str | None = None               # final tree when clean


def git(repo: Path, *args: str, check: bool = True, input: bytes | None = None
        ) -> subprocess.CompletedProcess[bytes]:
    env = {**os.environ, **GIT_ENV}
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, env=env,
                          input=input, check=False)
    if check and proc.returncode != 0:
        raise GateError(f"git {' '.join(args)} failed: {proc.stderr.decode(errors='replace')}")
    return proc


def origin_repo(cwd: Path) -> str:
    """OWNER/NAME of the caller's `origin` remote when it is on github.com."""
    proc = subprocess.run(["git", "-C", str(cwd), "remote", "get-url", "origin"],
                          capture_output=True, text=True, check=False)
    match = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$", proc.stdout.strip())
    if not match:
        raise GateError("origin is not a github.com remote; pass --repo OWNER/NAME")
    return match.group(1)


def open_pulls(repo: str) -> list[dict]:
    """Every open pull request, whatever its base, from the GitHub REST API (all pages). A PR
    stacked on another PR's branch is still squashed onto the gate's base: that is where it
    lands once its parent merges and it is retargeted, and it is the case that conflicts."""
    pulls, page = [], 1
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "praxen-merge-gate"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    while True:
        url = f"https://api.github.com/repos/{repo}/pulls?state=open&per_page=100&page={page}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                        timeout=30) as resp:
                batch = json.load(resp)
        except OSError as exc:
            raise GateError(f"GitHub API {url}: {exc}") from exc
        pulls += batch
        if len(batch) < 100:
            return sorted(pulls, key=lambda p: p["number"])
        page += 1


def orders_for(labels: list[str], max_orders: int) -> list[tuple[str, ...]]:
    if math.factorial(len(labels)) <= max_orders:
        return list(itertools.permutations(labels))
    seen, orders = set(), []
    for base in (labels, labels[::-1]):
        for i in range(len(base)):
            order = tuple(base[i:] + base[:i])
            if order not in seen:
                seen.add(order)
                orders.append(order)
    return orders


class Simulator:
    """Squash merges in a bare repository, memoised by order prefix (orders share prefixes)."""

    def __init__(self, repo: Path, base_sha: str, heads: dict[str, Head]):
        self.repo, self.heads = repo, heads
        self.tips: dict[tuple[str, ...], str] = {(): base_sha}
        self.conflicts: dict[tuple[str, ...], list[str]] = {}

    def squash(self, tip: str, head: Head) -> tuple[str | None, list[str]]:
        proc = git(self.repo, "merge-tree", "--write-tree", "--name-only", "--no-messages",
                   tip, head.sha, check=False)
        lines = proc.stdout.decode().splitlines()
        if proc.returncode == 1:
            return None, sorted(set(lines[1:]))
        if proc.returncode != 0:
            raise GateError(f"merge-tree {head.label}: {proc.stderr.decode(errors='replace')}")
        commit = git(self.repo, "commit-tree", lines[0], "-p", tip, "-m",
                     f"squash {head.label}").stdout.decode().strip()
        return commit, []

    def run(self, order: tuple[str, ...]) -> OrderResult:
        for i in range(1, len(order) + 1):
            prefix = order[:i]
            if prefix in self.conflicts:
                return OrderResult(order, order[i - 1], order[:i - 1], self.conflicts[prefix])
            if prefix not in self.tips:
                commit, files = self.squash(self.tips[order[:i - 1]], self.heads[order[i - 1]])
                if commit is None:
                    self.conflicts[prefix] = files
                    return OrderResult(order, order[i - 1], order[:i - 1], files)
                self.tips[prefix] = commit
        tip = self.tips[order]
        tree = git(self.repo, "rev-parse", f"{tip}^{{tree}}").stdout.decode().strip()
        return OrderResult(order, tree=tree)


def register_check(repo: Path, tree: str) -> tuple[str, str]:
    """("PASS"|"FAIL"|"SKIP", output) of `python -m ledger.registers check` on a merged tree."""
    archive = git(repo, "archive", "--format=tar", tree).stdout
    with tempfile.TemporaryDirectory(prefix="merge-gate-tree-") as tmp:
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(tmp, filter="data")
        if not (Path(tmp) / "ledger" / "registers.py").exists():
            return "SKIP", "tree has no ledger/registers.py"
        proc = subprocess.run([sys.executable, "-m", "ledger.registers", "check", "--root", tmp],
                              cwd=tmp, capture_output=True, text=True, check=False,
                              env={**os.environ, "PYTHONPATH": tmp, "PYTHONDONTWRITEBYTECODE": "1"})
        out = (proc.stdout + proc.stderr).strip()
        return ("PASS" if proc.returncode == 0 else "FAIL"), out


def gate(args: argparse.Namespace, work: Path) -> tuple[bool, str]:
    cwd = Path.cwd()
    repo_name = args.repo or origin_repo(cwd)
    source = args.source or f"https://github.com/{repo_name}.git"
    git(work, "init", "-q", "--bare")

    heads: dict[str, Head] = {}
    excluded: list[str] = []
    if args.pr:
        pulls = [{"number": n, "title": "", "draft": False} for n in sorted(set(args.pr))]
    elif args.no_open_prs:
        pulls = []
    else:
        pulls = open_pulls(repo_name)
    for pull in pulls:
        label = f"#{pull['number']}"
        if pull["number"] in args.exclude or (args.exclude_drafts and pull.get("draft")):
            excluded.append(f"{label}{' (draft)' if pull.get('draft') else ''}")
            continue
        base_ref = (pull.get("base") or {}).get("ref", args.base)
        heads[label] = Head(label, f"refs/gate/pr/{pull['number']}", title=pull.get("title", ""),
                            draft=bool(pull.get("draft")),
                            base="" if base_ref == args.base else base_ref)
    refspecs = [f"+refs/heads/{args.base}:refs/gate/base"] + [
        f"+refs/pull/{h.ref.rsplit('/', 1)[1]}/head:{h.ref}" for h in heads.values()]
    git(work, "fetch", "-q", "--no-tags", source, *refspecs)
    for spec in args.ref:
        label, _, ref = spec.partition("=")
        if not ref:
            raise GateError(f"--ref {spec!r}: expected LABEL=REF")
        local = f"refs/gate/local/{len(heads)}"
        sha = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--verify", f"{ref}^{{commit}}"],
                             capture_output=True, text=True, check=False)
        if sha.returncode != 0:
            raise GateError(f"--ref {spec!r}: {sha.stderr.strip()}")
        git(work, "fetch", "-q", "--no-tags", str(cwd), f"+{ref}:{local}")
        heads[label] = Head(label, local, title=f"local {ref}")
    base_sha = git(work, "rev-parse", "refs/gate/base").stdout.decode().strip()
    for head in heads.values():
        head.sha = git(work, "rev-parse", head.ref).stdout.decode().strip()

    # A head already contained in the base adds nothing; say so, since its "clean" proves nothing.
    empty = [h.label for h in heads.values() if git(
        work, "merge-base", "--is-ancestor", h.sha, base_sha, check=False).returncode == 0]

    labels = list(heads)
    orders = orders_for(labels, args.max_orders)
    sim = Simulator(work, base_sha, heads)
    results = [sim.run(order) for order in orders]
    failed = [r for r in results if r.conflict_at]

    checks: dict[str, tuple[str, str]] = {}
    if not args.no_register_check:
        for tree in sorted({r.tree for r in results if r.tree}):
            checks[tree] = register_check(work, tree)
        if not labels:
            checks[base_sha] = register_check(work, base_sha)
    check_failed = [t for t, (status, _) in checks.items() if status == "FAIL"]
    ok = not failed and not check_failed

    exhaustive = len(orders) == math.factorial(len(labels))
    out = [f"### Merge-order gate: {'PASS' if ok else 'FAIL'}", "",
           f"- repository `{repo_name}`, base `{args.base}` at `{base_sha}`",
           f"- heads ({len(labels)}): " + (", ".join(
               f"{h.label} `{h.sha[:12]}`{' draft' if h.draft else ''}"
               f"{f' (stacked on `{h.base}`)' if h.base else ''}" for h in heads.values())
               or "none"),
           f"- excluded: {', '.join(excluded) or 'none'}",
           f"- heads already in the base (they prove nothing): {', '.join(empty) or 'none'}",
           (f"- orders squashed: {len(orders)} "
            f"({'every permutation' if exhaustive else 'rotations of both directions'}); "
            f"clean {len(results) - len(failed)}, conflicting {len(failed)}"), ""]
    if failed:
        pairs: dict[tuple[tuple[str, ...], str], list[str]] = {}
        for r in failed:
            pairs.setdefault((r.after, r.conflict_at), r.files)
        out += ["| squashed first | then conflicts | files |", "| --- | --- | --- |"]
        for (after, head), files in sorted(pairs.items(), key=lambda kv: (len(kv[0][0]), kv[0])):
            out.append(f"| {' → '.join(after) or '(main)'} | {head} | "
                       f"{', '.join(f'`{f}`' for f in files)} |")
        out.append("")
    if checks:
        out += ["| merged tree | register check |", "| --- | --- |"]
        for tree, (status, text) in checks.items():
            detail = text.replace("\n", "<br>").replace("|", "\\|")
            out.append(f"| `{tree[:12]}` | {status}: {detail} |")
        out.append("")
    return ok, "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", help="OWNER/NAME on GitHub (default: from origin)")
    parser.add_argument("--source", help="git URL to fetch from (default: the GitHub repo)")
    parser.add_argument("--base", default="main")
    parser.add_argument("--pr", type=int, action="append", default=[],
                        help="only these PR numbers (repeatable; skips the GitHub API)")
    parser.add_argument("--no-open-prs", action="store_true", help="only --ref heads")
    parser.add_argument("--ref", action="append", default=[], metavar="LABEL=REF",
                        help="also squash this local commit (repeatable)")
    parser.add_argument("--exclude", type=int, action="append", default=[],
                        help="leave out this PR number (repeatable; shown in the report)")
    parser.add_argument("--exclude-drafts", action="store_true")
    parser.add_argument("--max-orders", type=int, default=720)
    parser.add_argument("--no-register-check", action="store_true")
    parser.add_argument("--summary", type=Path, help="also append the report to this file")
    args = parser.parse_args(argv)
    work = Path(tempfile.mkdtemp(prefix="merge-gate-"))
    try:
        ok, report = gate(args, work)
    except GateError as exc:
        print(f"merge gate could not run: {exc}", file=sys.stderr)
        return 2
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(report)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as f:
            f.write(report + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
