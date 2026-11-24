"""Source-bound, inductive state equality over every declared transition."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts'))
from test_cat_compile_readable import fm,write_v2
from cat_compile_v2 import load,render_model_markdown
from cat_model_conformance import validate
from cat_implementation_obligations import aggregate,generate

TOKEN='@cat:all-trigger-state-equality-preservation/v1'
SCOPE='initial-state-equality state.ready state.copy'


def source(root,scope=SCOPE,violate=False,partial=False,confirmed=True):
    p,pi,tce=write_v2(root,False)
    p.write_text(p.read_text(encoding='utf8').replace('| state.ready | boolean |','| state.ready | boolean |\n| state.copy | boolean |').replace('| submit | demo.process.pi |','| submit | demo.process.pi |\n| reset | demo.process.pi |'),encoding='utf8')
    pi.write_text(pi.read_text(encoding='utf8').replace('| submit_op | accept | submit |','| submit_op | accept | submit |\n| reset_op | accept | reset |'),encoding='utf8')
    data=tce.read_text(encoding='utf8').replace('state.ready = true;','state.ready = true; state.copy = true;')
    data+='| demo.reset | reset | `input.enabled` | 1 | `state.ready = state.copy; state.copy = state.ready; output.accepted = true` |\n'
    data+='| demo.reset | reset | `input.enabled` | 2 | `state.ready = false; '+('' if violate else 'state.copy = false; ')+'output.accepted = false` |\n'
    if not partial:data+='| demo.reset.reject | reset | `not input.enabled` | 1 | `output.accepted = false` |\n'
    else:data=data.replace('Coverage requirement: closed','Coverage requirement: partial')
    tce.write_text(data,encoding='utf8')
    r=root/'Rule.md';r.write_text(fm('domain-spec','demo.process.invariant',['demo.process.contract'],language='en')+'\n## Rules\n| ID | Condition | Requirement | Verification |\n| --- | --- | --- | --- |\n'+f'| demo.equality | {scope} | {TOKEN} | cat:intrinsic-model/v1 |\n',encoding='utf8')
    if confirmed:
        for path in p,pi,tce,r:
            path.write_text(path.read_text(encoding='utf8').replace('status: draft','status: confirmed').replace("decision_ref: ''",'decision_ref: synthetic-test-only'),encoding='utf8')
    return p,pi,tce,r


class StateEqualityPreservation(unittest.TestCase):
    def test_model_independent_and_aggregate(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p,pi,tce,r=source(root)
            model=load(p,pi,tce,domain_specs=[r],allow_partial=True)
            self.assertEqual(model['status'],'confirmed',model['unverified_rule_ids'])
            self.assertEqual(model['intrinsic_rule_proofs'][0]['scope'],SCOPE)
            for name,data in [('Model.json',json.dumps(model)),('Model.md',render_model_markdown(model))]:
                out=root/name;out.write_text(data,encoding='utf8')
                self.assertEqual(validate(p,pi,tce,out,domain_specs=[r])['status'],'passed')
            ob=aggregate(generate(p,pi,tce,domain_specs=[r]),model_conformance={'status':'passed'})
            self.assertEqual(next(x for x in ob['items'] if x['source_ref'].endswith('#demo.equality'))['status'],'passed')
            model['intrinsic_rule_proofs'][0]['scope']='initial-state-equality state.ready state.ready'
            out=root/'forged.json';out.write_text(json.dumps(model),encoding='utf8')
            self.assertEqual(validate(p,pi,tce,out,domain_specs=[r])['status'],'blocked')

    def test_invalid_or_unestablished_relations_not_proved(self):
        for opts in ({'violate':True},{'scope':'initial-state-equality state.ready state.ready'},
                     {'scope':'initial-state-equality state.ready output.accepted'},
                     {'scope':'initial-state-equality state.ready state.unknown'},
                     {'scope':'assembled-process'},{'confirmed':False}):
            with self.subTest(opts=opts),tempfile.TemporaryDirectory() as d:
                p,pi,tce,r=source(Path(d),**opts)
                model=load(p,pi,tce,domain_specs=[r],allow_draft=True,allow_partial=True)
                self.assertEqual(model['intrinsic_rule_proofs'],[])
                self.assertIn('demo.equality',model['unverified_rule_ids'])

    def test_canonical_closure(self):
        for opts,expected in [({},'passed'),({'violate':True},'inconclusive'),({'partial':True},'inconclusive')]:
            with self.subTest(opts=opts),tempfile.TemporaryDirectory() as d:
                root=Path(d);sources=source(root,**opts)
                work={'schema':'cat-work/v1','id':'demo.equality.work','entry':'confirmed-spec','mode':'implementation','flow':'spec-implementation','work_kind':'implementation','parent':'','depends_on':[],'issue_ref':'spec-entry','project_entry_ref':'project-entry','normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],'specification':{'status':'confirmed','decision_ref':'decision','artifact_refs':['demo.tce']},'scope':{'process_ids':['demo.process'],'changed_ids':[],'preserved_ids':[]},'technologies':[],'repositories':[],'checks':[],'gates':[],'compilation':{'schema':'cat-compile/v2','process':'Process.md','pi':'PI.md','tce':'TCE.md','domain_specs':['Rule.md'],'model':'Model.json','allow_draft':False,'allow_partial':True}}
                path=root/'Work.json';path.write_text(json.dumps(work),encoding='utf8')
                argv=[sys.executable,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts/cat_flow.py'),'conformance','--work',str(path),'--kind','process-closure']
                run=subprocess.run(argv,capture_output=True,text=True,timeout=75)
                self.assertEqual(run.returncode,0,(run.stdout,run.stderr))
                gate=json.loads(run.stdout);self.assertEqual(gate['status'],expected,gate)
                digest=lambda x:hashlib.sha256(x.read_bytes()).hexdigest()
                print('STATE-EQUALITY-GATE',json.dumps({'status':gate['status'],'exit':run.returncode,'source_sha256':{x.name:digest(x) for x in sources},'receipt_sha256':digest(root/'.cat-flow/conformance/process-closure.json'),'model_sha256':digest(root/'.cat-flow/cache/process-closure.model.json')},sort_keys=True),flush=True)

if __name__=='__main__':unittest.main()
