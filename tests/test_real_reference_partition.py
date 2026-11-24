"""Exact direct real reference order partitions, not numerical sampling."""
import json,sys,tempfile,unittest,subprocess,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts'))
from test_cat_compile_readable import write_v2
from cat_compile_v2 import load,selection_vectors,expand_cases
from cat_model_conformance import validate


def source(root,left='input.enabled < state.limit',right='input.enabled >= state.limit',first='real[0..10]',second='real[0.5..5.5]',constraint=None,confirmed=True):
    p,pi,tce=write_v2(root,False)
    p.write_text(p.read_text(encoding='utf8').replace('| state.ready | boolean |',f'| state.ready | boolean |\n| state.limit | {second} |'),encoding='utf8')
    pi.write_text(pi.read_text(encoding='utf8').replace('| input.enabled | receive | boolean | required |',f'| input.enabled | receive | {first} | required |'),encoding='utf8')
    tce.write_text(tce.read_text(encoding='utf8').replace('`input.enabled`',f'`{left}`').replace('`not input.enabled`',f'`{right}`'),encoding='utf8')
    if constraint:pi.write_text(pi.read_text(encoding='utf8')+f'| `{constraint}` |\n',encoding='utf8')
    if confirmed:
        for path in p,pi,tce:
            path.write_text(path.read_text(encoding='utf8').replace('status: draft','status: confirmed').replace("decision_ref: ''",'decision_ref: synthetic-test-only'),encoding='utf8')
    return p,pi,tce


class RealReferencePartition(unittest.TestCase):
    def test_exact_coupled_order_and_vectors(self):
        for domains in [('real','real'),('real[0..10]','real[0.5..5.5]'),('real[0..1]','real[0..1]')]:
            with self.subTest(domains=domains),tempfile.TemporaryDirectory() as d:
                root=Path(d);p,pi,tce=source(root,first=domains[0],second=domains[1])
                model=load(p,pi,tce,allow_partial=True);proof=model['coverage_checks']['submit']
                self.assertEqual(proof['result'],'proved',proof)
                self.assertEqual(proof['proof_method'],'real-reference-order-partition/v1')
                out=root/'Model.json';out.write_text(json.dumps(model),encoding='utf8')
                self.assertEqual(validate(p,pi,tce,out)['status'],'passed')
                self.assertEqual(len(expand_cases(model,selection_vectors(model))),2)
                proof['abstract_state_count']-=1;out.write_text(json.dumps(model),encoding='utf8')
                self.assertEqual(validate(p,pi,tce,out)['status'],'blocked')

    def test_boundaries_mixed_predicates_and_no_false_proofs(self):
        for left,right,expected in [
            ('input.enabled < state.limit and input.enabled < 3.5','input.enabled >= state.limit or input.enabled >= 3.5','proved'),
            ('input.enabled < state.limit','input.enabled > state.limit','uncovered'),
            ('input.enabled <= state.limit','input.enabled >= state.limit','conflict'),
            ('input.enabled + 1 < state.limit','input.enabled + 1 >= state.limit','unproven'),
            ('input.enabled == state.limit','input.enabled != state.limit','unproven')]:
            with self.subTest(left=left),tempfile.TemporaryDirectory() as d:
                model=load(*source(Path(d),left,right,confirmed=False),allow_draft=True,allow_partial=True)
                self.assertEqual(model['coverage_checks']['submit']['result'],expected,model['coverage_checks']['submit'])
        with tempfile.TemporaryDirectory() as d:
            model=load(*source(Path(d),first='real[1..1.0000000000000002]',second='real[1..1.0000000000000002]',confirmed=False),allow_draft=True,allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'],'unproven')

    def test_canonical_closure(self):
        for gap in (False,True):
            with self.subTest(gap=gap),tempfile.TemporaryDirectory() as d:
                root=Path(d);sources=source(root,right='input.enabled > state.limit' if gap else 'input.enabled >= state.limit')
                work={'schema':'cat-work/v1','id':'demo.real-ref.work','entry':'confirmed-spec','mode':'implementation','flow':'spec-implementation','work_kind':'implementation','parent':'','depends_on':[],'issue_ref':'spec-entry','project_entry_ref':'project-entry','normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],'specification':{'status':'confirmed','decision_ref':'decision','artifact_refs':['demo.tce']},'scope':{'process_ids':['demo.process'],'changed_ids':[],'preserved_ids':[]},'technologies':[],'repositories':[],'checks':[],'gates':[],'compilation':{'schema':'cat-compile/v2','process':'Process.md','pi':'PI.md','tce':'TCE.md','model':'Model.json','allow_draft':False,'allow_partial':True}}
                path=root/'Work.json';path.write_text(json.dumps(work),encoding='utf8')
                argv=[sys.executable,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts/cat_flow.py'),'conformance','--work',str(path),'--kind','process-closure']
                run=subprocess.run(argv,capture_output=True,text=True,timeout=75)
                self.assertEqual(run.returncode,0,(run.stdout,run.stderr))
                gate=json.loads(run.stdout);self.assertEqual(gate['status'],'inconclusive' if gap else 'passed',gate)
                digest=lambda x:hashlib.sha256(x.read_bytes()).hexdigest()
                print('REAL-REFERENCE-GATE',json.dumps({'status':gate['status'],'exit':run.returncode,'source_sha256':{x.name:digest(x) for x in sources},'receipt_sha256':digest(root/'.cat-flow/conformance/process-closure.json'),'model_sha256':digest(root/'.cat-flow/cache/process-closure.model.json')},sort_keys=True),flush=True)

if __name__=='__main__':unittest.main()
