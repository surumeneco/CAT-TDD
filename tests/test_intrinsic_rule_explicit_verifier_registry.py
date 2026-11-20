"""U03/U06: submitted Rule verifier evidence is not skipped by intrinsic proof."""
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


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class IntrinsicRuleExplicitVerifierRegistryTests(unittest.TestCase):
    def _exercise(self, *, assertion_expected=True, invalid_hash=False, unknown_rule=False,
                  no_runner=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            process, pi, tce, rule = build(root)
            work = {
                'id': 'demo.work', 'scope': {'process_ids': ['demo.process']},
                'compilation': {
                    'process': process.name, 'pi': pi.name,
                    'tce': tce.name, 'common_rules': [rule.name],
                    'allow_partial': True, 'allow_draft': False,
                },
            }
            workpath = root / 'Work.json'
            workpath.write_text(json.dumps(work), encoding='utf-8')
            baseline = cat_flow.conformance_work(workpath, work, 'process-closure')
            self.assertEqual(baseline['status'], 'passed', baseline)
            model_path = root / '.cat-flow/cache/process-closure.model.json'
            model = json.loads(model_path.read_bytes())
            self.assertEqual(model['unverified_rule_ids'], [])
            self.assertEqual(model['intrinsic_rule_proofs'][0]['rule_id'], 'demo.rule.check')
            raw = b'{"ok":true}'
            (root / 'fixture.json').write_bytes(raw)
            runner = ("import hashlib,json,sys\n"
                      "data=open(sys.argv[1],'rb').read()\n"
                      "print(json.dumps({'schema':'cat-verifier-observation/v1',"
                      "'rule_id':'demo.rule.check','subject':'static',"
                      "'fixture_sha256':hashlib.sha256(data).hexdigest(),"
                      "'observed':json.loads(data)}))\n")
            (root / 'runner.py').write_bytes(runner.encode('utf-8'))
            entry = {
                'rule_id': 'demo.rule.nonexistent' if unknown_rule else 'demo.rule.check',
                'source_artifact': model['rule_obligations'][0]['source_artifact'],
                'source_sha256': model['normative_rule_inputs'][0]['sha256'],
                'subject': 'static', 'verifier_id': 'synthetic-optional-fixture',
                'fixture': {'path': 'fixture.json', 'sha256': digest(raw)},
                'assertions': [{'id': 'ok', 'path': 'ok', 'op': 'eq',
                                'expected': assertion_expected}],
            }
            if not no_runner:
                entry['runner'] = {'type': 'python-json-v1', 'path': 'runner.py',
                                   'sha256': digest(runner.encode('utf-8'))}
            registry = {'schema': 'cat-verifier-registry/v1',
                        'model_sha256': '0'*64 if invalid_hash else digest(model_path.read_bytes()),
                        'entries': [entry]}
            (root / 'registry.json').write_text(json.dumps(registry), encoding='utf-8')
            work['compilation']['verifier_registry'] = 'registry.json'
            workpath.write_text(json.dumps(work), encoding='utf-8')
            verdict = cat_flow.conformance_work(workpath, work, 'process-closure')
            receipt_file = root / '.cat-flow/cache/process-closure-verifiers.json'
            return verdict, json.loads(receipt_file.read_bytes()) if receipt_file.exists() else None

    def test_submitted_failure_blocks_even_when_intrinsic_rule_is_proved(self):
        verdict, receipt = self._exercise(assertion_expected=False)
        self.assertEqual(verdict['status'], 'blocked', verdict)
        self.assertEqual(receipt['status'], 'failed')
        self.assertEqual(receipt['normative_status'], 'inconclusive')

    def test_submitted_stale_registry_is_rejected_even_when_all_rules_intrinsic(self):
        verdict, _ = self._exercise(invalid_hash=True)
        self.assertEqual(verdict['status'], 'blocked', verdict)
        self.assertIn('hash mismatch', verdict['reason'])

    def test_submitted_unknown_rule_is_rejected_even_when_all_rules_intrinsic(self):
        verdict, _ = self._exercise(unknown_rule=True)
        self.assertEqual(verdict['status'], 'blocked', verdict)
        self.assertIn('unknown rule', verdict['reason'])

    def test_valid_optional_fixture_does_not_replace_intrinsic_proof(self):
        verdict, receipt = self._exercise(assertion_expected=True)
        self.assertEqual(verdict['status'], 'passed', verdict)
        self.assertEqual(receipt['status'], 'passed')
        self.assertEqual(receipt['normative_status'], 'inconclusive')
        self.assertIsNotNone(verdict.get('verifier_evidence'))

    def test_unrun_optional_fixture_does_not_erase_intrinsic_proof(self):
        verdict, receipt = self._exercise(no_runner=True)
        self.assertEqual(verdict['status'], 'passed', verdict)
        self.assertEqual(receipt['status'], 'inconclusive')
        self.assertEqual(receipt['results'][0]['status'], 'not-run')
        self.assertEqual(receipt['normative_status'], 'inconclusive')


if __name__ == '__main__':
    unittest.main()
