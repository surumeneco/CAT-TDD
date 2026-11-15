#!/usr/bin/env python3
"""Audit declared within-run causality in an explicitly supplied trace.

This is a structural diagnostic, NOT a CAT Gate or a claim that a provider
actually made HTTP calls, replaced a file, delivered a notification, etc.
It does not reconstruct events from source code or infer normative semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


class TraceError(ValueError):
    """Malformed, stale, or internally contradictory trace evidence."""


def _require(test, message):
    if not test:
        raise TraceError(message)


def _label(value, label):
    _require(isinstance(value, str) and bool(value), label + ' must be a nonempty string')
    return value


def _model_inventory(model):
    _require(isinstance(model, dict) and model.get('schema') == 'cat-test-model/v2',
             'requires cat-test-model/v2')
    items = model.get('source_records')
    _require(isinstance(items, list) and bool(items), 'source identity inventory missing')
    source = {}
    for item in items:
        _require(isinstance(item, dict), 'invalid source identity entry')
        name = _label(item.get('id'), 'source identity ID')
        sha = item.get('sha256')
        _require(isinstance(sha, str) and len(sha) == 64
                 and all(c in '0123456789abcdef' for c in sha),
                 'invalid source identity sha256')
        _require(name not in source, 'duplicate source identity')
        source[name] = sha
    return source


def _operations(model):
    boundaries = {}
    for boundary in model.get('pi_boundaries', []):
        _require(isinstance(boundary, dict), 'invalid PI boundary')
        pi = _label(boundary.get('artifact'), 'PI boundary artifact')
        _require(pi not in boundaries, 'duplicate PI boundary')
        peers = boundary.get('peers', [boundary.get('peer')])
        _require(isinstance(peers, list) and bool(peers)
                 and all(isinstance(p, str) and p for p in peers)
                 and len(set(peers)) == len(peers)
                 and boundary.get('peer') == peers[0], 'invalid boundary peer inventory')
        boundaries[pi] = peers
    operations = {}
    for op in model.get('pi_operations', []):
        _require(isinstance(op, dict), 'invalid PI operation')
        name = _label(op.get('id'), 'PI operation ID')
        _require(name not in operations, 'ambiguous duplicate operation')
        pi = _label(op.get('source_pi'), 'PI operation owner')
        _require(pi in boundaries, 'operation missing PI boundary')
        role = op.get('direction')
        _require(role in ('accept', 'provide'), 'invalid operation direction')
        peer = op.get('peer')
        if peer is None:
            _require(len(boundaries[pi]) == 1,
                     'ambiguous operation: multiple peers without mapping')
            peer = boundaries[pi][0]
        _require(peer in boundaries[pi], 'operation peer outside declared PI boundary')
        operations[name] = {'direction': role, 'source_pi': pi, 'peer': peer}
    return operations


def _check_operation(operations, op_id, role, peer):
    operation = operations.get(op_id)
    _require(operation is not None, 'unknown operation')
    _require(operation['direction'] == role, 'operation direction mismatch')
    _require(operation['peer'] == peer, 'operation peer mismatch')


def evaluate(model, model_bytes, trace):
    """Validate graph integrity and identity; never return a normative passed."""
    _require(isinstance(model_bytes, bytes), 'model must be accompanied by exact raw bytes')
    _require(isinstance(trace, dict) and trace.get('schema') == 'cat-execution-trace/v1',
             'invalid execution trace schema')
    expected_hash = hashlib.sha256(model_bytes).hexdigest()
    _require(trace.get('model_sha256') == expected_hash, 'model identity mismatch')
    source = _model_inventory(model)
    _require(trace.get('source_sha256') == source, 'source identity mismatch')
    operations = _operations(model)

    runs = trace.get('runs')
    events = trace.get('events')
    _require(isinstance(runs, list) and bool(runs), 'trace needs declared runs')
    _require(isinstance(events, list), 'trace events must be a list')
    run_by_id = {}
    for run in runs:
        _require(isinstance(run, dict), 'run record required')
        rid = _label(run.get('execution_id'), 'run execution_id')
        _require(rid not in run_by_id, 'duplicate execution id')
        peer = _label(run.get('peer'), 'run peer')
        op = _label(run.get('entry_operation'), 'run entry_operation')
        _check_operation(operations, op, 'accept', peer)
        run_by_id[rid] = run

    kinds = {'trigger', 'input', 'request', 'response', 'projection', 'replace',
             'result', 'followup'}
    seen = {}
    kinds_by_run = {rid: {'trigger': 0, 'result': 0, 'unknown': 0} for rid in run_by_id}
    for index, event in enumerate(events):
        _require(isinstance(event, dict), 'event record required')
        eid = _label(event.get('event_id'), 'event_id')
        rid = _label(event.get('execution_id'), 'event execution_id')
        _require(eid not in seen, 'duplicate event_id')
        _require(rid in run_by_id, 'event references unknown execution')
        kind = event.get('kind')
        _require(kind in kinds, 'unsupported event kind')
        run = run_by_id[rid]
        if kind == 'trigger':
            _require(event.get('parent_event_id') is None, 'trigger cannot have a parent')
            _require(event.get('operation') == run['entry_operation'],
                     'trigger operation does not match run entry')
            _require(event.get('peer') == run['peer'], 'trigger peer does not match run')
            _check_operation(operations, event['operation'], 'accept', run['peer'])
            kinds_by_run[rid]['trigger'] += 1
        else:
            parent_id = _label(event.get('parent_event_id'), 'non-trigger parent_event_id')
            parent = seen.get(parent_id)
            _require(parent is not None, 'parent event missing or not causally earlier')
            _require(parent['execution_id'] == rid,
                     'parent and child belong to different execution')
            # Events are not allowed to change the observed run identity.
            if 'peer' in event:
                _require(event['peer'] == run['peer'], 'event peer differs from run')
            if kind == 'projection' and event.get('source_kind') == 'response':
                ancestor_id = parent_id
                has_response = False
                while ancestor_id is not None:
                    ancestor = seen[ancestor_id]
                    if ancestor['kind'] == 'response':
                        has_response = True
                        break
                    ancestor_id = ancestor.get('parent_event_id')
                _require(has_response, 'projection lacks response ancestor')
            if kind == 'result':
                kinds_by_run[rid]['result'] += 1
                _require(kinds_by_run[rid]['result'] <= 1,
                         'multiple terminal results in one execution')
                op = _label(event.get('operation'), 'result operation')
                _require(event.get('peer') == run['peer'], 'result peer differs from run')
                _check_operation(operations, op, 'provide', run['peer'])
                outcome = event.get('outcome')
                _require(outcome in ('success', 'failure', 'unknown'),
                         'result outcome must be success/failure/unknown')
                if outcome == 'unknown':
                    kinds_by_run[rid]['unknown'] += 1
            if kind == 'followup':
                ancestor_id = parent_id
                has_result = False
                while ancestor_id is not None:
                    ancestor = seen[ancestor_id]
                    if ancestor['kind'] == 'result':
                        has_result = True
                        break
                    ancestor_id = ancestor.get('parent_event_id')
                _require(has_result, 'followup must descend from a result')
        seen[eid] = event

    inconclusive = []
    for rid, state in kinds_by_run.items():
        _require(state['trigger'] == 1, 'each run must have exactly one trigger')
        if state['result'] == 0:
            inconclusive.append({'execution_id': rid, 'reason': 'terminal-result-not-observed'})
        elif state['unknown']:
            inconclusive.append({'execution_id': rid, 'reason': 'unknown-outcome'})
    return {'schema': 'cat-execution-trace-diagnostic/v1',
            'trace_integrity': 'inconclusive' if inconclusive else 'consistent',
            'normative_status': 'inconclusive', 'formal_gate_status': 'not-run',
            'external_effect_proof': 'not-run',
            'model_sha256': expected_hash, 'source_sha256': source,
            'execution_count': len(runs), 'event_count': len(events),
            'unresolved': inconclusive,
            'limitations': ['event-truth-unverified', 'no-runtime-transport-proof',
                            'no-cross-process-effect-proof',
                            'no-normative-source-to-predicate-equivalence']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--trace', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        data = args.model.read_bytes()
        result = evaluate(json.loads(data), data,
                          json.loads(args.trace.read_text(encoding='utf-8')))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                          sort_keys=True) + '\n', encoding='utf-8')
        print(json.dumps({'trace_integrity': result['trace_integrity'],
                          'normative_status': result['normative_status'],
                          'output': str(args.output)}))
        return 0
    except (OSError, TypeError, ValueError, KeyError) as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
