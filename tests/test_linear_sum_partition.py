"""Exact order cells for a single sum or difference of two required numeric fields."""
import json, subprocess, sys, tempfile, unittest, hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts'))
from cat_compile_v2 import load, selection_vectors, expand_cases, eval_expr, parse_expr_text
from cat_model_conformance import validate
from test_cat_compile_readable import write_v2


def source(root, first='input.enabled + input.other <= 100000', second='input.enabled + input.other > 100000', domain='real[0..]', other=None, constraint=None, confirmed=True):
    p,pi,tce=write_v2(root,False)
    pi.write_text(pi.read_text(encoding='utf8').replace('| input.enabled | receive | boolean | required |',f'| input.enabled | receive | {domain} | required |\n| input.other | receive | {other or domain} | required |')+(f'| `{constraint}` |\n' if constraint else ''),encoding='utf8')
    tce.write_text(tce.read_text(encoding='utf8').replace('`input.enabled`',f'`{first}`').replace('`not input.enabled`',f'`{second}`'),encoding='utf8')
    if confirmed:
        for f in (p,pi,tce):f.write_text(f.read_text(encoding='utf8').replace('status: draft','status: confirmed').replace("decision_ref: ''",'decision_ref: synthetic-test-only'),encoding='utf8')
    return p,pi,tce


class LinearSumPartition(unittest.TestCase):
    def test_exact_unbounded_and_bounded(self):
        for options in ({},{'domain':'real[-10..100001]','other':'real[0..200000]'},{'domain':'integer[0..]'}, {'first':'input.enabled - input.other <= 0','second':'input.enabled - input.other > 0','domain':'real'}):
            with self.subTest(options=options),tempfile.TemporaryDirectory() as d:
                root=Path(d);files=source(root,**options);model=load(*files,allow_partial=True)
                proof=model['coverage_checks']['submit'];self.assertEqual(proof['result'],'proved',proof)
                self.assertEqual(proof['proof_method'],'two-reference-linear-order-partition/v1')
                out=root/'Model.json';out.write_text(json.dumps(model),encoding='utf8')
                self.assertEqual(validate(*files,out)['status'],'passed')
                self.assertEqual(len(expand_cases(model,selection_vectors(model))),2)
                proof['abstract_state_count']+=1;out.write_text(json.dumps(model),encoding='utf8')
                self.assertEqual(validate(*files,out)['status'],'blocked')
    def test_gap_overlap_and_unknown(self):
        for first,second,expected in [('input.enabled + input.other < 100000','input.enabled + input.other > 100000','uncovered'),('input.enabled + input.other <= 100000','input.enabled + input.other >= 100000','conflict'),('input.enabled * input.other <= 100000','input.enabled * input.other > 100000','unproven'),('input.enabled + input.other <= 100000','input.enabled <= 100000','unproven'),('input.enabled + input.other == 100000','input.enabled + input.other != 100000','unproven')]:
            with self.subTest(first=first,second=second),tempfile.TemporaryDirectory() as d:
                model=load(*source(Path(d),first,second,confirmed=False),allow_draft=True,allow_partial=True)
                self.assertEqual(model['coverage_checks']['submit']['result'],expected,model['coverage_checks']['submit'])
    def test_exact_arithmetic_no_float_rounding_or_overflow(self):
        expr=parse_expr_text('input.enabled + input.other <= 100000')
        self.assertFalse(eval_expr(expr,{'input.enabled':100000,'input.other':2.0**-40},{}))
        self.assertFalse(eval_expr(expr,{'input.enabled':10**400,'input.other':0.5},{}))
    def test_formal_closure_and_pi_constraints(self):
        for gap in (False,True):
            with self.subTest(gap=gap),tempfile.TemporaryDirectory() as d:
                root=Path(d);files=source(root,first='input.enabled + input.other < 100000' if gap else 'input.enabled + input.other <= 100000',constraint='input.enabled + input.other >= 0')
                work={'schema':'cat-work/v1','id':'demo.sum.work','entry':'confirmed-spec','mode':'implementation','flow':'spec-implementation','work_kind':'implementation','parent':'','depends_on':[],'issue_ref':'spec-entry','project_entry_ref':'project-entry','normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],'specification':{'status':'confirmed','decision_ref':'decision','artifact_refs':['demo.tce']},'scope':{'process_ids':['demo.process'],'changed_ids':[],'preserved_ids':[]},'technologies':[],'repositories':[],'checks':[],'gates':[],'compilation':{'schema':'cat-compile/v2','process':'Process.md','pi':'PI.md','tce':'TCE.md','model':'Model.json','allow_draft':False,'allow_partial':True}}
                path=root/'Work.json';path.write_text(json.dumps(work),encoding='utf8')
                argv=[sys.executable,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts/cat_flow.py'),'conformance','--work',str(path),'--kind','process-closure']
                run=subprocess.run(argv,capture_output=True,text=True,timeout=75);self.assertEqual(run.returncode,0,run.stderr)
                gate=json.loads(run.stdout);self.assertEqual(gate['status'],'inconclusive' if gap else 'passed',gate)
                digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
                print('LINEAR-GATE',json.dumps({'status':gate['status'],'exit':run.returncode,'source_sha256':{f.name:digest(f) for f in files},'model_sha256':digest(root/'.cat-flow/cache/process-closure.model.json'),'receipt_sha256':digest(root/'.cat-flow/conformance/process-closure.json')},sort_keys=True),flush=True)

if __name__=='__main__':unittest.main()
