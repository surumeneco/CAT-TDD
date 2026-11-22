"""U03/U06: an internally consistent Compiler result is not independent Source proof."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.cat-system' / 'scripts'))
import cat_flow
from test_intrinsic_rule_proofs import build


class ProcessClosureSourceConformanceTests(unittest.TestCase):
    def _gate(self, mutation=None, *, free_text=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kwargs = ({'requirement': 'Send the correct message to the external system',
                       'verification': 'external-delivery-verifier/v1'} if free_text else {})
            process, pi, tce, rule = build(root, **kwargs)
            work = {'id': 'demo.work', 'scope': {'process_ids': ['demo.process']},
                    'compilation': {'process': process.name, 'pi': pi.name,
                                    'tce': tce.name, 'common_rules': [rule.name],
                                    'allow_partial': True, 'allow_draft': False}}
            workfile = root / 'Work.json'
            workfile.write_text(json.dumps(work), encoding='utf-8')
            original_run = subprocess.run
            def intercepted_run(argv, **args):
                result = original_run(argv, **args)
                if (mutation is not None and result.returncode == 0
                        and any(str(a).endswith('cat_compile_v2.py') for a in argv)
                        and 'model' in argv and '-o' in argv):
                    model_file = Path(argv[argv.index('-o') + 1])
                    model = json.loads(model_file.read_text(encoding='utf-8'))
                    mutation(model)
                    model_file.write_text(json.dumps(model, ensure_ascii=False), encoding='utf-8')
                return result
            with patch.object(cat_flow.subprocess, 'run', side_effect=intercepted_run):
                return cat_flow.conformance_work(workfile, work, 'process-closure')

    def test_unchanged_intrinsic_source_still_passes(self):
        result = self._gate()
        self.assertEqual(result['status'], 'passed', result)
        self.assertTrue(result.get('source_model_evidence'))

    def test_source_conformant_partial_model_is_inconclusive_not_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            process, pi, tce, rule = build(root)
            process.write_text(process.read_text(encoding='utf-8').replace(
                'Closed world: true', 'Closed world: false'), encoding='utf-8')
            tce.write_text(tce.read_text(encoding='utf-8').replace(
                'Coverage requirement: closed', 'Coverage requirement: partial'),
                encoding='utf-8')
            work = {'id': 'demo.partial', 'scope': {'process_ids': ['demo.process']},
                    'compilation': {'process': process.name, 'pi': pi.name,
                                    'tce': tce.name, 'common_rules': [rule.name],
                                    'allow_partial': True, 'allow_draft': False}}
            path = root / 'Work.json'
            path.write_text(json.dumps(work), encoding='utf-8')
            verdict = cat_flow.conformance_work(path, work, 'process-closure')
            self.assertEqual(verdict['status'], 'inconclusive', verdict)
            source_receipt = root / '.cat-flow/cache/process-closure-source-model.json'
            self.assertEqual(json.loads(source_receipt.read_text(encoding='utf-8'))['status'], 'passed')

    def test_rehashed_intrinsic_rule_requirement_is_rejected(self):
        def tamper(model):
            model['rule_obligations'][0]['requirement'] = '@cat:invented-property/v1'
        result = self._gate(tamper)
        self.assertEqual(result['status'], 'blocked', result)
        self.assertIn('source', result['reason'].lower())

    def test_rehashed_intrinsic_certificate_is_rejected(self):
        def tamper(model):
            model['intrinsic_rule_proofs'][0]['source_sha256'] = '0' * 64
        result = self._gate(tamper)
        self.assertEqual(result['status'], 'blocked', result)
        self.assertIn('source', result['reason'].lower())

    def test_rehashed_free_text_cannot_be_marked_dischargeable(self):
        def tamper(model):
            model['unverified_rule_ids'] = []
            model['rule_obligations'][0]['verification_status'] = 'intrinsic-proved'
        result = self._gate(tamper, free_text=True)
        self.assertEqual(result['status'], 'blocked', result)
        self.assertIn('source', result['reason'].lower())

    def test_corrupted_coverage_evidence_is_rejected(self):
        def tamper(model):
            model['coverage_checks']['submit']['guard_refs'].append('invented.guard')
        result = self._gate(tamper)
        self.assertEqual(result['status'], 'blocked', result)
        self.assertIn('source', result['reason'].lower())


if __name__ == '__main__':
    unittest.main()
