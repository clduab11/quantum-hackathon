"""Prove the 19.5 mHa error1 check detects a removed margin gate.

Run from the repo: uv run python ledger/evidence/pra242/check_acceptance.py
Add --negative to remove that gate in memory: expected exit 1. Writes nothing.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--negative', action='store_true')
args = parser.parse_args()
source = Path(__file__).resolve().parents[3]/'tasks/dfthcsos/factor_measure.py'
text = source.read_text()
if args.negative:
    text = text.replace("('error_1', 'error_2')", "('error_2',)")
namespace = {}
exec(compile(text, str(source), 'exec'), namespace)
bad = dict(error_1=.0196, error_2=.0195, Lambda=49.001,
           E_gap=3.915048, lambda_eff=19.)
if not namespace['floor_problems'](bad, 3.):
    print('FAIL: missing error1 margin gate accepts 19.6 mHa; restore both-error check', file=sys.stderr)
    raise SystemExit(1)
print('PASS: 19.6 mHa error1 rejected at the 19.5 mHa floor')
