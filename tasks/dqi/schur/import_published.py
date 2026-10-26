"""Use the already committed Gu arithmetic; never load a circuit tape.

The source derives from andigu/uncompute at
64b5a13aa249f1360846657392e6c66817b26d0f (Apache-2.0). The existing port
uses the official 4179 field. Derive formulas for that field in memory;
window constants are committed and are not used by the Schur schedule.
"""
from functools import lru_cache
import json
from pathlib import Path
from types import ModuleType
from tasks.dqi.generate import _port_modules


@lru_cache(None)
def load():
    formulas = _port_modules()
    tables, _ = formulas.run_b12()
    root = Path(__file__).resolve().parents[1] / 'bm_forney'
    constants = json.loads((root / 'windows.json').read_text())
    constants.update(tables)
    path = root / 'gu_port.py'
    source = path.read_text()
    old = 'CONSTS = json.loads(pathlib.Path(os.environ["DQI_CONSTANTS"]).read_bytes())'
    if source.count(old) != 1:
        raise RuntimeError('committed Gu constants adapter no longer matches')
    source = source.replace(old, 'CONSTS = _derived_constants')
    module = ModuleType('schur_gu_arithmetic')
    module.__file__ = str(path)
    module._derived_constants = constants
    exec(compile(source, str(path), 'exec'), module.__dict__)
    return module
