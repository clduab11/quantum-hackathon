# SPDX-License-Identifier: Apache-2.0
"""Per-task search adapters (invsqrt, dfthcsos, dqi)."""
from __future__ import annotations

from search.adapters.base import TaskAdapter
from search.adapters.dfthcsos import DfthcsosAdapter
from search.adapters.dqi import DqiAdapter
from search.adapters.invsqrt import InvsqrtAdapter

ADAPTERS: dict[str, type[TaskAdapter]] = {
    "invsqrt": InvsqrtAdapter,
    "dfthcsos": DfthcsosAdapter,
    "dqi": DqiAdapter,
}


def get_adapter(task: str, **kwargs) -> TaskAdapter:
    """Return a TaskAdapter instance for ``task``."""
    try:
        cls = ADAPTERS[task]
    except KeyError as exc:
        raise ValueError(f"unknown task {task!r}; expected one of {sorted(ADAPTERS)}") from exc
    return cls(task=task, **kwargs)
