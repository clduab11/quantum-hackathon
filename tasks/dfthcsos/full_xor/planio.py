# SPDX-License-Identifier: Apache-2.0
"""Exact Plan JSON and fixed-schedule carry replay; NO synthesis on replay."""
from dataclasses import asdict
from tasks.dfthcsos.full_xor.paired_anf import Plan,Product,build_circuit

def plan_dict(plan):return asdict(plan)
def plan_from_dict(d):
 required={'addresses','batch','brot','low_bits','products','pure','ranks','cache_masks','blocks','parity_scratch'}
 if set(d)!=required:raise ValueError('bad saved Plan fields')
 ints=('addresses','batch','brot','low_bits','parity_scratch')
 if any(type(d[k])is not int for k in ints):raise ValueError('noninteger saved Plan routing')
 if d['addresses']<1 or(d['batch'],d['brot'],d['low_bits'])!=(5,8,4)or d['parity_scratch']not in(0,2):raise ValueError('unsupported carry Plan layout')
 pure={}
 for k,v in d['pure'].items():
  kk=int(k)
  if str(kk)!=str(k)or kk in pure or type(v)is not int or not 0<=kk<d['addresses']or not 0<v<(1<<40):raise ValueError('ambiguous/out-of-range pure-polynomial key/value')
  pure[kk]=v
 products=[]
 for p in d['products']:
  if set(p)!={'left1','right1','left2','right2','fanout'}or any(type(v)is not int or v<0 for v in p.values()):raise ValueError('bad saved Product')
  if p['left1'].bit_length()>16 or p['left2'].bit_length()>16 or p['right1'].bit_length()>((d['addresses']-1)>>4)+1 or p['right2'].bit_length()>((d['addresses']-1)>>4)+1 or not 0<p['fanout']<(1<<40):raise ValueError('product outside declared wire coordinates')
  products.append(Product(**p))
 cache=d['cache_masks']
 if any(type(m)is not int or not 0<m<d['addresses']or m.bit_count()<2 for m in cache)or cache!=sorted(set(cache)):raise ValueError('bad cache order/masks')
 if any((m^(1<<(m.bit_length()-1))).bit_count()>=2 and(m^(1<<(m.bit_length()-1)))not in cache for m in cache):raise ValueError('cache is not parent closed')
 if any(type(r)is not int or r<0 for r in d['ranks']):raise ValueError('bad saved ranks')
 return Plan(*(d[k]for k in('addresses','batch','brot','low_bits')),products,pure,list(d['ranks']),list(d['cache_masks']),
  blocks=None if d['blocks']is None else[plan_from_dict(x)for x in d['blocks']],parity_scratch=d['parity_scratch'])
