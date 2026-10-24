"""Load the inventoried metric; append data fallbacks so installed modules win."""
import hashlib
import importlib.util
import os
from pathlib import Path
import sys

DATA = Path(os.environ.get('VQCC_DATA', '/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation'))
METRIC = Path(os.environ.get('VQCC_METRIC', str(DATA.parent / 'google-quantum-ai-metric-v10.py')))
METRIC_SHA256 = 'e7c5bfafa13cb54e138c70a281ca08ecece3e9203b514f6616fa19bf33475c8f'
LOCAL_SALT = 'PRA171_LOCAL_PUBLIC_FIXED_SALT_0001'


def load_metric():
    if not METRIC.is_file():
        raise ValueError(f'Metric snapshot missing: {METRIC}; follow docs/handoffs/p0-4-kickmix-build.md')
    if hashlib.sha256(METRIC.read_bytes()).hexdigest() != METRIC_SHA256:
        raise ValueError('Metric snapshot hash mismatch; restore the inventoried v10 snapshot.')
    sys.path.extend(str(p) for p in (DATA / 'kickmix', DATA / 'verifiers') if str(p) not in sys.path)
    spec = importlib.util.spec_from_file_location('vqcc_metric_v10', METRIC)
    metric = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(metric)
    return metric
