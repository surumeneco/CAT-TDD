"""Bounded exact bit masks over already justified finite Guard partitions.

This is a pure expression-evaluation primitive, not a Source or Model validator.
Each bit represents one row in native Cartesian order. Undefined reads survive
until excluded by ordered short circuit; no value classes are sampled or added.
"""
from __future__ import annotations
import itertools
import json
import math


class MaskUnavailable(Exception):
    """Unsupported or exhausted bounded proof; never success."""


def truth_masks(names, dimensions, constraints, guards, definitions, evaluate, references, blocked):
    sizes=list(map(len,dimensions)); count=math.prod(sizes)
    if not 0<count<=2_000_000:return None
    # Bound native evaluations, whole-mask work and retained masks separately.
    # Whole-mask work uses the full row width; mask construction charges its
    # actual intermediate widths. Account for retained result masks too.
    words=(count+63)//64
    work=0; evaluations=0
    universe=(1<<count)-1
    cache={}; axis_cache={}
    strides=[math.prod(sizes[i+1:]) for i in range(len(sizes))]
    def charge(n=1, width=None):
        nonlocal work
        work+=n*(words if width is None else (width+63)//64)
        if work>64_000_000:raise MaskUnavailable('mask work budget exceeded')
    def remember():
        if (2*len(cache)+len(axis_cache)+len(guards)+8)*((count+7)//8)>64*1024*1024:
            raise MaskUnavailable('mask storage budget exceeded')
    if (len(guards)+8)*((count+7)//8)>64*1024*1024:return None
    def axis_mask(i,j):
        key=(i,j)
        if key not in axis_cache:
            remember()
            stride=strides[i]; width=stride*sizes[i]; times=math.prod(sizes[:i])
            pattern=((1<<stride)-1)<<(stride*j)
            repeated=0; offset=0
            while times:
                if times&1:
                    charge(2,offset+width);repeated|=pattern<<offset;offset+=width
                times>>=1
                if times:
                    charge(2,2*width);pattern|=pattern<<width;width*=2
            axis_cache[key]=repeated
        return axis_cache[key]
    def build(expr):
        nonlocal evaluations
        key=json.dumps(expr,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        if key in cache:return cache[key]
        op=expr.get('op');args=expr.get('args',[])
        if op in ('and','or'):
            pending=universe; positive=invalid=0
            for child in args:
                if not pending:break
                t,u=build(child);charge(3 if op=='and' else 6)
                invalid|=pending&u
                if op=='and':pending&=t
                else:
                    positive|=pending&t;pending&=universe^(t|u)
            result=(pending if op=='and' else positive,invalid)
        elif op=='not':
            if len(args)!=1:raise MaskUnavailable('invalid not')
            t,u=build(args[0]);charge(2);result=(universe^(t|u),u)
        else:
            refs=references(expr,definitions)
            if not refs<=set(names):raise MaskUnavailable('unknown dependency')
            indices=[i for i,name in enumerate(names) if name in refs]
            size=math.prod(sizes[i] for i in indices)
            if size>65536 or evaluations+size>1_000_000:raise MaskUnavailable('atomic proof budget exceeded')
            evaluations+=size
            t=u=0
            for values in itertools.product(*(range(sizes[i]) for i in indices)):
                env={names[i]:dimensions[i][j] for i,j in zip(indices,values)}
                try:
                    value=evaluate(expr,env,definitions)
                    if type(value) is not bool:value=None
                except (blocked,TypeError,ValueError,KeyError,OverflowError):value=None
                if value is False:continue
                cell=universe
                for i,j in zip(indices,values):
                    charge();cell&=axis_mask(i,j)
                charge()
                if value is True:t|=cell
                else:u|=cell
            result=t,u
        remember();cache[key]=result
        return result
    try:
        accepted=universe
        for constraint in constraints:
            if not accepted:break
            t,u=build(constraint);charge(2)
            if accepted&u:return None
            accepted&=t
        matches=[]
        for guard in guards:
            if not accepted:matches.append(0);continue
            t,u=build(guard);charge(2)
            if accepted&u:return None
            matches.append(accepted&t)
        return accepted,matches
    except MaskUnavailable:return None


def row_indices(index, dimensions):
    result=[]
    for size in reversed(list(map(len,dimensions))):
        index,offset=divmod(index,size);result.append(offset)
    return tuple(reversed(result))


def first_indices(mask, limit):
    for _ in range(limit):
        if not mask:break
        first=mask&-mask
        yield first.bit_length()-1
        mask^=first
