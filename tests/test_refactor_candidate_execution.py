"""Independent refactor controls: candidate evidence does not authorize normative TDD.

The small JUnit-XML fixture tests routing and evidence parsing only; it is not
product-level JUnit proof. Production refactors still require a fresh baseline,
unchanged regression oracle and a scope-limited write guard.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.cat-system' / 'scripts'))
import cat_flow as flow


def fixture_check(stage):
    xml = '<testsuites><testsuite tests="1"><testcase classname="example" name="preserved" /></testsuite></testsuites>'
    script = 'from pathlib import Path;import sys;Path(sys.argv[1]).write_text(' + repr(xml) + ')'
    return {
        'id': stage, 'stage': stage, 'runner': 'junit', 'cwd': '@work',
        'argv': [sys.executable, '-c', script, '{report}'], 'test_ids': ['preserved']
    }


class IndependentRefactorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'work.json'
        self.work = {
            'schema': 'cat-work/v1', 'id': 'refactor.independent.test',
            'entry': 'refactor', 'mode': 'implementation',
            'flow': 'refactor', 'work_kind': 'refactor',
            'issue_ref': 'existing-behavior', 'project_entry_ref': 'source-commit',
            'normative': [{'uri': 'existing-source-contract'}],
            'evidence': [{'uri': 'unchanged-junit-oracle'}],
            'specification': {
                'status': 'candidate', 'decision_ref': None, 'artifact_refs': []
            },
            'scope': {
                'process_ids': ['coin.lookup'], 'changed_ids': [],
                'preserved_ids': ['coin.value']
            },
            'technologies': [], 'repositories': [],
            'checks': [fixture_check('refactor-baseline'), fixture_check('regression')],
            'gates': []
        }
        self.save()

    def save(self):
        self.path.write_bytes(flow.json_bytes(self.work))

    def test_candidate_refactor_baseline_uses_junit_evidence(self):
        self.assertEqual(flow.validate(self.work), [])
        result = flow.command_work(self.path, self.work, 'refactor-baseline', True)
        self.assertEqual(result['verdict'], 'passed')
        self.assertEqual(result['observed_targets'], {'preserved': 'passed'})

    def test_candidate_refactor_regression_uses_junit_evidence(self):
        self.assertEqual(flow.command_work(self.path, self.work, 'regression', True)['verdict'], 'passed')

    def test_candidate_refactor_guard_checks_current_source(self):
        (self.path.parent / 'source.txt').write_text('unchanged', encoding='utf-8')
        self.assertEqual(
            flow.command_work(self.path, self.work, 'refactor-baseline', True)['verdict'], 'passed'
        )
        handoff = flow.handoff_work(self.path, self.work, 'refactor')
        self.assertEqual(handoff['guard']['status'], 'passed')
        self.assertEqual(flow.guard_work(self.path, self.work, 'refactor', 'finish')['status'], 'passed')
        (self.path.parent / 'source.txt').write_text('stale', encoding='utf-8')
        with self.assertRaisesRegex(flow.Blocked, 'baseline is stale'):
            flow.handoff_work(self.path, self.work, 'refactor')

    def test_red_green_still_require_confirmed_specification(self):
        for stage in ('red', 'green'):
            self.work['checks'] = [fixture_check(stage)]
            self.save()
            with self.assertRaisesRegex(flow.Blocked, 'confirmed specification'):
                flow.command_work(self.path, self.work, stage, True)

    def test_nonrefactor_flow_cannot_use_refactor_stages(self):
        self.work['flow'] = 'issue-work'
        self.work['entry'] = 'issue'
        self.save()
        for stage in ('refactor-baseline', 'regression'):
            with self.assertRaisesRegex(flow.Blocked, 'refactor flow'):
                flow.command_work(self.path, self.work, stage, True)

    def test_shadow_work_remains_nonexecutable(self):
        self.work['mode'] = 'shadow'
        self.save()
        with self.assertRaisesRegex(flow.Blocked, 'shadow Work'):
            flow.command_work(self.path, self.work, 'refactor-baseline', True)


if __name__ == '__main__':
    unittest.main()
