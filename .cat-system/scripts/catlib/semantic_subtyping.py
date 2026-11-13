"""Conservative typed domain inclusion used by Compiler and Process Composition.

Returns True only with a proved inclusion, False with a known incompatible
value/presence, and None when a type is unresolved or evidence is incomplete.
No semantic conversion, transport adapter or external Effect proof is implied.
"""
from __future__ import annotations
from catlib import semantic_types

def _unresolved_domain(domain):
    if not isinstance(domain,dict):
        return False  # Legacy scalar collection element names.
    kind=domain.get('type')
    if kind in (None,'unknown'):
        return True
    if kind=='reference':
        return not domain.get('resolved') or _unresolved_domain(domain.get('of'))
    if kind=='record':
        return domain.get('resolved') is not True or any(
            _unresolved_domain(f.get('domain')) for f in domain.get('fields',[]))
    if kind in ('set','sequence'):
        return _unresolved_domain(domain.get('element'))
    if kind=='nullable':
        return _unresolved_domain(domain.get('of'))
    if kind=='union':
        return any(_unresolved_domain(x) for x in domain.get('variants',[]))
    return False


def subset(source,target):
    """True only for proved inclusion; False for a counterexample; None if unknown."""
    if _unresolved_domain(source) or _unresolved_domain(target):
        return None
    # Python dict equality conflates enum booleans with integers (True == 1).
    # Domain identity must preserve scalar types throughout nested structures.
    if semantic_types.same(source,target):
        return True
    if isinstance(source,dict) and source.get('type')=='reference':
        return subset(source['of'],target)
    if isinstance(target,dict) and target.get('type')=='reference':
        return subset(source,target['of'])
    if isinstance(source,str):
        source={'type':source}
    if isinstance(target,str):
        target={'type':target}
    a=source.get('type');b=target.get('type')
    if a=='union':
        results=[subset(x,target) for x in source['variants']]
        return False if False in results else (True if all(x is True for x in results) else None)
    if b=='union':
        results=[subset(source,x) for x in target['variants']]
        if True in results:return True
        # A source can be covered by a union without fitting any one branch.
        # Only exhaustive finite evidence may establish that relation.
        values=semantic_types.finite_values(source,max_values=4096)
        if values is None:return None
        try:return all(semantic_types.contains(target,value) for value in values)
        except semantic_types.DomainError:return None
    if b=='nullable':
        if a=='null':return True
        return subset(source['of'],target['of']) if a=='nullable' else subset(source,target['of'])
    if a=='nullable':
        if b=='null':return subset(source['of'],target)
        return False  # Null cannot inhabit any other non-nullable, non-union target.
    if a=='enum':
        if b=='enum':
            return all(any(semantic_types.same(v,x) for x in target['values'])
                       for v in source['values'])
        try:
            return all(semantic_types.contains(target,v) for v in source['values'])
        except semantic_types.DomainError:
            return None
    if b=='enum':
        # A finite non-enum Domain may still fit a literal value set.
        # Never infer containment from a representative sample.
        try:
            values=semantic_types.finite_values(source,max_values=4096)
            return (all(semantic_types.contains(target,value) for value in values)
                    if values is not None else None)
        except semantic_types.DomainError:
            return None
    if a==b and a in ('integer','real'):
        return ((target.get('min') is None or (source.get('min') is not None
                                               and source['min']>=target['min']))
                and (target.get('max') is None or (source.get('max') is not None
                                                   and source['max']<=target['max'])))
    if a==b=='string':
        return target.get('format','any')=='any'
    if a in ('set','sequence') and b in ('set','sequence'):
        if a=='sequence' and b=='set':
            return False  # Sequence permits duplicates; Set forbids duplicates.
        return subset(source['element'],target['element'])
    if a==b=='record':
        # Records are closed: omitting a declaration means that key is always
        # missing. Presence is a separate state dimension from Domain.
        states={'required':{'value'},'optional':{'missing','value'},
                'absent':{'missing'},'undefined':{'undefined'}}
        left=source.get('fields',[]);right=target.get('fields',[])
        mine={x['id']:x for x in left}
        theirs={x['id']:x for x in right}
        if len(mine)!=len(left) or len(theirs)!=len(right):
            return None  # Malformed duplicate declarations have no proof.
        unknown=False
        for field_id in sorted(set(mine)|set(theirs)):
            producer=mine.get(field_id)
            consumer=theirs.get(field_id)
            producer_states=(states.get(producer.get('presence','required'))
                             if producer else {'missing'})
            consumer_states=(states.get(consumer.get('presence','required'))
                             if consumer else {'missing'})
            if producer_states is None or consumer_states is None:
                return None
            if not producer_states.issubset(consumer_states):
                return False  # Counterexample: key absent/undefined/value.
            if 'value' in producer_states:
                # Presence already guarantees a value on both boundaries.
                # Structural Domain inclusion is still required for that case.
                if producer is None or consumer is None:
                    return False
                result=subset(producer['domain'],consumer['domain'])
                if result is False:
                    return False
                if result is None:
                    unknown=True
        return None if unknown else True
    if a=='integer' and b=='real':
        return None  # Unbounded integers need a representability proof.
    if a!=b:
        return False
    return None


