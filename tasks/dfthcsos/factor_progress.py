# SPDX-License-Identifier: Apache-2.0
"""Persist unverified intermediate factors without replacing completed checkpoints."""
import time
from tasks.dfthcsos.factor_support import write_npz, sha256, json_text


def checkpoint_callback(out, stage, every):
    if every < 1:
        raise ValueError('checkpoint interval must be positive')
    count, records, started = 0, [], time.monotonic()
    def save(params):
        nonlocal count
        count += 1
        if count % every:
            return
        path = out/f'inflight-{stage:02d}-{count:06d}.npz'
        write_npz(path, params)
        records.append(dict(iteration=count, file=path.name, sha256=sha256(path),
                            seconds=time.monotonic()-started, verified=False))
        tmp = out/f'inflight-{stage:02d}.tmp'
        tmp.write_text(json_text(records))
        tmp.replace(out/f'inflight-{stage:02d}.json')
        print(json_text(dict(stage=stage, checkpoint=records[-1])), flush=True)
    return save
