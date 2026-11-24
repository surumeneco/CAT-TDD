"""Only independently established, explicitly opted-in Source invariants restrict Guard space."""
import hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts'))
from test_cat_compile_readable import fm,write_v2
from cat_compile_v2 import load,selection_vectors,expand_cases,render_model_markdown,Blocked
from cat_model_conformance import validate

TOKEN='@cat:finite-state-guard-invariant/v1'
SCOPE='initial-state-relation state.ready == (state.status == "published")'


def source(root,scope=SCOPE,token=TOKEN,violate=False,confirmed=True,foreign=False):
    p,pi,t=write_v2(root,False)
    p.write_text(p.read_text(encoding='utf8').replace('| state.ready | boolean |','| state.ready | boolean |\n| state.status | enum{draft,published} |'),encoding='utf8')
    t.write_text(t.read_text(encoding='utf8').replace('`input.enabled`','`state.ready and state.status == "published"`').replace('`not input.enabled`','`not state.ready and state.status == "draft"`').replace('state.ready = true;',('state.ready = true;' if violate else 'state.ready = false;')+' state.status = "draft";').replace('`output.accepted = false`','`state.ready = true; state.status = "published"; output.accepted = false`'),encoding='utf8')
    r=root/'Rule.md';r.write_text(fm('domain-spec','demo.process.invariant',['demo.process.contract'],language='en')+'\n## Rules\n| ID | Condition | Requirement | Verification |\n| --- | --- | --- | --- |\n'+f'| demo.invariant | {scope} | {token} | cat:intrinsic-model/v1 |\n',encoding='utf8')
    if foreign:r.write_text(r.read_text().replace('process: demo.process\n','process: demo\n'),encoding='utf8')
    if confirmed:
        for f in (p,pi,t,r):f.write_text(f.read_text(encoding='utf8').replace('status: draft','status: confirmed').replace("decision_ref: ''",'decision_ref: synthetic-test-only'),encoding='utf8')
    return p,pi,t,r


class GuardInvariantRelationTests(unittest.TestCase):
    def test_valid_domain_not_cartesian_and_vectors(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p,pi,t,r=source(root);m=load(p,pi,t,domain_specs=[r],allow_partial=True)
            self.assertEqual(m['status'],'confirmed',m['coverage_checks'])
            self.assertEqual(m['coverage_checks']['submit']['guard_invariant_rule_ids'],['demo.invariant'])
            self.assertEqual(m['coverage_checks']['submit']['result'],'proved')
            for name,content in [('Model.json',json.dumps(m)),('Model.md',render_model_markdown(m))]:
                f=root/name;f.write_text(content,encoding='utf8');self.assertEqual(validate(p,pi,t,f,domain_specs=[r])['status'],'passed')
            v=selection_vectors(m);self.assertEqual(len(expand_cases(m,v)),2)
            v['cases'][0]['state']['state.ready']=not v['cases'][0]['state']['state.ready']
            with self.assertRaisesRegex(Blocked,'invariant'):expand_cases(m,v)
            m['coverage_checks']['submit']['guard_invariant_rule_ids']=[]
            out=root/'forged.json';out.write_text(json.dumps(m),encoding='utf8');self.assertEqual(validate(p,pi,t,out,domain_specs=[r])['status'],'blocked')
    def test_unproved_or_undeclared_invariants_do_not_shrink(self):
        for opts in ({'violate':True},{'scope':'initial-state-relation false'},{'scope':'initial-state-relation input.enabled'},{'scope':'initial-state-relation state.nope'},{'foreign':True},{'confirmed':False},{'token':'unrecognized'}):
            with self.subTest(opts=opts),tempfile.TemporaryDirectory() as d:
                p,pi,t,r=source(Path(d),**opts);m=load(p,pi,t,domain_specs=[r],allow_draft=True,allow_partial=True)
                self.assertEqual(m['coverage_checks']['submit']['result'],'uncovered')
                self.assertNotIn('guard_invariant_rule_ids',m['coverage_checks']['submit'])
                self.assertIn('demo.invariant',m['unverified_rule_ids'])
    def test_existing_pi_constraint_and_first_failure_order(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p,pi,t=write_v2(root,False)
            pi.write_text(pi.read_text().replace('| input.enabled | receive | boolean | required |','| input.enabled | receive | boolean | required |\n| input.other | receive | boolean | required |')+'\n| `not input.other or input.enabled` |\n',encoding='utf8')
            t.write_text(t.read_text().replace('`input.enabled`','`input.enabled and input.other`').replace('`not input.enabled`','`not input.enabled and not input.other`')+'\n| demo.first-failure | submit | `input.enabled and not input.other` | 1 | `output.accepted = false` |\n',encoding='utf8')
            for f in (p,pi,t):f.write_text(f.read_text().replace('status: draft','status: confirmed').replace("decision_ref: ''",'decision_ref: synthetic-test-only'),encoding='utf8')
            model=load(p,pi,t,allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'],'proved')
            out=root/'Model.json';out.write_text(json.dumps(model),encoding='utf8')
            self.assertEqual(validate(p,pi,t,out)['status'],'passed')
            self.assertEqual(len(expand_cases(model,selection_vectors(model))),3)

    def test_formal_closure(self):
        for violation in (False,True):
            with self.subTest(violation=violation),tempfile.TemporaryDirectory() as d:
                root=Path(d);files=source(root,violate=violation)
                work={'schema':'cat-work/v1','id':'demo.invariant.work','entry':'confirmed-spec','mode':'implementation','flow':'spec-implementation','work_kind':'implementation','parent':'','depends_on':[],'issue_ref':'spec-entry','project_entry_ref':'project-entry','normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],'specification':{'status':'confirmed','decision_ref':'decision','artifact_refs':['demo.tce']},'scope':{'process_ids':['demo.process'],'changed_ids':[],'preserved_ids':[]},'technologies':[],'repositories':[],'checks':[],'gates':[],'compilation':{'schema':'cat-compile/v2','process':'Process.md','pi':'PI.md','tce':'TCE.md','domain_specs':['Rule.md'],'model':'Model.json','allow_draft':False,'allow_partial':True}}
                path=root/'Work.json';path.write_text(json.dumps(work),encoding='utf8')
                argv=[sys.executable,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts/cat_flow.py'),'conformance','--work',str(path),'--kind','process-closure']
                run=subprocess.run(argv,text=True,capture_output=True,timeout=75);self.assertEqual(run.returncode,0,run.stderr)
                gate=json.loads(run.stdout);self.assertEqual(gate['status'],'inconclusive' if violation else 'passed',gate)
                digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
                print('GUARD-INVARIANT-GATE',json.dumps({'status':gate['status'],'exit':run.returncode,'source_sha256':{f.name:digest(f) for f in files},'model_sha256':digest(root/'.cat-flow/cache/process-closure.model.json'),'receipt_sha256':digest(root/'.cat-flow/conformance/process-closure.json')},sort_keys=True),flush=True)

if __name__=='__main__':unittest.main()
