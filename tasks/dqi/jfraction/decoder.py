# SPDX-License-Identifier: Apache-2.0
# Modified port of anazemcev v6 build_paired_dqi.py, selected paired-v6 only.
# Praxen: new projection; fixed variant; package imports; no notebook wrapper.
"""In-place paired J-fraction decoder. Approximate at three gaps or higher-order gaps."""
from .common import build
from .jfraction_gap_decoder import GapJFractionDecoder
from .projection import project_masks
from .merge_kernels import PointerBank, convert_pointers
from .matrix_pair_kernels import extract_hybrid
from .mc4_inverse import builder_class
from .phase_tensor import forney_tensor


class PairedDecoder(GapJFractionDecoder):
    def build_syndrome_decoding_mbuc(self, builder, *, syndromes, error_mbuc, n_iters):
        if (len(syndromes), len(error_mbuc), n_iters) != (70, 4095, 35):
            raise ValueError('The paired decoder supports only the competition instance.')
        residual = project_masks(builder, syndromes, error_mbuc)
        builder.stage_records = []
        words = list(syndromes)
        bank = PointerBank(builder, 35)
        self._record(builder, 'initialization')
        extract_hybrid(builder, words, bank, matrix_threshold=14, fused=True)
        self._record(builder, 'moment_to_fraction')
        numerator, denominator = convert_pointers(builder, words, bank, release_inverse='small')
        self._record(builder, 'fraction_to_polynomials')
        forney_tensor(builder, numerator, denominator[1:], residual, field=self.field)
        self._record(builder, 'phase_correction')
        convert_pointers(builder, words, bank, reverse=True, release_inverse='small')
        self._record(builder, 'polynomials_to_fraction')
        extract_hybrid(builder, words, bank, reverse=True, matrix_threshold=14, fused=True)
        bank.release_zero()
        self._record(builder, 'fraction_to_moments')


def build_decoder():
    builder = builder_class()()
    circuit = build(builder, decoder_type=PairedDecoder)
    return circuit, builder.stage_records
