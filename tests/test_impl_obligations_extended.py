import sys,unittest,tempfile,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
import cat_implementation_obligations as impl
import cat_flow
from cat_compile_v2 import load

HEADER='''---
cat_version: '0.3'
kind: {kind}
id: {id}
status: confirmed
process: demo.process
source_refs:
  - https://example.org/contract
refs: {refs}
decision_ref: https://example.org/authorized-decision
semantic_contract: markdown-v2
language: en
---
'''

def write(root,name,kind,id,refs,body):
    path=root/name
    path.write_text(HEADER.format(kind=kind,id=id,refs=json.dumps(refs))+'\n'+body,encoding='utf8')
    return path

class TestObligations(unittest.TestCase):
 def setup(self,root):
  p=write(root,'Process.md','process','demo.process.spec',[],'''## Contract
Closed world: true
## Interfaces
| PI |
| --- |
| demo.process.first |
| demo.process.second |
## State
| ID | Domain |
| --- | --- |
| state.ready | boolean |
## Triggers
| ID | Origin |
| --- | --- |
| submit | demo.process.first |
''')
  a=write(root,'PIa.md','pi','demo.process.first',['demo.process.spec'],'''## Boundary
| Peer process | Direction |
| --- | --- |
| peer.first | bidirectional |
## Fields
| ID | Direction | Domain | Presence |
| --- | --- | --- | --- |
| input.ready | receive | boolean | required |
## Operations
| ID | Direction | Trigger |
| --- | --- | --- |
| op.first | accept | submit |
''')
  b=write(root,'PIb.md','pi','demo.process.second',['demo.process.spec'],'''## Boundary
| Peer process | Direction |
| --- | --- |
| peer.second | bidirectional |
## Fields
| ID | Direction | Domain | Presence |
| --- | --- | --- | --- |
| output.result | send | boolean | required |
## Operations
| ID | Direction | Trigger |
| --- | --- | --- |
| op.second | provide | submit |
''')
  t=write(root,'TCE.md','tce','demo.process.tce',['demo.process.first','demo.process.second'],'''Coverage requirement: partial
## Behaviors
| ID | Trigger | Condition | Outcome | Effects |
| --- | --- | --- | ---: | --- |
| demo.yes | submit | `input.ready` | 1 | `output.result = true` |
| demo.no | submit | `not input.ready` | 1 | `output.result = false` |
''')
  cr=write(root,'Common.md','common-rule','demo.process.common',[],'''## Rules
| ID | Condition | Requirement | Verification |
| --- | --- | --- | --- |
| demo.common.one | every call | maintain agreement | static protocol check |
''')
  ds=write(root,'Domain.md','domain-spec','demo.process.domains',[],'''## Rules
| ID | Condition | Requirement | Verification |
| --- | --- | --- | --- |
| demo.domain.two | response | preserve value | structural contract check |
''')
  return p,a,b,t,cr,ds
 def test_generate(self):
  with tempfile.TemporaryDirectory() as tmp:
   r=Path(tmp);p,a,b,t,cr,ds=self.setup(r)
   result=impl.generate(p,[a,b],[t],common_rules=[cr],domain_specs=[ds])
   ids={x['id'] for x in result['items']}
   self.assertIn('interface.op.first',ids)
   self.assertIn('interface.op.second',ids)
   self.assertIn('normative-rule.demo.common.one',ids)
   self.assertIn('normative-rule.demo.domain.two',ids)
   self.assertEqual(len([x for x in ids if x.startswith('cross-process.boundary')]),2)
   self.assertEqual(result['model_status'],'draft')
   self.assertEqual(len(result['unresolved_rule_ids']),2)
   pending=impl.aggregate(result,technology_results=[{'status':'passed'}],model_conformance={'status':'passed'})
   by={x['id']:x for x in pending['items']}
   self.assertEqual(by['normative-rule.demo.common.one']['status'],'inconclusive')
   self.assertEqual(by['cross-process.boundary.demo.process.first.peer.first']['status'],'inconclusive')
   self.assertEqual(by['normative-rule.demo.domain.two']['status'],'inconclusive')
 def test_non_deterministic_allowed_set_is_one_runtime_obligation_not_per_outcome_reachability(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p,a,b,t,cr,ds=self.setup(root)
   old='| demo.yes | submit | `input.ready` | 1 | `output.result = true` |'
   new=old+'\n| demo.yes | submit | `input.ready` | 2 | `output.result = false` |'
   data=t.read_text(encoding='utf-8')
   self.assertIn(old,data)
   t.write_text(data.replace(old,new),encoding='utf-8')
   doc=impl.generate(p,[a,b],[t])
   ids={x['id'] for x in doc['items']}
   self.assertIn('behavior.demo.yes',ids)
   self.assertIn('invariant.demo.yes.allowed-set',ids)
   self.assertNotIn('invariant.demo.yes.1',ids)
   self.assertNotIn('invariant.demo.yes.2',ids)
   frames=[x for x in doc['model_outcome_frames']
           if x['rule_id']=='demo.yes']
   self.assertEqual(len(frames),2)
   self.assertEqual([x['source_ref'].split(':outcome:')[1] for x in frames],['1','2'])
   # One Green for a selected input establishes only observed membership,
   # not that both allowed alternatives ever happened.
   observed=impl.aggregate(doc,
      verified_green={'demo.yes':['queue:observed-a']},
      model_conformance={'status':'passed','evidence':'model-source-proof'})
   by={x['id']:x for x in observed['items']}
   self.assertEqual(by['behavior.demo.yes']['status'],'passed')
   self.assertEqual(by['invariant.demo.yes.allowed-set']['status'],'passed')
   self.assertIn('allowed set',by['invariant.demo.yes.allowed-set']['limitation'])
   self.assertNotIn('invariant.demo.yes.2',by)
   self.assertTrue(all('status' not in frame and 'evidence' not in frame for frame in frames))
   without_model=impl.aggregate(doc,
      verified_green={'demo.yes':['queue:observed-a']})
   by={x['id']:x for x in without_model['items']}
   self.assertEqual(by['behavior.demo.yes']['status'],'passed')
   self.assertEqual(by['invariant.demo.yes.allowed-set']['status'],'inconclusive')
   unobserved=impl.aggregate(doc,model_conformance={'status':'passed'})
   by={x['id']:x for x in unobserved['items']}
   self.assertEqual(by['invariant.demo.yes.allowed-set']['status'],'inconclusive')
   legacy={'schema':doc['schema'],'source_sha256':doc['source_sha256'],
           'items':[impl.item('invariant.demo.yes.2','invariant',
                   'demo.process.tce#demo.yes:outcome:2','generated-test-frame')]}
   stale=impl.aggregate(legacy,verified_green={'demo.yes':['queue:observed-a']})
   self.assertEqual(stale['items'][0]['status'],'inconclusive')

 def test_shared_domain_rule_requires_ancestor_scope_and_explicit_references(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p,a,b,t,cr,ds=self.setup(root)
   dr=write(root,'shared.md','domain-rule','demo.shared',['demo.process'],
             """## Definitions
| ID | Parameters | Expression |
| --- | --- | --- |
| add_one | value | `value + 1` |
""")
   dr.write_text(dr.read_text().replace('process: demo.process','process: demo'))
   t.write_text(t.read_text().replace('"demo.process.second"]','"demo.process.second", "demo.shared"]'))
   doc=impl.generate(p,[a,b],[t],domain_path=dr,common_rules=[cr],domain_specs=[ds])
   self.assertIn('domain.add_one',{x['id'] for x in doc['items']})
   dr.write_text(dr.read_text().replace('["demo.process"]','[]'))
   with self.assertRaisesRegex(ValueError,'shared DomainRule must explicitly reference'):
    impl.generate(p,[a,b],[t],domain_path=dr,common_rules=[cr],domain_specs=[ds])

 def test_aggregator_needs_per_obligation_technology_coverage(self):
  with tempfile.TemporaryDirectory() as tmp:
   r=Path(tmp);p,a,b,t,cr,ds=self.setup(r)
   doc=impl.generate(p,[a,b],[t],common_rules=[cr],domain_specs=[ds])
   generic=impl.aggregate(doc,technology_results=[{'technology':'TypeScript','status':'passed'}],
                          model_conformance={'status':'passed'})
   by={x['id']:x for x in generic['items']}
   self.assertEqual(by['interface.op.first']['status'],'inconclusive')
   self.assertEqual(by['capability.closed-set']['status'],'inconclusive')
   self.assertEqual(by['cross-process.boundary.demo.process.first.peer.first']['status'],'inconclusive')
   focused=impl.aggregate(doc,technology_results=[{'technology':'TypeScript','status':'passed',
                               'covered_obligation_ids':['interface.op.first']}])
   lookup={x['id']:x for x in focused['items']}
   self.assertEqual(lookup['interface.op.first']['status'],'passed')
   self.assertEqual(lookup['interface.op.second']['status'],'inconclusive')

 def test_technology_constraint_needs_its_own_inspection_coverage(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);process,first,second,tce,cr,ds=self.setup(root)
   skeleton=impl.generate(process,[first,second],[tce],technologies=['TypeScript','JUnit'])
   constraints={x['id'] for x in skeleton['items'] if x['category']=='implementation-constraint'}
   self.assertEqual(constraints, {'implementation-constraint.typescript',
                                  'implementation-constraint.junit'})
   def statuses(evidence):
    evaluated=impl.aggregate(skeleton, technology_results=evidence)
    return {x['id']:x for x in evaluated['items']}
   # Passing public-interface inspection says nothing about language/runtime constraints.
   only_interface=statuses([{'technology':'TypeScript','status':'passed',
                             'covered_obligation_ids':['interface.op.first']}])
   for cid in constraints:
    self.assertEqual(only_interface[cid]['status'],'inconclusive',cid)
   # Even a matching technology with a globally passed inspector needs exact coverage.
   no_coverage=statuses([{'technology':'TypeScript','status':'passed','checks':[]}])
   self.assertEqual(no_coverage['implementation-constraint.typescript']['status'],
                    'inconclusive')
   # Only an inspector explicitly naming the matching obligation may discharge it.
   focused=statuses([{'technology':'TypeScript','status':'passed',
                      'covered_obligation_ids':['implementation-constraint.typescript']},
                     {'technology':'JUnit','status':'inconclusive',
                      'covered_obligation_ids':['implementation-constraint.junit']}])
   self.assertEqual(focused['implementation-constraint.typescript']['status'],'passed')
   self.assertEqual(focused['implementation-constraint.junit']['status'],'inconclusive')
   # An unrelated inspector cannot claim a different technology's constraint.
   cross=statuses([{'technology':'TypeScript','status':'passed',
                    'covered_obligation_ids':['implementation-constraint.junit']}])
   self.assertEqual(cross['implementation-constraint.junit']['status'],'inconclusive')

 def test_rule_aggregator_requires_source_and_matching_result(self):
  with tempfile.TemporaryDirectory() as tmp:
   r=Path(tmp);p,a,b,t,cr,ds=self.setup(r)
   doc=impl.generate(p,[a,b],[t],common_rules=[cr],domain_specs=[ds])
   evidence={'status':'passed','results':[{'rule_id':'demo.common.one',
         'source_artifact':'demo.process.common','status':'passed'}]}
   result=impl.aggregate(doc,rule_verification=evidence)
   by={x['id']:x for x in result['items']}
   self.assertEqual(by['normative-rule.demo.common.one']['status'],'inconclusive')
   self.assertEqual(by['normative-rule.demo.domain.two']['status'],'inconclusive')
   evidence['results'][0]['source_artifact']='unrelated.contract'
   result=impl.aggregate(doc,rule_verification=evidence)
   by={x['id']:x for x in result['items']}
   self.assertEqual(by['normative-rule.demo.common.one']['status'],'inconclusive')

 def test_intrinsic_proof_requires_fresh_model_conformance_and_source_sha(self):
  from test_intrinsic_rule_proofs import build
  from test_intrinsic_rule_proofs import PROOF
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p,pi,t,rule=build(root)
   doc=impl.generate(p,pi,[t],common_rules=[rule])
   self.assertEqual(doc['unresolved_rule_ids'],[])
   self.assertEqual(len(doc['intrinsic_rule_proofs']),1)
   proof=doc['intrinsic_rule_proofs'][0]
   self.assertEqual(proof['rule_id'],'demo.rule.check')
   self.assertEqual(proof['source_sha256'],doc['source_sha256']['demo.rule.document'])
   evidence={'status':'passed','evidence':'source-model/sha'}
   evaluated=impl.aggregate(doc,model_conformance=evidence)
   by={x['id']:x for x in evaluated['items']}
   self.assertEqual(by['normative-rule.demo.rule.check']['status'],'passed')
   self.assertIn('intrinsic-model/v1',by['normative-rule.demo.rule.check']['evidence'])
   evaluated=impl.aggregate(doc,model_conformance={'status':'inconclusive'})
   by={x['id']:x for x in evaluated['items']}
   self.assertEqual(by['normative-rule.demo.rule.check']['status'],'inconclusive')
   doc['intrinsic_rule_proofs'][0]['source_sha256']='0'*64
   evaluated=impl.aggregate(doc,model_conformance=evidence)
   by={x['id']:x for x in evaluated['items']}
   self.assertEqual(by['normative-rule.demo.rule.check']['status'],'inconclusive')

 def test_executed_external_observation_never_self_confirms_free_text_rule(self):
  import cat_verifier_contracts as verifier
  from test_rule_verifier import RuleVerifierTests
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   model,registry=RuleVerifierTests().prepare(root,'discord',True)
   observed=verifier.evaluate(model,registry)
   self.assertEqual(observed['status'],'passed')
   doc={'schema':'cat-implementation-obligations/v1',
        'source_sha256':{'demo.spec':'a'*64},
        'intrinsic_rule_proofs':[],
        'items':[{'id':'normative-rule.demo.rule','category':'domain',
                  'source_ref':'demo.spec#demo.rule','method':'normative-rule-verifier',
                  'status':'not-run','reason':'pending','limitation':'pending'}]}
   evaluated=impl.aggregate(doc,model_conformance={'status':'passed'},
                            rule_verification=observed)
   self.assertEqual(evaluated['items'][0]['status'],'inconclusive')
   self.assertIn('observation',evaluated['items'][0]['reason'])

 def test_failed_registered_rule_assertion_blocks_implementation_gate(self):
  # This fixture checks an executable verifier's *failure*, not the truth
  # of a free-text normative Rule. Its failed evidence must not be softened
  # to the same inconclusive status as a passing but non-normative fixture.
  from unittest.mock import patch
  from test_rule_verifier import RuleVerifierTests
  import cat_verifier_contracts as verifier
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   model,registry=RuleVerifierTests().prepare(root,'discord',True)
   doc={'schema':'cat-implementation-obligations/v1',
        'source_sha256':{'demo.spec':'a'*64},
        'intrinsic_rule_proofs':[],
        'items':[{'id':'normative-rule.demo.rule','category':'domain',
                  'source_ref':'demo.spec#demo.rule','method':'normative-rule-verifier',
                  'status':'not-run','reason':'pending','limitation':'pending'}]}
   for category in ('interface','capability','behavior','invariant',
                    'cross-process','implementation-constraint'):
    doc['items'].append({'id':'other.'+category,'category':category,
                         'source_ref':'demo.spec','method':'model-conformance',
                         'status':'not-run','reason':'pending','limitation':'pending'})
   obpath=root/'obligations.json';obpath.write_text(json.dumps(doc),encoding='utf-8')
   for name in ('process.md','pi.md','tce.md'):
    (root/name).write_text('fixture',encoding='utf-8')
   conf={'process':'process.md','pi':'pi.md','tce':'tce.md',
         'model':'model.json','obligations':'obligations.json',
         'verifier_registry':'registry.json','allow_draft':False}
   work={'id':'demo.work','scope':{'process_ids':['demo.process']},
         'compilation':conf,'technologies':[], 'repositories':[]}
   workpath=root/'work.json';workpath.write_text(json.dumps(work),encoding='utf-8')

   def inspect(expected, result_status, obligation_status):
    content=json.loads(registry.read_text(encoding='utf-8'))
    content['entries'][0]['assertions'][0]['expected']=expected
    registry.write_text(json.dumps(content),encoding='utf-8')
    observed=verifier.evaluate(model,registry)
    evaluated=impl.aggregate(doc,model_conformance={'status':'passed','evidence':'fixture'},
                             rule_verification=observed)
    rule=next(item for item in evaluated['items']
              if item['id']=='normative-rule.demo.rule')
    self.assertEqual(rule['status'],obligation_status)
    with patch.object(cat_flow,'obligations_work',return_value={'status':'passed'}),\
         patch.object(cat_flow,'conformance_evidence_status',
                      return_value={'status':'passed','evidence':'synthetic'}):
     verdict=cat_flow.conformance_work(workpath,work,'implementation-conformance')
    self.assertEqual(verdict['status'],result_status,verdict)
    return rule,verdict

   failed,blocked=inspect(False,'blocked','failed')
   self.assertIn('registered verifier',failed['reason'])
   self.assertIn('fixture',failed['limitation'])
   self.assertIn('implementation obligations failed',blocked['reason'])
   successful,inconclusive=inspect(True,'inconclusive','inconclusive')
   self.assertIn('equivalence is unproved',successful['reason'])

 def test_flow_does_not_drop_declared_sources(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p,a,b,t,cr,ds=self.setup(root)
   work={'compilation': {'schema':'cat-compile/v2','process':p.name,'pi':a.name,'pis':[a.name,b.name],
             'tce':t.name,'tces':[t.name],'common_rules':[cr.name],'domain_specs':[ds.name],
             'obligations':'obligations.json','allow_draft':False},'technologies':[]}
   wpath=root/'Work.json';wpath.write_text('{}')
   res=cat_flow.obligations_work(wpath,work)
   self.assertEqual(res['status'],'passed',res)
   out=json.loads((root/'obligations.json').read_text())
   self.assertIn('normative-rule.demo.common.one',{x['id'] for x in out['items']})
   self.assertEqual(cat_flow.obligations_work(wpath,work,check=True)['status'],'passed')

if __name__=='__main__':unittest.main(verbosity=2)
