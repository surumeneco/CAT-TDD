"""UP20-03/06: source-bound cross-evidence identity without external self-proof."""
from __future__ import annotations
import copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
from test_execution_trace_diagnostic import payload as trace_payload
import cat_effect_trace_correlation as correlation

DRIVER=b'project runner source\n'

def data(root):
    model,trace=trace_payload()
    model['source_records'].append({'id':'demo.tce','sha256':'b'*64,'kind':'tce'})
    model['rules']=[{'id':'sync_rule','source_artifact':'demo.tce',
                     'allowed':[{'write':[{'target':'action.replace','expr':{'literal':True}}]}]}]
    trace['events'][4].update(rule_id='sync_rule',outcome_index=1,effect_target='action.replace')
    trace['events'][5].update(rule_id='sync_rule',outcome_index=1)
    raw=json.dumps(model,sort_keys=True).encode()
    trace['source_sha256']={'demo.pi':'a'*64,'demo.tce':'b'*64}
    trace['model_sha256']=hashlib.sha256(raw).hexdigest()
    observation={'schema':'cat-effect-observation/v1','rule_id':'sync_rule','outcome_index':1,
                 'effect_target':'action.replace','execution_id':'run-1','reported_status':'succeeded'}
    observed_raw=json.dumps(observation,sort_keys=True).encode()
    (root/'observation.json').write_bytes(observed_raw)
    packet={'schema':'cat-external-effect-receipts/v1',
            'model_sha256':hashlib.sha256(raw).hexdigest(),
            'source_sha256':trace['source_sha256'],
            'driver_sha256':hashlib.sha256(DRIVER).hexdigest(),
            'implementation_head':'1'*40,
            'observations':[{'rule_id':'sync_rule','outcome_index':1,
                             'effect_target':'action.replace','execution_id':'run-1',
                             'reported_status':'succeeded','observation_file':'observation.json',
                             'observation_sha256':hashlib.sha256(observed_raw).hexdigest(),
                             'effect_event_id':'replace'}]}
    return raw,trace,packet



BINDING={'request_id':'request-42','transaction_id':'tx-7','target_id':'notice-5'}


def bound(raw,trace,packet):
    # Explicit self-reported identifiers, not a proof of Source equivalence.
    trace['runs'][0]['correlation']=dict(BINDING)
    trace['events'][4]['correlation']=dict(BINDING)
    trace['events'][5]['correlation']=dict(BINDING)
    packet['observations'][0]['correlation']=dict(BINDING)
    return raw,trace,packet

def inspect(root,raw,trace,packet):
    return correlation.correlate(raw,trace,packet,DRIVER,root)


class CorrelationTests(unittest.TestCase):
    def test_exact_cross_receipt_is_still_non_normative(self):
        with tempfile.TemporaryDirectory() as d:
            raw,t,p=data(Path(d));r=inspect(d,raw,t,p)
            self.assertEqual(r['status'],'identity-consistent-only')
            self.assertEqual(r['normative_status'],'inconclusive')
            self.assertEqual(r['external_effect_proof'],'not-run')
            self.assertFalse(r['implementation_head_checkout_verified'])

    def test_bound_execution_identity_is_consistent_but_not_normative_proof(self):
        with tempfile.TemporaryDirectory() as d:
            raw,t,p=bound(*data(Path(d)))
            result=inspect(d,raw,t,p)
            self.assertEqual(result['status'],'identity-consistent-only')
            self.assertEqual(result['normative_status'],'inconclusive')
            self.assertEqual(result['external_effect_proof'],'not-run')

    def test_different_transaction_id_in_receipt_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            raw,t,p=bound(*data(Path(d)))
            p['observations'][0]['correlation']['transaction_id']='tx-other'
            with self.assertRaisesRegex(correlation.CorrelationError,'correlation'):
                inspect(d,raw,t,p)

    def test_different_request_id_in_effect_event_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            raw,t,p=bound(*data(Path(d)))
            t['events'][4]['correlation']['request_id']='request-other'
            with self.assertRaisesRegex(correlation.CorrelationError,'correlation'):
                inspect(d,raw,t,p)

    def test_different_target_id_in_terminal_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            raw,t,p=bound(*data(Path(d)))
            t['events'][5]['correlation']['target_id']='other-notice'
            with self.assertRaisesRegex(correlation.CorrelationError,'correlation'):
                inspect(d,raw,t,p)

    def test_missing_binding_on_one_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            raw,t,p=bound(*data(Path(d)))
            del t['events'][4]['correlation']
            with self.assertRaisesRegex(correlation.CorrelationError,'correlation'):
                inspect(d,raw,t,p)

    def test_malformed_or_partial_correlation_is_rejected(self):
        for update in ({'transaction_id': ''}, {'target_id': None}):
            with self.subTest(update=update), tempfile.TemporaryDirectory() as d:
                raw,t,p=bound(*data(Path(d)))
                p['observations'][0]['correlation'].update(update)
                with self.assertRaisesRegex(correlation.CorrelationError,'correlation'):
                    inspect(d,raw,t,p)
        with tempfile.TemporaryDirectory() as d:
            raw,t,p=bound(*data(Path(d)))
            del p['observations'][0]['correlation']['target_id']
            with self.assertRaisesRegex(correlation.CorrelationError,'correlation'):
                inspect(d,raw,t,p)

    def test_failed_caller_response_does_not_prove_transaction_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            raw,t,p=bound(*data(Path(d)))
            t['events'][5]['outcome']='failure'
            result=inspect(d,raw,t,p)
            self.assertEqual(result['status'],'identity-consistent-only')
            self.assertEqual(result['normative_status'],'inconclusive')
            self.assertIn('source-to-rule-predicate-equivalence-unproved', result['limitations'])

    def test_unobserved_effect_with_bound_request_stays_inconclusive(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw,t,p=bound(*data(root))
            record=p['observations'][0]
            record.update(reported_status='not-observed',observation_file=None,
                          observation_sha256=None,effect_event_id=None)
            r=inspect(d,raw,t,p)
            self.assertEqual(r['status'],'inconclusive')
            self.assertNotEqual(r['normative_status'],'passed')

    def test_unobserved_effect_still_rejects_explicit_terminal_rule_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw,t,p=data(root)
            rec=p['observations'][0]
            rec.update(reported_status='not-observed',observation_file=None,
                       observation_sha256=None,effect_event_id=None)
            t['events'][5]['rule_id']='unrelated-rule'
            with self.assertRaisesRegex(correlation.CorrelationError,'terminal Rule'):
                inspect(d,raw,t,p)

    def test_unobserved_effect_still_rejects_explicit_terminal_outcome_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw,t,p=data(root)
            rec=p['observations'][0]
            rec.update(reported_status='not-observed',observation_file=None,
                       observation_sha256=None,effect_event_id=None)
            t['events'][5]['outcome_index']=2
            with self.assertRaisesRegex(correlation.CorrelationError,'terminal allowed Outcome'):
                inspect(d,raw,t,p)

    def test_unobserved_effect_without_terminal_binding_remains_inconclusive(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw,t,p=data(root)
            rec=p['observations'][0]
            rec.update(reported_status='not-observed',observation_file=None,
                       observation_sha256=None,effect_event_id=None)
            del t['events'][5]['outcome_index']
            result=inspect(d,raw,t,p)
            self.assertEqual(result['status'],'inconclusive')
            self.assertEqual(result['normative_status'],'inconclusive')

    def test_receipt_for_run_not_in_trace_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw,t,p=data(root)
            p['observations'][0]['execution_id']='run-2'
            obs=json.loads((root/'observation.json').read_bytes());obs['execution_id']='run-2'
            payload=json.dumps(obs,sort_keys=True).encode();(root/'observation.json').write_bytes(payload)
            p['observations'][0]['observation_sha256']=hashlib.sha256(payload).hexdigest()
            with self.assertRaisesRegex(correlation.CorrelationError,'absent from trace'):
                inspect(d,raw,t,p)

    def test_effect_event_must_refer_to_same_run_and_declared_target(self):
        with tempfile.TemporaryDirectory() as d:
            raw,t,p=data(Path(d));t['events'][4]['effect_target']='other'
            with self.assertRaisesRegex(correlation.CorrelationError,'Rule/Outcome/target'):
                inspect(d,raw,t,p)

    def test_receipt_cannot_take_an_unrelated_event(self):
        with tempfile.TemporaryDirectory() as d:
            raw,t,p=data(Path(d));p['observations'][0]['effect_event_id']='result'
            with self.assertRaisesRegex(correlation.CorrelationError,'not a supported side-effect'):
                inspect(d,raw,t,p)

    def test_terminal_outcome_index_must_match(self):
        with tempfile.TemporaryDirectory() as d:
            raw,t,p=data(Path(d));t['events'][5]['outcome_index']=2
            with self.assertRaisesRegex(correlation.CorrelationError,'terminal allowed Outcome'):
                inspect(d,raw,t,p)

    def test_terminal_rule_must_match(self):
        with tempfile.TemporaryDirectory() as d:
            raw,t,p=data(Path(d));t['events'][5]['rule_id']='unrelated'
            with self.assertRaisesRegex(correlation.CorrelationError,'terminal Rule'):
                inspect(d,raw,t,p)

    def test_result_without_explicit_outcome_binding_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as d:
            raw,t,p=data(Path(d));del t['events'][5]['outcome_index']
            r=inspect(d,raw,t,p)
            self.assertEqual(r['status'],'inconclusive')
            self.assertEqual(r['observations'][0]['status'],'inconclusive')

    def test_unknown_result_is_not_transformed_to_success(self):
        with tempfile.TemporaryDirectory() as d:
            raw,t,p=data(Path(d));t['events'][5]['outcome']='unknown'
            r=inspect(d,raw,t,p)
            self.assertEqual(r['status'],'inconclusive')
            self.assertNotEqual(r['observations'][0]['status'],'passed')

    def test_unobserved_effect_cannot_claim_an_event(self):
        with tempfile.TemporaryDirectory() as d:
            raw,t,p=data(Path(d));e=p['observations'][0]
            e.update(reported_status='not-observed',observation_file=None,
                     observation_sha256=None)
            with self.assertRaisesRegex(correlation.CorrelationError,'unobserved Effect'):
                inspect(d,raw,t,p)

    def test_missing_effect_event_is_not_silently_assigned(self):
        with tempfile.TemporaryDirectory() as d:
            raw,t,p=data(Path(d));del p['observations'][0]['effect_event_id']
            with self.assertRaisesRegex(correlation.CorrelationError,'explicit effect_event_id'):
                inspect(d,raw,t,p)

    def test_trace_cannot_rebind_a_different_model_hash(self):
        with tempfile.TemporaryDirectory() as d:
            raw,t,p=data(Path(d));t['model_sha256']='f'*64
            with self.assertRaisesRegex(correlation.CorrelationError,'model identity'):
                inspect(d,raw,t,p)

if __name__=='__main__':unittest.main()
