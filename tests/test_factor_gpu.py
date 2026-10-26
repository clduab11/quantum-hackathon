"""Runtime smoke and real failure case; never run a chemistry fit on CPU."""
import importlib.util
import json
import os
import subprocess
import sys

import pytest


def run(*args, hidden=False):
    env = dict(os.environ)
    if hidden:
        env['CUDA_VISIBLE_DEVICES'] = ''
    return subprocess.run([sys.executable, '-m', 'tasks.dfthcsos.factor_gpu', *args],
                          capture_output=True, text=True, env=env, timeout=60)


def test_help_without_gpu():
    result = run('--help', hidden=True)
    assert result.returncode == 0
    assert 'uv sync --group gpu' in result.stdout


@pytest.mark.skipif(importlib.util.find_spec('torch') is None, reason='optional gpu group')
def test_hidden_gpu_refuses_cpu_fallback():
    result = run(hidden=True)
    assert result.returncode == 1
    assert result.stdout == ''
    assert 'CPU fitting is forbidden' in result.stderr


@pytest.mark.skipif(importlib.util.find_spec('torch') is None, reason='optional gpu group')
def test_real_cuda_forward_and_backward():
    import torch
    if not torch.cuda.is_available():
        pytest.skip('CUDA hardware unavailable')
    result = run()
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['device'] == 'cuda:0'
    assert report['checks'] == {'torch.float32': 'PASS', 'torch.float64': 'PASS'}
    assert report['peak_allocated_bytes'] > 0
