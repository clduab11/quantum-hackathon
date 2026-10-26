# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Production decoder builder using GF(4) multiplication and subfield inversion."""
import kickmix as km
from . import crt_multiplier as crt
from . import tower_inverse as tower
from .gf4_multiplier import terms as gf4_terms

# The original construction functions remain available for independent algebra checks.
# These providers select exact binary linear forms; all emitted instructions are kickmix gates.
legacy_tower_terms=tower.crt_terms

def selected_terms(n):
    return gf4_terms(n) if n in [6,12] else legacy_tower_terms(n)


def install():
    crt.terms12=lambda modulus=None:gf4_terms(12)
    tower.crt_terms=selected_terms


class FastBuilder(tower.TowerBuilder):
    def __init__(self,builder):
        install()
        super().__init__(builder)



