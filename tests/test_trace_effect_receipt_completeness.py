"""U04: explicit Trace Effect claims require a receipt or remain unproved.

The request/response Trace and Effect receipt are independently self-reported.
A complete set of labels is structural evidence only, not normative proof of
actual execution or of the originating Source specification.
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


def inspect(root, raw, trace, packet):
    return correlation.correlate(raw, trace, packet, DRIVER, root)


def second_claim(root):
    raw, trace, packet = data(root)
    model = json.loads(raw)
    model['rules'][0]['allowed'][0]['write'].append({
        'target': 'action.extra', 'expr': {'literal': True}})
    raw = json.dumps(model, sort_keys=True).encode()
    sha = hashlib.sha256(raw).hexdigest()
    trace['model_sha256'] = sha
    packet['model_sha256'] = sha
    trace['events'].insert(5, {
        'event_id': 'second-effect', 'execution_id': 'run-1',
        'kind': 'replace', 'parent_event_id': 'replace',
        'rule_id': 'sync_rule', 'outcome_index': 1,
        'effect_target': 'action.extra'})
    trace['events'][6]['parent_event_id'] = 'second-effect'
    return raw, trace, packet


class ExplicitEffectReceiptCompletenessTests(unittest.TestCase):
    def test_empty_packet_must_not_claim_all_explicit_effects_correlated(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw, trace, packet = data(root)
            packet['observations'] = []
            result = inspect(root, raw, trace, packet)
            self.assertEqual(result['status'], 'inconclusive')
            self.assertEqual(result['normative_status'], 'inconclusive')
            self.assertEqual(result['external_effect_proof'], 'not-run')
            self.assertEqual(result['unresolved'], [{
                'execution_id': 'run-1', 'event_id': 'replace',
                'rule_id': 'sync_rule', 'outcome_index': 1,
                'effect_target': 'action.replace',
                'reason': 'trace-effect-without-receipt'}])

    def test_second_explicit_effect_in_same_allowed_outcome_needs_own_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw, trace, packet = second_claim(root)
            result = inspect(root, raw, trace, packet)
            self.assertEqual(result['status'], 'inconclusive')
            self.assertEqual(len(result['unresolved']), 1)
            self.assertEqual(result['unresolved'][0]['event_id'], 'second-effect')
            self.assertEqual(result['unresolved'][0]['reason'], 'trace-effect-without-receipt')
            self.assertEqual(len(result['observations']), 1)

    def test_second_valid_receipt_accounts_for_declared_effect_but_not_external_truth(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw, trace, packet = second_claim(root)
            observed = {
                'schema': 'cat-effect-observation/v1',
                'rule_id': 'sync_rule', 'outcome_index': 1,
                'effect_target': 'action.extra', 'execution_id': 'run-1',
                'reported_status': 'succeeded'}
            bytes_ = json.dumps(observed, sort_keys=True).encode()
            (root / 'extra.json').write_bytes(bytes_)
            packet['observations'].append({
                'rule_id': 'sync_rule', 'outcome_index': 1,
                'effect_target': 'action.extra', 'execution_id': 'run-1',
                'reported_status': 'succeeded',
                'observation_file': 'extra.json',
                'observation_sha256': hashlib.sha256(bytes_).hexdigest(),
                'effect_event_id': 'second-effect'})
            result = inspect(root, raw, trace, packet)
            self.assertEqual(result['status'], 'identity-consistent-only')
            self.assertEqual(result['unresolved'], [])
            self.assertEqual(result['normative_status'], 'inconclusive')
            self.assertEqual(result['provider_authentication_status'], 'not-run')

    def test_explicit_not_observed_receipt_is_counted_but_keeps_inconclusive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw, trace, packet = data(root)
            packet['observations'][0].update(
                reported_status='not-observed', observation_file=None,
                observation_sha256=None, effect_event_id=None)
            result = inspect(root, raw, trace, packet)
            self.assertEqual(result['status'], 'inconclusive')
            self.assertEqual(len(result['unresolved']), 1)
            self.assertEqual(result['unresolved'][0]['reason'], 'not-observed')

    def test_legacy_unbound_side_effect_event_does_not_invent_a_rule(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw, trace, packet = data(root)
            for field in ('rule_id', 'outcome_index', 'effect_target'):
                trace['events'][4].pop(field)
            packet['observations'] = []
            result = inspect(root, raw, trace, packet)
            self.assertEqual(result['status'], 'identity-consistent-only')
            self.assertEqual(result['unresolved'], [])
            self.assertEqual(result['normative_status'], 'inconclusive')

    def test_partially_bound_explicit_effect_is_inconclusive_not_auto_linked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw, trace, packet = data(root)
            trace['events'][4].pop('effect_target')
            packet['observations'] = []
            result = inspect(root, raw, trace, packet)
            self.assertEqual(result['status'], 'inconclusive')
            self.assertEqual(result['unresolved'][0]['reason'],
                             'trace-effect-binding-incomplete')

    def test_declared_effect_target_not_in_allowed_outcome_must_block_trace(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw, trace, packet = data(root)
            trace['events'][4]['effect_target'] = 'action.undeclared'
            packet['observations'] = []
            with self.assertRaisesRegex(correlation.CorrelationError,
                                        'Effect target.*not declared'):
                inspect(root, raw, trace, packet)

    def test_other_allowed_outcome_target_cannot_be_borrowed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw, trace, packet = data(root)
            model = json.loads(raw)
            model['rules'][0]['allowed'].append(
                {'write': [{'target': 'action.later', 'expr': {'literal': True}}]})
            raw = json.dumps(model, sort_keys=True).encode()
            trace['model_sha256'] = hashlib.sha256(raw).hexdigest()
            trace['events'][4]['effect_target'] = 'action.later'
            packet['model_sha256'] = trace['model_sha256']
            packet['observations'] = []
            with self.assertRaisesRegex(correlation.CorrelationError,
                                        'Effect target.*not declared'):
                inspect(root, raw, trace, packet)

    def test_no_rule_inventory_keeps_unbound_model_inconclusive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw, trace, packet = data(root)
            model = json.loads(raw)
            del model['rules']
            raw = json.dumps(model, sort_keys=True).encode()
            trace['model_sha256'] = hashlib.sha256(raw).hexdigest()
            packet['model_sha256'] = trace['model_sha256']
            packet['observations'] = []
            result = inspect(root, raw, trace, packet)
            self.assertEqual(result['status'], 'inconclusive')
            self.assertEqual(result['normative_status'], 'inconclusive')

    def test_official_work_effect_preflight_keeps_missing_receipt_unproved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work, workpath = setup(root)
            packet = json.loads((root / 'Packet.json').read_text())
            packet['observations'] = []
            (root / 'Packet.json').write_text(json.dumps(packet))
            verdict = cat_flow.implementation_effect_preflight(
                workpath, work, work['compilation'])
            self.assertEqual(verdict['status'], 'inconclusive')
            self.assertEqual(verdict['normative_status'], 'inconclusive')
            details = json.loads(Path(verdict['path']).read_text())
            self.assertEqual(details['unresolved'][0]['reason'],
                             'trace-effect-without-receipt')

    def test_formal_preflight_rejects_declared_target_outside_allowed_outcome(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work, workpath = setup(root)
            trace = json.loads((root / 'Trace.json').read_text())
            packet = json.loads((root / 'Packet.json').read_text())
            trace['events'][4]['effect_target'] = 'action.undeclared'
            packet['observations'] = []
            (root / 'Trace.json').write_text(json.dumps(trace))
            (root / 'Packet.json').write_text(json.dumps(packet))
            with self.assertRaisesRegex(cat_flow.Blocked,
                                        'Effect target.*not declared'):
                cat_flow.implementation_effect_preflight(
                    workpath, work, work['compilation'])


if __name__ == '__main__':
    unittest.main()
