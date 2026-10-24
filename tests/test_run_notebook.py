"""The headless notebook runner. Needs the `notebooks` group: `uv run --group notebooks pytest`."""
from pathlib import Path
import subprocess
import sys

import pytest

nbformat = pytest.importorskip("nbformat")
pytest.importorskip("nbclient")
pytest.importorskip("ipykernel")

RUNNER = Path(__file__).resolve().parent.parent / "harness" / "run_notebook.py"


def write_notebook(path, *sources):
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_code_cell(source) for source in sources]
    nbformat.write(nb, path)
    return path


def run(path, *args):
    return subprocess.run([sys.executable, str(RUNNER), str(path), *args],
                          capture_output=True, text=True, timeout=300)


def test_executes_in_place(tmp_path):
    path = write_notebook(tmp_path / "two.ipynb", "x = 6 * 7\nprint('x =', x)", "x + 1")
    result = run(path)
    assert result.returncode == 0, result.stderr
    first, second = nbformat.read(path, as_version=4).cells
    assert [(o.output_type, o.name, o.text) for o in first.outputs] == [("stream", "stdout", "x = 42\n")]
    assert [(o.output_type, o.data["text/plain"]) for o in second.outputs] == [("execute_result", "43")]
    assert (first.execution_count, second.execution_count) == (1, 2)


def test_cell_error_exits_non_zero_and_names_the_cell(tmp_path):
    path = write_notebook(tmp_path / "bad.ipynb", "y = 1", "y / 0", "print('never')")
    result = run(path)
    assert result.returncode == 1
    assert "cell 2 of 3" in result.stderr and "'y / 0'" in result.stderr
    assert "ZeroDivisionError" in result.stderr
    cells = nbformat.read(path, as_version=4).cells
    assert cells[1].outputs[0].output_type == "error"  # traceback kept for review
    assert cells[2].outputs == []


def test_timeout_names_the_cell(tmp_path):
    path = write_notebook(tmp_path / "slow.ipynb", "import time", "time.sleep(30)")
    result = run(path, "--timeout", "2")
    assert result.returncode == 1
    assert "cell 2 of 2" in result.stderr and "timed out after 2s" in result.stderr
