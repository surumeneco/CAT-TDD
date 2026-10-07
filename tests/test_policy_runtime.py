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
        self.assertEqual(set(flows),{'spec-implementation','issue-work','code-to-spec','refactor'})
        self.assertNotIn('refactor',flows['spec-implementation']['stages'])
        self.assertIn('intake',flows['issue-work']['stages'])
        self.assertIn('spec',flows['issue-work']['stages'])
        self.assertIn('spec-closure',flows['issue-work']['stages'])


    def test_non_implementation_issue_can_complete_without_tdd(self):
        handoff=self.routing['flows']['issue-work']['handoff_by_work_kind']
        self.assertEqual(handoff['analysis'],'complete-in-flow')
        self.assertEqual(handoff['documentation'],'complete-in-flow')
        self.assertEqual(handoff['verification'],'complete-in-flow')

    def test_code_to_spec_cannot_write_production_source(self):
        reverse=self.routing['stages']['reverse']['permissions']
        self.assertNotIn('repo:production',reverse['write'])
        self.assertIn('production-source',reverse['prohibited'])


    def test_deterministic_stages_do_not_invoke_agents_by_default(self):
        for stage in ('process-closure','model','model-conformance','vectors','queue','tests','red','green','queue-state','implementation-conformance','refactor-baseline','regression','git'):
            self.assertNotEqual(self.routing['stages'][stage]['executor']['type'],'agent')
        self.assertEqual(self.routing['stages']['implementation']['executor']['id'],'tdd-implementer')

    def test_reviewers_are_conditional_on_inconclusive(self):
        expected={'process-closure':'cat-reviewer','model-conformance':'cat-model-reviewer',
                  'test-review':'tdd-reviewer','red':'tdd-checker',
                  'implementation-conformance':'cat-implementation-reviewer','git':'cycle-git-manager'}
        for stage,agent in expected.items():
            self.assertEqual(self.routing['stages'][stage]['conditional']['inconclusive']['id'],agent)

    def test_queue_state_and_refactor_baseline_are_connected(self):
        spec=self.routing['flows']['spec-implementation']['stages']
        self.assertEqual(spec[spec.index('green')+1],'queue-state')
        self.assertEqual(self.routing['stages']['queue-state']['executor']['type'],'script')
        self.assertEqual(self.routing['stages']['queue-state']['on_result']['passed'],'result.next_stage')
        self.assertEqual(set(self.routing['stages']['queue-state']['result_next_stage']['allowed']),
                         {'tests','implementation-conformance'})
        ref=self.routing['flows']['refactor']['stages']
        self.assertEqual(ref,['refactor-scope','refactor-baseline','refactor','regression'])

    def test_removed_specification_flow_has_no_dangling_transition(self):
        self.assertNotIn('specification',self.routing['flows'])
        for stage in ('implementation','refactor-scope','refactor'):
            self.assertNotEqual(self.routing['stages'][stage]['on_result'].get('decision-required'),'specification')
            self.assertEqual(self.routing['stages'][stage]['on_result'].get('decision-required'),'normative-authority')

    def test_promotion_is_authority_not_agent(self):
        self.assertEqual(self.routing['stages']['promotion']['executor']['type'],'authority')
        self.assertIn('normative-promotion',self.routing['stages']['promotion']['permissions']['authority'])

    def test_orchestrator_has_no_artifact_write_authority(self):
        text=(RUNTIME/'agents'/'orchestrator.agent.md').read_text(encoding='utf-8')
        self.assertIn('直接変更しない',text)
        self.assertIn('permission broker',text)

if __name__=='__main__': unittest.main()
