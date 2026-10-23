from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS = ("invsqrt", "dqi", "dfthcsos")


def test_numpy_imports():
    assert np.arange(3).sum() == 3


def test_task_directories_exist():
    for task in TASKS:
        assert (REPO_ROOT / "tasks" / task).is_dir(), f"missing tasks/{task}"
        assert (REPO_ROOT / "tasks" / task / "candidates").is_dir(), f"missing tasks/{task}/candidates"
