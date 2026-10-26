# SPDX-License-Identifier: Apache-2.0
"""Dimensionless Phase M penalties over the unchanged verifier mirror terms."""
import jax
import jax.numpy as jnp
from .loss import admissible


def effective(m):
    return jnp.sqrt(jnp.maximum(m['E_gap']*(2*m['Lambda']-m['E_gap']), 1e-20))


def targets(summary, baseline):
    return dict(m2=max(.0005, summary['error_2']['absolute_p95']),
                mg=max(1e-6, summary['E_gap']['absolute_p95']),
                cap=1.01*float(effective(baseline)))


def penalty(m, target):
    """All weights one except score/domain guards, each weighted 100."""
    m2, mg, cap = (target[k] for k in ('m2','mg','cap'))
    residuals = jnp.stack([(m['error_1']-.0195)/.0005,
                           (m['error_2']-(.020-m2))/m2,
                           (3.914898+mg-m['E_gap'])/mg])
    guards = jnp.stack([(effective(m)-cap)/(cap/101),
                       (49.0001-m['Lambda'])/49.,
                       (m['E_gap']-2*m['Lambda']+.0001)/49.])
    return jnp.sum(jax.nn.relu(residuals)**2)+100*jnp.sum(jax.nn.relu(guards)**2)


def eligible(m, target):
    """Necessary pre-export gate, never a substitute for the official cascade."""
    return (admissible(m) & (m['error_2'] <= .020-target['m2'])
            & (m['E_gap'] >= 3.914898+target['mg']) & (effective(m) <= target['cap']))
