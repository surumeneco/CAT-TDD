"""Interpret static PI peers and the per-execution origin Process.

The sentinel is not a Process ID: it is resolved for each execution from
its initiating Process. An explicit runtime identity check is still required;
this helper never proves the runtime origin or delivery by itself.
"""

# Process IDs in runtime evidence use the same stable grammar as static PI peers.
import re

PROCESS_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")

ORIGIN = '@execution-origin'


def normalize_peer(value):
    return ORIGIN if value == '実行元Process' else value


def concrete_process_id(value):
    return isinstance(value, str) and PROCESS_ID.fullmatch(value) is not None


def match_operation(peers, assigned, actual):
    """Return static/dynamic compatibility or None; never authenticate a caller."""
    if not concrete_process_id(actual):
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
