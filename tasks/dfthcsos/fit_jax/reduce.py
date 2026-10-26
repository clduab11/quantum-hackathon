# SPDX-License-Identifier: Apache-2.0
"""Deterministic GPU proposals for smaller factors; caller must enforce admissible."""
import jax.numpy as jnp


def reduce(params, shape):
    """Drop weakest groups/bases, truncate augmented [w; offsets] SVD on device."""
    w, offsets, angles = params['w'],params['offsets'],params['angles']
    old = w.shape
    if any(new < 1 or new > prev for new,prev in zip(shape,old)) or len(shape) != 3:
        raise ValueError('R,B,C must be positive and cannot grow')
    r,b,c = shape
    if c < old[2] and c > min(old[2],b+1):
        raise ValueError('C truncation exceeds the retained augmented rank; choose C <= B+1')
    n = angles.shape[1]+1
    body = angles[n:].reshape(*old[:2],n-1)
    groups = jnp.sort(jnp.argsort(-jnp.sum(w*w,axis=(1,2)),stable=True)[:r])
    w,offsets,body = w[groups],offsets[groups],body[groups]
    bases = jnp.sort(jnp.argsort(-jnp.sum(w*w,axis=2),axis=1,stable=True)[:,:b],axis=1)
    w,body = w[jnp.arange(r)[:,None],bases],body[jnp.arange(r)[:,None],bases]
    if c < old[2]:
        augmented = jnp.concatenate([w,offsets[:,None,:]],axis=1)
        left,singular,_ = jnp.linalg.svd(augmented,full_matrices=False)
        # Resolve sign ambiguity by the first largest-magnitude component.
        pivot = jnp.argmax(jnp.abs(left),axis=1)
        sign = jnp.sign(left[jnp.arange(r)[:,None],pivot,jnp.arange(left.shape[2])[None,:]])
        reduced = left[:,:,:c]*sign[:,None,:c]*singular[:,None,:c]
        w,offsets = reduced[:,:-1],reduced[:,-1]
    return dict(angles=jnp.concatenate([angles[:n],body.reshape(r*b,n-1)]),w=w,offsets=offsets)
