"""Causal response lineage and explicit request/response receipt correlation.

The trace is self-reported and non-normative. The v1 request/response profile
must reject contradictory identities without requiring absent legacy labels.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from test_execution_trace_diagnostic import payload, diagnose
from test_effect_trace_correlation import data, bound, BINDING, DRIVER
from test_effect_trace_work_gate import setup
import cat_execution_trace_diagnostic as trace_runtime
import cat_effect_trace_correlation as correlation
import cat_flow


def other_request_id():
    return {**BINDING, 'request_id': 'different-request'}


class TraceRequestResponseCausalityTests(unittest.TestCase):
    def test_response_cannot_be_parented_directly_by_trigger(self):
        model, trace = payload()
        trace['events'][2]['parent_event_id'] = 'start'
        with self.assertRaisesRegex(trace_runtime.TraceError, 'response.*request ancestor'):
            diagnose(model, trace)

    def test_response_cannot_borrow_an_unrelated_input_event_as_request(self):
        model, trace = payload()
        trace['events'].insert(2, {
            'event_id': 'unrelated-input', 'execution_id': 'run-1',
            'kind': 'input', 'parent_event_id': 'start'})
        trace['events'][3]['parent_event_id'] = 'unrelated-input'
        with self.assertRaisesRegex(trace_runtime.TraceError, 'response.*request ancestor'):
            diagnose(model, trace)

    def test_response_can_descend_from_request_via_processing_event(self):
        model, trace = payload()
        trace['events'].insert(2, {
            'event_id': 'decode', 'execution_id': 'run-1',
            'kind': 'input', 'parent_event_id': 'request'})
        trace['events'][3]['parent_event_id'] = 'decode'
        checked = diagnose(model, trace)
        self.assertEqual(checked['trace_integrity'], 'consistent')
        self.assertEqual(checked['normative_status'], 'inconclusive')

    def test_explicit_response_request_pair_disagreement_is_rejected(self):
        model, trace = payload()
        trace['events'][1]['correlation'] = dict(BINDING)
        trace['events'][2]['correlation'] = other_request_id()
        with self.assertRaisesRegex(trace_runtime.TraceError, 'request/response correlation'):
            diagnose(model, trace)

    def test_matching_explicit_pair_and_legacy_absent_pair_are_supported(self):
        for declared in (False, True):
            with self.subTest(declared=declared):
                model, trace = payload()
                if declared:
                    trace['events'][1]['correlation'] = dict(BINDING)
                    trace['events'][2]['correlation'] = dict(BINDING)
                self.assertEqual(diagnose(model, trace)['trace_integrity'],
                                 'consistent')

    def test_malformed_explicit_response_correlation_is_rejected(self):
        for invalid in ({'request_id':'only-one'}, {
            **BINDING, 'request_id': ''}):
            with self.subTest(invalid=invalid):
                model, trace = payload()
                trace['events'][2]['correlation'] = invalid
                with self.assertRaisesRegex(trace_runtime.TraceError,
                                            'response correlation'):
                    diagnose(model, trace)

    def test_receipt_cannot_use_response_from_different_request(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw, trace, packet = bound(*data(root))
            trace['events'][2]['correlation'] = other_request_id()
            with self.assertRaisesRegex(correlation.CorrelationError,
                                        'causal request/response correlation'):
                correlation.correlate(raw, trace, packet, DRIVER, root)

    def test_receipt_cannot_use_request_from_different_transaction(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw, trace, packet = bound(*data(root))
            trace['events'][1]['correlation'] = {
                **BINDING, 'transaction_id': 'other-transaction'}
            with self.assertRaisesRegex(correlation.CorrelationError,
                                        'causal request/response correlation'):
                correlation.correlate(raw, trace, packet, DRIVER, root)

    def test_unobserved_receipt_still_rejects_mismatched_terminal_lineage(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw, trace, packet = bound(*data(root))
            record = packet['observations'][0]
            record.update(reported_status='not-observed', observation_file=None,
                          observation_sha256=None, effect_event_id=None)
            trace['events'][2]['correlation'] = other_request_id()
            with self.assertRaisesRegex(correlation.CorrelationError,
                                        'causal request/response correlation'):
                correlation.correlate(raw, trace, packet, DRIVER, root)

    def test_unrelated_sibling_request_may_have_other_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw, trace, packet = bound(*data(root))
            trace['events'].insert(2, {
                'event_id': 'unrelated-side-call', 'execution_id': 'run-1',
                'kind': 'request', 'parent_event_id': 'start',
                'correlation': other_request_id()})
            checked = correlation.correlate(raw, trace, packet, DRIVER, root)
            self.assertEqual(checked['status'], 'identity-consistent-only')
            self.assertEqual(checked['normative_status'], 'inconclusive')

    def test_correct_causal_lineage_is_identity_consistent_not_provider_proof(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw, trace, packet = bound(*data(root))
            trace['events'][1]['correlation'] = dict(BINDING)
            trace['events'][2]['correlation'] = dict(BINDING)
            checked = correlation.correlate(raw, trace, packet, DRIVER, root)
            self.assertEqual(checked['status'], 'identity-consistent-only')
            self.assertEqual(checked['external_effect_proof'], 'not-run')
            self.assertEqual(checked['provider_authentication_status'], 'not-run')

    def test_canonical_implementation_effect_preflight_rejects_response_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work, workpath = setup(root)
            raw, trace, packet = bound(*data(root))
            trace['events'][2]['correlation'] = other_request_id()
            (root / 'Model.json').write_bytes(raw)
            (root / 'Trace.json').write_text(json.dumps(trace), encoding='utf-8')
            (root / 'Packet.json').write_text(json.dumps(packet), encoding='utf-8')
            with self.assertRaisesRegex(cat_flow.Blocked,
                                        'causal request/response correlation'):
                cat_flow.implementation_effect_preflight(
                    workpath, work, work['compilation'])


if __name__ == '__main__':
    unittest.main()
