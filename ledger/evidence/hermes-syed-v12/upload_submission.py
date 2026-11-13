"""Upload a zip with the Kaggle CLI, then print the new submission's ref as the last stdout line.

Called by `ledger.scorecard submit --upload-command`, which appends the zip path:
    python kaggle_submit_and_ref.py "<unique message>" <zip>
All Kaggle CLI output goes to stderr so stdout carries only the ref. If the ref cannot be found,
nothing is printed and the ledger keeps the reservation pending for `record`/`reconcile`.
No credentials are read here; the Kaggle CLI uses its own configuration.
"""
import csv
import io
import os
import subprocess
import sys
import time

KAGGLE = 'C:/Users/cld-main/.local/bin/kaggle.exe'
COMP = 'google-verifiable-quantum-circuit-compilation'
LOG = 'C:/Users/cld-main/Desktop/ops/quantum-hackathon-phase0-data/kaggle-upload-cli.log'


def rows():
    out = subprocess.run([KAGGLE, 'competitions', 'submissions', COMP, '--csv'],
                         capture_output=True, text=True, check=True, timeout=120).stdout
    lines = out.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith('ref,'))
    return list(csv.DictReader(io.StringIO('\n'.join(lines[start:]))))


def main(argv):
    if len(argv) == 2 and argv[1] == '--list':
        for row in rows()[:3]:
            print(row['ref'], row['date'], row['status'], row['publicScore'], row['description'][:60],
                  file=sys.stderr)
        return 0
    message, zip_path = argv[1], argv[2]
    # Kaggle refuses any upload not named submission.zip (D-PRA178-03). Upload a byte-identical
    # copy under that name and refuse if the copy's SHA-256 differs from the gated zip.
    import hashlib
    import shutil
    stage = os.path.join(os.path.dirname(LOG), 'upload-stage', f'{os.getpid()}')
    os.makedirs(stage, exist_ok=False)
    staged = os.path.join(stage, 'submission.zip')
    shutil.copyfile(zip_path, staged)

    def digest(path):
        with open(path, 'rb') as handle:
            return hashlib.file_digest(handle, 'sha256').hexdigest()

    if digest(staged) != digest(zip_path):
        print('staged submission.zip differs from the gated zip', file=sys.stderr)
        return 1
    before = {row['ref'] for row in rows()}
    log = open(LOG, 'a', encoding='utf-8')
    log.write(f'--- {time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())} submit {zip_path} as '
              f'{staged} sha256 {digest(staged)}\n')
    log.flush()
    proc = subprocess.run([KAGGLE, 'competitions', 'submit', COMP, '-f', staged, '-m', message, '-q'],
                          capture_output=True, text=True, errors='replace', timeout=3600,
                          env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'})
    log.write(f'rc={proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}\n')
    log.close()
    sys.stderr.write(proc.stdout + proc.stderr)
    if proc.returncode != 0:
        return proc.returncode
    for _ in range(18):
        new = [row for row in rows() if row['ref'] not in before and row['description'] == message]
        if len(new) == 1:
            print(new[0]['ref'])
            return 0
        if len(new) > 1:
            print(f'ambiguous: {len(new)} new rows share the message', file=sys.stderr)
            return 0
        time.sleep(10)
    print('uploaded, but no matching new submission row was found', file=sys.stderr)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main(sys.argv))
    except Exception:
        import traceback
        with open(LOG, 'a', encoding='utf-8') as handle:
            handle.write('TRACEBACK:\n' + traceback.format_exc())
        raise
