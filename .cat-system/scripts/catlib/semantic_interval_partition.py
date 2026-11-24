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
