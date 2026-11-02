"""The Paperclip kill-switch (OPS-01): arm pauses only the targets and disables only their
automations; disarm restores exactly what arm recorded. The API is a fake that records calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import paperclip_killswitch as ks

WAKE_ON = {"heartbeat": {"enabled": False, "wakeOnDemand": True, "maxConcurrentRuns": 20}}
BOUND = {"heartbeat": {"enabled": False, "wakeOnDemand": True, "maxConcurrentRuns": 20},
         "aiConnection": {"mode": "responsible_user", "method": "subscription", "provider": "anthropic"}}


def agent(name: str, status: str = "idle", runtime: dict | None = None, adapter: str = "hermes_local") -> dict:
    return {"id": f"id-{name}", "name": name, "status": status, "adapterType": adapter,
            "runtimeConfig": WAKE_ON if runtime is None else runtime, "budgetMonthlyCents": 1200}


AGENTS = [
    agent("marcus"), agent("the-bowery-king"), agent("caine", adapter="codex_local"),
    agent("sofia", status="paused", adapter="codex_local"),
    agent("aurelio", runtime=BOUND, adapter="claude_local"),
    agent("john-wick", runtime=BOUND, adapter="claude_local"),
    agent("the-high-table", runtime={"heartbeat": {"enabled": False, "maxConcurrentRuns": 1}}, adapter="claude_local"),
    agent("the-adjudicator", adapter="codex_local"),
    agent("the-tracker", runtime={"heartbeat": {"wakeOnDemand": False}}),
    agent("old-grok", status="terminated"),
]
ROUTINES = [
    {"id": "r-caine", "title": "caine hourly", "status": "active", "assigneeAgentId": "id-caine"},
    {"id": "r-caine-old", "title": "caine archived", "status": "archived", "assigneeAgentId": "id-caine"},
    {"id": "r-jw", "title": "john-wick hourly", "status": "active", "assigneeAgentId": "id-john-wick"},
    {"id": "r-sofia", "title": "sofia paused", "status": "paused", "assigneeAgentId": "id-sofia"},
]


class FakeClient:
    """Enough of PaperclipClient to apply a plan: records every write and mutates its own copy."""

    def __init__(self, agents: list[dict], routines: list[dict]) -> None:
        self.api_url = "http://fake"
        self.agents = {a["id"]: json.loads(json.dumps(a)) for a in agents}
        self.routines = {r["id"]: dict(r) for r in routines}
        self.calls: list[tuple[str, str, object]] = []

    def get(self, path: str):
        self.calls.append(("GET", path, None))
        if path == "/api/companies":
            return [{"id": "co", "name": "Praxen"}]
        if path.endswith("/agents"):
            return list(self.agents.values())
        if path.endswith("/routines"):
            return list(self.routines.values())
        if path.endswith("/live-runs"):
            return []
        raise AssertionError(path)

    def patch(self, path: str, body):
        self.calls.append(("PATCH", path, body))
        if path.startswith("/api/agents/"):
            self.agents[path.split("/")[3]]["runtimeConfig"] = body["runtimeConfig"]
        elif path.startswith("/api/routines/"):
            self.routines[path.split("/")[3]]["status"] = body["status"]
        return {}

    def post(self, path: str, body=None):
        self.calls.append(("POST", path, body))
        agent_id, verb = path.split("/")[3], path.split("/")[4]
        self.agents[agent_id]["status"] = {"pause": "paused", "resume": "idle"}[verb]
        return self.agents[agent_id]


def test_plan_arm_targets_only_the_default_list_and_their_automations():
    plan = ks.plan_arm(AGENTS, ROUTINES)
    kinds = [(a["kind"], a.get("name") or a.get("title")) for a in plan.actions]
    assert kinds == [
        ("disable_wake", "marcus"), ("disable_wake", "the-bowery-king"), ("disable_wake", "caine"),
        ("disable_wake", "sofia"), ("disable_wake", "aurelio"),
        ("pause_routine", "caine hourly"),
        ("pause_agent", "marcus"), ("pause_agent", "the-bowery-king"), ("pause_agent", "caine"),
        ("pause_agent", "aurelio"),
    ]
    assert "sofia: already paused (left as is; disarm will not resume it)" in plan.notes
    touched = {a.get("name") or a.get("title") for a in plan.actions}
    assert not touched & {"john-wick", "the-high-table", "the-adjudicator", "the-tracker", "old-grok", "john-wick hourly"}


def test_disable_wake_keeps_everything_but_the_gates():
    plan = ks.plan_arm(AGENTS, ROUTINES, ["aurelio"])
    (wake,) = [a for a in plan.actions if a["kind"] == "disable_wake"]
    assert wake["before"] == BOUND
    assert wake["after"]["aiConnection"] == BOUND["aiConnection"]
    assert wake["after"]["heartbeat"] == {"enabled": False, "wakeOnDemand": False, "maxConcurrentRuns": 20}
    assert ks.wake_on_demand_enabled({"runtimeConfig": wake["after"]}) is False
    # absent flags mean "on" (Paperclip's default), so the-high-table counts as wake-on.
    assert ks.wake_on_demand_enabled(AGENTS[6]) is True
    assert ks.wake_on_demand_enabled(AGENTS[8]) is False


def test_protected_agents_need_all_and_unknown_names_are_reported():
    plan = ks.plan_arm(AGENTS, ROUTINES, ["john-wick", "nobody", "old-grok", "caine"])
    assert [a["name"] for a in plan.actions if a["kind"] == "pause_agent"] == ["caine"]
    assert "john-wick: protected (pass --all to include)" in plan.notes
    assert "nobody: no such agent" in plan.notes
    assert "old-grok: terminated" in plan.notes
    everything = ks.plan_arm(AGENTS, ROUTINES, ["john-wick"], include_protected=True)
    assert [a["kind"] for a in everything.actions] == ["disable_wake", "pause_routine", "pause_agent"]


def test_arm_then_disarm_round_trip_restores_exactly(tmp_path: Path):
    client = FakeClient(AGENTS, ROUTINES)
    before = json.loads(json.dumps({"agents": client.agents, "routines": client.routines}))
    state = tmp_path / "state.json"

    assert ks.cmd_arm(client, "co", state, None, False, False, False, False) == 0
    writes = [c for c in client.calls if c[0] != "GET"]
    assert [(m, p) for m, p, _ in writes] == [
        ("PATCH", "/api/agents/id-marcus"), ("PATCH", "/api/agents/id-the-bowery-king"),
        ("PATCH", "/api/agents/id-caine"), ("PATCH", "/api/agents/id-sofia"), ("PATCH", "/api/agents/id-aurelio"),
        ("PATCH", "/api/routines/r-caine"),
        ("POST", "/api/agents/id-marcus/pause"), ("POST", "/api/agents/id-the-bowery-king/pause"),
        ("POST", "/api/agents/id-caine/pause"), ("POST", "/api/agents/id-aurelio/pause"),
    ]
    assert client.agents["id-caine"]["status"] == "paused"
    assert client.routines["r-caine"]["status"] == "paused"
    assert ks.wake_on_demand_enabled(client.agents["id-aurelio"]) is False
    assert client.agents["id-john-wick"] == before["agents"]["id-john-wick"]
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["version"] == ks.STATE_VERSION and len(saved["actions"]) == 10

    # A second arm refuses while the state file exists.
    with pytest.raises(ks.KillSwitchError):
        ks.cmd_arm(client, "co", state, None, False, False, False, False)

    client.calls.clear()
    assert ks.cmd_disarm(client, state, False, False) == 0
    writes = [c for c in client.calls if c[0] != "GET"]
    assert [(m, p) for m, p, _ in writes] == [
        ("POST", "/api/agents/id-aurelio/resume"), ("POST", "/api/agents/id-caine/resume"),
        ("POST", "/api/agents/id-the-bowery-king/resume"), ("POST", "/api/agents/id-marcus/resume"),
        ("PATCH", "/api/routines/r-caine"),
        ("PATCH", "/api/agents/id-aurelio"), ("PATCH", "/api/agents/id-sofia"), ("PATCH", "/api/agents/id-caine"),
        ("PATCH", "/api/agents/id-the-bowery-king"), ("PATCH", "/api/agents/id-marcus"),
    ]
    assert {"agents": client.agents, "routines": client.routines} == before
    assert not state.exists()
    (restored,) = tmp_path.glob("state.json.*.restored")
    assert json.loads(restored.read_text(encoding="utf-8"))["actions"][0]["applied"] is True

    # A second full cycle must not trip over the first archive (Windows rename would).
    assert ks.cmd_arm(client, "co", state, None, False, False, False, False) == 0
    assert ks.cmd_disarm(client, state, False, False) == 0
    assert len(list(tmp_path.glob("state.json.*.restored"))) == 2
    assert {"agents": client.agents, "routines": client.routines} == before


def test_force_archives_the_original_record_and_warns(tmp_path: Path, capsys):
    client = FakeClient(AGENTS, ROUTINES)
    state = tmp_path / "state.json"
    assert ks.cmd_arm(client, "co", state, None, False, False, False, False) == 0
    original = state.read_text(encoding="utf-8")
    client.agents["id-caine"]["status"] = "idle"          # someone resumed caine by hand
    assert ks.cmd_arm(client, "co", state, None, False, False, True, False) == 0
    err = capsys.readouterr().err
    (archived,) = tmp_path.glob("state.json.*.superseded")
    assert archived.read_text(encoding="utf-8") == original
    assert "already armed" in err and str(archived) in err and "--state" in err
    # The new record was planned from the armed state: it only knows about caine's pause, so the
    # original record is the one that restores the fleet.
    assert [a["kind"] for a in json.loads(state.read_text(encoding="utf-8"))["actions"]] == ["pause_agent"]
    assert ks.cmd_disarm(client, archived, False, False) == 0
    assert all(a["status"] == "idle" for n, a in client.agents.items() if n not in ("id-sofia", "id-old-grok"))
    assert ks.wake_on_demand_enabled(client.agents["id-marcus"]) is True


class FailingClient(FakeClient):
    def __init__(self, agents, routines, fail: set[str]) -> None:
        super().__init__(agents, routines)
        self.fail = fail

    def patch(self, path, body):
        if path in self.fail:
            self.calls.append(("PATCH", path, body))
            raise ks.KillSwitchError(f"PATCH {path} -> HTTP 500")
        return super().patch(path, body)

    def post(self, path, body=None):
        if path in self.fail:
            self.calls.append(("POST", path, body))
            raise ks.KillSwitchError(f"POST {path} -> HTTP 500")
        return super().post(path, body)


def test_arm_is_best_effort_and_disarm_undoes_only_what_ran(tmp_path: Path, capsys):
    client = FailingClient(AGENTS, ROUTINES, {"/api/agents/id-marcus", "/api/agents/id-caine/pause"})
    before = json.loads(json.dumps({"agents": client.agents, "routines": client.routines}))
    state = tmp_path / "state.json"
    assert ks.cmd_arm(client, "co", state, None, False, False, False, False) == 1
    err = capsys.readouterr().err
    assert "FAILED disable_wake: marcus" in err and "FAILED pause_agent: caine" in err
    # Every other action still ran: the later agents are paused despite the early failure.
    assert client.agents["id-aurelio"]["status"] == "paused"
    assert client.agents["id-marcus"]["status"] == "paused"          # pause worked, wake PATCH did not
    assert client.agents["id-caine"]["status"] == "idle"              # pause failed
    assert ks.wake_on_demand_enabled(client.agents["id-caine"]) is False
    saved = json.loads(state.read_text(encoding="utf-8"))
    applied = {(a["kind"], a.get("name") or a.get("title")): a["applied"] for a in saved["actions"]}
    assert applied[("disable_wake", "marcus")] is False and applied[("pause_agent", "caine")] is False
    assert sum(1 for v in applied.values() if v) == 8

    client.fail.clear()
    client.calls.clear()
    assert ks.cmd_disarm(client, state, False, False) == 0
    writes = [(m, p) for m, p, _ in client.calls if m != "GET"]
    assert ("POST", "/api/agents/id-caine/resume") not in writes
    assert ("PATCH", "/api/agents/id-marcus") not in writes
    assert len(writes) == 8
    assert {"agents": client.agents, "routines": client.routines} == before


def test_incomplete_disarm_keeps_only_the_undone_actions(tmp_path: Path):
    client = FailingClient(AGENTS, ROUTINES, set())
    state = tmp_path / "state.json"
    assert ks.cmd_arm(client, "co", state, None, False, False, False, False) == 0
    client.fail.add("/api/agents/id-caine/resume")
    assert ks.cmd_disarm(client, state, False, False) == 1
    assert state.exists()
    left = json.loads(state.read_text(encoding="utf-8"))["actions"]
    assert [(a["kind"], a["name"]) for a in left] == [("pause_agent", "caine")]
    client.fail.clear()
    client.calls.clear()
    assert ks.cmd_disarm(client, state, False, False) == 0
    assert [(m, p) for m, p, _ in client.calls if m != "GET"] == [("POST", "/api/agents/id-caine/resume")]
    assert client.agents["id-caine"]["status"] == "idle" and not state.exists()


def test_dry_run_writes_nothing(tmp_path: Path, capsys):
    client = FakeClient(AGENTS, ROUTINES)
    state = tmp_path / "state.json"
    assert ks.cmd_arm(client, "co", state, None, False, True, False, True) == 0
    assert not state.exists()
    assert all(c[0] == "GET" for c in client.calls)
    plan = json.loads(capsys.readouterr().out.split("\ndry run")[0])
    assert len(plan["actions"]) == 10


def test_disarm_of_an_errored_agent_resumes_to_idle_and_says_so():
    state = {"version": ks.STATE_VERSION, "actions": [
        {"kind": "pause_agent", "agentId": "id-marcus", "name": "marcus", "before": "error", "after": "paused"}]}
    plan = ks.plan_disarm(state)
    assert plan.actions == [{"kind": "resume_agent", "agentId": "id-marcus", "name": "marcus",
                             "before": "paused", "after": "idle"}]
    assert plan.notes and "error" in plan.notes[0]
    with pytest.raises(ks.KillSwitchError):
        ks.plan_disarm({"version": 99, "actions": []})


def test_client_needs_a_key_and_never_reads_it_from_argv():
    with pytest.raises(ks.KillSwitchError):
        ks.client_from_env({"PAPERCLIP_API_URL": "http://x"})
    client = ks.client_from_env({"PAPERCLIP_API_KEY": "k", "PAPERCLIP_API_URL": "http://x/"})
    assert client.api_url == "http://x"
    parser = ks.build_parser()
    assert not any("key" in a.dest for a in parser._actions)
