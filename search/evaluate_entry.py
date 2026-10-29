# SPDX-License-Identifier: Apache-2.0
"""OpenEvolve evaluation entry: route live runs to the task-specific evaluator.

``SEARCH_TASK`` (set by ``search.run``) selects the backend:

* ``dfthcsos`` → ``search.evaluator`` (chemistry cascade)
* ``invsqrt`` / ``dqi`` → ``search.adapter_cascade`` (adapter cascade)

Smoke runs do not use this file; they go through ``search.staged`` instead.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_SEARCH_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SEARCH_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _task() -> str:
    """Active search task from the environment (default ``dfthcsos``)."""
    return os.environ.get("SEARCH_TASK", "dfthcsos")


def _backend():
    """Import the evaluator module that matches ``SEARCH_TASK``."""
    task = _task()
    if task == "dfthcsos":
        from search import evaluator as backend
        return backend, task
    if task in {"invsqrt", "dqi"}:
        from search import adapter_cascade as backend
        return backend, task
    raise ValueError(f"unknown SEARCH_TASK {task!r}; expected invsqrt, dfthcsos, or dqi")


def evaluate_stage1(program_path: str) -> Any:
    """Cascade stage 1 for the active task."""
    backend, task = _backend()
    if task == "dfthcsos":
        return backend.evaluate_stage1(program_path)
    return backend.evaluate_stage1(program_path, task=task)


def evaluate_stage2(program_path: str) -> Any:
    """Cascade stage 2 for the active task."""
    backend, task = _backend()
    if task == "dfthcsos":
        return backend.evaluate_stage2(program_path)
    return backend.evaluate_stage2(program_path, task=task)


def evaluate_stage3(program_path: str) -> Any:
    """Cascade stage 3 for the active task."""
    backend, task = _backend()
    if task == "dfthcsos":
        return backend.evaluate_stage3(program_path)
    return backend.evaluate_stage3(program_path, task=task)


def evaluate(program_path: str) -> Any:
    """Full non-cascade pipeline for the active task."""
    backend, task = _backend()
    if task == "dfthcsos":
        return backend.evaluate(program_path)
    return backend.evaluate(program_path, task=task)
