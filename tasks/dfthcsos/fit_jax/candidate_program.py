# SPDX-License-Identifier: Apache-2.0
"""Build exact ANF angle circuits from the fitted words; evaluator CLI contract."""
from search import initial_program as program
from tasks.dfthcsos.generate import batch_deltas
from tasks.dfthcsos.qrom import build_qrom


def build_family(words, source_brot):
    selection = (len(words)-1).bit_length()
    batch = min(75,(128-selection-8)//source_brot)
    if batch < 1:
        raise ValueError('no angle word fits the 128-qubit cap with eight scratch qubits')
    circuits = [build_qrom(delta,source_brot,bank_bits=0,scratch=8,pebble_degree=4)[0]
                for delta in batch_deltas(words,batch)]
    return circuits,dict(variant='anf',brot=source_brot,batch_size=batch),words


if __name__ == '__main__':
    program.build_family = build_family
    program.main()
