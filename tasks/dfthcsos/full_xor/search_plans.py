# SPDX-License-Identifier: Apache-2.0
"""Search full-XOR plans for a word table and report Toffolis per pass and peak width.

    uv run python -m tasks.dfthcsos.full_xor.search_plans --out /tmp/pra359/b143.json
    uv run python -m tasks.dfthcsos.full_xor.search_plans --requantize 7 --clamp-canonical --emit-check

The factor is the declared non-circuit input of `tasks.dfthcsos.b143`. `--requantize 7` maps its 8-bit
words to 7 bits by half-up rounding (PRA-314). Nothing is written except the JSON named by `--out`.
The rows have the layout of `plans.json`, so `b143.compile_batch` replays them.
"""
import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from tasks.dfthcsos.full_xor import words as word_tools
from tasks.dfthcsos.full_xor.paired_anf import batch_deltas
from tasks.dfthcsos.full_xor.planio import plan_dict
from tasks.dfthcsos.full_xor.planner import BATCH, PlannerConfig, plan_delta

COMMITTED_TOFFOLI_PER_PASS = 4218   # the 15 committed plans of tasks/dfthcsos/full_xor/plans.json


def delta_sha256(delta) -> str:
    return hashlib.sha256(np.ascontiguousarray(np.asarray(delta, dtype=np.int64)).tobytes()).hexdigest()


def _work(job):
    index, delta, brot, config, emit = job
    result = plan_delta(delta, brot, config)
    report = dict(result.report)
    if emit:
        from tasks.dfthcsos.full_xor.emitter import build_staged
        _, meta = build_staged(result.plan, result.schedule)
        report['emitted'] = dict(T=meta['T'], Q=meta['Q'], products=meta['products'])
    return dict(batch=index, delta_sha256=delta_sha256(delta), plan=plan_dict(result.plan),
                schedule=result.schedule, report=report)


def search(words, brot: int, config: PlannerConfig, workers: int = 1, emit: bool = False) -> list[dict]:
    tables = [np.asarray(t, dtype=np.int64) for t in batch_deltas(np.asarray(words, dtype=np.int64), BATCH)]
    jobs = [(i, t.tolist(), brot, config, emit) for i, t in enumerate(tables)]
    if workers <= 1:
        return [_work(job) for job in jobs]
    with ProcessPoolExecutor(workers) as pool:
        return list(pool.map(_work, jobs))


def summarize(rows: list[dict]) -> dict:
    total = sum(r['report']['toffolis'] for r in rows)
    return dict(circuits=len(rows), toffolis_per_pass=total,
                peak_qubits=max(r['report']['qubits'] for r in rows),
                products=sum(r['report']['products'] for r in rows),
                low_computations=sum(r['report']['low_computations'] for r in rows),
                rejected_width=sum(r['report']['rejected_width'] for r in rows))


def main(argv=None):
    from tasks.dfthcsos import b143
    from tasks.dfthcsos.generate import DEFAULT_DATA, sha256_file
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--requantize', type=int, help='half-up requantize the 8-bit words to this many bits')
    parser.add_argument('--clamp-canonical', action='store_true',
                        help='measurement only: move non-canonical words one step in (not a shippable table)')
    parser.add_argument('--sizes', default='3,4', help='block sizes tried, comma separated')
    parser.add_argument('--partitions', type=int, default=1)
    parser.add_argument('--restarts', type=int, default=3)
    parser.add_argument('--effort', type=int, default=600, help='schedule local-search steps per capacity')
    parser.add_argument('--max-width', type=int, default=128)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--emit-check', action='store_true', help='also build each circuit with build_staged')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)

    source = args.data / b143.INPUT_PATH
    if sha256_file(source) != b143.INPUT_SHA256:
        raise SystemExit('B143 factor SHA-256 mismatch; restore the declared input')
    with np.load(source, allow_pickle=False) as archive:
        words, brot = np.asarray(archive['angle_words']), int(archive['brot'])
    if args.requantize:
        words, brot = word_tools.requantize(words, brot, args.requantize), args.requantize
    bad = int(word_tools.noncanonical(words, brot).sum())
    if args.clamp_canonical:
        words = word_tools.clamp_canonical(words, brot)
    config = PlannerConfig(sizes=tuple(int(x) for x in args.sizes.split(',')), partitions=args.partitions,
                           restarts=args.restarts, schedule_effort=args.effort, max_width=args.max_width,
                           seed=args.seed)
    started = time.time()
    rows = search(words, brot, config, args.workers, args.emit_check)
    summary = summarize(rows)
    summary.update(factor_sha256=b143.INPUT_SHA256, brot=brot, noncanonical_words=bad,
                   clamped=bool(args.clamp_canonical), committed_toffolis_per_pass=COMMITTED_TOFFOLI_PER_PASS,
                   seconds=round(time.time() - started, 1))
    for row in rows:
        r = row['report']
        print(f"batch {row['batch']:2d}  products {r['products']:3d}  T {r['toffolis']:3d}  Q {r['qubits']:3d}"
              f"  slots {r['capacity']:2d}  low {r['low_computations']:2d}  outputs {r['outputs']:2d}"
              f"  {r['seconds']:6.1f}s", flush=True)
    print(json.dumps(summary, indent=1))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(dict(summary=summary, config=dict(vars(args), out=str(args.out),
                                                                        data=str(args.data)), circuits=rows),
                                       default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
