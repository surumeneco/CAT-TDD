from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.cat-system' / 'scripts'))
import cat_flow as flow


def base_work():
    return {
        'schema': 'cat-work/v1',
        'id': 'demo.conformance.work',
        'entry': 'confirmed-spec',
        'mode': 'implementation',
        'flow': 'spec-implementation',
        'work_kind': 'implementation',
        'parent': '',
        'depends_on': [],
        'issue_ref': 'spec-entry',
        'project_entry_ref': 'project-entry',
        'normative': [{'uri': 'spec'}],
        'evidence': [{'uri': 'evidence'}],
        'specification': {'status': 'confirmed', 'decision_ref': 'decision', 'artifact_refs': ['demo.tce']},
        'scope': {'process_ids': ['demo.process'], 'changed_ids': [], 'preserved_ids': []},
        'technologies': [],
        'repositories': [],
        'checks': [],
        'gates': [],
    }


class ConformanceRuntimeTest(unittest.TestCase):
    def write_work(self, root, work):
        path = root / 'work.json'
        path.write_bytes(flow.json_bytes(work))
        return path

    def test_declared_conformance_pass_is_not_accepted_without_machine_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work = base_work()
            work['gates'] = [{'id': 'process-closure', 'status': 'passed', 'evidence': 'review:claimed'}]
            path = self.write_work(root, work)
            status = flow.status_work(path, work)
            self.assertEqual(status['gates']['process-closure']['status'], 'not-run')

    def test_blocked_machine_gate_cannot_be_overridden_by_review_claim(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work = base_work()
            work['gates'] = [{'id': 'process-closure', 'status': 'passed', 'evidence': 'review:claimed'}]
            path = self.write_work(root, work)
            target = root / '.cat-flow' / 'conformance'
            target.mkdir(parents=True)
            (target / 'process-closure.json').write_bytes(flow.json_bytes({
                'schema': 'cat-conformance-evidence/v1',
                'work_id': work['id'],
                'gate': 'process-closure',
                'context_sha256': flow.conformance_context_sha(work),
                'input_sha256': {},
                'verdict': 'blocked',
                'reason': 'deterministic failure',
                'supporting_evidence': None,
            }))
            status = flow.status_work(path, work)
            self.assertEqual(status['gates']['process-closure']['status'], 'blocked')

    def test_inconclusive_machine_gate_may_be_closed_by_explicit_review(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work = base_work()
            work['gates'] = [{'id': 'process-closure', 'status': 'passed', 'evidence': 'review:independent'}]
            path = self.write_work(root, work)
            target = root / '.cat-flow' / 'conformance'
            target.mkdir(parents=True)
            (target / 'process-closure.json').write_bytes(flow.json_bytes({
                'schema': 'cat-conformance-evidence/v1',
                'work_id': work['id'],
                'gate': 'process-closure',
                'context_sha256': flow.conformance_context_sha(work),
                'input_sha256': {},
                'verdict': 'inconclusive',
                'reason': 'composition requires semantic review',
                'supporting_evidence': None,
            }))
            status = flow.status_work(path, work)
            self.assertEqual(status['gates']['process-closure']['status'], 'passed')
            self.assertEqual(status['gates']['process-closure']['deterministic_status'], 'inconclusive')

    def test_partial_local_tce_cannot_pass_process_closure_by_itself(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work = base_work()
            for name in ('Process.md', 'PI.md', 'TCE.md'):
                (root / name).write_text('placeholder', encoding='utf-8')
            work['compilation'] = {
                'schema': 'cat-compile/v2',
                'process': 'Process.md',
                'pi': 'PI.md',
                'tce': 'TCE.md',
                'model': 'Model.json',
                'allow_draft': False,
            }
            path = self.write_work(root, work)

            def fake_run(argv, **kwargs):
                out = Path(argv[argv.index('-o') + 1])
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps({
                    'coverage_requirement': 'partial',
                    'coverage_checks': {'submit': {'result': 'proved'}},
                }), encoding='utf-8')
                return SimpleNamespace(returncode=0, stdout='', stderr='')

            with patch.object(flow.subprocess, 'run', side_effect=fake_run):
                result = flow.conformance_work(path, work, 'process-closure')
            self.assertEqual(result['status'], 'inconclusive')
            self.assertIn('partial', result['reason'])

    def test_unmapped_common_rule_or_domain_spec_blocks_normative_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work = base_work()
            work['compilation'] = {
                'schema': 'cat-compile/v2',
                'process': 'Process.md',
                'pi': 'PI.md',
                'tce': 'TCE.md',
                'model': 'Model.md',
                'common_rules': ['CommonRule.md'],
                'domain_specs': ['DomainSpec.md'],
                'allow_draft': False,
            }
            path = self.write_work(root, work)
            result = flow.conformance_work(path, work, 'process-closure')
            self.assertEqual(result['status'], 'blocked')
            with self.assertRaisesRegex(flow.Blocked, 'CommonRule/DomainSpec'):
                flow.compile_work(path, work, 'model', False)


    def test_implementation_obligations_require_trace_and_method(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work = base_work()
            obligations = root / 'obligations.json'
            obligations.write_text(json.dumps({
                'schema': 'cat-implementation-obligations/v1',
                'items': [
                    {'category': category, 'status': 'passed', 'evidence': 'e:' + category}
                    for category in ('interface', 'capability', 'behavior', 'invariant',
                                     'cross-process', 'domain', 'implementation-constraint')
                ],
            }), encoding='utf-8')
            work['compilation'] = {
                'schema': 'cat-compile/v2',
                'process': 'Process.md',
                'pi': 'PI.md',
                'tce': 'TCE.md',
                'model': 'Model.md',
                'obligations': 'obligations.json',
                'allow_draft': False,
            }
            path = self.write_work(root, work)
            with self.assertRaisesRegex(flow.Blocked, 'source_ref'):
                flow.conformance_work(path, work, 'implementation-conformance')


if __name__ == '__main__':
    unittest.main()
