# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Compact decoder with a cheaper per-position Forney phase kickback.

Per position the reference spends 12 ANDs on `sigma == 0`, 12 gating `omega`,
and 12 more re-evaluating `sigma == 0`. Here the MBUC parity
`P = <M_j, omega * sigma'^-1>` is computed into one qubit (12 ANDs, using
classically conditioned CNOTs for the mask-dependent linear map), the
phase `(-1)^([sigma == 0] P)` is one multi-controlled Z (11 ANDs), and `P`
is erased by X-basis measurement with a Toffoli-free `gf2_phase_by_product` fixup.
"""
import kickmix as km
from .compact_dqi import CompactDecoder


def product_terms(gf):
    """terms[k] = [(i, j)] with bit k of x^i * x^j set."""
    d=gf.degree;terms=[[] for _ in range(d)]
    for i in range(d):
        for j in range(d):
            v=gf.mul(1<<i,1<<j)
            for k in range(d):
                if v>>k&1:terms[k].append((i,j))
    return terms


class ForneyDecoder(CompactDecoder):
    def _chien_search_and_forney_mbuc(self, builder, reg_b, error_mbuc, n_b, n_B):
        gf = self.field
        degree = gf.degree
        m = len(reg_b)
        t = self.n_syndromes // 2
        block_length = (1 << degree) - 1
        primitive = gf.primitive_element
        terms = product_terms(gf)

        with builder.mark('pre_align_reg_b'):
            self._pre_align_reg_b(builder, reg_b, n_b, n_B, is_adjoint=False)

        sigma = reg_b[0]
        sigma_prime = reg_b[1]
        omega = reg_b[m // 2 + t]
        sigma_prime_inv = builder.alloc_qubits(degree)
        u = builder.alloc_qubits(degree)
        parity = builder.alloc_qubits(1)[0]
        ladder = builder.alloc_qubits(degree - 1)
        is_error = builder.alloc_bits(1)
        meas = builder.alloc_bits(1)[0]

        omega_indices = range(m // 2 + 1, m // 2 + t + 1)
        step_multipliers = [
            (k, gf.pow(primitive, k))
            for k in range(1, t + 1)
        ] + [
            (k, gf.pow(primitive, (m - 2 - k) % block_length))
            for k in omega_indices
            if (m - 2 - k) % block_length != 0
        ]
        sum_pairs = (
            [(reg_b[k], omega) for k in range(m // 2 + 1, m // 2 + t)]
            + [(reg_b[k], sigma_prime) for k in range(3, t + 1, 2)]
            + [(reg_b[k], sigma) for k in range(2, t + 1, 2)]
            + [(sigma_prime, sigma)]
        )
        fwd_src = km.array([q for src, _ in sum_pairs for q in src])
        fwd_dst = km.array([q for _, dst in sum_pairs for q in dst])
        rev_src = km.array([q for src, _ in reversed(sum_pairs) for q in src])
        rev_dst = km.array([q for _, dst in reversed(sum_pairs) for q in dst])

        def mask_map(mask):
            # u_i ^= sum_k M_k sum_{(i,j) in terms[k]} inv_j
            for k in range(degree):
                builder.push_condition(mask[k])
                for i, j in terms[k]:
                    builder.cx(sigma_prime_inv[j], u[i])
                builder.pop_condition()

        num_positions = min(block_length, len(error_mbuc))
        forney_step = builder.mark('forney_step')
        for j in range(num_positions):
            with forney_step:
                mask = error_mbuc[j]
                builder.bit_store(is_error[0], True, control=mask)
                builder.push_condition(is_error[0])

                builder.cx(fwd_src, fwd_dst)
                _, inverse_chain = builder.init_gf2_inverse_with_scaffold(
                    sigma_prime, target=sigma_prime_inv, field=gf)

                mask_map(mask)
                for i in range(degree):
                    builder.ccx(omega[i], u[i], parity)
                mask_map(mask)

                # (-1)^(parity and sigma == 0)
                builder.x(sigma)
                builder.init_and(sigma[0], sigma[1], ladder[0])
                for k in range(1, degree - 1):
                    builder.init_and(ladder[k - 1], sigma[k + 1], ladder[k])
                builder.cz(ladder[degree - 2], parity)
                for k in reversed(range(1, degree - 1)):
                    builder.del_and(ladder[k - 1], sigma[k + 1], ladder[k])
                builder.del_and(sigma[0], sigma[1], ladder[0])
                builder.x(sigma)

                builder.hmr(parity, meas)
                builder.push_condition(meas)
                builder.gf2_phase_by_product(omega, sigma_prime_inv, mask=mask, field=gf)
                builder.pop_condition()

                builder.del_gf2_inverse_with_scaffold(
                    sigma_prime, target=sigma_prime_inv, scaffold=inverse_chain, field=gf)
                builder.free(inverse_chain)
                builder.cx(rev_src, rev_dst)

                builder.pop_condition()
                builder.bit_store(is_error, False)

                if j + 1 < num_positions:
                    for k, step in step_multipliers:
                        builder.gf2_imul(step, target=reg_b[k], field=gf)

        if num_positions > 1:
            for k, step in step_multipliers:
                builder.gf2_idiv(gf.pow(step, num_positions - 1), target=reg_b[k], field=gf)

        builder.free(is_error)
        builder.bit_store(meas, False)
        builder.free(km.array([meas]))
        builder.free(sigma_prime_inv + u + km.array([parity]) + ladder)

        with builder.mark('unalign_reg_b'):
            self._pre_align_reg_b(builder, reg_b, n_b, n_B, is_adjoint=True)
