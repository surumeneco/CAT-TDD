"""An execution ID must not silently combine incompatible declared correlations."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from test_external_effect_receipts import DRIVER, inputs
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
import cat_external_effect_receipts as evidence

A={'request_id':'request-1','transaction_id':'tx-1','target_id':'target-1'}
B={'request_id':'request-1','transaction_id':'tx-2','target_id':'target-1'}


def two_targets(root,second_status='succeeded'):
    raw,packet=inputs(root)
    model=json.loads(raw)
    model['rules'][0]['allowed'][0]['write'].append(
        {'target':'state.flag','expr':{'literal':False}})
    raw=json.dumps(model,sort_keys=True).encode()
    packet['model_sha256']=hashlib.sha256(raw).hexdigest()
    first=packet['observations'][0]
    first['correlation']=dict(A)
    observed=json.loads((root/'obs.json').read_bytes())
    observed['correlation']=dict(A)
    payload=json.dumps(observed,sort_keys=True).encode()
    (root/'obs.json').write_bytes(payload)
    first['observation_sha256']=hashlib.sha256(payload).hexdigest()
    second={'rule_id':'rule','outcome_index':1,'effect_target':'state.flag',
            'execution_id':'run1','reported_status':second_status,
            'correlation':dict(A)}
    if second_status!='not-observed':
        observation={'schema':'cat-effect-observation/v1','rule_id':'rule',
                     'outcome_index':1,'effect_target':'state.flag',
                     'execution_id':'run1','reported_status':second_status,
                     'correlation':dict(A)}
        content=json.dumps(observation,sort_keys=True).encode()
        (root/'obs2.json').write_bytes(content)
        second.update(observation_file='obs2.json',
                      observation_sha256=hashlib.sha256(content).hexdigest())
    packet['observations'].append(second)
    return raw,packet


class ExternalEffectRunCorrelationTests(unittest.TestCase):
    def test_same_execution_two_targets_matching_correlation_is_consistent(self):
        with tempfile.TemporaryDirectory() as t:
            raw,packet=two_targets(Path(t))
            result=evidence.inspect(raw,packet,DRIVER,t)
            self.assertEqual(result['status'],'consistent-receipts-only')
            self.assertEqual(len(result['receipts']),2)
            self.assertEqual(result['normative_status'],'inconclusive')

    def test_same_execution_disjoint_transactions_are_rejected_even_with_updated_observation_sha(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);raw,packet=two_targets(root)
            second=packet['observations'][1]
            second['correlation']=dict(B)
            observed=json.loads((root/'obs2.json').read_bytes())
            observed['correlation']=dict(B)
            content=json.dumps(observed,sort_keys=True).encode()
            (root/'obs2.json').write_bytes(content)
            second['observation_sha256']=hashlib.sha256(content).hexdigest()
            with self.assertRaisesRegex(evidence.ReceiptError,'execution correlation'):
                evidence.inspect(raw,packet,DRIVER,root)

    def test_unobserved_effect_cannot_claim_different_transaction_for_same_run(self):
        with tempfile.TemporaryDirectory() as t:
            raw,packet=two_targets(Path(t),second_status='not-observed')
            packet['observations'][1]['correlation']=dict(B)
            with self.assertRaisesRegex(evidence.ReceiptError,'execution correlation'):
                evidence.inspect(raw,packet,DRIVER,t)

    def test_declared_correlation_cannot_be_dropped_on_second_effect_of_same_run(self):
        with tempfile.TemporaryDirectory() as t:
            raw,packet=two_targets(Path(t),second_status='not-observed')
            del packet['observations'][1]['correlation']
            with self.assertRaisesRegex(evidence.ReceiptError,'execution correlation'):
                evidence.inspect(raw,packet,DRIVER,t)

    def test_distinct_runs_are_allowed_distinct_transactions(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);raw,packet=two_targets(root)
            second=packet['observations'][1]
            second['execution_id']='run2';second['correlation']=dict(B)
            observed=json.loads((root/'obs2.json').read_bytes())
            observed['execution_id']='run2';observed['correlation']=dict(B)
            content=json.dumps(observed,sort_keys=True).encode()
            (root/'obs2.json').write_bytes(content)
            second['observation_sha256']=hashlib.sha256(content).hexdigest()
            result=evidence.inspect(raw,packet,DRIVER,root)
            self.assertEqual(result['status'],'consistent-receipts-only')
            self.assertEqual(len(result['receipts']),2)

    def test_multiple_legacy_receipts_with_no_declared_correlation_remain_accepted(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);raw,packet=two_targets(root)
            for i,entry in enumerate(packet['observations']):
                del entry['correlation']
                name='obs.json' if i==0 else 'obs2.json'
                observed=json.loads((root/name).read_bytes())
                del observed['correlation']
                content=json.dumps(observed,sort_keys=True).encode()
                (root/name).write_bytes(content)
                entry['observation_sha256']=hashlib.sha256(content).hexdigest()
            result=evidence.inspect(raw,packet,DRIVER,root)
            self.assertEqual(result['status'],'consistent-receipts-only')
            self.assertEqual(result['normative_status'],'inconclusive')


if __name__=='__main__':unittest.main()
