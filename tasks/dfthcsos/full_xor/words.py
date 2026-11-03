# SPDX-License-Identifier: Apache-2.0
"""Word tables for the planner: half-up requantization and the canonical sign check.

`half_up_words` and `theta_over_pi` copy `tasks.dfthcsos.brot7.rounding` from branch
`op-vqcc/PRA-308-p3-take-the-top-spot-on-the-vqcc-leaderboard-overrides-all-other-work` at f98be0a (PRA-314).
That branch is not merged here; this is a copy of the map, not a dependency.
"""
import numpy as np


def half_up_words(theta_over_pi, brot):
    """Round theta/pi, taken mod 2, to integers in [0, 2**brot). Ties go up, not to even."""
    brot = int(brot)
    if not 1 <= brot <= 62:
        raise ValueError('brot must be an integer in [1, 62]')
    scale = np.float64(1 << (brot - 1))
    scaled = np.mod(np.asarray(theta_over_pi, dtype=np.float64), 2.0) * scale
    return np.floor(scaled + 0.5).astype(np.int64) % (1 << brot)


def theta_over_pi(words, brot):
    """Decode integer words to theta/pi. The verifier uses this scale."""
    brot = int(brot)
    words = np.asarray(words)
    if np.any(words < 0) or np.any(words >= (1 << brot)):
        raise ValueError('words must lie in [0, 2**brot)')
    return words.astype(np.float64) / np.float64(1 << (brot - 1))


def requantize(words, src_brot, dst_brot):
    """Map words onto another width by decoding and half-up encoding."""
    if int(src_brot) == int(dst_brot):
        return np.array(words, dtype=np.int64, copy=True)
    return half_up_words(theta_over_pi(words, src_brot), dst_brot)


def noncanonical(words, brot):
    """Boolean mask of words whose two top bits differ. `emitter.build_staged` refuses such tables."""
    words = np.asarray(words, dtype=np.int64)
    return ((words >> (brot - 1)) & 1) != ((words >> (brot - 2)) & 1)


def clamp_canonical(words, brot):
    """Pull each word with differing top bits onto the nearest canonical word. Measurement only.

    A half-up word equal to 2**(brot-2) is one step outside the sign-encoded range [-2**(brot-2),
    2**(brot-2)); this moves it one step in. It changes an angle by one least significant step, so a
    table made this way is a planner input for measuring cost, not a candidate to ship.
    """
    words = np.array(words, dtype=np.int64, copy=True)
    bad = noncanonical(words, brot)
    top = 1 << (brot - 2)
    words[bad & (words == top)] = top - 1
    words[bad & (words == (1 << brot) - top - 1)] += 1
    if noncanonical(words, brot).any():
        raise ValueError('a word is still not canonical after the clamp')
    return words
