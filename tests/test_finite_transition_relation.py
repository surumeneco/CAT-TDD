"""Exact source-declared before/after relation, not a trace or fixture claim."""
import hashlib, json, subprocess, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts'))
from test_cat_compile_readable import fm, write_v2
from cat_compile_v2 import load, render_model_markdown
from cat_model_conformance import validate

TOKEN='@cat:finite-transition-relation/v1'

def source(root, defect=None):
    p,pi,t=write_v2(root,False)
    p.write_text(p.read_text().replace('| state.ready | boolean |','| state.ready | boolean |\n| state.phase | enum{idle,waiting,responded,done} |\n| state.request | boolean |\n| state.target | boolean |\n| state.execution | boolean |\n| state.other | boolean |\n| state.committed | boolean |').replace('| submit | demo.process.pi |','| submit | demo.process.pi |\n| response | demo.process.pi |\n| terminal | demo.process.pi |'),encoding='utf8')
    pi.write_text(pi.read_text().replace('| input.enabled | receive | boolean | required |','| input.enabled | receive | boolean | required |\n| input.target | receive | boolean | required |\n| input.execution | receive | boolean | required |').replace('| output.accepted | send | boolean | required |','| output.knowledge | send | enum{accepted,rejected,unknown} | required |').replace('| submit_op | accept | submit |','| submit_op | accept | submit |\n| response_op | accept | response |\n| terminal_op | accept | terminal |\n| reply_op | provide | terminal |'),encoding='utf8')
    first='state.phase == "idle"'
    identity='input.enabled == state.request and input.target == state.target and input.execution == state.execution'
    response='state.phase == "waiting" and '+identity
    terminal='state.phase == "responded" and '+identity
    rows=[('start','submit',first,1,'state.phase = "waiting"; state.request = input.enabled; state.target = input.target; state.execution = input.execution; output.knowledge = "accepted"'),('start-reject','submit','not ('+first+')',1,'output.knowledge = "rejected"'),('response','response',response if defect!='wrong-request' else 'state.phase == "waiting"',1,'state.phase = "responded"; output.knowledge = "accepted"'),('response-reject','response','not ('+(response if defect!='wrong-request' else 'state.phase == "waiting"')+')',1,'output.knowledge = "rejected"')]
    term=terminal if defect!='double-terminal' else '(state.phase == "responded" or state.phase == "done") and '+identity
    for committed in (False,True):
        if defect=='lost-alternative' and committed:continue
        for other in (False,True):
            if defect=='overbroad-frame' and other:continue
            rows.append(('terminal','terminal',term,1+len([r for r in rows if r[0]=='terminal']),f'state.phase = "done"; state.committed = {str(committed).lower()}; '+('' if defect=='overbroad-frame' else f'state.other = {str(other).lower()}; ')+('output.knowledge = "rejected"' if defect=='false-knowledge' else 'output.knowledge = "unknown"')))
    rows.append(('terminal-reject','terminal','not ('+term+')',1,'output.knowledge = "rejected"'))
    head=t.read_text().split('| demo.accept |')[0]
    t.write_text(head+''.join(f'| demo.{rid} | {tr} | `{guard}` | {n} | `{effects}` |\n' for rid,tr,guard,n,effects in rows),encoding='utf8')
    equal=' and '.join('after.state.'+name+' == state.'+name for name in ('request','target','execution'))
    phase='after.state.phase == state.phase'
    start_relation='('+first+' and after.state.phase == "waiting" and after.state.request == input.enabled and after.state.target == input.target and after.state.execution == input.execution) or (not ('+first+') and '+phase+' and '+equal+')'
    response_relation='('+response+' and after.state.phase == "responded" and '+equal+') or (not ('+response+') and '+phase+' and '+equal+')'
    terminal_relation='('+terminal+' and after.state.phase == "done" and after.output.knowledge == "unknown") or (not ('+terminal+') and '+phase+' and after.state.committed == state.committed and after.state.other == state.other and after.output.knowledge == "rejected")'
    r=root/'Rule.md';header=fm('domain-spec','demo.process.transitions',['demo.process.contract'],language='en')+'\n## Rules\n| ID | Condition | Requirement | Verification |\n| --- | --- | --- | --- |\n'
    for name,trigger,relation in [('start','submit',start_relation),('response','response',response_relation),('terminal','terminal',terminal_relation),('terminal-identity','terminal',equal)]:
        fields=['state.phase','state.request','state.target','state.execution']
        scope={'trigger':trigger,'pi':'demo.process.pi','operation':trigger+'_op','peer':'demo.user' if defect!='wrong-peer' else 'demo.other','when':'true','fields':fields,'relation':relation}
        if name=='terminal':scope.update(fields=['state.phase','state.committed','state.other','output.knowledge'],provide='reply_op')
        if name=='terminal-identity':scope.update(fields=['state.request','state.target','state.execution'])
        if defect=='wrong-scope' and name=='start':scope['operation']='response_op'
        if defect=='future-read' and name=='start':scope['when']='output.knowledge'
        header+=f'| demo.relation-{name} | transition-relation {json.dumps(scope,separators=(",",":"))} | {TOKEN} | cat:intrinsic-model/v1 |\n'
    r.write_text(header,encoding='utf8')
    for f in (p,pi,t,r):f.write_text(f.read_text().replace('status: draft','status: confirmed').replace("decision_ref: ''",'decision_ref: synthetic-test-only'),encoding='utf8')
    return p,pi,t,r

class FiniteTransitionRelation(unittest.TestCase):
    def test_all_three_source_relations_and_negative_cases(self):
        for defect in (None,'wrong-request','double-terminal','lost-alternative','false-knowledge','overbroad-frame','wrong-peer','wrong-scope','future-read'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as d:
                root=Path(d);p,pi,t,r=source(root,defect);m=load(p,pi,t,domain_specs=[r],allow_partial=True)
                if defect is None:
                    self.assertEqual(m['status'],'confirmed',m['unverified_rule_ids'])
                    self.assertEqual(len(m['intrinsic_rule_proofs']),4)
                    for filename,content in [('Model.json',json.dumps(m)),('Model.md',render_model_markdown(m))]:
                        out=root/filename;out.write_text(content,encoding='utf8');self.assertEqual(validate(p,pi,t,out,domain_specs=[r])['status'],'passed')
                    m['intrinsic_rule_proofs'][0]['source_sha256']='0'*64
                    out=root/'forged.json';out.write_text(json.dumps(m),encoding='utf8');self.assertEqual(validate(p,pi,t,out,domain_specs=[r])['status'],'blocked')
                else:
                    self.assertEqual(m['status'],'draft');self.assertTrue(m['unverified_rule_ids'])
    def test_formal_closure(self):
        for defect in (None,'lost-alternative'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as d:
                root=Path(d);source(root,defect)
                work={'schema':'cat-work/v1','id':'demo.relation.work','entry':'confirmed-spec','mode':'implementation','flow':'spec-implementation','work_kind':'implementation','parent':'','depends_on':[],'issue_ref':'spec-entry','project_entry_ref':'project-entry','normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],'specification':{'status':'confirmed','decision_ref':'decision','artifact_refs':['demo.tce']},'scope':{'process_ids':['demo.process'],'changed_ids':[],'preserved_ids':[]},'technologies':[],'repositories':[],'checks':[],'gates':[],'compilation':{'schema':'cat-compile/v2','process':'Process.md','pi':'PI.md','tce':'TCE.md','domain_specs':['Rule.md'],'model':'Model.json','allow_draft':False,'allow_partial':True}}
                path=root/'Work.json';path.write_text(json.dumps(work),encoding='utf8')
                argv=[sys.executable,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts/cat_flow.py'),'conformance','--work',str(path),'--kind','process-closure']
                run=subprocess.run(argv,text=True,capture_output=True,timeout=75);self.assertEqual(run.returncode,0,run.stderr)
                gate=json.loads(run.stdout);self.assertEqual(gate['status'],'passed' if defect is None else 'inconclusive',gate)
                digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
                print('TRANSITION-RELATION-GATE',json.dumps({'status':gate['status'],'exit':run.returncode,'source_sha256':{f:digest(root/f) for f in ('Process.md','PI.md','TCE.md','Rule.md')},'model_sha256':digest(root/'.cat-flow/cache/process-closure.model.json'),'receipt_sha256':digest(root/'.cat-flow/conformance/process-closure.json')},sort_keys=True),flush=True)

if __name__=='__main__':unittest.main()
