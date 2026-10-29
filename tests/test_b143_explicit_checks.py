"""Correctness checks that must still fire when Python is started with -O."""
import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FULL_XOR = ROOT / 'tasks' / 'dfthcsos' / 'full_xor'


def _run_optimized(code):
    env = os.environ.copy()
    env['PYTHONPATH'] = str(ROOT) + os.pathsep + env.get('PYTHONPATH', '')
    # Drop interpreter flags that would hide a failure, and force -O.
    env.pop('PYTHONOPTIMIZE', None)
    return subprocess.run(
        [sys.executable, '-O', '-c', code],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False)


def test_assert_independent_names_the_first_address_under_optimize():
    completed = _run_optimized(
        'from types import SimpleNamespace\n'
        'from tasks.dfthcsos.full_xor.validation import assert_independent\n'
        'plan = SimpleNamespace(addresses=1, blocks=None, pure={}, products=[], brot=8)\n'
        'try:\n'
        '    assert_independent(plan, [[1]])\n'
        'except RuntimeError as exc:\n'
        '    if "address 0" not in str(exc):\n'
        '        raise SystemExit(str(exc))\n'
        '    raise SystemExit(0)\n'
        'raise SystemExit("did not raise")\n')
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_cache_audit_fires_under_optimize():
    completed = _run_optimized(
        'from types import SimpleNamespace\n'
        'from tasks.dfthcsos.full_xor.scheduler import audit\n'
        'plan = SimpleNamespace(products=[object()], pure={})\n'
        'schedule = {"events": [], "capacity": 8, "low_computations": 0}\n'
        'try:\n'
        '    audit(plan, schedule)\n'
        'except RuntimeError as exc:\n'
        '    if "products" not in str(exc):\n'
        '        raise SystemExit(str(exc))\n'
        '    raise SystemExit(0)\n'
        'raise SystemExit("did not raise")\n')
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_emitter_control_check_fires_under_optimize():
    completed = _run_optimized(
        'from tasks.dfthcsos.b143 import load_plans\n'
        'from tasks.dfthcsos.full_xor.emitter import build_staged\n'
        'from tasks.dfthcsos.full_xor.planio import plan_from_dict\n'
        'row = load_plans()[0]\n'
        'plan = plan_from_dict(row["plan"])\n'
        'plan.products[0].right1 |= 1\n'
        'try:\n'
        '    build_staged(plan, row["schedule"])\n'
        'except RuntimeError as exc:\n'
        '    if str(exc) != "constant product control unsupported":\n'
        '        raise SystemExit(str(exc))\n'
        '    raise SystemExit(0)\n'
        'raise SystemExit("did not reject constant product control")\n')
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_control_and_resource_checks_are_not_asserts():
    """`python -O` strips Assert nodes. These functions must not contain one."""
    expected = {
        'validation.py': {'assert_independent'},
        'scheduler.py': {'audit', 'optimize_cache'},
        'emitter.py': {'build_staged', 'require'},
    }
    for name, functions in expected.items():
        tree = ast.parse((FULL_XOR / name).read_text())
        found = set()
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in functions:
                found.add(node.name)
                asserts = [item for item in ast.walk(node) if isinstance(item, ast.Assert)]
                assert asserts == [], (name, node.name)
        assert found == functions, (name, found)
    emitter = ast.parse((FULL_XOR / 'emitter.py').read_text())
    staged = next(node for node in emitter.body
                  if isinstance(node, ast.FunctionDef) and node.name == 'build_staged')
    text = ast.get_source_segment((FULL_XOR / 'emitter.py').read_text(), staged)
    for phrase in (
        'constant product control unsupported',
        'nonborrowed output used as a control/workspace',
        'is also a control',
        'circuit toffolis',
        'circuit qubits',
    ):
        assert phrase in text
