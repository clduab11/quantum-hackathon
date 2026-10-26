# SPDX-License-Identifier: Apache-2.0
# Modified port of SomeJoint v7 runtime.py, fixed Hankel/cyclic Gold variant.
# Praxen: new projection; fixed variant; package imports; no notebook wrapper.
"""Submission-9 decoder; retains upstream rare degree-gap approximations."""
from ..jfraction.common import build
from ..jfraction.jfraction_gap_decoder import GapJFractionDecoder
from ..jfraction.projection import project_masks
from ..jfraction.merge_kernels import PointerBank, convert_pointers
from .cyclic_gold import extract
from ..jfraction.mc4_inverse import builder_class
from .hankel_half import forney


class HankelDecoder(GapJFractionDecoder):
    def build_syndrome_decoding_mbuc(self, builder, *, syndromes, error_mbuc, n_iters):
        if (len(syndromes), len(error_mbuc), n_iters) != (70, 4095, 35):
            raise ValueError('The paired decoder supports only the competition instance.')
        residual = project_masks(builder, syndromes, error_mbuc)
        builder.stage_records = []
        words = list(syndromes)
        bank = PointerBank(builder, 35)
        self._record(builder, 'initialization')
        extract(builder, words, bank)
        self._record(builder, 'moment_to_fraction')
        numerator, denominator = convert_pointers(builder, words, bank, release_inverse='small')
        self._record(builder, 'fraction_to_polynomials')
        forney(builder, numerator, denominator[1:], residual, field=self.field)
        self._record(builder, 'phase_correction')
        convert_pointers(builder, words, bank, reverse=True, release_inverse='small')
        self._record(builder, 'polynomials_to_fraction')
        extract(builder, words, bank, reverse=True)
        bank.release_zero()
        self._record(builder, 'fraction_to_moments')


def build_decoder():
    builder = builder_class()()
    circuit = build(builder, decoder_type=HankelDecoder)
    return circuit, builder.stage_records
