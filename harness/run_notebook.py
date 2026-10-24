"""Execute a Jupyter notebook headless and write its outputs back in place.

Run with the project environment: `uv run --group notebooks python harness/run_notebook.py NOTEBOOK.ipynb`.
The kernel runs with the notebook's directory as its working directory. On a cell error or timeout the outputs
so far are still written back, the failing cell is named on stderr and the exit status is 1.
"""
import argparse
from pathlib import Path
import sys

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError, CellTimeoutError

DEFAULT_TIMEOUT = 900


def describe(nb, index):
    cell = nb.cells[index]
    first = next((line for line in cell.source.splitlines() if line.strip()), '')
    return f'cell {index + 1} of {len(nb.cells)} (id {cell.get("id", "-")}): {first[:80]!r}'


def run(path: Path, *, timeout: int = DEFAULT_TIMEOUT) -> int:
    nb = nbformat.read(path, as_version=4)
    current = {}

    def on_cell_start(cell, cell_index, **_):
        current['index'] = cell_index

    client = NotebookClient(nb, timeout=timeout, kernel_name='python3', on_cell_start=on_cell_start,
                            resources={'metadata': {'path': str(path.parent)}})
    try:
        client.execute()
    except (CellExecutionError, CellTimeoutError) as exc:
        nbformat.write(nb, path)
        where = describe(nb, current['index']) if 'index' in current else 'unknown cell'
        reason = f'{exc.ename}: {exc.evalue}' if isinstance(exc, CellExecutionError) else f'timed out after {timeout}s'
        print(f'{path}: FAILED at {where}\n{reason}', file=sys.stderr)
        return 1
    nbformat.write(nb, path)
    print(f'{path}: executed {len(nb.cells)} cells')
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('notebook', type=Path)
    parser.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT, help='per-cell timeout in seconds')
    args = parser.parse_args(argv)
    if not args.notebook.is_file():
        parser.error(f'{args.notebook}: no such notebook')
    return run(args.notebook, timeout=args.timeout)


if __name__ == '__main__':
    sys.exit(main())
