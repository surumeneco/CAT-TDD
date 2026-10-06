from __future__ import annotations
import json, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'.cat-system'

class PolicyRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routing=json.loads((RUNTIME/'config'/'routing.json').read_text(encoding='utf-8'))

    def test_four_primary_flows_remain_independent(self):
        flows=self.routing['flows']
        for name in ('spec-implementation','issue-work','code-to-spec','refactor'):
            self.assertIn(name,flows)
        self.assertNotIn('refactor',flows['spec-implementation']['stages'])
        self.assertEqual(flows['issue-work']['stages'],['intake'])

    def test_deterministic_stages_do_not_invoke_agents_by_default(self):
        for stage in ('process-closure','model','model-conformance','queue','tests','red','green','implementation-conformance','regression','git'):
            self.assertNotEqual(self.routing['stages'][stage]['executor']['type'],'agent')
        self.assertEqual(self.routing['stages']['implementation']['executor']['id'],'tdd-implementer')

    def test_reviewers_are_conditional_on_inconclusive(self):
        expected={'process-closure':'cat-reviewer','model-conformance':'cat-model-reviewer',
                  'test-review':'tdd-reviewer','red':'tdd-checker',
                  'implementation-conformance':'cat-implementation-reviewer','git':'cycle-git-manager'}
        for stage,agent in expected.items():
            self.assertEqual(self.routing['stages'][stage]['conditional']['inconclusive']['id'],agent)

    def test_orchestrator_has_no_artifact_write_authority(self):
        text=(RUNTIME/'agents'/'orchestrator.agent.md').read_text(encoding='utf-8')
        self.assertIn('直接変更しない',text)
        self.assertIn('permission broker',text)

if __name__=='__main__': unittest.main()
