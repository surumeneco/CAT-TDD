"""U06: registered verifier failures block the formal Gate without refuting free-text rules."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.cat-system' / 'scripts'))
import cat_flow
from test_intrinsic_rule_proofs import build


def sha(content):
    return hashlib.sha256(content).hexdigest()


class RuleVerifierClosureFailureTests(unittest.TestCase):
    def _gate(self, expected, with_runner=True):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            process, pi, tce, common = build(
                root, requirement='Record must be delivered to an external peer',
                verification='delivery-provider-verifier/v1')
            w = {'id': 'demo.work', 'scope': {'process_ids': ['demo.process']},
                 'compilation': {'process': process.name, 'pi': pi.name,
                                 'tce': tce.name, 'common_rules': [common.name],
                                 'allow_partial': True, 'allow_draft': False}}
            wp = root / 'Work.json'
            wp.write_text(json.dumps(w), encoding='utf-8')
            preliminary = cat_flow.conformance_work(wp, w, 'process-closure')
            self.assertEqual(preliminary['status'], 'inconclusive', preliminary)
            model_path = root / '.cat-flow' / 'cache' / 'process-closure.model.json'
            model_bytes = model_path.read_bytes()
            model = json.loads(model_bytes)
            rule = model['rule_obligations'][0]
            fixture_bytes = b'{"delivered":true}'
            (root / 'fixture.json').write_bytes(fixture_bytes)
            entry = {'rule_id': rule['id'], 'source_artifact': rule['source_artifact'],
                     'source_sha256': rule['source_sha256'] if rule.get('source_sha256') else model['normative_rule_inputs'][0]['sha256'],
                     'subject': 'discord', 'verifier_id': 'synthetic-fixture-checker',
                     'fixture': {'path': 'fixture.json', 'sha256': sha(fixture_bytes)},
                     'assertions': [{'id': 'delivered', 'path': 'delivered', 'op': 'eq',
                                     'expected': expected}]}
            if with_runner:
                script = ("import hashlib,json,sys\n"
                          "raw=open(sys.argv[1],'rb').read()\n"
                          "print(json.dumps({'schema':'cat-verifier-observation/v1',"
                          "'rule_id':'demo.rule.check','subject':'discord',"
                          "'fixture_sha256':hashlib.sha256(raw).hexdigest(),"
                          "'observed':json.loads(raw)}))\n")
                (root / 'runner.py').write_text(script, encoding='utf-8')
                entry['runner'] = {'type': 'python-json-v1', 'path': 'runner.py',
                                   'sha256': sha(script.encode())}
            registry = {'schema': 'cat-verifier-registry/v1',
                        'model_sha256': sha(model_bytes), 'entries': [entry]}
            (root / 'registry.json').write_text(json.dumps(registry), encoding='utf-8')
            w['compilation']['verifier_registry'] = 'registry.json'
            wp.write_text(json.dumps(w), encoding='utf-8')
            verdict = cat_flow.conformance_work(wp, w, 'process-closure')
            verifier_receipt = root / '.cat-flow' / 'cache' / 'process-closure-verifiers.json'
            self.assertTrue(verifier_receipt.is_file())
            receipt = json.loads(verifier_receipt.read_text(encoding='utf-8'))
            self.assertEqual(receipt['normative_status'], 'inconclusive')
            self.assertEqual(receipt['status'], 'failed' if expected is False else ('passed' if with_runner else 'inconclusive'))
            return verdict

    def test_registered_failed_assertion_blocks_formal_gate(self):
        verdict = self._gate(False)
        self.assertEqual(verdict['status'], 'blocked', verdict)
        self.assertIn('verifier', verdict['reason'].lower())
        self.assertIn('fixture', verdict['reason'].lower())

    def test_green_fixture_cannot_discharge_normative_rule(self):
        verdict = self._gate(True)
        self.assertEqual(verdict['status'], 'inconclusive', verdict)

    def test_unexecuted_verifier_remains_inconclusive_not_blocked(self):
        verdict = self._gate(True, with_runner=False)
        self.assertEqual(verdict['status'], 'inconclusive', verdict)


if __name__ == '__main__':
    unittest.main()
