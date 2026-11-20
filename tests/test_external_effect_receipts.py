"""UP20-06: independent receipt identity, no synthetic external proof."""
from __future__ import annotations
import hashlib,json,sys,tempfile,unittest,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
import cat_external_effect_receipts as evidence
SHA='a'*64
DRIVER=b'actual executable source here\n'

def inputs(root,reported_status='succeeded'):
    model={'schema':'cat-test-model/v2','process':'demo',
           'source_records':[{'id':'demo.tce','kind':'tce','sha256':SHA}],
           'rules':[{'id':'rule','source_artifact':'demo.tce','allowed':[
               {'write':[{'target':'action.reload','expr':{'literal':True}}]},
               {'write':[{'target':'action.keep','expr':{'literal':True}}]}]}]}
    raw=json.dumps(model,sort_keys=True).encode()
    obs={'schema':'cat-effect-observation/v1','rule_id':'rule','outcome_index':1,
         'effect_target':'action.reload','execution_id':'run1',
         'reported_status':reported_status}
    obs_raw=json.dumps(obs,sort_keys=True).encode()
    (root/'obs.json').write_bytes(obs_raw)
    packet={'schema':'cat-external-effect-receipts/v1',
            'model_sha256':hashlib.sha256(raw).hexdigest(),
            'source_sha256':{'demo.tce':SHA},
            'driver_sha256':hashlib.sha256(DRIVER).hexdigest(),
            'implementation_head':'b'*40,
            'observations':[{'rule_id':'rule','outcome_index':1,
                             'effect_target':'action.reload','execution_id':'run1',
                             'reported_status':reported_status,
                             'observation_file':'obs.json',
                             'observation_sha256':hashlib.sha256(obs_raw).hexdigest()}]}
    return raw,packet

class ExternalEvidenceTests(unittest.TestCase):
    def test_matching_receipt_remains_non_normative(self):
        with tempfile.TemporaryDirectory() as t:
            raw,packet=inputs(Path(t));r=evidence.inspect(raw,packet,DRIVER,t)
            self.assertEqual(r['status'],'consistent-receipts-only')
            self.assertEqual(r['normative_status'],'inconclusive')
            self.assertEqual(r['external_effect_proof'],'not-run')
            self.assertFalse(r['implementation_head_checkout_verified'])
    def test_unknown_outcome_is_not_success(self):
        with tempfile.TemporaryDirectory() as t:
            raw,packet=inputs(Path(t),'unknown');r=evidence.inspect(raw,packet,DRIVER,t)
            self.assertEqual(r['status'],'inconclusive')
            self.assertEqual(r['unresolved'][0]['reason'],'unknown')
    def test_not_observed_is_not_forged_observation(self):
        with tempfile.TemporaryDirectory() as t:
            raw,packet=inputs(Path(t));e=packet['observations'][0]
            e.update(reported_status='not-observed',observation_file=None,observation_sha256=None)
            r=evidence.inspect(raw,packet,DRIVER,t)
            self.assertEqual(r['status'],'inconclusive')
    def test_observation_correlation_agrees_with_declared_receipt(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);raw,packet=inputs(root)
            ids={'request_id':'req-7','transaction_id':'tx-3','target_id':'object-9'}
            packet['observations'][0]['correlation']=dict(ids)
            observed=json.loads((root/'obs.json').read_bytes())
            observed['correlation']=dict(ids)
            content=json.dumps(observed,sort_keys=True).encode()
            (root/'obs.json').write_bytes(content)
            packet['observations'][0]['observation_sha256']=hashlib.sha256(content).hexdigest()
            result=evidence.inspect(raw,packet,DRIVER,root)
            self.assertEqual(result['status'],'consistent-receipts-only')
            self.assertEqual(result['normative_status'],'inconclusive')
            self.assertEqual(result['provider_authentication_status'],'not-run')

    def test_observation_correlation_cannot_rebind_transaction_even_with_current_sha(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);raw,packet=inputs(root)
            packet['observations'][0]['correlation']={
                'request_id':'req-7','transaction_id':'tx-3','target_id':'object-9'}
            observed=json.loads((root/'obs.json').read_bytes())
            observed['correlation']={
                'request_id':'req-7','transaction_id':'tx-other','target_id':'object-9'}
            content=json.dumps(observed,sort_keys=True).encode()
            (root/'obs.json').write_bytes(content)
            packet['observations'][0]['observation_sha256']=hashlib.sha256(content).hexdigest()
            with self.assertRaisesRegex(evidence.ReceiptError,'observation correlation'):
                evidence.inspect(raw,packet,DRIVER,root)

    def test_observation_explicit_correlation_requires_receipt_identity(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);raw,packet=inputs(root)
            observed=json.loads((root/'obs.json').read_bytes())
            observed['correlation']={
                'request_id':'req-7','transaction_id':'tx-3','target_id':'object-9'}
            content=json.dumps(observed,sort_keys=True).encode()
            (root/'obs.json').write_bytes(content)
            packet['observations'][0]['observation_sha256']=hashlib.sha256(content).hexdigest()
            with self.assertRaisesRegex(evidence.ReceiptError,'observation correlation'):
                evidence.inspect(raw,packet,DRIVER,root)

    def test_malformed_observation_correlation_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);raw,packet=inputs(root)
            observed=json.loads((root/'obs.json').read_bytes())
            observed['correlation']={'request_id':'req-7','transaction_id':''}
            content=json.dumps(observed,sort_keys=True).encode()
            (root/'obs.json').write_bytes(content)
            packet['observations'][0]['observation_sha256']=hashlib.sha256(content).hexdigest()
            with self.assertRaisesRegex(evidence.ReceiptError,'observation correlation'):
                evidence.inspect(raw,packet,DRIVER,root)

    def test_observation_outcome_index_preserves_json_integer_identity(self):
        # A hashed observation containing true or 1.0 cannot attest to
        # Allowed Outcome 1, even though Python compares them equal to 1.
        for invalid in (True, 1.0, False, 0.0, "1", None):
            with self.subTest(outcome_index=repr(invalid)), tempfile.TemporaryDirectory() as t:
                root = Path(t)
                raw, packet = inputs(root)
                observed = json.loads((root/'obs.json').read_bytes())
                observed['outcome_index'] = invalid
                content = json.dumps(observed, sort_keys=True).encode()
                (root/'obs.json').write_bytes(content)
                packet['observations'][0]['observation_sha256'] = hashlib.sha256(content).hexdigest()
                with self.assertRaisesRegex(evidence.ReceiptError, 'outcome_index'):
                    evidence.inspect(raw, packet, DRIVER, root)

    def test_wrong_source_or_model_sha_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            raw,packet=inputs(Path(t));packet['source_sha256']['demo.tce']='c'*64
            with self.assertRaisesRegex(evidence.ReceiptError,'Source identity'):
                evidence.inspect(raw,packet,DRIVER,t)
            packet['source_sha256']['demo.tce']=SHA
            packet['model_sha256']='0'*64
            with self.assertRaisesRegex(evidence.ReceiptError,'Model SHA'):
                evidence.inspect(raw,packet,DRIVER,t)
    def test_driver_change_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            raw,packet=inputs(Path(t))
            with self.assertRaisesRegex(evidence.ReceiptError,'Driver SHA'):
                evidence.inspect(raw,packet,DRIVER+b'x',t)
    def test_wrong_outcome_or_unlisted_effect_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            raw,packet=inputs(Path(t));packet['observations'][0]['outcome_index']=2
            with self.assertRaisesRegex(evidence.ReceiptError,'Effect target not declared'):
                evidence.inspect(raw,packet,DRIVER,t)
    def test_unexpected_reload_target_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            raw,packet=inputs(Path(t));packet['observations'][0]['effect_target']='action.disallowed'
            with self.assertRaisesRegex(evidence.ReceiptError,'Effect target not declared'):
                evidence.inspect(raw,packet,DRIVER,t)
    def test_wrong_execution_in_observation_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);raw,packet=inputs(root);data=json.loads((root/'obs.json').read_bytes())
            data['execution_id']='other-run';obs=json.dumps(data,sort_keys=True).encode()
            (root/'obs.json').write_bytes(obs)
            packet['observations'][0]['observation_sha256']=hashlib.sha256(obs).hexdigest()
            with self.assertRaisesRegex(evidence.ReceiptError,'execution_id'):
                evidence.inspect(raw,packet,DRIVER,t)
    def test_duplicate_observation_does_not_create_double_evidence(self):
        with tempfile.TemporaryDirectory() as t:
            raw,packet=inputs(Path(t));packet['observations'].append(dict(packet['observations'][0]))
            with self.assertRaisesRegex(evidence.ReceiptError,'duplicate observation'):
                evidence.inspect(raw,packet,DRIVER,t)
    def test_checkout_proves_driver_blob_identity_not_external_effect(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);repo=root/'repository';repo.mkdir()
            def git(*argv):
                return subprocess.run(['git','-C',str(repo),*argv],check=True,
                                      capture_output=True,text=True).stdout.strip()
            git('init','-q')
            (repo/'runner.py').write_bytes(DRIVER)
            git('add','runner.py')
            git('-c','user.email=tests@example.org','-c','user.name=CAT Test',
                'commit','-qm','pin runner')
            head=git('rev-parse','HEAD')
            raw,packet=inputs(root);packet['implementation_head']=head
            result=evidence.inspect(raw,packet,DRIVER,root,repo,'runner.py')
            self.assertTrue(result['implementation_head_checkout_verified'])
            self.assertEqual(result['external_effect_proof'],'not-run')
            self.assertEqual(result['provider_authentication_status'],'not-run')
            packet['implementation_head']='0'*40
            with self.assertRaisesRegex(evidence.ReceiptError,'HEAD'):
                evidence.inspect(raw,packet,DRIVER,root,repo,'runner.py')
            packet['implementation_head']=head
            (repo/'runner.py').write_bytes(DRIVER+b'changed')
            with self.assertRaisesRegex(evidence.ReceiptError,'Driver bytes'):
                evidence.inspect(raw,packet,DRIVER,root,repo,'runner.py')
            with self.assertRaisesRegex(evidence.ReceiptError,'root and driver'):
                evidence.inspect(raw,packet,DRIVER,root,repo,None)

    def test_stale_fixture_file_or_path_traversal_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);raw,packet=inputs(root);(root/'obs.json').write_text('{}')
            with self.assertRaisesRegex(evidence.ReceiptError,'observation file SHA'):
                evidence.inspect(raw,packet,DRIVER,t)
            packet['observations'][0]['observation_file']='../secret.json'
            with self.assertRaisesRegex(evidence.ReceiptError,'observation path'):
                evidence.inspect(raw,packet,DRIVER,t)
if __name__=='__main__':unittest.main()
