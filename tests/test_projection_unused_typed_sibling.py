"""Scalar member projection must not depend on a provably unread typed sibling."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.cat-system/scripts'))
from cat_compile_v2 import Blocked, load, render_model_markdown, eval_expr, selection_vectors
from cat_model_conformance import validate
from catlib import semantic_json_instant as json_time
from test_scoped_output_presence import artifact


def fixture(root, sibling, guard='input.request.version == state.version', gap=False):
    p, pi, tce = (root / name for name in ('Process.md', 'PI.md', 'TCE.md'))
    p.write_text(artifact('process', 'probe.presence', ['probe.presence.pi'], '''# Process
## Contract
Closed world: true
## Interfaces
| PI |
| --- |
| probe.presence.pi |
## State
| ID | Domain |
| --- | --- |
| state.version | integer |
## Observations
| ID | Source | Domain |
| --- | --- | --- |
## Actions
| ID | Target | Domain |
| --- | --- | --- |
## Triggers
| ID | Source |
| --- | --- |
| compare | probe.presence.pi/request |'''), encoding='utf8')
    pi.write_text(artifact('pi', 'probe.presence.pi', ['probe.presence'], f'''# PI
## Boundary
| Peer process | Direction |
| --- | --- |
| probe.caller | bidirectional |
## Fields
| ID | Direction | Domain | Presence |
| --- | --- | --- | --- |
| input.request | receive | record<version:integer,metadata:{sibling}> | required |
| output.answer | send | boolean | required |
## Operations
| ID | Direction | Trigger |
| --- | --- | --- |
| request | accept | compare |
| reply | provide | compare |
## Constraints
| Expression |
| --- |'''), encoding='utf8')
    body = f'''# TCE
Coverage requirement: closed
## Behaviors
| ID | Trigger | Condition | Outcome | Effects |
| --- | --- | --- | --- | --- |
| equal | compare | `{guard}` | 1 | `output.answer = true` |'''
    if not gap:
        body += f'\n| different | compare | `not ({guard})` | 1 | `output.answer = false` |'
    tce.write_text(artifact('tce', 'probe.presence.tce', ['probe.presence.pi'], body), encoding='utf8')
    return p, pi, tce


def closure(root):
    work = {'schema':'cat-work/v1','id':'probe.projection.work','entry':'confirmed-spec',
            'mode':'implementation','flow':'spec-implementation','work_kind':'implementation',
            'parent':'','depends_on':[],'issue_ref':'spec-entry','project_entry_ref':'project-entry',
            'normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],
            'specification':{'status':'confirmed','decision_ref':'synthetic-test-only','artifact_refs':['probe.presence.tce']},
            'scope':{'process_ids':['probe.presence'],'changed_ids':[],'preserved_ids':[]},
            'technologies':[],'repositories':[],'checks':[],'gates':[],
            'compilation':{'schema':'cat-compile/v2','process':'Process.md','pi':'PI.md','tce':'TCE.md',
                           'model':'Model.json','allow_draft':False,'allow_partial':True}}
    path=root/'Work.json';path.write_text(json.dumps(work),encoding='utf8')
    run=subprocess.run([sys.executable,str(ROOT/'.cat-system/scripts/cat_flow.py'),
                        'conformance','--work',str(path),'--kind','process-closure'],
                       capture_output=True,text=True,timeout=75)
    if run.returncode!=0:raise AssertionError((run.stdout,run.stderr))
    return json.loads(run.stdout)['status']


class ProjectionTypedSiblingTests(unittest.TestCase):
    def test_unread_siblings(self):
        for sibling, value in [('string','x'), ('json-object',{'nested':[1,2]}), ('instant',json_time.decode_offset_datetime('2020-01-01T00:00:00Z'))]:
            with self.subTest(sibling=sibling), tempfile.TemporaryDirectory() as td:
                p, pi, tce = fixture(Path(td), sibling)
                model = load(p,pi,tce)
                self.assertEqual(model['status'], 'confirmed')
                self.assertEqual(model['coverage_checks']['compare']['result'],'proved')
                self.assertEqual(closure(Path(td)),'passed')
                for name, content in [('Model.json',json.dumps(model)),('Model.md',render_model_markdown(model))]:
                    out=Path(td)/name;out.write_text(content,encoding='utf8')
                    self.assertEqual(validate(p,pi,tce,out)['status'],'passed')
                for version in (1,2):
                    env={'input.request':{'version':version,'metadata':value},'state.version':1}
                    self.assertEqual([eval_expr(r['when'],env,{}) for r in model['rules']].count(True),1)
                if sibling!='string':
                    with self.assertRaises(Blocked):selection_vectors(model)

    def test_unbound_or_unknown_value_refused(self):
        for guard in ('input.request.metadata == input.request.metadata','input.request == input.request','input.request.unknown == state.version'):
            with self.subTest(guard=guard), tempfile.TemporaryDirectory() as td:
                p,pi,tce=fixture(Path(td),'instant',guard)
                with self.assertRaises(Blocked):load(p,pi,tce)

    def test_gap_is_not_proved(self):
        for sibling in ('json-object','instant'):
            with self.subTest(sibling=sibling), tempfile.TemporaryDirectory() as td:
                p,pi,tce=fixture(Path(td),sibling,gap=True)
                model=load(p,pi,tce,allow_partial=True)
                self.assertEqual(model['coverage_checks']['compare']['result'],'uncovered')
                self.assertNotEqual(closure(Path(td)),'passed')
                json.dumps(model)

if __name__=='__main__':unittest.main()
