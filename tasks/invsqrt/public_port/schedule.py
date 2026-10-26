# SPDX-License-Identifier: Apache-2.0
"""Port of Dmitrii Gluzdov's Apache-2.0 notebook v7, scriptVersionId 361726742.

Source SHA-256 d689cc89f41a6c9130e9f4c3a6b08dfd5d758fcbbb79f527d55cbd3b48e15280.
https://www.kaggle.com/code/dmitriigluzdov/quantum-circuit-compilation-from-source?scriptVersionId=361726742
Credits: Sumit Chongder (centered polynomial), Rudra Bhaskar (split),
Gu/Kemeny/Yelin/Lukin (deferred repairs), Zongao Bian (virtual low bit),
and the authors named in tasks/invsqrt/PROVENANCE.md.
Local changes: package imports; reuse existing arithmetic helpers; remove
notebook setup, fitting drivers, saved-data replay and verifier calls.
"""
# Parent code cell 42.
import kickmix as km
from fractions import Fraction
from tasks.invsqrt import signed_digit as H
from tasks.invsqrt import signed_digit as A
from . import arithmetic as O, deferred as D, virtual_low


def joint_top_normalization_repair(b, x, m8, m16):
    """On positive22-bit inputs, f16=g16 and f8=g8 XOR g16,
 where gk tests whether the highest k input bits are zero.
 Thus the joint phase is m8*g8 XOR (m8 XOR m16)*g16.
 A shared16-bit prefix ladder, or an8-bit phase, costs8.5 mean
 Toffolis instead of10 for the two separate repairs.
 """
    parity = m16
    b.cx(m8, parity)
    b.push_condition(parity)
    top = list(reversed(x[6:22]))
    b.x(top)
    anc = b.alloc_qubits(14)
    b.init_and(top[0], top[1], anc[0])
    for j in range(1, 14):
        b.init_and(anc[j - 1], top[j + 1], anc[j])
    b.push_condition(m8)
    b.z(anc[6])
    b.pop_condition()
    b.cz(anc[13], top[15])
    for j in reversed(range(1, 14)):
        b.del_and(anc[j - 1], top[j + 1], anc[j])
    b.del_and(top[0], top[1], anc[0])
    b.free(anc)
    b.x(top)
    b.pop_condition()
    b.x(parity)
    b.push_condition(parity)
    b.push_condition(m8)
    top = x[14:22]
    b.x(top)
    H.phase_all(b, list(top))
    b.x(top)
    b.pop_condition()
    b.pop_condition()

def anf_lookup(b, address, target, table):
    """Compute an XOR lookup with depth-first ANF monomials, at most
 2**n-n-1 temporary ANDs and n-1 ladder wires. New implementation.
 """
    address = list(address)
    coef = list(table)
    n = len(address)
    for i in range(n):
        for mask in range(1 << n):
            if mask >> i & 1:
                coef[mask] ^= coef[mask ^ 1 << i]
    active = {}

    def needed(mask, nextbit):
        children = [(mask | 1 << j, j + 1, j) for j in range(nextbit, n)]
        active[mask] = bool(coef[mask])
        for child, nxt, j in children:
            active[mask] |= needed(child, nxt)
        return active[mask]
    for i in range(n):
        needed(1 << i, i + 1)

    def xor(value, control=None):
        for i, q in enumerate(target):
            if value >> i & 1:
                if control is None:
                    b.x(q)
                else:
                    b.cx(control, q)
    xor(coef[0])

    def visit(mask, control, nextbit):
        xor(coef[mask], control)
        for j in range(nextbit, n):
            child = mask | 1 << j
            if not active[child]:
                continue
            q = b.alloc_qubits(1)[0]
            b.init_and(control, address[j], q)
            visit(child, q, j + 1)
            b.del_and(control, address[j], q)
            b.free(q)
    for i in range(n):
        if active[1 << i]:
            visit(1 << i, address[i], i + 1)

def adaptive_lookup(b, address, target, table, affine=False):
    """Unary decoder pruned wherever every remaining output word is equal.

 A full M-leaf binary tree costs M-2 temporary ANDs; address wires and
 one ladder wire per active depth suffice. Demolition is standard MBU.
 """
    address = list(address)

    def xor_word(value, control):
        for i, q in enumerate(target):
            if value >> i & 1:
                if control is None:
                    b.x(q)
                else:
                    b.cx(control, q)

    def walk(bits, rows, parent):
        if len(set(rows)) == 1:
            xor_word(rows[0], parent)
            return
        assert bits
        if affine:
            base = rows[0]
            columns = [rows[1 << i] ^ base for i in range(len(bits))]
            test = [base]
            for col in columns:
                test += [v ^ col for v in test]
            if rows == test:
                xor_word(base, parent)
                for bit, col in zip(bits, columns):
                    if not col:
                        continue
                    if parent is None:
                        xor_word(col, bit)
                    else:
                        q = b.alloc_qubits(1)[0]
                        b.init_and(parent, bit, q)
                        xor_word(col, q)
                        b.del_and(parent, bit, q)
                        b.free(q)
                return
        bit = bits[-1]
        half = len(rows) // 2
        if parent is None:
            b.x(bit)
            walk(bits[:-1], rows[:half], bit)
            b.x(bit)
            walk(bits[:-1], rows[half:], bit)
        else:
            tmp = b.alloc_qubits(1)[0]
            b.x(bit)
            b.init_and(parent, bit, tmp)
            b.x(bit)
            walk(bits[:-1], rows[:half], tmp)
            b.cx(parent, tmp)
            walk(bits[:-1], rows[half:], tmp)
            b.cx(parent, tmp)
            b.x(bit)
            b.del_and(parent, bit, tmp)
            b.x(bit)
            b.free(tmp)
    walk(address, list(table), None)

def build(c, tabs, group_bits=2, mode='mux', interpolation=None, main_lookup='unary', affine=False, joint_norm=False):
    lay = H.layout(c, tabs, LB=c.fy - 7, S=c.fy - 8)
    sp = O.prepare(c, tabs)
    assert all((v % 2 == 0 for v in lay['lo'].values())), 'virtual low bit requires even anchors'
    b = km.CircuitBuilder()
    x = b.create_quantum_register(22, name='x')
    flags = b.alloc_qubits(4)
    f = [x[21]] + list(flags)
    for k, amount in H.NSTAGES[:-1]:
        top = x[22 - amount:22]
        b.x(top)
        H.and_all_into(b, list(top), f[k])
        b.x(top)
        for i in reversed(range(22 - amount)):
            b.cswap(f[k], x[i], x[i + amount])
    b.x(x[21])
    b.left_rotate(x[:21], 1, control=x[21])
    b.cx(x[21], x[0])
    res, coarse, low, high = [b.alloc_qubits(n) for n in [sp['rw'], sp['cw'], lay['LB'] - 1, lay['whi']]]
    full = km.array(list(low) + list(res) + list(high) + list(coarse))
    rest = km.array(list(low) + list(res) + list(coarse))
    ft = []
    rt = []
    ht = []
    ct = []
    for e in range(2):
        for a in range(128):
            k = (e, a)
            common = lay['lo'][k] >> 1 | sp['residual'][k] << lay['LB'] - 1
            rt.append(common | sp['coarse'][k] << lay['LB'] - 1 + sp['rw'])
            ft.append(common | lay['hi'][k] << lay['LB'] - 1 + sp['rw'] | sp['coarse'][k] << lay['LB'] - 1 + sp['rw'] + lay['whi'])
            ht.append(lay['hi'][k])
        if group_bits is not None:
            for a in range(0, 128, 1 << group_bits):
                assert len({tabs[e, j][0] for j in range(a, a + (1 << group_bits))}) == 1
                ct.append(tabs[e, a][0])
        else:
            ct.extend((tabs[e, a][0] for a in range(128)))
    address = km.array(list(x[14:21]) + [f[0]])
    ca = km.array(list(x[14 + (group_bits or 0):21]) + [f[0]])
    delta = x[:14]
    c2 = None
    step_masks = []

    def add(a, t, cin=None, sub=False):
        A.folded_gadd(b, a, t, cin, sub)

    def phase(reg, lowbit):
        ext = b.alloc_qubits(10)
        word = km.array(list(reg) + list(ext))
        O.shift(b, f, word, len(reg), False)
        for i, q in enumerate(word):
            ex = lowbit + i - c.fy - 10
            if ex < 0:
                b.z_pow(q, Fraction(2) ** (ex + 1))
        O.shift(b, f, word, len(reg), True)
        b.free(ext)

    def load():
        nonlocal c2
        c2 = b.alloc_qubits(c.w2)
        if interpolation is not None:
            sw = interpolation['step_width']
            step = b.alloc_qubits(sw)
            uw = interpolation.get('update_width', c.w2)
            mask = (1 << uw) - 1
            packed = [base & mask | tabs[a // 128, a % 128][0] & ~mask | s << c.w2 for a, (base, s) in enumerate(interpolation['rows'])]
            adaptive_lookup(b, address, km.array(list(c2) + list(step)), packed, affine=affine)
            for i in range(interpolation['remainder_bits']):
                sh = interpolation['fraction_bits'] - i
                if sh >= 0:
                    a = step[sh:]
                    t = c2[:uw]
                    cin = step[sh - 1] if sh else None
                else:
                    a = step
                    t = c2[-sh:uw]
                    cin = None
                # Arithmetic is modulo 2**uw. Higher addend bits cannot
                # affect the low suffix; the lookup supplies the final high
                # curvature bits for this address directly.
                a = a[:len(t)]
                b.cx(x[14 + i], t)
                add(a, t, cin)
                b.cx(x[14 + i], t)
            step_masks.extend(D.demolish(b, step))
            b.free(step)
        elif group_bits is None:
            adaptive_lookup(b, ca, c2, ct, affine=affine)
        else:
            b.init_lookup(table=ct, address=ca, target=c2)

    def erase():
        nonlocal c2
        mm = D.demolish(b, c2)
        b.free(c2)
        c2 = None
        return mm

    def inner(inverse):
        rows = c.rrow_list()
        rows = rows[::-1] if inverse else rows
        for i in rows:
            sh = c.sh2[i]
            if sh >= 0:
                a = c2[sh:]
                t = res
                cin = c2[sh - 1] if sh else None
            else:
                a = c2
                t = res[-sh:]
                cin = None
            b.cx(delta[i], t)
            add(a, t, cin, sub=inverse)
            b.cx(delta[i], t)

    def outer(inverse):
        derivative = res[:sp['block']] + coarse
        virtual_low.outer(b, add, derivative, low, delta, c.sh1, inverse)
    if main_lookup == 'anf':
        anf_lookup(b, address, full, ft)
    else:
        b.init_lookup(table=ft, address=address, target=full)
    phase(high, lay['S'])
    bits = D.demolish(b, high)
    b.free(high)
    load()
    inner(False)
    cm1 = erase()
    add(res[sp['block']:], coarse)
    outer(False)
    phase(low[c.gy - 1:], c.gy)
    outer(True)
    add(res[sp['block']:], coarse, sub=True)
    load()
    inner(True)
    cm2 = erase()
    bits += D.demolish(b, rest)
    b.free(rest)
    bits += cm1 + cm2
    rtwidth = len(rest)
    hw = lay['whi']
    repairtable = [h | r << hw | tabs[e, a][0] << hw + rtwidth | tabs[e, a][0] << hw + rtwidth + c.w2 for e in range(2) for a, (h, r) in enumerate(zip(ht[128 * e:128 * (e + 1)], rt[128 * e:128 * (e + 1)]))]
    if interpolation is not None:
        bits += step_masks
        sw = interpolation['step_width']
        off = hw + rtwidth + 2 * c.w2
        for a, (_, step) in enumerate(interpolation['rows']):
            repairtable[a] |= step << off | step << off + sw
    D.repair_anf(b, address, repairtable, bits)
    b.cx(x[21], x[0])
    b.right_rotate(x[:21], 1, control=x[21])
    b.x(x[21])
    pending = None
    for k, amount in reversed(H.NSTAGES[:-1]):
        for i in range(22 - amount):
            b.cswap(f[k], x[i], x[i + amount])
        top = x[22 - amount:22]
        m = b.alloc_bits(1)[0]
        b.hmr(f[k], m)
        if joint_norm and k == 3:
            pending = m
            continue
        if joint_norm and k == 4:
            joint_top_normalization_repair(b, x, pending, m)
            b.free(pending)
            b.free(m)
        else:
            b.push_condition(m)
            b.x(top)
            H.phase_all(b, list(top))
            b.x(top)
            b.pop_condition()
            b.free(m)
    b.free(flags)
    return (b.finish_circuit(), {k: v for k, v in sp.items() if k not in ['coarse', 'residual']})
