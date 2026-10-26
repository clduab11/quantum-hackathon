"""Regenerate the Schur DQI oracle from committed source, without data tapes.

The worker runs in an explicit temporary directory because the attributed
component emitters use relative scratch paths. No notebook, parameter download,
or circuit file is an input. See schur/PROVENANCE.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


def _worker(out: Path, n: int, m: int):
    import kickmix as km
    from tasks.dqi.schur.schur_extract_raw_compact import build as extract
    from tasks.dqi.schur.raw_cf_synthesize_destructive import build as synthesize, layout
    from tasks.dqi.schur.raw_cf_middle_lowtemp import write_middle

    started = time.monotonic()
    Path('candidates').mkdir()
    Path('results').mkdir()
    for reverse in (False, True):
        extract(n, reverse)
        synthesize(n, reverse)
    builder = km.CircuitBuilder()
    for i in range(n):
        builder.create_quantum_register(12, f'S{i}')
    for j in range(m):
        builder.create_classical_register(12, f'E{j}')
    half = n // 2
    slots = layout(n)
    extract_bits = 24 * half * (half - 1) // 2
    synthesis_bits = 24 * half
    private = 12 * m + extract_bits + synthesis_bits
    live = {q for word in slots['N'][:half] + slots['B'][:half] for q in word}
    scratch = [q for q in range(12 * n + 240) if q not in live]
    scan_path = Path('candidates/scan.kmx')
    with scan_path.open('w') as stream:
        stream.write(f"X q{slots['B'][half][0]}\n")
        middle = write_middle(stream, n, m, private, slots['N'][:half], slots['B'][:half], scratch)
        stream.write(f"X q{slots['B'][half][0]}\n")
    components = [
        (f'schur_extract_raw_compact_n{n}_forward.kmx', 12 * m),
        (f'raw_cf_synthesize_destructive_n{n}_forward.kmx', 12 * m + extract_bits),
        ('scan.kmx', 0),
        (f'raw_cf_synthesize_destructive_n{n}_inverse.kmx', 12 * m + extract_bits),
        (f'schur_extract_raw_compact_n{n}_inverse.kmx', 12 * m),
    ]
    bit = re.compile(r'(?<![a-zA-Z0-9])b(\d+)')
    full = Path('candidates/full.kmx')
    with full.open('w') as stream:
        stream.write(str(builder.finish_circuit()) + '\n')
        for filename, shift in components:
            with (Path('candidates') / filename).open() as source:
                for line in source:
                    if line.startswith(('REGISTER', 'APPEND_TO_REGISTER')):
                        continue
                    if shift:
                        line = bit.sub(lambda match: f'b{int(match[1]) + shift}', line)
                    stream.write(line)
    circuit = km.Circuit.from_file(str(full), format='kmx')
    target = out / 'dqi.kmb'
    circuit.to_file(str(target), format='kmb')
    with target.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    print(json.dumps(dict(N=n, M=m, Q=circuit.num_qubits,
        T=circuit.operation_statistics().num_toffoli_like, sha256=digest,
        seconds=time.monotonic()-started, middle=middle)), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--n', type=int, default=70)
    parser.add_argument('--m', type=int, default=4095)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.n < 6 or args.n > 70 or args.n % 2 or not 1 <= args.m <= 4095:
        parser.error('require even 6 <= n <= 70 and 1 <= m <= 4095')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.worker:
        _worker(out, args.n, args.m)
        return
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ, PYTHONPATH=str(root))
    with tempfile.TemporaryDirectory(prefix='dqi-schur-') as work:
        subprocess.run([sys.executable, '-m', 'tasks.dqi.generate_schur', '--worker',
            '--out', str(out), '--n', str(args.n), '--m', str(args.m)],
            cwd=work, env=env, check=True)


if __name__ == '__main__':
    main()
