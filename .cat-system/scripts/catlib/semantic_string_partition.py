"""Exact truth partition for unrestricted strings tested against constants.

The witness for the remaining class is chosen outside all mentioned literals.
Because every allowed predicate observes the value only via equality or
inequality with those literals, all remaining strings have the same truth
profile. This is not a finite enumeration of the string Domain and does not
prove the effect of arbitrary string transformations or external operations.
"""
from __future__ import annotations

MAX_PARTITION_VALUES=65536


def _reads(node, field):
    if not isinstance(node, dict):
        return False
    return node.get('ref') == field or any(
        _reads(child, field) for child in node.get('args', []))


def _constants(node, field, allow_presence=False):
    if not isinstance(node, dict):
        return None
    if node.get('op') == 'call':
        # Named functions may inspect a field through a hidden body.
        return None
    if not _reads(node, field):
        return []
    op, args = node.get('op'), node.get('args')
    if allow_presence and op in ('is-present','is-missing','is-undefined') and args==[{'ref':field}]:
        return []
    if op in ('eq', 'ne') and isinstance(args, list) and len(args) == 2:
        for left, right in ((args[0], args[1]), (args[1], args[0])):
            if (isinstance(left, dict) and set(left) == {'ref'}
                    and left['ref'] == field and isinstance(right, dict)
                    and set(right) == {'literal'}
                    and type(right['literal']) is str):
                return [right['literal']]
        return None
    if op in ('and', 'or', 'not') and isinstance(args, list):
        if (op == 'not' and len(args) != 1) or (op != 'not' and len(args) < 2):
            return None
        found = []
        for arg in args:
            nested = _constants(arg, field, allow_presence)
            if nested is None:
                return None
            found.extend(nested)
        return found
    return None


def string_partition_values(domain, field, predicates, allow_unused=False, allow_presence=False):
    """Give concrete representatives of exact eq/ne truth classes, or None.

    Only the unrestricted string Domain is eligible. Aliases, formatted
    strings, functions, cross-field comparisons, non-equality predicates and
    transforms remain outside this small proof fragment.
    """
    if not isinstance(domain, dict) or domain != {'type': 'string'}:
        return None
    found = []
    for predicate in predicates:
        literals = _constants(predicate, field, allow_presence)
        if literals is None:
            return None
        found.extend(literals)
    if not found and not allow_unused:
        return None
    constants = set(found)
    if len(constants) >= MAX_PARTITION_VALUES:
        return None
    other = ''
    while other in constants:
        other += '\x00'
    return [*sorted(constants), other]


def reference_palette(names,predicates,extra_literals=(),require_pair=True):
    """Complete equality classes of up to five unrestricted string variables.

    All mentioned constants are fixed. N fresh distinct strings suffice for
    every equality pattern of N variables; no transform or hidden call allowed.
    This may also cover before/after variables and explicit copy/literal writes.
    """
    group=set(names)
    if not 1<=len(group)<=5:return None
    constants=set(extra_literals);paired=False
    def has_call(node):return node.get('op')=='call' or any(has_call(a) for a in node.get('args',[]))
    def inspect(node):
        nonlocal paired
        if not any(_reads(node,k) for k in group):return True
        args=node.get('args',[])
        if node.get('op') in ('and','or','not'):return all(inspect(a) for a in args)
        if node.get('op') not in ('eq','ne') or len(args)!=2:return False
        a,b=args
        if set(a)==set(b)=={'ref'} and {a['ref'],b['ref']}<=group:
            paired |= a['ref']!=b['ref'];return True
        for ref,lit in ((a,b),(b,a)):
            if set(ref)=={'ref'} and ref['ref'] in group and set(lit)=={'literal'} and type(lit['literal']) is str:
                constants.add(lit['literal']);return True
        return False
    if any(has_call(p) or not inspect(p) for p in predicates) or require_pair and not paired:return None
    fresh=[];value=''
    while len(fresh)<len(group):
        if value not in constants:fresh.append(value)
        value+='\x00'
    return [*sorted(constants),*fresh]


def nullable_string_null_partition(domain, field, predicates):
    """Required nullable<string>: exact null/non-null Guard classes only."""
    if domain!={'type':'nullable','of':{'type':'string'}}:return None
    def check(node):
        if node.get('op')=='call':return False
        if not _reads(node,field):
            return all(check(a) for a in node.get('args',[]))
        args=node.get('args',[])
        if node.get('op') in ('eq','ne') and len(args)==2:
            return args in ([{'ref':field},{'literal':None}],[{'literal':None},{'ref':field}])
        if node.get('op') in ('and','or','not'):return all(check(a) for a in args)
        return False
    if not any(_reads(p,field) for p in predicates) or not all(check(p) for p in predicates):return None
    return [None,'']
