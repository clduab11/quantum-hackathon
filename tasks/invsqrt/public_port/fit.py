# SPDX-License-Identifier: Apache-2.0
"""GPU enumeration of Gluzdov v7's published interpolated-curvature recipe.

Parent cell 22 enumerates base/slope and the neighboring linear coefficient.
Cell 34 requires an even anchor for the virtual bit. We enforce that during
the same search. All residuals are evaluated on CUDA in int64/float64.
Only the small deterministic choice of groups runs on the host.
"""
import argparse
import json
import math
from pathlib import Path

from .model import Config, certificate, interpolation_values, pipeline, rd


def fit_group(e, group, group_bits=3, fraction_bits=3):
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required; CPU-only fitting is not authorized")
    cfg = Config()
    size = 1 << group_bits
    mid = 1 + (group + .5) * size / 128
    scale = 2 ** ((e-1)/2)
    bc = round(.375 * scale * mid**-2.5 * 2**cfg.f2)
    sc = round(1.25 * .375 * scale * mid**-3.5 * 2**cfg.f2 / 128 * 2**fraction_bits)
    candidates, needed = [], set()
    for base in range(bc-4, bc+5):
        for step in range(max(0, sc-3), sc+4):
            try:
                values = interpolation_values(base, step, fraction_bits=fraction_bits, group_bits=group_bits)
            except ValueError:
                continue
            candidates.append((base, step, values))
            needed.update(enumerate(values))
    cache = {}
    for low in range(size):
        a = group*size + low
        d = torch.arange(16384, device="cuda", dtype=torch.int64)
        xn = (1 << 21) + (a << 14) + d
        d = d[d % 2 == 0] if e else d[(xn <= 3133452) | (d % 4 == 0)]
        target = scale / torch.sqrt(1 + (a*16384+d).double() * 2**-21) * 2**cfg.fy
        midpoint = 1 + (a*16384+8191.5) * 2**-21
        k1c = round(.5 * scale * midpoint**-1.5 * 2**cfg.f1)
        # ±9 includes cell 22's ±5 followed by cell 34's ±4 refinement.
        k1 = torch.arange(k1c-9, k1c+10, device="cuda", dtype=torch.int64)[:, None]
        for k2 in sorted(k for i, k in needed if i == low):
            r, q = pipeline(cfg, k2, k1, d[None, :])
            values = target + q
            center = (values.amin(1) + values.amax(1))/2 + 1.5
            anchor = 2 * torch.floor(center/2).to(torch.int64)
            # Deterministic order: k1, then even k0 ascending, as in the source.
            scores, anchors = [], []
            for offset in range(-10, 13, 2):
                k0 = anchor + offset
                y = ((k0[:, None] - q) >> cfg.gy) << cfg.gy
                score = ((y-target).abs()/target).amax(1)*2**24
                score[(y.amax(1) >= 1 << cfg.fy) | (r.amin(1) < 0)] = float('inf')
                scores.append(score)
                anchors.append(k0)
            score_matrix = torch.stack(scores, dim=1)
            index = int(score_matrix.argmin())
            row, col = divmod(index, len(scores))
            cache[low, k2] = (float(score_matrix[row, col]), k2, int(k1[row, 0]), int(anchors[col][row]))
    choices = []
    for base, step, values in candidates:
        rows = [cache[low, k2] for low, k2 in enumerate(values)]
        choices.append((max(row[0] for row in rows), base, step, rows))
    score, base, step, rows = min(choices, key=lambda item: item[0])
    if not math.isfinite(score):
        raise RuntimeError(f"No legal fit for parity {e}, group {group}")
    return dict(score=score, base=base, step=step, rows=[row[1:] for row in rows])


def fit_tables(group_bits=3, fraction_bits=3, threshold=.95):
    """Refine only groups that miss the stated error bound; never fit to a salt."""
    size = 1 << group_bits
    tables, encoding, scores, groups = {}, {}, [], []

    def visit(e, group, bits):
        fit = fit_group(e, group, bits, fraction_bits)
        print(json.dumps(dict(parity=e, group=group, group_bits=bits, score=fit['score'])), flush=True)
        if fit['score'] > threshold and bits:
            visit(e, group*2, bits-1)
            visit(e, group*2+1, bits-1)
            return
        scores.append(fit['score'])
        groups.append(dict(parity=e, group=group, group_bits=bits, score=fit['score']))
        for j, row in enumerate(fit['rows']):
            address = group*(1 << bits)+j
            # Embed a smaller group's interpolation in the same global adder
            # schedule. The upper address bits are constant inside this group.
            base = fit['base'] + sum((2*((address >> i)&1)-1)*rd(fit['step'], fraction_bits-i)
                                     for i in range(bits, group_bits))
            tables[e, address] = row
            encoding[e, address] = (base, fit['step'])
            expected = base - sum((2*((address >> i)&1)-1)*rd(fit['step'], fraction_bits-i)
                                  for i in range(group_bits))
            if expected != row[0] or not 0 <= base < 256:
                raise RuntimeError('Refined curvature encoding is invalid')

    for e in range(2):
        for group in range(128//size):
            visit(e, group, group_bits)
    encoded = [encoding[e,a] for e in range(2) for a in range(128)]
    return dict(params=[9, 19, 26, 2, [5]], rows=[tables[e,a] for e in range(2) for a in range(128)],
                interpolation=dict(fraction_bits=fraction_bits, remainder_bits=group_bits,
                                   step_width=max(1, max(s.bit_length() for _,s in encoded)), rows=encoded),
                normalized_worst=max(scores), certificate=certificate(Config(), tables),
                device='cuda', refinement_threshold=threshold, groups=groups)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--group-bits', type=int, choices=range(4), default=3)
    parser.add_argument('--fraction-bits', type=int, choices=(2, 3, 4), default=3)
    parser.add_argument('--threshold', type=float, default=.95)
    args = parser.parse_args()
    result = fit_tables(args.group_bits, args.fraction_bits, args.threshold)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result['certificate']), flush=True)


if __name__ == '__main__':
    main()
