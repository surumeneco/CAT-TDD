"""Exact real order truth cells; no sampled or arithmetic closure."""
import json,sys,tempfile,unittest,subprocess,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts'))
from test_cat_compile_readable import write_v2
from cat_compile_v2 import load,selection_vectors,expand_cases
from cat_model_conformance import validate

class RealLiteralPartitionTests(unittest.TestCase):
    def source(self,root,left,right,domain='real'):
        p,pi,tce=write_v2(root,False)
        pi.write_text(pi.read_text(encoding='utf8').replace('| input.enabled | receive | boolean | required |',f'| input.enabled | receive | {domain} | required |'),encoding='utf8')
        tce.write_text(tce.read_text(encoding='utf8').replace('`input.enabled`',f'`{left}`').replace('`not input.enabled`',f'`{right}`'),encoding='utf8')
        return p,pi,tce
    def test_real_comparison_partition(self):
        for domain in ('real','real[0..10]'):
            with self.subTest(domain=domain),tempfile.TemporaryDirectory() as d:
                root=Path(d);p,pi,tce=self.source(root,'input.enabled < 0.5','input.enabled >= 0.5',domain)
                for path in (p,pi,tce):
                    path.write_text(path.read_text(encoding='utf8').replace('status: draft','status: confirmed').replace("decision_ref: ''",'decision_ref: synthetic-test-only'),encoding='utf8')
                model=load(p,pi,tce,allow_partial=True)
                proof=model['coverage_checks']['submit'];self.assertEqual(proof['result'],'proved',proof)
                self.assertEqual(proof['proof_method'],'real-literal-order-partition/v1')
                out=root/'Model.json';out.write_text(json.dumps(model),encoding='utf8')
                self.assertEqual(validate(p,pi,tce,out)['status'],'passed')
                vectors=selection_vectors(model);self.assertEqual(len(expand_cases(model,vectors)),2)
                model['coverage_checks']['submit']['abstract_state_count']-=1
                out.write_text(json.dumps(model),encoding='utf8');self.assertEqual(validate(p,pi,tce,out)['status'],'blocked')
    def test_formal_closure_and_constraints(self):
        for gap in (False,True):
            with self.subTest(gap=gap),tempfile.TemporaryDirectory() as d:
                root=Path(d);sources=self.source(root,'input.enabled < 0.5','input.enabled > 0.5' if gap else 'input.enabled >= 0.5','real[0..10]')
                for path in sources:
                    path.write_text(path.read_text(encoding='utf8').replace('status: draft','status: confirmed').replace("decision_ref: ''",'decision_ref: synthetic-test-only'),encoding='utf8')
                work={'schema':'cat-work/v1','id':'demo.real-order.work','entry':'confirmed-spec',
                      'mode':'implementation','flow':'spec-implementation','work_kind':'implementation',
                      'parent':'','depends_on':[],'issue_ref':'spec-entry','project_entry_ref':'project-entry',
                      'normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],
                      'specification':{'status':'confirmed','decision_ref':'decision','artifact_refs':['demo.tce']},
                      'scope':{'process_ids':['demo.process'],'changed_ids':[],'preserved_ids':[]},
                      'technologies':[],'repositories':[],'checks':[],'gates':[],
                      'compilation':{'schema':'cat-compile/v2','process':'Process.md','pi':'PI.md','tce':'TCE.md',
                                     'model':'Model.json','allow_draft':False,'allow_partial':True}}
                path=root/'Work.json';path.write_text(json.dumps(work),encoding='utf8')
                argv=[sys.executable,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts/cat_flow.py'),
                      'conformance','--work',str(path),'--kind','process-closure']
                run=subprocess.run(argv,capture_output=True,text=True,timeout=75)
                self.assertEqual(run.returncode,0,(run.stdout,run.stderr))
                gate=json.loads(run.stdout);self.assertEqual(gate['status'],'inconclusive' if gap else 'passed',gate)
                receipt=root/'.cat-flow/conformance/process-closure.json';model=root/'.cat-flow/cache/process-closure.model.json'
                digest=lambda x:hashlib.sha256(x.read_bytes()).hexdigest()
                print('REAL-ORDER-GATE',json.dumps({'status':gate['status'],'exit':run.returncode,
                      'source_sha256':{x.name:digest(x) for x in sources},'receipt_sha256':digest(receipt),
                      'model_sha256':digest(model)},sort_keys=True),flush=True)

    def test_unrepresentable_open_interval_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            model=load(*self.source(Path(d),'input.enabled <= 1.0','input.enabled >= 1.0000000000000002','real[1..1.0000000000000002]'),allow_draft=True,allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'],'unproven')

    def test_boundary_gap_overlap_and_unhandled_math(self):
        for left,right,expected in [('input.enabled < 0.5','input.enabled > 0.5','uncovered'),('input.enabled <= 0.5','input.enabled >= 0.5','conflict'),('input.enabled + 1 < 2','input.enabled + 1 >= 2','unproven'),('input.enabled == 1','input.enabled != 1','unproven')]:
            with self.subTest(left=left),tempfile.TemporaryDirectory() as d:
                model=load(*self.source(Path(d),left,right),allow_draft=True,allow_partial=True)
                self.assertEqual(model['coverage_checks']['submit']['result'],expected)
if __name__=='__main__':unittest.main()
