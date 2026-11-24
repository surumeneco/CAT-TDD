"""An explicitly scoped observed-value relation is a normative input premise, not provider proof."""
import hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts'))
from test_cat_compile_readable import fm,write_v2
from cat_compile_v2 import load,Blocked,render_model_markdown
from cat_model_conformance import validate

TOKEN='@cat:trigger-observation-relation/v1'

def source(root,relation='observation-relation submit observation.published == (state.status == "published")',availability='submit',extra=None):
    p,pi,t=write_v2(root,False)
    p.write_text(p.read_text().replace('| state.ready | boolean |','| state.ready | boolean |\n| state.status | enum{draft,published} |').replace('| ID | Source | Domain |\n| --- | --- | --- |','| ID | Source | Domain | Available on |\n| --- | --- | --- | --- |\n| observation.published | declared-read | boolean | '+availability+' |'),encoding='utf8')
    t.write_text(t.read_text().replace('`input.enabled`','`observation.published and state.status == "published"`').replace('`not input.enabled`','`not observation.published and state.status == "draft"`'),encoding='utf8')
    r=root/'Rule.md';r.write_text(fm('domain-spec','demo.process.observations',['demo.process.contract'],language='en')+'\n## Rules\n| ID | Condition | Requirement | Verification |\n| --- | --- | --- | --- |\n'+f'| demo.observation | {relation} | {TOKEN} | cat:intrinsic-model/v1 |\n'+(f'| demo.other | {extra} | {TOKEN} | cat:intrinsic-model/v1 |\n' if extra else ''),encoding='utf8')
    for f in (p,pi,t,r):f.write_text(f.read_text().replace('status: draft','status: confirmed').replace("decision_ref: ''",'decision_ref: synthetic-test-only'),encoding='utf8')
    return p,pi,t,r

class ObservationDomainRelation(unittest.TestCase):
    def test_exact_trigger_relation_and_nonempty_domain(self):
        for opts in ({},{'relation':'observation-relation submit observation.published and state.status == "published"'},{'relation':'observation-relation future observation.published == (state.status == "published")'},{'availability':'-'},{'extra':'observation-relation submit observation.published != (state.status == "published")'}):
            with self.subTest(opts=opts),tempfile.TemporaryDirectory() as d:
                root=Path(d);p,pi,t,r=source(root,**opts);m=load(p,pi,t,domain_specs=[r],allow_partial=True)
                self.assertEqual(m['coverage_checks']['submit']['result'],'proved' if not opts else 'uncovered')
                self.assertEqual(m['status'],'confirmed' if not opts else 'draft')
                if not opts:
                    self.assertEqual(m['coverage_checks']['submit']['observation_relation_rule_ids'],['demo.observation'])
                    for file,data in [('Model.json',json.dumps(m)),('Model.md',render_model_markdown(m))]:
                        out=root/file;out.write_text(data,encoding='utf8');self.assertEqual(validate(p,pi,t,out,domain_specs=[r])['status'],'passed')
                    m['coverage_checks']['submit']['observation_relation_rule_ids']=[]
                    out=root/'forged.json';out.write_text(json.dumps(m),encoding='utf8');self.assertEqual(validate(p,pi,t,out,domain_specs=[r])['status'],'blocked')
    def test_future_observation_cannot_be_read(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p,pi,t,r=source(root,availability='future')
            p.write_text(p.read_text().replace('| submit | demo.process.pi |','| submit | demo.process.pi |\n| future | demo.process.pi |'),encoding='utf8')
            with self.assertRaisesRegex(Blocked,'Observation unavailable'):load(p,pi,t,domain_specs=[r],allow_partial=True)
    def test_daily_minute_order_without_exhaustive_cartesian(self):
        for gap in (False,True):
            with self.subTest(gap=gap),tempfile.TemporaryDirectory() as d:
                root=Path(d);p,pi,t=write_v2(root,False)
                p.write_text(p.read_text().replace('| ID | Source | Domain |\n| --- | --- | --- |','| ID | Source | Domain | Available on |\n| --- | --- | --- | --- |\n| observation.now | clock | integer[0..1439] | submit |\n| observation.planned | schedule | integer[0..1439] | submit |'),encoding='utf8')
                t.write_text(t.read_text().replace('`input.enabled`','`observation.now < observation.planned`').replace('`not input.enabled`','`observation.now > observation.planned`' if gap else '`observation.now >= observation.planned`'),encoding='utf8')
                for f in (p,pi,t):f.write_text(f.read_text().replace('status: draft','status: confirmed').replace("decision_ref: ''",'decision_ref: synthetic-test-only'),encoding='utf8')
                m=load(p,pi,t,allow_partial=True)
                self.assertEqual(m['coverage_checks']['submit']['result'],'uncovered' if gap else 'proved')
                out=root/'Model.json';out.write_text(json.dumps(m),encoding='utf8');self.assertEqual(validate(p,pi,t,out)['status'],'passed')

    def test_canonical_gate(self):
        for invalid in (False,True):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);source(root,availability='-' if invalid else 'submit')
                work={'schema':'cat-work/v1','id':'demo.observation.work','entry':'confirmed-spec','mode':'implementation','flow':'spec-implementation','work_kind':'implementation','parent':'','depends_on':[],'issue_ref':'spec-entry','project_entry_ref':'project-entry','normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],'specification':{'status':'confirmed','decision_ref':'decision','artifact_refs':['demo.tce']},'scope':{'process_ids':['demo.process'],'changed_ids':[],'preserved_ids':[]},'technologies':[],'repositories':[],'checks':[],'gates':[],'compilation':{'schema':'cat-compile/v2','process':'Process.md','pi':'PI.md','tce':'TCE.md','domain_specs':['Rule.md'],'model':'Model.json','allow_draft':False,'allow_partial':True}}
                path=root/'Work.json';path.write_text(json.dumps(work),encoding='utf8')
                run=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts/cat_flow.py'),'conformance','--work',str(path),'--kind','process-closure'],text=True,capture_output=True,timeout=75)
                self.assertEqual(run.returncode,0,run.stderr);gate=json.loads(run.stdout);self.assertEqual(gate['status'],'inconclusive' if invalid else 'passed')
                digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
                print('OBSERVATION-RELATION-GATE',json.dumps({'status':gate['status'],'exit':run.returncode,'source_sha256':{f:digest(root/f) for f in ('Process.md','PI.md','TCE.md','Rule.md')},'model_sha256':digest(root/'.cat-flow/cache/process-closure.model.json'),'receipt_sha256':digest(root/'.cat-flow/conformance/process-closure.json')},sort_keys=True),flush=True)
if __name__=='__main__':unittest.main()
