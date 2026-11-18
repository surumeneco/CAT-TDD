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


def _constants(node, field):
    if not isinstance(node, dict):
        return None
    if node.get('op') == 'call':
        # Named functions may inspect a field through a hidden body.
        return None
    if not _reads(node, field):
        return []
    op, args = node.get('op'), node.get('args')
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
            nested = _constants(arg, field)
            if nested is None:
                return None
            found.extend(nested)
        return found
    return None


def string_partition_values(domain, field, predicates, allow_unused=False):
    """Give concrete representatives of exact eq/ne truth classes, or None.

    Only the unrestricted string Domain is eligible. Aliases, formatted
    strings, functions, cross-field comparisons, non-equality predicates and
    transforms remain outside this small proof fragment.
    """
    if not isinstance(domain, dict) or domain != {'type': 'string'}:
        return None
    found = []
    for predicate in predicates:
        literals = _constants(predicate, field)
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
