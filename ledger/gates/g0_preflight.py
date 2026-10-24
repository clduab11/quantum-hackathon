"""Check all metric files before simulation. G0 success is not verifier acceptance."""
import argparse
from contextlib import contextmanager
from pathlib import Path
import stat
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.archive import unpack
from harness.runtime import load_metric


def preflight(root, metric=None):
    metric = metric or load_metric()
    from dfthcsos import verify as dfthc
    from dfthcsos.scoreinfra.reference import FACTORIZATION_KEYS, ORBITALS
    from dqi import verify_submission_dqi as dqi

    root = Path(root)
    def read(path, reader, spec):
        status = path.lstat()
        if (not stat.S_ISREG(status.st_mode) or status.st_nlink > 1
                or not path.resolve().is_relative_to(root.resolve())):
            raise ValueError(f'{path.name} must be a regular file inside the submission.')
        try:
            return reader(path, spec)
        except Exception as error:
            raise ValueError(f'{path.relative_to(root)} is invalid: {error}') from error

    # Resolve all names before parsing potentially large circuits.
    inv_path = metric.find_one(root, 'invsqrt.km[xb]', 'invsqrt.kmx or invsqrt.kmb')
    dqi_path = metric.find_one(root, 'dqi.km[xb]', 'dqi.kmx or dqi.kmb')
    folder = metric.find_one(root, 'dfthcsos', 'dfthcsos directory', is_dir=True)
    angle_files = list(folder.glob('angle_k_*.km[xb]'))
    angle_paths = {p.stem: p for p in angle_files}
    stems = [f'angle_k_{k}' for k in range(len(angle_files))]
    if not stems or sorted(angle_paths) != sorted(stems):
        raise ValueError('dfthcsos/ must hold consecutive angle_k_0 ... angle_k_<n-1>, each once.')
    npz_path = metric.find_one(folder, 'submission.npz', 'dfthcsos/submission.npz')
    npz_spec = {
        'U': ('f', ('R', 'B', ORBITALS)), 'W': ('f', ('R', 'B', 'C')),
        'H2_I': ('f', ('R', 'C')), 'H1_I': ('f', ()),
        'Hsym_lower': ('f', (ORBITALS * (ORBITALS + 1) // 2,)),
        'tree_edges': ('iu', (ORBITALS - 1, 2)),
    }
    if set(npz_spec) != {*FACTORIZATION_KEYS, 'tree_edges'}:
        raise ValueError('Verifier factorization keys changed; review the metric NPZ spec.')
    arrays = read(npz_path, metric.read_npz, npz_spec)
    invsqrt = read(inv_path, metric.read_circuit, 1)
    if invsqrt.num_registers != 1:
        raise ValueError('invsqrt must have exactly one named register.')
    spec = dqi.ProblemSpecDQI.benchmark_instance()
    return {'invsqrt': invsqrt,
            'dqi': read(dqi_path, metric.read_circuit, spec.n + spec.m),
            'angles': [read(angle_paths[s], metric.read_circuit, dfthc.QUBIT_CAP) for s in stems],
            'tree_edges': arrays.pop('tree_edges'), 'factorization': arrays}


@contextmanager
def preflight_zip(path, metric=None):
    with unpack(path) as root:
        yield preflight(root, metric)


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        'Example: uv run python ledger/gates/g0_preflight.py reference.zip. '
        'Needs the v10 metric and project dependencies; see docs/handoffs/p0-4-kickmix-build.md. '
        'Writes only temporary extracted files; exits 1 with a reason on rejection.'))
    parser.add_argument('submission', type=Path)
    args = parser.parse_args()
    try:
        with preflight_zip(args.submission):
            print('G0 PASS: all metric files checked; no simulation performed.')
    except Exception as error:
        print(f'G0 REJECT: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
