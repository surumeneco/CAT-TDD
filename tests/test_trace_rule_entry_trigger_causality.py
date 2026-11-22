"""U04: Source-declared entry Trigger must own every explicit run Rule claim.

This checks identity/causality only; never asserts Provider authenticity or
Source Rule semantic equivalence.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from test_effect_trace_correlation import data, DRIVER
from test_effect_trace_work_gate import setup
import cat_execution_trace_diagnostic as trace_runtime
import cat_effect_trace_correlation as correlation
import cat_flow


def bound_fixture(root, rule_trigger='startup-t'):
    model_raw, trace, packet = data(root)
    model = json.loads(model_raw)
    model['triggers'] = [
        {'id': 'startup-t', 'origin': 'demo.pi'},
        {'id': 'manual-t', 'origin': 'demo.pi'},
    ]
    for operation in model['pi_operations']:
        if operation['id'] == 'startup':
            operation['trigger'] = 'startup-t'
        elif operation['id'] == 'manual':
            operation['trigger'] = 'manual-t'
    model['rules'][0]['trigger'] = rule_trigger
    model_raw = json.dumps(model, sort_keys=True).encode('utf-8')
    fingerprint = hashlib.sha256(model_raw).hexdigest()
    trace['model_sha256'] = fingerprint
    packet['model_sha256'] = fingerprint
    return model_raw, trace, packet


class TraceRuleEntryTriggerCausalityTests(unittest.TestCase):
    def test_matching_rule_and_entry_trigger_remains_identity_consistent_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw, trace, packet = bound_fixture(root)
            checked = trace_runtime.evaluate(json.loads(raw), raw, trace)
            self.assertEqual(checked['trace_integrity'], 'consistent')
            combined = correlation.correlate(raw, trace, packet, DRIVER, root)
            self.assertEqual(combined['status'], 'identity-consistent-only')
            self.assertEqual(combined['normative_status'], 'inconclusive')
            self.assertEqual(combined['external_effect_proof'], 'not-run')

    def test_trace_rejects_effect_event_claiming_rule_for_different_trigger(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, trace, _ = bound_fixture(Path(temp), rule_trigger='manual-t')
            with self.assertRaisesRegex(trace_runtime.TraceError, 'Rule.*Trigger'):
                trace_runtime.evaluate(json.loads(raw), raw, trace)

    def test_trace_rejects_terminal_claiming_rule_for_different_trigger(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, trace, _ = bound_fixture(Path(temp), rule_trigger='manual-t')
            trace['events'][4].pop('rule_id')
            trace['events'][4].pop('outcome_index')
            with self.assertRaisesRegex(trace_runtime.TraceError, 'Rule.*Trigger'):
                trace_runtime.evaluate(json.loads(raw), raw, trace)

    def test_effect_receipt_cannot_borrow_wrong_trigger_when_trace_rule_unbound(self):
        # A receipt is independently Source-bound to a valid Rule, but only
        # the trace knows the particular run's accepted Operation/Trigger.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw, trace, packet = bound_fixture(root, rule_trigger='manual-t')
            for e in trace['events']:
                e.pop('rule_id', None)
                e.pop('outcome_index', None)
            with self.assertRaisesRegex(correlation.CorrelationError, 'Rule.*Trigger'):
                correlation.correlate(raw, trace, packet, DRIVER, root)

    def test_unobserved_effect_receipt_also_cannot_borrow_other_trigger(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw, trace, packet = bound_fixture(root, rule_trigger='manual-t')
            for e in trace['events']:
                e.pop('rule_id', None)
                e.pop('outcome_index', None)
            packet['observations'][0].update(
                reported_status='not-observed',
                observation_file=None, observation_sha256=None,
                effect_event_id=None)
            with self.assertRaisesRegex(correlation.CorrelationError, 'Rule.*Trigger'):
                correlation.correlate(raw, trace, packet, DRIVER, root)

    def test_formal_work_effect_preflight_rejects_cross_trigger_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            work, workpath = setup(root)
            raw, trace, packet = bound_fixture(root, rule_trigger='manual-t')
            (root / 'Model.json').write_bytes(raw)
            (root / 'Trace.json').write_text(json.dumps(trace), encoding='utf-8')
            (root / 'Packet.json').write_text(json.dumps(packet), encoding='utf-8')
            with self.assertRaisesRegex(cat_flow.Blocked, 'Rule.*Trigger'):
                cat_flow.implementation_effect_preflight(
                    workpath, work, work['compilation'])

    def test_different_explicit_entry_trigger_can_use_its_own_rule(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, trace, packet = bound_fixture(Path(temp))
            model = json.loads(raw)
            model['rules'].append({
                'id': 'manual_rule', 'source_artifact': 'demo.tce',
                'trigger': 'manual-t',
                'allowed': [{'write': []}],
            })
            raw = json.dumps(model, sort_keys=True).encode('utf-8')
            trace['model_sha256'] = hashlib.sha256(raw).hexdigest()
            trace['runs'].append({
                'execution_id': 'run-2', 'entry_operation': 'manual',
                'peer': 'command'})
            trace['events'].extend([
                {'event_id': 'manual-trigger', 'execution_id': 'run-2',
                 'kind': 'trigger', 'operation': 'manual', 'peer': 'command'},
                {'event_id': 'manual-terminal', 'execution_id': 'run-2',
                 'kind': 'result', 'parent_event_id': 'manual-trigger',
                 'operation': 'manual_result', 'peer': 'command',
                 'outcome': 'success', 'rule_id': 'manual_rule',
                 'outcome_index': 1},
            ])
            self.assertEqual(
                trace_runtime.evaluate(model, raw, trace)['trace_integrity'],
                'consistent')

    def test_missing_legacy_explicit_trigger_binding_is_not_fabricated(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, trace, packet = data(Path(temp))
            result = correlation.correlate(raw, trace, packet, DRIVER, Path(temp))
            self.assertEqual(result['status'], 'identity-consistent-only')
            self.assertEqual(result['normative_status'], 'inconclusive')


if __name__ == '__main__':
    unittest.main()
