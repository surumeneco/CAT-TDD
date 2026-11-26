"""Source-bound symbolic preservation and exact per-cut output/action footprint.

This proves declared Outcomes only, not live effects, delivery or value equality
for nonstate writes. Guard exhaustiveness and Presence are separate Gate checks.
"""
from __future__ import annotations
import json
from catlib import peer_binding
from catlib.output_frame_contract import declarations, active_frames

TOKEN = '@cat:trigger-frame-footprint/v1'
PREFIX = 'trigger-frame-footprint '


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate footprint key')
        result[key] = value
    return result


def resolve(scope, fields, pi_docs):
    """Parse exact boundary and per-condition inventory; no proof verdict."""
    from cat_compile_v2 import parse_expr_text, Blocked
    try:
        spec = json.loads(scope[len(PREFIX):], object_pairs_hook=_unique)
        if set(spec) != {'trigger', 'pi', 'accept', 'peer', 'cases'}:
            return None
        trigger, owner, peer = (spec[k] for k in ('trigger', 'pi', 'peer'))
        if any(type(x) is not str or not x for x in (trigger, owner, peer)):
            return None
        if spec['accept'] is not None and type(spec['accept']) is not str:
            return None
        selected = [p for _, fm, p in pi_docs if fm['id'] == owner]
        if len(selected) != 1:
            return None
        pi = selected[0]
        peers = pi['boundary'].get('peers', [pi['boundary']['peer']])
        operations = [dict(op, source_pi=fm['id']) for _, fm, p in pi_docs for op in p['operations']]
        if any(op.get('trigger') is None for op in operations):
            return None
        cut = [op for op in operations if op['trigger'] == trigger]
        if not cut or any(op['source_pi'] != owner for op in cut):
            return None
        for op in cut:
            assigned = op.get('peer')
            if assigned is None and len(peers) == 1:
                assigned = peers[0]
            # The dynamic sentinel names the declared operation scope, not a
            # concrete Process or a proof of same-execution correspondence.
            if assigned != peer or (peer != peer_binding.ORIGIN and peer not in peers):
                return None
        accepted = [op['id'] for op in cut if op['direction'] == 'accept']
        if accepted != ([] if spec['accept'] is None else [spec['accept']]):
            return None
        providers = {op['id'] for op in cut if op['direction'] == 'provide'}
        cases = []
        if not isinstance(spec['cases'], list) or not spec['cases']:
            return None
        for case in spec['cases']:
            if set(case) != {'when', 'provide', 'required', 'allowed'}:
                return None
            condition = parse_expr_text(case['when'])
            if condition == {'literal': False} or any(c[0] == condition for c in cases):
                return None
            provided = case['provide']
            if provided is not None and (type(provided) is not str or provided not in providers):
                return None
            for name in ('required', 'allowed'):
                values = case[name]
                if (not isinstance(values, list) or any(type(k) is not str or k not in fields for k in values)
                        or len(set(values)) != len(values)):
                    return None
                if any(fields[k]['role'] not in ('output', 'action') for k in values):
                    return None
                if any(fields[k]['role'] == 'output' and (provided is None or fields[k].get('source_pi') != owner) for k in values):
                    return None
            required, allowed = set(case['required']), set(case['allowed'])
            if not required <= allowed:
                return None
            cases.append((condition, provided, required, allowed))
        if {c[1] for c in cases if c[1] is not None} != providers:
            return None
        return trigger, owner, cases, operations, declarations(pi_docs)
    except (Blocked, ValueError, TypeError, KeyError, AttributeError):
        return None


def operation_at(owner, trigger, row, n, operations, frames):
    # Only the explicit owner/cut inventory can select between providers.
    cut_frames = [f for f in frames if f['source_pi'] == owner and f['trigger'] == trigger]
    if cut_frames:
        hits = [f for f in cut_frames if f['rule'] == row and f['outcome'] == n]
        if len(hits) != 1:
            raise ValueError('missing or ambiguous output frame')
        active = active_frames(cut_frames, operations, trigger, row, n)
        return active.get(owner, {}).get('id')
    candidates = [op['id'] for op in operations if op['source_pi'] == owner and op['direction'] == 'provide' and op['trigger'] == trigger]
    if len(candidates) > 1:
        raise ValueError('ambiguous output operation')
    return candidates[0] if candidates else None


def prove(scope, fields, pi_docs, rules, checks):
    resolved = resolve(scope, fields, pi_docs)
    if resolved is None:
        return False
    trigger, owner, cases, operations, frames = resolved
    states = {k for k, f in fields.items() if f['role'] == 'state'}
    nonstates = {k for k, f in fields.items() if f['role'] in ('output', 'action')}
    rows = [r for r in rules if r['trigger'] == trigger]
    seen = set()
    try:
        for row in rows:
            matches = [i for i, case in enumerate(cases) if case[0] == row['when']]
            if len(matches) != 1 or not row['allowed']:
                return False
            index = matches[0]
            seen.add(index)
            _, provided, required, allowed = cases[index]
            for n, out in enumerate(row['allowed'], 1):
                if operation_at(owner, trigger, row['id'], n, operations, frames) != provided:
                    return False
                written = set()
                for i, write in enumerate(out['write'], 1):
                    k = write['target']
                    key = f"{row['source_artifact']}#{row['id']}:{n}:{i}:{k}"
                    if k in written or checks.get(key, {}).get('result') != 'proved':
                        return False
                    if k in states and write['expr'] != {'ref': k}:
                        return False
                    if k not in states | nonstates:
                        return False
                    written.add(k)
                if not required <= written - states <= allowed:
                    return False
                if set(out['unchanged']) != states - written or set(out['absent_outputs']) != nonstates - written:
                    return False
        return seen == set(range(len(cases)))
    except (ValueError, TypeError, KeyError, AttributeError):
        return False


def verify(scope, fields, pi_docs, tces, checks, rejected):
    """Reconstruct preservation and absence from original TCE write inventory."""
    resolved = resolve(scope, fields, pi_docs)
    if resolved is None:
        return False
    trigger, owner, cases, operations, frames = resolved
    seen = set()
    try:
        for _, fm, tce in tces:
            for row in tce['rules']:
                if row['trigger'] != trigger:
                    continue
                candidates = [(i, c) for i, c in enumerate(cases) if c[0] == row['when']]
                if len(candidates) != 1 or not row['allowed']:
                    return False
                index, (_, provided, required, allowed) = candidates[0]
                seen.add(index)
                for n, outcome in enumerate(row['allowed'], 1):
                    if operation_at(owner, trigger, row['id'], n, operations, frames) != provided:
                        return False
                    projection = {k: {'ref': k} for k, f in fields.items() if f['role'] == 'state'}
                    emitted = set()
                    assigned = set()
                    for i, write in enumerate(outcome['write'], 1):
                        k = write['target']
                        key = f"{fm['id']}#{row['id']}:{n}:{i}:{k}"
                        if k in assigned or key in rejected or checks.get(key, {}).get('result') != 'proved':
                            return False
                        assigned.add(k)
                        if k in projection:
                            projection[k] = write['expr']
                        elif fields[k]['role'] in ('output', 'action'):
                            emitted.add(k)
                        else:
                            return False
                    if any(value != {'ref': k} for k, value in projection.items()):
                        return False
                    if not required <= emitted <= allowed:
                        return False
        return seen == set(range(len(cases)))
    except (ValueError, TypeError, KeyError, AttributeError):
        return False
