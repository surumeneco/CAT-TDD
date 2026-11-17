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
