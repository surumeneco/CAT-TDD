"""Exact finite masks preserve native short circuit and source closure."""
import itertools
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system/scripts'))
from cat_compile_v2 import (Blocked, eval_expr, used_refs, parse_expr_text,
                            load, selection_vectors, expand_cases, render_model_markdown)
from cat_model_conformance import validate
from catlib.finite_truth_masks import truth_masks, row_indices
from catlib import semantic_types as typed


def artifact(kind, ident, refs, body):
    return (f"---\ncat_version: '0.3'\nkind: {kind}\nid: {ident}\nstatus: confirmed\n"
            "process: probe.masks\nsource_refs: [\"synthetic-test-only\"]\n"
            f"decision_ref: synthetic-test-only\nrefs: {json.dumps(refs)}\n"
            "semantic_contract: markdown-v2\nlanguage: en\n---\n\n"+body+'\n')


class FiniteTruthMasksTests(unittest.TestCase):
    def test_native_exhaustive_oracle_including_undefined_short_circuit(self):
        names=['input.a','input.b','input.c']
        dims=[[False,True],[typed.MISSING,typed.UNDEFINED,False,True],[False,True]]
        ref=lambda name:{'ref':name}
        a,b,c=map(ref,names)
        present={'op':'is-present','args':[b]}
        neg=lambda x:{'op':'not','args':[x]}
        conjunction=lambda *x:{'op':'and','args':list(x)}
        disjunction=lambda *x:{'op':'or','args':list(x)}
        expressions=[a,b,c,present,neg(a),neg(b),conjunction(present,b),
                     disjunction(neg(present),b),conjunction(a,b,c),
                     disjunction(a,b,c),neg(conjunction(present,b))]
        for constraints in ([],[present],[a,present],[a,neg(a)],[b]):
            for guards in ([x] for x in expressions):
                expected=[0,[0]];undefined=False
                for i,values in enumerate(itertools.product(*dims)):
                    env=dict(zip(names,values))
                    try:
                        if not all(eval_expr(e,env,{}) for e in constraints):continue
                        expected[0]|=1<<i
                        if eval_expr(guards[0],env,{}):expected[1][0]|=1<<i
                    except Blocked:
                        undefined=True;break
                actual=truth_masks(names,dims,constraints,guards,{},eval_expr,used_refs,Blocked)
                self.assertEqual(actual,None if undefined else tuple(expected))
        self.assertIsNone(truth_masks(['input.a'],[range(2_000_001)],[],[a],{},
                                      eval_expr,used_refs,Blocked))
        self.assertIsNone(truth_masks(['input.a'],[range(65537)],[],[a],{},
                                      eval_expr,used_refs,Blocked))
        self.assertEqual(row_indices(11,dims),(1,1,1))

    def test_large_source_closure_and_vectors(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p,pi,t=[root/n for n in ('Process.md','PI.md','TCE.md')]
            p.write_text(artifact('process','probe.masks',['probe.masks.pi'],'''# Process
## Contract
Closed world: true
## Interfaces
| PI |
| --- |
| probe.masks.pi |
## State
| ID | Domain |
| --- | --- |
## Observations
| ID | Source | Domain |
| --- | --- | --- |
## Actions
| ID | Target | Domain |
| --- | --- | --- |
## Triggers
| ID | Source |
| --- | --- |
| submit | probe.masks.pi/request |'''),encoding='utf8')
            pi.write_text(artifact('pi','probe.masks.pi',['probe.masks'],'''# PI
## Boundary
| Peer process | Direction |
| --- | --- |
| probe.caller | bidirectional |
## Fields
| ID | Direction | Domain | Presence |
| --- | --- | --- | --- |
'''+ '\n'.join(f'| input.b{i} | receive | boolean | required |' for i in range(19))+'''
| output.ok | send | boolean | required |
## Operations
| ID | Direction | Trigger |
| --- | --- | --- |
| request | accept | submit |
## Constraints
| Expression |
| --- |'''),encoding='utf8')
            header='''# TCE
Coverage requirement: closed
## Behaviors
| ID | Trigger | Condition | Outcome | Effects |
| --- | --- | --- | --- | --- |
'''
            rows=[]
            for i,bits in enumerate(itertools.product((False,True),repeat=3)):
                expr=' and '.join([*(f'input.b{j}' if v else f'not input.b{j}' for j,v in enumerate(bits)),
                                   *(f'(input.b{j} or not input.b{j})' for j in range(3,19))])
                rows.append(f'| rule.r{i} | submit | `{expr}` | 1 | `output.ok = true` |')
            work={'schema':'cat-work/v1','id':'probe.masks.work','entry':'confirmed-spec',
                  'mode':'implementation','flow':'spec-implementation','work_kind':'implementation',
                  'parent':'','depends_on':[],'issue_ref':'spec-entry','project_entry_ref':'project-entry',
                  'normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],
                  'specification':{'status':'confirmed','decision_ref':'synthetic-test-only',
                                   'artifact_refs':['probe.masks.tce']},
                  'scope':{'process_ids':['probe.masks'],'changed_ids':[],'preserved_ids':[]},
                  'technologies':[],'repositories':[],'checks':[],'gates':[],
                  'compilation':{'schema':'cat-compile/v2','process':'Process.md','pi':'PI.md','tce':'TCE.md',
                                 'model':'Model.json','vectors':'Vectors.json','queue':'Queue.json',
                                 'allow_draft':False,'allow_partial':True}}
            w=root/'Work.json';w.write_text(json.dumps(work),encoding='utf8')
            for positive,selected in [(True,rows),(False,rows[1:])]:
                t.write_text(artifact('tce','probe.masks.tce',['probe.masks.pi'],
                                      header+'\n'.join(selected)),encoding='utf8')
                run=subprocess.run([sys.executable,str(ROOT/'.cat-system/scripts/cat_flow.py'),
                                    'conformance','--work',str(w),'--kind','process-closure'],
                                   capture_output=True,text=True,timeout=75)
                self.assertEqual(run.returncode,0,(run.stdout,run.stderr))
                self.assertEqual(json.loads(run.stdout)['status'],'passed' if positive else 'inconclusive')
                model=load(p,pi,t,allow_partial=True)
                check=model['coverage_checks']['submit']
                self.assertEqual(check['result'],'proved' if positive else 'uncovered')
                self.assertEqual(check['uncovered_count'],0 if positive else 65536)
                for name,body in [('Model.json',json.dumps(model)),('Model.md',render_model_markdown(model))]:
                    out=root/name;out.write_text(body,encoding='utf8')
                    self.assertEqual(validate(p,pi,t,out)['status'],'passed')
                if positive:
                    self.assertEqual(len(expand_cases(model,selection_vectors(model))),8)
                    for kind in ('model','vectors','queue'):
                        cmd=[sys.executable,str(ROOT/'.cat-system/scripts/cat_flow.py'),
                             'compile','--work',str(w),'--kind',kind]
                        run=subprocess.run(cmd,capture_output=True,text=True,timeout=75)
                        self.assertEqual(run.returncode,0,(run.stdout,run.stderr))
                        run=subprocess.run([*cmd,'--check'],capture_output=True,text=True,timeout=75)
                        self.assertEqual(run.returncode,0,(run.stdout,run.stderr))
                else:
                    self.assertEqual(len(check['uncovered']),64)
                    self.assertTrue(all(not witness['input.b0'] and not witness['input.b1']
                                        and not witness['input.b2'] for witness in check['uncovered']))


if __name__=='__main__':
    unittest.main()
