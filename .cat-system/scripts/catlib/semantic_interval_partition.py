"""Exact predicate partition for integer comparisons against literal constants.

Only direct integer field vs integer literal comparisons, nested in Boolean
and/or/not, qualify. One witness per truth-equivalence cell is exhaustive
for this fragment; it is not a proof of external Effects or arbitrary math.
"""
from __future__ import annotations

COMPARATORS=frozenset(('eq','ne','lt','le','gt','ge'))
BOOLEANS=frozenset(('and','or','not'))
MAX_PARTITION_VALUES=65536


def _reads(expr, field):
    if not isinstance(expr,dict):
        return False
    if expr.get('ref') == field:
        return True
    return any(_reads(arg,field) for arg in expr.get('args',[]))


def _thresholds(expr,field,allow_presence=False):
    if isinstance(expr,dict) and expr.get('op')=='call':
        # DomainRule bodies may read this field without an explicit call arg.
        return None
    if not _reads(expr,field):
        return []
    if not isinstance(expr,dict):
        return None
    op,args=expr.get('op'),expr.get('args')
    if allow_presence and op in ('is-present','is-missing','is-undefined') and args==[{'ref':field}]:
        return []
    if op in COMPARATORS and isinstance(args,list) and len(args)==2:
        for a,b in ((args[0],args[1]),(args[1],args[0])):
            if (isinstance(a,dict) and set(a)=={'ref'} and a['ref']==field
                    and isinstance(b,dict) and set(b)=={'literal'}
                    and type(b['literal']) is int):
                return [b['literal']]
        return None
    if op in BOOLEANS and isinstance(args,list) and args:
        if (op=='not' and len(args)!=1) or (op in ('and','or') and len(args)<2):
            return None
        cuts=[]
        for arg in args:
            sub=_thresholds(arg,field,allow_presence)
            if sub is None:
                return None
            cuts.extend(sub)
        return cuts
    return None


def integer_partition_values(domain,field,predicates,allow_unused=False,allow_presence=False):
    """Return exact predicate-class witnesses, or None if not soundly decidable.

    The returned witness count is not a finite cardinality of the Domain.
    Named aliases, optional input states and expressions involving arithmetic
    or field-to-field comparisons deliberately remain outside this contract.
    """
    if not isinstance(domain,dict) or domain.get('type')!='integer':
        return None
    low,high=domain.get('min'),domain.get('max')
    if low is not None and type(low) is not int:return None
    if high is not None and type(high) is not int:return None
    if low is not None and high is not None and low>high:return None
    cuts=[]
    for predicate in predicates:
        sub=_thresholds(predicate,field,allow_presence)
        if sub is None:return None
        cuts.extend(sub)
    if not cuts:
        if not allow_unused:return None
        point=0
        if low is not None and point<low:point=low
        if high is not None and point>high:point=high
        return [point]
    cuts=sorted(set(cuts))
    witnesses={cuts[0]-1,cuts[-1]+1}
    for cut in cuts:witnesses.update((cut-1,cut,cut+1))
    if low is not None:witnesses.add(low)
    if high is not None:witnesses.add(high)
    values=sorted(x for x in witnesses if (low is None or x>=low)
                  and (high is None or x<=high))
    return values if values and len(values)<=MAX_PARTITION_VALUES else None


def real_partition_values(domain,field,predicates,allow_unused=False):
    """Exact order cells for direct real-vs-numeric-literal comparisons.

    Equality is excluded: CAT equality distinguishes integer and float values.
    Require a representable in-domain witness for each mathematical cell.
    """
    import math
    from fractions import Fraction
    if not isinstance(domain,dict) or domain.get('type')!='real':return None
    low,high=domain.get('min'),domain.get('max')
    def number(x):return type(x) is int or type(x) is float and math.isfinite(x)
    if any(x is not None and not number(x) for x in (low,high)):return None
    if low is not None and high is not None and low>high:return None
    def cuts_of(node):
        if not isinstance(node,dict) or node.get('op')=='call':return None
        if not _reads(node,field):return []
        op,args=node.get('op'),node.get('args',[])
        if op in BOOLEANS:
            out=[]
            for arg in args:
                part=cuts_of(arg)
                if part is None:return None
                out.extend(part)
            return out
        if op in ('lt','le','gt','ge') and len(args)==2:
            for a,b in ((args[0],args[1]),(args[1],args[0])):
                if a=={'ref':field} and set(b)=={'literal'} and number(b['literal']):
                    return [b['literal']]
        return None
    cuts=[]
    for clause in predicates:
        part=cuts_of(clause)
        if part is None:return None
        cuts.extend(part)
    if not cuts:
        if not allow_unused:return None
        return [low if low is not None else high if high is not None else 0]
    def in_range(x):return (low is None or low<=x) and (high is None or x<=high)
    points=sorted({Fraction(x) for x in [*cuts,low,high] if x is not None and in_range(x)})
    if not points:return None
    result=[]
    if low is None:result.append(math.floor(points[0])-1)
    for i,point in enumerate(points):
        result.append(int(point) if point.denominator==1 else float(point))
        if i+1<len(points):
            other=points[i+1]
            integer=math.floor(point)+1
            if integer<other:result.append(integer);continue
            try:mid=float((point+other)/2)
            except OverflowError:return None
            if not math.isfinite(mid) or not point<Fraction(mid)<other:return None
            result.append(mid)
    if high is None:result.append(math.ceil(points[-1])+1)
    return result if result and len(result)<=MAX_PARTITION_VALUES else None


def sequence_length_values(domain, field, predicates):
    """Exact length truth classes, witnessed by concrete in-domain sequences.

    Only direct length(field) vs integer literal, under Boolean composition.
    Never replace an observed sequence value with its length in Effects.
    """
    from catlib import semantic_types as typed
    from catlib.semantic_structural_copy import _example
    if domain.get('type')!='sequence':return None
    def rewrite(node):
        if node.get('op')=='call':raise ValueError('opaque call')
        if node.get('op')=='length' and node.get('args')==[{'ref':field}]:return {'ref':field}
        if node.get('ref')==field:raise ValueError('value read outside length')
        return ({**node,'args':[rewrite(x) for x in node['args']]} if 'args' in node else node)
    try:
        lengths=integer_partition_values({'type':'integer','min':0},field,[rewrite(x) for x in predicates])
        if lengths is None or max(lengths)>4096 or sum(lengths)>16384:return None
        element=_example(domain['element'])
        if not typed.contains(domain['element'],element):return None
        return [[element]*length for length in lengths]
    except (ValueError,TypeError,KeyError,IndexError,RecursionError):return None
