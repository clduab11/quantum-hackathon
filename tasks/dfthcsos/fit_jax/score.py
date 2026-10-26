# SPDX-License-Identifier: Apache-2.0
"""Score an exported factor through the unchanged official evaluator cascade."""
import json
import os
from pathlib import Path
from tasks.dfthcsos.factor_support import sha256


def score(factor, bits, out):
    config = out/'factor.json'  # JSON is a YAML subset, accepted by factor_config.
    with config.open('x') as stream:
        json.dump(dict(factorization=str(factor.resolve()),sha256=sha256(factor),source_brot=bits),stream)
    keys = dict(SEARCH_FACTOR_CONFIG=str(config),SEARCH_SCRATCH=str(out/'scratch'),
                SEARCH_RUN_DIR=str(out),SEARCH_KEEP_OUTPUTS='1')
    old = {k:os.environ.get(k) for k in keys}
    os.environ.update(keys)
    try:
        from search import evaluator
        program = str(Path(__file__).with_name('candidate_program.py'))
        result = evaluator.evaluate(program)
        full = json.loads(result.artifacts.get('verifier_full','{}'))
        return dict(metrics=result.metrics,artifacts=result.artifacts,official=full)
    finally:
        for key,value in old.items():
            if value is None:
                os.environ.pop(key,None)
            else:
                os.environ[key] = value
