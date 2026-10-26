# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Independent characteristic-two polynomial and exact RS reference.

No imported decoder, lookup tables, or verifier truth is used by decoding.
"""
class Field:
    def __init__(self, degree=12, modulus=0x1053):
        self.degree, self.modulus = degree, modulus
        self.size = 1 << degree

    def mul(self, a, b):
        out = 0
        while b:
            if b & 1: out ^= a
            b >>= 1; a <<= 1
            if a & self.size: a ^= self.modulus
        return out

    def pow(self, a, n):
        out = 1
        while n:
            if n & 1: out = self.mul(out, a)
            a = self.mul(a, a); n >>= 1
        return out

    def inv(self, a):
        if not a: raise ZeroDivisionError('zero field pivot')
        return self.pow(a, self.size - 2)

    def sqrt(self, a): return self.pow(a, self.size // 2)

    def add(self, a, b):
        c = list(a) + [0] * max(0, len(b) - len(a))
        for i, x in enumerate(b): c[i] ^= x
        return trim(c)

    def scale(self, a, c): return trim([self.mul(x, c) for x in a])

    def product(self, a, b):
        if not a or not b: return []
        c = [0] * (len(a) + len(b) - 1)
        for i, x in enumerate(a):
            for j, y in enumerate(b): c[i+j] ^= self.mul(x, y)
        return trim(c)

    def divide(self, a, b):
        a, b = trim(a), trim(b)
        if not b: raise ZeroDivisionError('zero polynomial')
        q = [0] * max(0, len(a) - len(b) + 1); bi = self.inv(b[-1])
        while a and len(a) >= len(b):
            k = len(a) - len(b); c = self.mul(a[-1], bi); q[k] = c
            for j, x in enumerate(b): a[k+j] ^= self.mul(c, x)
            a = trim(a)
        return trim(q), a

    def evaluate(self, a, x):
        out = 0
        for c in reversed(a): out = self.mul(out, x) ^ c
        return out

    def derivative(self, a): return trim([a[i+1] if not i % 2 else 0 for i in range(len(a)-1)])

    def reciprocal(self, a, length):
        ai = self.inv(a[0]); b = [ai]
        for i in range(1, length):
            v = 0
            for j in range(1, min(i+1, len(a))): v ^= self.mul(a[j], b[i-j])
            b.append(self.mul(ai, v))
        return b

    def pade(self, s):
        """Exact Euclid; unrestricted quotient degrees, monic final locator."""
        N = len(s); f = [0]*N+[1]; g = trim(s); u, v = [], [1]
        if not g: return [1], [], []
        gaps = []
        while len(g) > N//2:
            q, r = self.divide(f, g)
            f, g, u, v = g, r, v, self.add(u, self.product(q, v))
            gaps.append(len(q)-1)
        vi = self.inv(v[-1])
        return self.scale(v, vi), self.scale(g, vi), gaps

    def bm(self, s):
        """Independent conventional BM, coefficients in the position variable."""
        C, B, L, shift, pivot = [1], [1], 0, 1, 1
        for n, sn in enumerate(s):
            delta = sn
            for i in range(1, L+1):
                if i < len(C): delta ^= self.mul(C[i], s[n-i])
            if not delta: shift += 1; continue
            old = C[:]; ratio = self.mul(delta, self.inv(pivot))
            C = self.add(C, [0]*shift+self.scale(B, ratio))
            if 2*L <= n: L, B, pivot, shift = n+1-L, old, delta, 1
            else: shift += 1
        return self.scale(C, self.inv(C[-1]))

    def syndrome(self, positions, values, N):
        s = [0]*N
        for a, e in zip(positions, values):
            power = a
            for i in range(N): s[i] ^= self.mul(e, power); power = self.mul(power, a)
        return s

    def locator(self, positions):
        b = [1]
        for a in positions: b = self.product(b, [self.inv(a), 1])
        return b


def trim(a):
    a = list(a)
    while a and not a[-1]: a.pop()
    return a


def sylvester_reference(F, f, g, c, d):
    """Euclidean factorization of c*f+d*g, arbitrary degree gaps.

    The output is built in exactly the c/d coefficient slots by the circuit;
    this independent version uses lists to expose the invariant.
    f degree m, g degree n; len(c)=n, len(d)=m.
    """
    f, g = trim(f), trim(g)
    m, n = len(f)-1, len(g)-1
    assert m >= n >= 0 and len(c) == n and len(d) == m
    if n == 0: return [F.mul(x, g[0]) for x in d]
    q, r = F.divide(f, g); k = len(r)-1
    if k < 0: raise ZeroDivisionError('noncoprime Sylvester factors')
    dd = F.add(d, F.product(q, c)); dd += [0]*(m-len(dd))
    low = sylvester_reference(F, g, r, dd[:k], c)
    full = low+[0]*(m-k)
    contribution = F.product([0]*k+dd[k:], g)
    for i, x in enumerate(contribution): full[i] ^= x
    return full
