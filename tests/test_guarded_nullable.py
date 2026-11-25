import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / '.cat-system/scripts'
sys.path.insert(0, str(SCRIPTS))
from cat_compile_v2 import load, render_model_markdown
from cat_model_conformance import validate


def artifact(kind, ident, refs, body):
    return (f"---\ncat_version: '0.3'\nkind: {kind}\nid: {ident}\nstatus: confirmed\n"
            'process: probe.nullable\nsource_refs: ["synthetic-test-only"]\n'
            f"decision_ref: synthetic-test-only\nrefs: {json.dumps(refs)}\n"
            "semantic_contract: markdown-v2\nlanguage: en\n---\n\n" + body + "\n")


class GuardedNullableTests(unittest.TestCase):
    def test_guarded_nullable_and_existing_id_partition(self):
        variants = [
            ('state.mode and state.part != null', 'state.part', 'passed'),
            ('not (state.part == null)', 'state.part', 'passed'),
            ('state.mode', 'state.part', 'blocked'),
            ('state.mode or state.part != null', 'state.part', 'blocked'),
            ('state.mode and state.other != null', 'state.part', 'blocked'),
            ('state.mode and output.answer != null', 'state.part', 'blocked'),
            ('input.left == input.right', 'input.left', 'passed'),
            ('input.left != input.right', 'input.left', 'passed'),
        ]
        for guard, value, expected in variants:
            with self.subTest(guard=guard), tempfile.TemporaryDirectory() as td:
                root=Path(td)
                p,pi,tce=[root/n for n in ('Process.md','PI.md','TCE.md')]
                p.write_text(artifact('process','probe.nullable',['probe.nullable.pi'],'''# Process
## Contract
Closed world: true
## Interfaces
| PI |
| --- |
| probe.nullable.pi |
## State
| ID | Domain |
| --- | --- |
| state.mode | boolean |
| state.part | nullable<string> |
| state.other | nullable<string> |
## Observations
| ID | Source | Domain |
| --- | --- | --- |
## Actions
| ID | Target | Domain |
| --- | --- | --- |
## Triggers
| ID | Source |
| --- | --- |
| first | probe.nullable.pi/request |'''), encoding='utf-8')
                pi.write_text(artifact('pi','probe.nullable.pi',['probe.nullable'],'''# PI
## Boundary
| Peer process | Direction |
| --- | --- |
| probe.caller | bidirectional |
## Fields
| ID | Direction | Domain | Presence |
| --- | --- | --- | --- |
| input.left | receive | string | required |
| input.right | receive | string | required |
| output.answer | send | string | required |
## Operations
| ID | Direction | Trigger |
| --- | --- | --- |
| request | accept | first |
## Constraints
| Expression |
| --- |'''), encoding='utf-8')
                tce.write_text(artifact('tce','probe.nullable.tce',['probe.nullable.pi'],f'''# TCE
Coverage requirement: closed
## Behaviors
| ID | Trigger | Condition | Outcome | Effects |
| --- | --- | --- | --- | --- |
| first.yes | first | `{guard}` | 1 | `output.answer = {value}` |
| first.no | first | `not ({guard})` | 1 | `output.answer = ""` |'''), encoding='utf-8')
                work={'schema':'cat-work/v1','id':'probe.nullable.work','entry':'confirmed-spec','mode':'implementation','flow':'spec-implementation','work_kind':'implementation','parent':'','depends_on':[],'issue_ref':'spec-entry','project_entry_ref':'project-entry','normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],'specification':{'status':'confirmed','decision_ref':'synthetic-test-only','artifact_refs':['probe.nullable.tce']},'scope':{'process_ids':['probe.nullable'],'changed_ids':[],'preserved_ids':[]},'technologies':[],'repositories':[],'checks':[],'gates':[],'compilation':{'schema':'cat-compile/v2','process':'Process.md','pi':'PI.md','tce':'TCE.md','model':'Model.json','allow_draft':False,'allow_partial':True}}
                w=root/'Work.json';w.write_text(json.dumps(work), encoding='utf-8')
                run=subprocess.run([sys.executable,str(SCRIPTS/'cat_flow.py'),'conformance','--work',str(w),'--kind','process-closure'],capture_output=True,text=True,encoding='utf-8',timeout=30)
                self.assertEqual(json.loads(run.stdout)['status'],expected,(run.stdout,run.stderr))
                self.assertEqual(run.returncode,0 if expected=='passed' else 2)
                if expected=='passed':
                    m=load(p,pi,tce)
                    for name,body in [('Model.json',json.dumps(m)),('Model.md',render_model_markdown(m))]:
                        out=root/name;out.write_text(body,encoding='utf-8')
                        self.assertEqual(validate(p,pi,tce,out)['status'],'passed')


if __name__ == '__main__':
    unittest.main()
