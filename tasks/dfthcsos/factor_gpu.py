# SPDX-License-Identifier: Apache-2.0
"""Check CUDA matrix multiplication and gradients before a chemistry GPU fit."""
import argparse
import json
import sys


def check_cuda():
    """Fail before fitting when CUDA or either required precision is unusable."""
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError('PyTorch is missing; run uv sync --group gpu in this worktree') from exc
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA is unavailable; check WSL GPU access and CUDA_VISIBLE_DEVICES; '
                           'CPU fitting is forbidden')
    device = torch.device('cuda:0')
    checks = {}
    for dtype in (torch.float32, torch.float64):
        x = torch.arange(1, 5, dtype=dtype, device=device).reshape(2, 2).requires_grad_()
        y = x @ x.T
        y.sum().backward()
        expected_y = torch.tensor([[5, 11], [11, 25]], dtype=dtype, device=device)
        expected_grad = torch.tensor([[8, 12], [8, 12]], dtype=dtype, device=device)
        if not torch.equal(y, expected_y) or not torch.equal(x.grad, expected_grad):
            raise RuntimeError(f'{dtype} CUDA matrix/gradient check failed; do not start a fit')
        checks[str(dtype)] = 'PASS'
    torch.cuda.synchronize(device)
    props = torch.cuda.get_device_properties(device)
    free, total = torch.cuda.mem_get_info(device)
    return dict(status='PASS', device=str(device), name=props.name,
                capability=list(torch.cuda.get_device_capability(device)),
                torch=torch.__version__, cuda_runtime=torch.version.cuda,
                python=sys.version.split()[0], free_bytes=free, total_bytes=total,
                peak_allocated_bytes=torch.cuda.max_memory_allocated(device), checks=checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False,
        epilog='Run: uv run --group gpu python -m tasks.dfthcsos.factor_gpu. '
               'Needs WSL GPU access and uv sync --group gpu. Writes no files; '
               'exit 0 prints JSON evidence, exit 1 prints an actionable error. '
               'This is a runtime check, not a factor or verifier result.')
    parser.parse_args()
    try:
        print(json.dumps(check_cuda(), indent=2))
        return 0
    except (RuntimeError, OSError) as exc:
        print(f'factor GPU: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
