"""Interpret static PI peers and the per-execution origin Process.

The sentinel is not a Process ID: it is resolved for each execution from
its initiating Process. An explicit runtime identity check is still required;
this helper never proves the runtime origin or delivery by itself.
"""

ORIGIN = '@execution-origin'


def normalize_peer(value):
    return ORIGIN if value == '実行元Process' else value


def match_operation(peers, assigned, actual):
    """Return static/dynamic compatibility or None; never authenticate a caller."""
    if not isinstance(actual, str) or not actual or actual == ORIGIN:
        return None
    if actual not in peers and ORIGIN not in peers:
        return None
    if assigned is None:
        if len(peers) != 1:
            return None
        assigned = peers[0]
    if assigned == ORIGIN:
        return 'dynamic'
    if assigned in peers and assigned == actual:
        return 'static'
    return None
