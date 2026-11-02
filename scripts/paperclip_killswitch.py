"""Reversible kill-switch for the Paperclip agent fleet (OPS-01).

Spend in this company comes from on-demand wakeups (assignment and comment automations), not
from timed heartbeats. Arming the switch therefore does two things per target agent, through
Paperclip's own API and nothing else:

1. disables the automations that target the agent: the agent's `runtimeConfig.heartbeat`
   wake-on-demand gate (assignment and automation wakeups) and every *active* routine whose
   assignee is the agent (set to `paused`);
2. pauses the agent with Paperclip's own pause status (`POST /api/agents/<id>/pause`), which
   also cancels its queued and running heartbeat runs.

The previous state of every touched object is written to a JSON state file before the first
write, so `disarm` restores exactly what was there: agents that were not paused are resumed,
their previous `runtimeConfig` is put back verbatim, and routines get their previous status.
Agents that were already paused when the switch was armed stay paused on disarm.

Nothing else is touched: no budgets, no AI connections, no adapters, no issues.

Usage (the API URL and key come from the environment, never from a flag or a file):

    export PAPERCLIP_API_URL=http://127.0.0.1:3100      # default when unset
    export PAPERCLIP_API_KEY=...                          # a board key (never printed)
    export PAPERCLIP_COMPANY_ID=...                       # optional when the key sees one company

    uv run python scripts/paperclip_killswitch.py status
    uv run python scripts/paperclip_killswitch.py arm --dry-run        # print the plan, write nothing
    uv run python scripts/paperclip_killswitch.py arm                  # pause + disable, write the state file
    uv run python scripts/paperclip_killswitch.py disarm               # restore from the state file
    uv run python scripts/paperclip_killswitch.py arm --agents marcus,caine
    uv run python scripts/paperclip_killswitch.py arm --all            # include the protected agents too

Default targets: marcus, the-bowery-king, caine, sofia, aurelio. The protected agents john-wick,
the-high-table and the-adjudicator are never touched unless `--all` is given, even when named in
`--agents`. Terminated agents are skipped. The state file defaults to
`$PAPERCLIP_KILLSWITCH_STATE` or `./paperclip-killswitch-state.json`; `arm` refuses to run while
one exists (disarm first). `arm --force` archives the existing file as `<name>.<stamp>.superseded`
and warns: the new record is planned from the already-armed state, so restoring the original
state means `disarm --state <that archive>`.

Both `arm` and `disarm` are best effort: a failed API call is reported, the remaining actions still
run, and the exit code is 1. `arm` marks every action `applied` true or false in the state file,
`disarm` undoes only the applied ones, and an incomplete `disarm` leaves the still-undone actions
in the state file for the next run. A finished `disarm` moves the file to `<name>.<stamp>.restored`.

Standard library only. Exit 0 on success, 1 on an API or state error, 2 on bad arguments.
"""

from __future__ import annotations

import argparse
import copy
import datetime as _dt
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_API_URL = "http://127.0.0.1:3100"
DEFAULT_TARGETS = ("marcus", "the-bowery-king", "caine", "sofia", "aurelio")
PROTECTED = ("john-wick", "the-high-table", "the-adjudicator")
DEFAULT_STATE = "paperclip-killswitch-state.json"
STATE_VERSION = 1
# Paperclip's heartbeat policy: wake-on-demand is on unless one of these says otherwise.
WAKE_KEYS = ("wakeOnDemand", "wakeOnAssignment", "wakeOnOnDemand", "wakeOnAutomation")


class KillSwitchError(Exception):
    """A safe-to-print failure (never carries the key)."""


# --------------------------------------------------------------------------- HTTP client


class PaperclipClient:
    """Minimal board-key client. The key lives only in this object and the Authorization header."""

    def __init__(self, api_url: str, api_key: str, timeout: float = 60.0) -> None:
        if not api_key:
            raise KillSwitchError("PAPERCLIP_API_KEY is not set")
        self.api_url = api_url.rstrip("/")
        self._key = api_key
        self.timeout = timeout

    def request(self, method: str, path: str, body: Any = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.api_url + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self._key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:400].decode("utf-8", "replace")
            raise KillSwitchError(f"{method} {path} -> HTTP {exc.code}: {detail}") from None
        except urllib.error.URLError as exc:
            raise KillSwitchError(f"{method} {path} -> {exc.reason}") from None
        return json.loads(raw) if raw else None

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, body: Any = None) -> Any:
        return self.request("POST", path, body if body is not None else {})

    def patch(self, path: str, body: Any) -> Any:
        return self.request("PATCH", path, body)


def client_from_env(environ: dict[str, str] | None = None) -> PaperclipClient:
    env = os.environ if environ is None else environ
    return PaperclipClient(env.get("PAPERCLIP_API_URL") or DEFAULT_API_URL, env.get("PAPERCLIP_API_KEY", ""))


def resolve_company_id(client: PaperclipClient, wanted: str | None) -> str:
    companies = client.get("/api/companies") or []
    if wanted:
        if any(c.get("id") == wanted for c in companies):
            return wanted
        raise KillSwitchError(f"company {wanted} is not visible to this key")
    if len(companies) == 1:
        return companies[0]["id"]
    names = ", ".join(f"{c.get('name')}={c.get('id')}" for c in companies)
    raise KillSwitchError(f"set PAPERCLIP_COMPANY_ID; the key sees {len(companies)} companies: {names}")


# --------------------------------------------------------------------------- pure planning


def wake_on_demand_enabled(agent: dict[str, Any]) -> bool:
    """Mirror of Paperclip's isHeartbeatWakeOnDemandEnabled: first explicit flag wins, default on."""
    heartbeat = ((agent.get("runtimeConfig") or {}).get("heartbeat")) or {}
    for key in WAKE_KEYS:
        value = heartbeat.get(key)
        if isinstance(value, bool):
            return value
    return True


def heartbeat_timer_enabled(agent: dict[str, Any]) -> bool:
    heartbeat = ((agent.get("runtimeConfig") or {}).get("heartbeat")) or {}
    return heartbeat.get("enabled") is True


def disabled_runtime_config(runtime_config: dict[str, Any] | None) -> dict[str, Any]:
    """The same runtimeConfig with every wake gate off; everything else (aiConnection, debug,
    maxConcurrentRuns, unknown keys) is kept byte for byte."""
    cfg = copy.deepcopy(runtime_config or {})
    heartbeat = dict(cfg.get("heartbeat") or {})
    heartbeat["enabled"] = False
    heartbeat["wakeOnDemand"] = False
    for key in WAKE_KEYS[1:]:
        if key in heartbeat:
            heartbeat[key] = False
    cfg["heartbeat"] = heartbeat
    return cfg


def select_targets(agents: list[dict[str, Any]], names: list[str] | None, include_protected: bool
                   ) -> tuple[list[dict[str, Any]], list[str]]:
    """Agents to act on, and the names that were asked for but skipped (with the reason)."""
    wanted = list(names) if names else list(DEFAULT_TARGETS)
    by_name = {a["name"]: a for a in agents}
    chosen, skipped = [], []
    for name in wanted:
        agent = by_name.get(name)
        if agent is None:
            skipped.append(f"{name}: no such agent")
        elif name in PROTECTED and not include_protected:
            skipped.append(f"{name}: protected (pass --all to include)")
        elif agent.get("status") == "terminated":
            skipped.append(f"{name}: terminated")
        else:
            chosen.append(agent)
    return chosen, skipped


@dataclass
class Plan:
    actions: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        kinds: dict[str, int] = {}
        for action in self.actions:
            kinds[action["kind"]] = kinds.get(action["kind"], 0) + 1
        parts = [f"{n} {k}" for k, n in sorted(kinds.items())]
        return ", ".join(parts) if parts else "nothing to do"


def plan_arm(agents: list[dict[str, Any]], routines: list[dict[str, Any]], names: list[str] | None = None,
             include_protected: bool = False) -> Plan:
    """What `arm` would do, in execution order: wake gates off, routines paused, agents paused."""
    plan = Plan()
    targets, skipped = select_targets(agents, names, include_protected)
    plan.notes.extend(skipped)
    target_ids = {a["id"] for a in targets}
    for agent in targets:
        if wake_on_demand_enabled(agent) or heartbeat_timer_enabled(agent):
            before = copy.deepcopy(agent.get("runtimeConfig") or {})
            plan.actions.append({"kind": "disable_wake", "agentId": agent["id"], "name": agent["name"],
                                 "before": before, "after": disabled_runtime_config(before)})
        else:
            plan.notes.append(f"{agent['name']}: wake-on-demand already off")
    for routine in routines:
        if routine.get("assigneeAgentId") in target_ids and routine.get("status") == "active":
            plan.actions.append({"kind": "pause_routine", "routineId": routine["id"],
                                 "title": routine.get("title"), "assigneeAgentId": routine["assigneeAgentId"],
                                 "before": "active", "after": "paused"})
    for agent in targets:
        if agent.get("status") == "paused":
            plan.notes.append(f"{agent['name']}: already paused (left as is; disarm will not resume it)")
            continue
        plan.actions.append({"kind": "pause_agent", "agentId": agent["id"], "name": agent["name"],
                             "before": agent.get("status"), "after": "paused"})
    return plan


def plan_disarm(state: dict[str, Any]) -> Plan:
    """The exact inverse of the recorded arm, in reverse order."""
    if state.get("version") != STATE_VERSION:
        raise KillSwitchError(f"state file version {state.get('version')!r} is not {STATE_VERSION}")
    plan = Plan()
    for action in reversed(state.get("actions", [])):
        kind = action["kind"]
        if action.get("applied") is False:
            plan.notes.append(f"{action.get('name') or action.get('title')}: {kind} never applied; nothing to undo")
            continue
        if kind == "pause_agent":
            after = "idle"
            if action["before"] == "error":
                plan.notes.append(f"{action['name']}: was in error status before arming; "
                                  "Paperclip resumes it to idle (the error cannot be put back)")
            plan.actions.append({"kind": "resume_agent", "agentId": action["agentId"], "name": action["name"],
                                 "before": "paused", "after": after})
        elif kind == "pause_routine":
            plan.actions.append({"kind": "resume_routine", "routineId": action["routineId"],
                                 "title": action.get("title"), "before": "paused", "after": action["before"]})
        elif kind == "disable_wake":
            plan.actions.append({"kind": "restore_wake", "agentId": action["agentId"], "name": action["name"],
                                 "before": action["after"], "after": action["before"]})
        else:
            raise KillSwitchError(f"unknown action kind in state file: {kind}")
    return plan


# --------------------------------------------------------------------------- applying


def _apply_action(client: PaperclipClient, action: dict[str, Any]) -> str:
    kind = action["kind"]
    if kind == "disable_wake" or kind == "restore_wake":
        client.patch(f"/api/agents/{action['agentId']}", {"runtimeConfig": action["after"]})
        return f"{kind}: {action['name']}"
    if kind == "pause_routine" or kind == "resume_routine":
        client.patch(f"/api/routines/{action['routineId']}", {"status": action["after"]})
        return f"{kind}: {action.get('title')}"
    if kind == "pause_agent":
        client.post(f"/api/agents/{action['agentId']}/pause")
        return f"{kind}: {action['name']} ({action['before']} -> paused)"
    if kind == "resume_agent":
        client.post(f"/api/agents/{action['agentId']}/resume")
        return f"{kind}: {action['name']}"
    raise KillSwitchError(f"unknown action kind: {kind}")


def apply_plan(client: PaperclipClient, plan: Plan) -> tuple[list[str], list[str]]:
    """Run every action through the API, in order, best effort: a failed call is reported and
    the loop goes on, so one bad PATCH never leaves the other agents running. Each action gets
    `applied` set to True or False. Returns (done lines, failure lines)."""
    done, failed = [], []
    for action in plan.actions:
        try:
            done.append(_apply_action(client, action))
            action["applied"] = True
        except KillSwitchError as exc:
            action["applied"] = False
            failed.append(f"{action['kind']}: {action.get('name') or action.get('title')}: {exc}")
    return done, failed


def _stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def archive_state(state_path: Path, suffix: str) -> Path:
    """Move the state file aside under a timestamped name (`replace`: works on Windows too)."""
    archived = state_path.with_name(f"{state_path.name}.{_stamp()}.{suffix}")
    state_path.replace(archived)
    return archived


def load_state(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise KillSwitchError(f"no state file at {path}; the switch is not armed") from None
    except json.JSONDecodeError as exc:
        raise KillSwitchError(f"state file {path} is not JSON: {exc}") from None


def write_state(path: Path, api_url: str, company_id: str, plan: Plan) -> None:
    state = {"version": STATE_VERSION, "armedAt": _dt.datetime.now(_dt.timezone.utc).isoformat(),
             "apiUrl": api_url, "companyId": company_id, "actions": plan.actions, "notes": plan.notes}
    path.write_text(json.dumps(state, indent=1), encoding="utf-8")


# --------------------------------------------------------------------------- commands


def fetch(client: PaperclipClient, company_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    agents = client.get(f"/api/companies/{company_id}/agents") or []
    routines = client.get(f"/api/companies/{company_id}/routines") or []
    return agents, routines


def render_plan(plan: Plan, as_json: bool) -> str:
    if as_json:
        return json.dumps({"actions": plan.actions, "notes": plan.notes}, indent=1)
    lines = [f"plan: {plan.summary()}"]
    for action in plan.actions:
        who = action.get("name") or action.get("title")
        lines.append(f"  {action['kind']:<15} {who}  ({_short(action['before'])} -> {_short(action['after'])})")
    for note in plan.notes:
        lines.append(f"  note: {note}")
    return "\n".join(lines)


def _short(value: Any) -> str:
    if isinstance(value, dict):
        heartbeat = value.get("heartbeat") or {}
        return "wake=" + ("on" if wake_on_demand_enabled({"runtimeConfig": value}) else "off") + \
            (", timer=on" if heartbeat.get("enabled") is True else "")
    return str(value)


def cmd_status(client: PaperclipClient, company_id: str, state_path: Path) -> int:
    agents, routines = fetch(client, company_id)
    try:
        live = client.get(f"/api/companies/{company_id}/live-runs") or []
    except KillSwitchError:
        live = []
    live_by_agent: dict[str, int] = {}
    for run in live:
        live_by_agent[run.get("agentId")] = live_by_agent.get(run.get("agentId"), 0) + 1
    active_routines: dict[str, int] = {}
    for routine in routines:
        if routine.get("status") == "active":
            active_routines[routine.get("assigneeAgentId")] = active_routines.get(routine.get("assigneeAgentId"), 0) + 1
    armed = state_path.exists()
    print(f"switch: {'ARMED' if armed else 'disarmed'} (state file {state_path}{'' if armed else ' absent'})")
    print(f"{'agent':<18} {'status':<10} {'adapter':<14} {'wake':<5} {'timer':<6} {'routines':<9} {'live':<5} {'budget':<7} target")
    for agent in sorted(agents, key=lambda a: a["name"]):
        if agent.get("status") == "terminated":
            continue
        target = ("protected" if agent["name"] in PROTECTED
                  else "default" if agent["name"] in DEFAULT_TARGETS else "-")
        print(f"{agent['name']:<18} {agent.get('status'):<10} {agent.get('adapterType'):<14} "
              f"{'on' if wake_on_demand_enabled(agent) else 'off':<5} "
              f"{'on' if heartbeat_timer_enabled(agent) else 'off':<6} "
              f"{active_routines.get(agent['id'], 0):<9} {live_by_agent.get(agent['id'], 0):<5} "
              f"${(agent.get('budgetMonthlyCents') or 0) / 100:<6.2f} {target}")
    return 0


def cmd_arm(client: PaperclipClient, company_id: str, state_path: Path, names: list[str] | None,
            include_protected: bool, dry_run: bool, force: bool, as_json: bool) -> int:
    if state_path.exists() and not dry_run and not force:
        raise KillSwitchError(f"{state_path} exists: the switch is already armed (disarm first or pass --force)")
    agents, routines = fetch(client, company_id)
    plan = plan_arm(agents, routines, names, include_protected)
    print(render_plan(plan, as_json))
    if dry_run:
        print("dry run: nothing written")
        return 0
    if not plan.actions:
        print("nothing to arm; no state file written")
        return 0
    if state_path.exists():
        archived = archive_state(state_path, "superseded")
        print(f"warning: the switch was already armed; its record is archived at {archived}. "
              f"This run plans from the live (armed) state, so to restore the original state run "
              f"disarm with --state {archived}", file=sys.stderr)
    write_state(state_path, client.api_url, company_id, plan)   # the plan, before the first write
    done, failed = apply_plan(client, plan)
    write_state(state_path, client.api_url, company_id, plan)   # the same plan with `applied` flags
    for line in done:
        print(line)
    for line in failed:
        print(f"FAILED {line}", file=sys.stderr)
    print(f"{'armed with failures' if failed else 'armed'}; previous state saved to {state_path}")
    return 1 if failed else 0


def cmd_disarm(client: PaperclipClient, state_path: Path, dry_run: bool, as_json: bool) -> int:
    state = load_state(state_path)
    plan = plan_disarm(state)
    print(render_plan(plan, as_json))
    if dry_run:
        print("dry run: nothing written")
        return 0
    done, failed = apply_plan(client, plan)
    for line in done:
        print(line)
    for line in failed:
        print(f"FAILED {line}", file=sys.stderr)
    if failed:
        # Keep only what is still to undo, so the next disarm does not replay the restored part.
        undone = {(a["kind"], a.get("agentId") or a.get("routineId")) for a in plan.actions if a.get("applied")}
        inverse = {"resume_agent": "pause_agent", "resume_routine": "pause_routine", "restore_wake": "disable_wake"}
        remaining = [a for a in state["actions"]
                     if a.get("applied") is not False
                     and not any(inverse[k] == a["kind"] and i == (a.get("agentId") or a.get("routineId"))
                                 for k, i in undone)]
        state["actions"] = remaining
        state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
        print(f"disarm incomplete; {len(remaining)} action(s) left in {state_path}; run disarm again", file=sys.stderr)
        return 1
    archived = archive_state(state_path, "restored")
    print(f"disarmed; state file moved to {archived}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paperclip_killswitch", description=__doc__.split("\n\n")[0])
    parser.add_argument("--state", default=os.environ.get("PAPERCLIP_KILLSWITCH_STATE") or DEFAULT_STATE,
                        help="state file written by arm and read by disarm")
    parser.add_argument("--company", default=os.environ.get("PAPERCLIP_COMPANY_ID") or None,
                        help="company id (default: $PAPERCLIP_COMPANY_ID, or the key's only company)")
    parser.add_argument("--json", action="store_true", help="print plans as JSON")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="show every agent's status, wake gates, routines and live runs")
    arm = sub.add_parser("arm", help="pause the target agents and disable their automations")
    arm.add_argument("--agents", help="comma-separated agent names (default: the built-in list)")
    arm.add_argument("--all", action="store_true", help="also act on the protected agents")
    arm.add_argument("--dry-run", action="store_true", help="print the plan and write nothing")
    arm.add_argument("--force", action="store_true",
                     help="arm again although a state file exists (it is archived first, with a warning)")
    disarm = sub.add_parser("disarm", help="restore exactly what arm recorded")
    disarm.add_argument("--dry-run", action="store_true", help="print the plan and write nothing")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    state_path = Path(args.state)
    try:
        client = client_from_env()
        if args.command == "disarm":
            return cmd_disarm(client, state_path, args.dry_run, args.json)
        company_id = resolve_company_id(client, args.company)
        if args.command == "status":
            return cmd_status(client, company_id, state_path)
        names = [n.strip() for n in args.agents.split(",") if n.strip()] if args.agents else None
        return cmd_arm(client, company_id, state_path, names, args.all, args.dry_run, args.force, args.json)
    except KillSwitchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
