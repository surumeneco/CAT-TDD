"""Fresh output frames belong to PI owners, not the number of providers."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from test_scoped_output_presence import fixture, artifact, ROOT
from cat_compile_v2 import load, render_model_markdown, selection_vectors, Blocked
from cat_model_conformance import validate


def build(root, variant):
    p, pi, tce, rule = fixture(root)
    other = root/'OtherPI.md'
    p.write_text(p.read_text().replace('refs: ["probe.presence.pi"]','refs: ["probe.presence.pi", "probe.other.pi"]').replace('| probe.presence.pi |','| probe.presence.pi |\n| probe.other.pi |'), encoding='utf8')
    other.write_text(artifact('pi','probe.other.pi',['probe.presence'], '''# PI
## Boundary
| Peer process | Direction |
| --- | --- |
| probe.receiver | outgoing |
## Fields
| ID | Direction | Domain | Presence |
| --- | --- | --- | --- |
| output.notice | send | boolean | optional |
## Operations
| ID | Direction | Trigger |
| --- | --- | --- |
| publish | provide | first |
## Constraints
| Expression |
| --- |
## Operation presence
| Operation | Field | Presence |
| --- | --- | --- |
| publish | output.notice | required |''').replace('| probe.receiver | outgoing |','| probe.receiver | bidirectional |'),encoding='utf8')
    tce.write_text(tce.read_text().replace('refs: ["probe.presence.pi"]','refs: ["probe.presence.pi", "probe.other.pi"]').replace('output.answer = true`','output.answer = true; output.notice = false`'),encoding='utf8')
    rule.write_text(rule.read_text()+ '| notification.presence | fresh-output probe.other.pi publish first output.notice | @cat:declared-outcome-output-presence/v1 | cat:intrinsic-model/v1 |\n',encoding='utf8')
    if variant=='missing':tce.write_text(tce.read_text().replace('; output.notice = false',''),encoding='utf8')
    if variant=='inactive':tce.write_text(tce.read_text().replace('state.anchor = state.anchor`','state.anchor = state.anchor; output.notice = true`'),encoding='utf8')
    if variant=='ambiguous':other.write_text(other.read_text().replace('| publish | provide | first |','| publish | provide | first |\n| extra | provide | first |'),encoding='utf8')
    if variant=='unscoped':other.write_text(other.read_text().replace('| publish | provide | first |','| publish | provide | |'),encoding='utf8')
    if variant=='wrong_owner':rule.write_text(rule.read_text().replace('fresh-output probe.other.pi publish','fresh-output probe.presence.pi publish'),encoding='utf8')
    if variant=='absent':other.write_text(other.read_text().replace('output.notice | required','output.notice | absent'),encoding='utf8')
    # Reuse the ordinary Work schema, with both owned PI inputs.
    return p,[pi,other],tce,rule


def run_gate(root):
    work={'schema':'cat-work/v1','id':'probe.presence.work','entry':'confirmed-spec',
          'mode':'implementation','flow':'spec-implementation','work_kind':'implementation',
          'parent':'','depends_on':[],'issue_ref':'spec-entry','project_entry_ref':'project-entry',
          'normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],
          'specification':{'status':'confirmed','decision_ref':'synthetic-test-only','artifact_refs':['probe.presence.tce']},
          'scope':{'process_ids':['probe.presence'],'changed_ids':[],'preserved_ids':[]},
          'technologies':[],'repositories':[],'checks':[],'gates':[],
          'compilation':{'schema':'cat-compile/v2','process':'Process.md','pi':'PI.md',
                         'pis':['PI.md','OtherPI.md'],'tce':'TCE.md','domain_specs':['Rule.md'],
                         'model':'Model.json','allow_draft':False,'allow_partial':True}}
    path=root/'Work.json'
    path.write_text(json.dumps(work),encoding='utf8')
    return subprocess.run([sys.executable,str(ROOT/'.cat-system/scripts/cat_flow.py'),'conformance','--work',str(path),'--kind','process-closure'],capture_output=True,text=True,timeout=75)


class MultiOwnerPresenceTests(unittest.TestCase):
    def test_distinct_owner_frames(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p,pis,tce,rule=build(root,'positive')
            model=load(p,pis,tce,domain_specs=[rule],allow_partial=True)
            self.assertEqual(model['presence_unproven'],[])
            self.assertEqual(model['unverified_rule_ids'],[])
            for name,content in [('Model.json',json.dumps(model)),('Model.md',render_model_markdown(model))]:
                f=root/name;f.write_text(content,encoding='utf8');self.assertEqual(validate(p,pis,tce,f,domain_specs=[rule])['status'],'passed')
            result=run_gate(root);self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['status'],'passed')
            # Closure is not evidence that the singular vector transport supports multiple providers.
            with self.assertRaisesRegex(Blocked,'ambiguous provided output operation'):
                selection_vectors(model)
            model['operation_presence'][0]['presence']='absent'
            f=root/'forged.json';f.write_text(json.dumps(model),encoding='utf8')
            self.assertNotEqual(validate(p,pis,tce,f,domain_specs=[rule])['status'],'passed')
    def test_negative_frames(self):
        for variant in ('missing','inactive','ambiguous','unscoped','wrong_owner','absent'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as td:
                root=Path(td);build(root,variant);result=run_gate(root)
                if result.returncode==0:self.assertNotEqual(json.loads(result.stdout)['status'],'passed')
                else:self.assertEqual(result.returncode,2)
