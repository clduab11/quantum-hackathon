# Paperclip kill-switch (OPS-01)

`scripts/paperclip_killswitch.py` is a reversible stop button for the Paperclip agent fleet. It
talks only to Paperclip's own API and records the previous state of everything it touches, so
`disarm` puts things back exactly.

## Why it looks the way it does

An audit of the company's runs (2026-10-21 to 2026-11-02, 1,000 runs) found that no agent has a
timed heartbeat. Every run is a wakeup: `invocationSource` `automation` (647: comment, mention and
status-change automations on issues), `assignment` (310: an issue assigned to the agent) or
`on_demand` (43: a person pressed wake). The only routines (scheduled jobs) are one archived and
one paused. So "the automations that target an agent" are the agent's own wake-on-demand gate
(`runtimeConfig.heartbeat.wakeOnDemand`, which Paperclip treats as on unless set to `false`) plus
any active routine assigned to it.

`arm` therefore, per target agent and in this order:

1. `PATCH /api/agents/<id>` with the same `runtimeConfig`, wake gates set to `false` (everything
   else, including an `aiConnection` binding, is kept verbatim);
2. `PATCH /api/routines/<id> {"status": "paused"}` for every *active* routine assigned to it;
3. `POST /api/agents/<id>/pause` (Paperclip's own pause; it also cancels the agent's queued and
   running runs).

`disarm` replays the recorded actions in reverse: resume, routine status back, `runtimeConfig`
back. An agent that was already paused when the switch was armed is left paused.

Not touched: budgets, AI connections and grants, adapters, issues, the protected agents.

## Targets

Default: `marcus`, `the-bowery-king`, `caine`, `sofia`, `aurelio`. Protected and never touched
unless `--all` is given: `john-wick` (merges and uploads), `the-high-table` (the CEO seat) and
`the-adjudicator` (reviews). `--agents a,b` names a different list; protected names in it are
still skipped without `--all`. Terminated agents are skipped.

## Usage

The URL and key come from the environment only; the script has no key flag and never prints it.
The board key is held in Windows Credential Manager (`praxen/paperclip-board-key`, Chris's ruling
of 2026-10-19), so on this box run the script from Windows Python with the key injected
in-process (see the-array `scripts/paperclip-board-key.py`), not from a WSL shell.

```sh
export PAPERCLIP_API_URL=http://127.0.0.1:3100   # default
export PAPERCLIP_API_KEY=...                       # board key
export PAPERCLIP_COMPANY_ID=...                    # optional when the key sees one company

uv run python scripts/paperclip_killswitch.py status
uv run python scripts/paperclip_killswitch.py arm --dry-run
uv run python scripts/paperclip_killswitch.py arm
uv run python scripts/paperclip_killswitch.py disarm
```

`arm` writes `paperclip-killswitch-state.json` (or `$PAPERCLIP_KILLSWITCH_STATE`, or `--state`)
before its first write and refuses to run while that file exists. `arm --force` archives the
existing file as `<name>.<stamp>.superseded` and warns: the new record is planned from the
already-armed state, so the original state comes back only by running `disarm` (clears the new
record) and then `disarm --state <archive>`; an ordinary `arm` works again after that.

Both commands are best effort. A failed API call is reported on stderr, the remaining actions
still run, and the exit code is 1. The state file is rewritten after every action, so an
interrupted run leaves an accurate record: each action's `applied` is `"pending"` (never started),
`"unknown"` (in flight, or failed and the read-back failed too), `true` or `false`. A failed call
is read back from the API before it is recorded, because Paperclip may have applied it before the
response was lost. `disarm` undoes the applied and the unknown ones and skips the rest; an
incomplete `disarm` leaves the still-undone actions in the file for the next run. A finished `disarm` moves the file to `<name>.<stamp>.restored`
(`Path.replace`, so repeated cycles work on Windows too). `--json` prints plans as JSON. Exit
codes: 0 ok, 1 API or state error, 2 bad arguments.

## Tests

`tests/test_paperclip_killswitch.py` drives the planner and the apply loop against a fake API
that records every call: default targets and exclusions, the wake-gate rewrite, the arm/disarm
round trip (state after disarm equals state before arm, call for call, over two cycles), dry run,
`--force` (the original record is archived and still restores), a best-effort arm with two failing
calls (the other agents are still paused; disarm undoes only what ran), an incomplete disarm
(the undone actions stay in the file), and the errored-agent case (Paperclip resumes to `idle`; the previous `error` status cannot be restored,
and the plan says so).
