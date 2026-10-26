# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""The host decoder with seven-bit degree counters for the m=73 benchmark.

Use seven-bit metadata storage for the fixed 70-syndrome instance, retaining
the host's arithmetic and schedule. Full benchmark and independent-salt
verification results are recorded with the submission.
"""
from typing import Sequence
import kickmix as km
from tasks.dqi.reference_circuit import ProosAndZalkaDecoder

class CompactDecoder(ProosAndZalkaDecoder):
    def build_syndrome_decoding_mbuc(self, builder: km.CircuitBuilder, *,
                                     syndromes: Sequence[km.array],
                                     error_mbuc: Sequence[km.array],
                                     n_iters: int) -> None:
        """Appends the syndrome-decoding MBUC phase circuit to `builder`.

        Args:
            builder: Circuit builder receiving the instructions.
            syndromes: `n_syndromes` quantum registers of width `field.degree`.
                Restored to their initial state on completion.
            error_mbuc: Classical bit registers of width `field.degree`, one per
                codeword position, holding X-basis measurement outcomes.
            n_iters: Number of synchronized EEA iterations (`default_n_iters(n)`).
        """
        gf = self.field
        n = self.n_syndromes
        degree = gf.degree
        if len(syndromes) != n:
            raise ValueError(f'Expected {n} syndrome registers, got {len(syndromes)}.')
        if not (n <= len(error_mbuc) <= (1 << degree) - 1):
            raise ValueError(
                f'Expected between {n} and {(1 << degree) - 1} error_mbuc registers, '
                f'got {len(error_mbuc)}.'
            )
        if any(len(s) != degree for s in syndromes):
            raise ValueError(f'Every syndrome register must have length {degree}.')
        if any(len(e) != degree for e in error_mbuc):
            raise ValueError(f'Every error_mbuc register must have length {degree}.')
        m = n + 3

        reg_a = [builder.alloc_qubits(degree) if i < 3 else syndromes[i - 3] for i in range(m)]
        reg_b = [builder.alloc_qubits(degree) for _ in range(m)]

        logm = m.bit_length()
        n_A = builder.alloc_qubits(logm)
        n_B = builder.alloc_qubits(logm)
        n_a = builder.alloc_qubits(logm)
        n_b = builder.alloc_qubits(logm)
        n_q = builder.alloc_qubits(logm)
        flag = builder.alloc_qubits(1)[0]
        counter = builder.alloc_qubits(2)
        halting_counter = builder.alloc_qubits(n_iters.bit_length())
        eea = (reg_a, reg_b, n_A, n_B, n_a, n_b, n_q, flag, counter, halting_counter)

        init_ones = km.array([reg_a[0][0], reg_b[m - 1][0], n_a[0], flag])
        builder.x(init_ones)
        builder.gf2_iadd(n, target=n_A)
        builder.gf2_iadd(n + 1, target=n_B)

        with builder.mark('initial_shift'):
            self._initial_shift_loop(builder, reg_a, n_A, is_adjoint=False)
        with builder.mark('forward_eea'):
            self._synchronized_eea(builder, *eea, n_iters=n_iters, is_adjoint=False)
        with builder.mark('chien_forney_mbuc'):
            self._chien_search_and_forney_mbuc(builder, reg_b, error_mbuc, n_b, n_B)
        with builder.mark('reverse_eea'):
            self._synchronized_eea(builder, *eea, n_iters=n_iters, is_adjoint=True)
        with builder.mark('uncompute_initial_shift'):
            self._initial_shift_loop(builder, reg_a, n_A, is_adjoint=True)

        builder.gf2_iadd(n + 1, target=n_B)
        builder.gf2_iadd(n, target=n_A)
        builder.x(init_ones)

        for reg in (halting_counter, counter, flag, n_q, n_b, n_a, n_B, n_A, *reg_a[:3], *reg_b):
            builder.free(reg)

