"""Unbounded opaque IDs: exact equality classes, not enumeration of example IDs."""
import json,subprocess,sys,tempfile,unittest,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts'))
from test_cat_compile_readable import write_v2,fm
from cat_compile_v2 import load,selection_vectors,expand_cases,render_model_markdown
from cat_model_conformance import validate


def source(root,defect=None):
    p,pi,t=write_v2(root,False)
    p.write_text(p.read_text().replace('| state.ready | boolean |','| state.ready | boolean |\n| state.request | string |\n| state.phase | enum{idle,waiting,done} |').replace('| submit | demo.process.pi |','| submit | demo.process.pi |\n| response | demo.process.pi |'),encoding='utf8')
    pi.write_text(pi.read_text().replace('| input.enabled | receive | boolean | required |','| input.enabled | receive | string | required |').replace('| submit_op | accept | submit |','| submit_op | accept | submit |\n| response_op | accept | response |'),encoding='utf8')
    start='state.phase == "idle"'
    response='state.phase == "waiting" and input.enabled == state.request'
    actual_response='state.phase == "waiting"' if defect=='wrong-request' else response
    if defect=='transformation':actual_response='state.phase == "waiting" and concat(input.enabled,"x") == state.request'
    t.write_text(t.read_text().split('| demo.accept |')[0]+f'''| demo.start | submit | `{start}` | 1 | `state.phase = "waiting"; state.request = input.enabled; output.accepted = true` |
| demo.start-reject | submit | `not ({start})` | 1 | `output.accepted = false` |
| demo.response | response | `{actual_response}` | 1 | `state.phase = "done"; output.accepted = true` |
| demo.response-reject | response | `not ({actual_response})` | 1 | `output.accepted = false` |
''',encoding='utf8')
    specs=[('submit',f'({start} and after.state.phase == "waiting" and after.state.request == input.enabled) or (not ({start}) and after.state.phase == state.phase and after.state.request == state.request)'),('response',f'({response} and after.state.phase == "done" and after.state.request == state.request) or (not ({response}) and after.state.phase == state.phase and after.state.request == state.request)')]
    r=root/'Rule.md';body=fm('domain-spec','demo.process.identities',['demo.process.contract'],language='en')+'\n## Rules\n| ID | Condition | Requirement | Verification |\n| --- | --- | --- | --- |\n'
    for tr,relation in specs:
        scope={'trigger':tr,'pi':'demo.process.pi','operation':tr+'_op','peer':'demo.user','when':'true','fields':['state.phase','state.request'],'relation':relation}
        body+=f'| demo.identity-{tr} | transition-relation {json.dumps(scope,separators=(",",":"))} | @cat:finite-transition-relation/v1 | cat:intrinsic-model/v1 |\n'
    r.write_text(body,encoding='utf8')
    for f in (p,pi,t,r):f.write_text(f.read_text().replace('status: draft','status: confirmed').replace("decision_ref: ''",'decision_ref: synthetic-test-only'),encoding='utf8')
    return p,pi,t,r

class StringIdentityRelation(unittest.TestCase):
    def test_exact_symbolic_identity_and_vectors(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p,pi,t,r=source(root);m=load(p,pi,t,domain_specs=[r],allow_partial=True)
            self.assertEqual(m['status'],'confirmed',m['unverified_rule_ids'])
            self.assertEqual(m['coverage_checks']['response']['proof_method'],'string-reference-equality-partition/v1')
            self.assertEqual(len(expand_cases(m,selection_vectors(m))),4)
            for fname,data in [('Model.json',json.dumps(m)),('Model.md',render_model_markdown(m))]:
                out=root/fname;out.write_text(data,encoding='utf8');self.assertEqual(validate(p,pi,t,out,domain_specs=[r])['status'],'passed')
    def test_wrong_identity_and_unsupported_transform(self):
        for defect in ('wrong-request','transformation'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as d:
                p,pi,t,r=source(Path(d),defect);m=load(p,pi,t,domain_specs=[r],allow_partial=True)
                self.assertEqual(m['status'],'draft');self.assertIn('demo.identity-response',m['unverified_rule_ids'])
    def test_formal_gate(self):
        for defect in (None,'wrong-request'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as d:
                root=Path(d);files=source(root,defect)
                work={'schema':'cat-work/v1','id':'demo.identity.work','entry':'confirmed-spec','mode':'implementation','flow':'spec-implementation','work_kind':'implementation','parent':'','depends_on':[],'issue_ref':'spec-entry','project_entry_ref':'project-entry','normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],'specification':{'status':'confirmed','decision_ref':'decision','artifact_refs':['demo.tce']},'scope':{'process_ids':['demo.process'],'changed_ids':[],'preserved_ids':[]},'technologies':[],'repositories':[],'checks':[],'gates':[],'compilation':{'schema':'cat-compile/v2','process':'Process.md','pi':'PI.md','tce':'TCE.md','domain_specs':['Rule.md'],'model':'Model.json','allow_draft':False,'allow_partial':True}}
                path=root/'Work.json';path.write_text(json.dumps(work),encoding='utf8')
                run=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts/cat_flow.py'),'conformance','--work',str(path),'--kind','process-closure'],text=True,capture_output=True,timeout=75);self.assertEqual(run.returncode,0,run.stderr)
                gate=json.loads(run.stdout);self.assertEqual(gate['status'],'passed' if defect is None else 'inconclusive',gate)
                digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
                print('STRING-IDENTITY-GATE',json.dumps({'status':gate['status'],'exit':run.returncode,'source_sha256':{f.name:digest(f) for f in files},'model_sha256':digest(root/'.cat-flow/cache/process-closure.model.json'),'receipt_sha256':digest(root/'.cat-flow/conformance/process-closure.json')},sort_keys=True),flush=True)
if __name__=='__main__':unittest.main()
