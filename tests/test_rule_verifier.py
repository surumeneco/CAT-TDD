#!/usr/bin/env python3
"""Trust-boundary regressions for rule-level deterministic verifier evidence."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
import cat_verifier_contracts as verifier

def sha(data):return hashlib.sha256(data).hexdigest()

class RuleVerifierTests(unittest.TestCase):
    def prepare(self,root,subject='static',runner=False):
        model={'schema':'cat-test-model/v2',
            'normative_rule_inputs':[{'id':'demo.spec','kind':'domain-spec','sha256':'a'*64}],
            'rule_obligations':[{'id':'demo.rule','source_artifact':'demo.spec',
                                 'verification_contract':'静的な構造検査' if subject=='static' else 'Discord配送確認'}]}
        model_path=root/'model.json'
        model_path.write_text(json.dumps(model),encoding='utf-8')
        fixture_data=b'{"message":{"delivered":true},"count":0}'
        fixture_path=root/'fixture.json'
        fixture_path.write_bytes(fixture_data)
        entry={'rule_id':'demo.rule','source_artifact':'demo.spec','source_sha256':'a'*64,
               'subject':subject,'verifier_id':'fixture-checker',
               'fixture':{'path':'fixture.json','sha256':sha(fixture_data)},
               'assertions':[{'id':'delivery','path':'message.delivered','op':'eq','expected':True}]}
        if runner:
            code="import json,sys,hashlib\np=sys.argv[1]\na=open(p,'rb').read()\nprint(json.dumps({'schema':'cat-verifier-observation/v1','rule_id':'demo.rule','subject':"+repr(subject)+",'fixture_sha256':hashlib.sha256(a).hexdigest(),'observed':json.loads(a)}))\n"
            (root/'runner.py').write_text(code,encoding='utf-8')
            entry['runner']={'type':'python-json-v1','path':'runner.py',
                             'sha256':sha(code.encode())}
        registry={'schema':verifier.SCHEMA,'model_sha256':sha(model_path.read_bytes()),'entries':[entry]}
        registry_path=root/'registry.json'
        registry_path.write_text(json.dumps(registry),encoding='utf-8')
        return model_path,registry_path

    def test_static_fixture_run_produces_traceable_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            model,registry=self.prepare(root,runner=True)
            result=verifier.evaluate(model,registry)
            self.assertEqual(result['status'],'passed')
            self.assertEqual(result['results'][0]['checks'][0]['status'],'passed')
            self.assertEqual(result['model_sha256'],sha(model.read_bytes()))

    def test_static_fixture_without_runner_is_not_execution_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            model,registry=self.prepare(Path(temp),'static')
            result=verifier.evaluate(model,registry)
            self.assertEqual(result['status'],'inconclusive')
            self.assertEqual(result['results'][0]['status'],'not-run')
            self.assertEqual(result['results'][0]['checks'],[])

    def test_external_verifier_without_runner_is_never_passed(self):
        with tempfile.TemporaryDirectory() as temp:
            model,registry=self.prepare(Path(temp),'discord')
            result=verifier.evaluate(model,registry)
            self.assertEqual(result['status'],'inconclusive')
            self.assertEqual(result['results'][0]['status'],'not-run')

    def test_external_runner_executes_and_binds_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            model,registry=self.prepare(Path(temp),'discord',True)
            result=verifier.evaluate(model,registry)
            self.assertEqual(result['status'],'passed')
            self.assertEqual(result['results'][0]['subject'],'discord')

    def test_external_runner_hash_tamper_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            model,registry=self.prepare(root,'discord',True)
            (root/'runner.py').write_text('print("forgery")',encoding='utf-8')
            with self.assertRaisesRegex(verifier.VerifierError,'hash mismatch'):
                verifier.evaluate(model,registry)

    def test_model_source_hash_mismatch_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            model,registry=self.prepare(root)
            data=json.loads(registry.read_text())
            data['entries'][0]['source_sha256']='0'*64
            registry.write_text(json.dumps(data))
            with self.assertRaisesRegex(verifier.VerifierError,'rule/source hash'):
                verifier.evaluate(model,registry)

    def test_missing_rule_registration_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as temp:
            model,registry=self.prepare(Path(temp))
            data=json.loads(registry.read_text());data['entries']=[]
            registry.write_text(json.dumps(data))
            result=verifier.evaluate(model,registry)
            self.assertEqual(result['status'],'inconclusive')
            self.assertEqual(result['results'][0]['status'],'not-run')

    def test_declared_external_action_cannot_be_proved_by_dom(self):
        with tempfile.TemporaryDirectory() as temp:
            model,registry=self.prepare(Path(temp),'dom')
            with self.assertRaisesRegex(verifier.VerifierError,'DOM verifier cannot'):
                verifier.evaluate(model,registry)

    def test_fixture_changes_are_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            model,registry=self.prepare(root)
            (root/'fixture.json').write_text('{"message":{"delivered":false}}')
            with self.assertRaisesRegex(verifier.VerifierError,'fixture hash mismatch'):
                verifier.evaluate(model,registry)

    def test_nested_presence_and_null_are_distinct(self):
        observed={'missing':{},'null':None,'zero':0,'false':False}
        self.assertEqual(verifier.assertion({'id':'m','path':'missing.a','op':'absent'},observed)['status'],'passed')
        self.assertEqual(verifier.assertion({'id':'n','path':'null','op':'eq','expected':None},observed)['status'],'passed')
        self.assertEqual(verifier.assertion({'id':'z','path':'zero','op':'eq','expected':False},observed)['status'],'failed')

    def test_path_escape_and_duplicate_assertions_block(self):
        with tempfile.TemporaryDirectory() as temp:
            model,registry=self.prepare(Path(temp))
            data=json.loads(registry.read_text())
            entry=data['entries'][0]
            entry['assertions'].append(entry['assertions'][0])
            registry.write_text(json.dumps(data))
            with self.assertRaisesRegex(verifier.VerifierError,'duplicate assertion'):
                verifier.evaluate(model,registry)

if __name__=='__main__':unittest.main()
