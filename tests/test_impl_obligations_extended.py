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

 def test_rule_aggregator_requires_source_and_matching_result(self):
  with tempfile.TemporaryDirectory() as tmp:
   r=Path(tmp);p,a,b,t,cr,ds=self.setup(r)
   doc=impl.generate(p,[a,b],[t],common_rules=[cr],domain_specs=[ds])
   evidence={'status':'passed','results':[{'rule_id':'demo.common.one',
         'source_artifact':'demo.process.common','status':'passed'}]}
   result=impl.aggregate(doc,rule_verification=evidence)
   by={x['id']:x for x in result['items']}
   self.assertEqual(by['normative-rule.demo.common.one']['status'],'passed')
   self.assertEqual(by['normative-rule.demo.domain.two']['status'],'inconclusive')
   evidence['results'][0]['source_artifact']='unrelated.contract'
   result=impl.aggregate(doc,rule_verification=evidence)
   by={x['id']:x for x in result['items']}
   self.assertEqual(by['normative-rule.demo.common.one']['status'],'inconclusive')

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
