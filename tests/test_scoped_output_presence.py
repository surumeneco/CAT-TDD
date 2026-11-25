"""Source-bound output Presence must distinguish independent Trigger frames."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.cat-system/scripts'))
from cat_compile_v2 import load, render_model_markdown, selection_vectors, expand_cases
from cat_model_conformance import validate


def artifact(kind, ident, refs, body):
    return (f"---\ncat_version: '0.3'\nkind: {kind}\nid: {ident}\nstatus: confirmed\n"
            "process: probe.presence\nsource_refs: [\"synthetic-test-only\"]\n"
            f"decision_ref: synthetic-test-only\nrefs: {json.dumps(refs)}\n"
            "semantic_contract: markdown-v2\nlanguage: en\n---\n\n" + body + '\n')


def fixture(root, variant='positive'):
    p, pi, tce, rule = (root / name for name in ('Process.md', 'PI.md', 'TCE.md', 'Rule.md'))
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
| state.anchor | boolean |
## Observations
| ID | Source | Domain |
| --- | --- | --- |
## Actions
| ID | Target | Domain |
| --- | --- | --- |
## Triggers
| ID | Source |
| --- | --- |
| first | probe.presence.pi/request_first |
| second | probe.presence.pi/request_second |'''), encoding='utf8')
    operations = '| reply_second | provide | second |'
    if variant == 'ambiguous':
        operations += '\n| extra_reply | provide | first |'
    override = 'request_second' if variant == 'accept_override' else 'reply_second'
    pi.write_text(artifact('pi', 'probe.presence.pi', ['probe.presence'], f'''# PI
## Boundary
| Peer process | Direction |
| --- | --- |
| probe.caller | bidirectional |
## Fields
| ID | Direction | Domain | Presence |
| --- | --- | --- | --- |
| output.answer | send | boolean | optional |
## Operations
| ID | Direction | Trigger |
| --- | --- | --- |
| request_first | accept | first |
| reply_first | provide | first |
| request_second | accept | second |
{operations}
## Constraints
| Expression |
| --- |
## Operation presence
| Operation | Field | Presence |
| --- | --- | --- |
| reply_first | output.answer | required |
| {override} | output.answer | absent |'''), encoding='utf8')
    first = 'state.anchor = state.anchor' if variant == 'missing' else 'output.answer = true'
    second = 'output.answer = false' if variant == 'absent_write' else 'state.anchor = state.anchor'
    tce.write_text(artifact('tce', 'probe.presence.tce', ['probe.presence.pi'], f'''# TCE
Coverage requirement: closed
## Behaviors
| ID | Trigger | Condition | Outcome | Effects |
| --- | --- | --- | --- | --- |
| first.reply | first | `true` | 1 | `{first}` |
| second.reply | second | `true` | 1 | `{second}` |'''), encoding='utf8')
    owner = 'probe.wrong.pi' if variant == 'wrong_owner' else 'probe.presence.pi'
    rule.write_text(artifact('domain-spec', 'probe.presence.contract', [], f'''# Domain Specification
## Targets
| Ref | Aspect |
| --- | --- |
| probe.presence | Fresh response |
## Rules
| ID | Condition | Requirement | Verification |
| --- | --- | --- | --- |
| first.presence | fresh-output {owner} reply_first first output.answer | @cat:declared-outcome-output-presence/v1 | cat:intrinsic-model/v1 |
| second.presence | fresh-output probe.presence.pi reply_second second output.answer | @cat:declared-outcome-output-presence/v1 | cat:intrinsic-model/v1 |'''), encoding='utf8')
    return p, pi, tce, rule


def gate(root):
    work = {'schema':'cat-work/v1','id':'probe.presence.work','entry':'confirmed-spec',
            'mode':'implementation','flow':'spec-implementation','work_kind':'implementation',
            'parent':'','depends_on':[],'issue_ref':'spec-entry','project_entry_ref':'project-entry',
            'normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],
            'specification':{'status':'confirmed','decision_ref':'synthetic-test-only','artifact_refs':['probe.presence.tce']},
            'scope':{'process_ids':['probe.presence'],'changed_ids':[],'preserved_ids':[]},
            'technologies':[],'repositories':[],'checks':[],'gates':[],
            'compilation':{'schema':'cat-compile/v2','process':'Process.md','pi':'PI.md','tce':'TCE.md',
                           'domain_specs':['Rule.md'],'model':'Model.json','allow_draft':False,'allow_partial':True}}
    path = root / 'Work.json'
    path.write_text(json.dumps(work), encoding='utf8')
    return subprocess.run([sys.executable, str(ROOT / '.cat-system/scripts/cat_flow.py'),
                           'conformance','--work',str(path),'--kind','process-closure'],
                          capture_output=True,text=True,timeout=75)


class ScopedOutputPresenceTests(unittest.TestCase):
    def test_independent_operations_same_pi(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p, pi, tce, rule = fixture(root)
            model = load(p, pi, tce, domain_specs=[rule], allow_partial=True)
            self.assertEqual(model['presence_unproven'], [])
            self.assertEqual(model['status'], 'confirmed')
            for name, content in [('Model.json',json.dumps(model)),('Model.md',render_model_markdown(model))]:
                out = root / name
                out.write_text(content, encoding='utf8')
                self.assertEqual(validate(p, pi, tce, out, domain_specs=[rule])['status'], 'passed')
            run = gate(root)
            self.assertEqual(run.returncode, 0, (run.stdout, run.stderr))
            self.assertEqual(json.loads(run.stdout)['status'], 'passed')
            cases = expand_cases(model, selection_vectors(model))
            for case in cases:
                self.assertEqual(case['output_operation'], 'reply_' + case['trigger'])
                for outcome in case['allowed']:
                    self.assertEqual('output.answer' in outcome['output'], case['trigger']=='first')
            model['operation_presence'][0]['presence'] = 'absent'
            out = root / 'forged.json'
            out.write_text(json.dumps(model), encoding='utf8')
            self.assertNotEqual(validate(p, pi, tce, out, domain_specs=[rule])['status'], 'passed')

    def test_negative_frames(self):
        for variant in ('ambiguous','missing','absent_write','wrong_owner','accept_override'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                fixture(root, variant)
                run = gate(root)
                if run.returncode == 0:
                    self.assertNotEqual(json.loads(run.stdout)['status'], 'passed', run.stdout)
                else:
                    self.assertIn(run.returncode, (2,))


if __name__ == '__main__':
    unittest.main()
