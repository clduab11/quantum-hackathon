# Decisions register

Append-only. This file is also the negative-results memory: failed hypotheses are recorded here and never deleted.
To correct a row, append a new row that supersedes it and set the old row's status by reference in the new row.

| date | id | decision | evidence | status |
| --- | --- | --- | --- | --- |
| 2026-10-23 | D-001 | Repo bring-up on `op-vqcc/bringup`: Apache-2.0 licence, `pyproject.toml`, directory layout, `AGENTS.md`, `.gitignore` | Paperclip PRA-172; parent plan PRA-169 | accepted |
