"""Source-authorized proof of one fresh provided output over all outcomes."""
import json
import subprocess
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts'))
from test_cat_compile_readable import fm, write_v2
from cat_compile_v2 import load, render_model_markdown
from cat_model_conformance import validate
from cat_implementation_obligations import generate, aggregate

TOKEN='@cat:declared-outcome-output-presence/v1'
SCOPE='fresh-output demo.process.pi submit_result submit output.accepted'


def source(root, scope=SCOPE, token=TOKEN, presence='optional', provide=True,
           invalid_effect=False, partial=False, confirmed=True):
    p,pi,tce=write_v2(root,False)
    data=pi.read_text(encoding='utf8').replace(
        '| output.accepted | send | boolean | required |',
        f'| output.accepted | send | boolean | {presence} |')
    if provide:
        data=data.replace('| submit_op | accept | submit |',
                          '| submit_op | accept | submit |\n| submit_result | provide | submit |')
    pi.write_text(data,encoding='utf8')
    data=tce.read_text(encoding='utf8').replace('`output.accepted = false`','`none`')
    # An additional alternative of the same TCE is part of the quantified set.
    data += '| demo.accept | submit | `input.enabled` | 2 | `state.ready = true` |\n'
    if invalid_effect:
        data=data.replace('output.accepted = true','output.accepted = state.ready')
    if partial:
        data=data.replace('Coverage requirement: closed','Coverage requirement: partial')
        data='\n'.join(line for line in data.split('\n') if not line.startswith('| demo.reject |'))
    tce.write_text(data,encoding='utf8')
    rule=root/'Rule.md'
    rule.write_text(fm('domain-spec','demo.process.presence',['demo.process.contract'],language='en')+
                    '\n## Rules\n| ID | Condition | Requirement | Verification |\n| --- | --- | --- | --- |\n'
                    f'| demo.output.presence | {scope} | {token} | cat:intrinsic-model/v1 |\n',encoding='utf8')
    if confirmed:
        for path in (p,pi,tce,rule):
            path.write_text(path.read_text(encoding='utf8').replace('status: draft','status: confirmed')
                            .replace("decision_ref: ''",'decision_ref: synthetic-test-only'),encoding='utf8')
    return p,pi,tce,rule


class DeclaredOutcomePresenceProofTests(unittest.TestCase):
    def test_confirmed_exact_source_proof_and_independent_checks(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p,pi,tce,r=source(root)
            model=load(p,pi,tce,domain_specs=[r],allow_partial=True)
            self.assertEqual(model['status'],'confirmed',model['unverified_rule_ids'])
            proof=model['intrinsic_rule_proofs'][0]
            self.assertEqual(proof['scope'],SCOPE)
            self.assertEqual(proof['requirement'],TOKEN)
            for name,content in [('Model.json',json.dumps(model)),('Model.md',render_model_markdown(model))]:
                out=root/name;out.write_text(content,encoding='utf8')
                self.assertEqual(validate(p,pi,tce,out,domain_specs=[r])['status'],'passed')
            obligations=generate(p,pi,tce,domain_specs=[r])
            for evidence,expected in [({'status':'passed'},'passed'),({'status':'blocked'},'inconclusive')]:
                result=aggregate(obligations,model_conformance=evidence)
                ob=next(x for x in result['items'] if x['source_ref'].endswith('#demo.output.presence'))
                self.assertEqual(ob['status'],expected,ob)
            model['intrinsic_rule_proofs'][0]['scope']=SCOPE.replace('submit_result','other')
            out=root/'forged.json';out.write_text(json.dumps(model),encoding='utf8')
            self.assertEqual(validate(p,pi,tce,out,domain_specs=[r])['status'],'blocked')

    def test_canonical_closure_and_source_binding(self):
        for opts,expected in [({},'passed'),({'scope':SCOPE.replace('submit_result','unknown')},'inconclusive'),({'partial':True},'inconclusive')]:
            with self.subTest(opts=opts),tempfile.TemporaryDirectory() as d:
                root=Path(d);sources=source(root,**opts)
                work={'schema':'cat-work/v1','id':'demo.fresh-output.work','entry':'confirmed-spec',
                      'mode':'implementation','flow':'spec-implementation','work_kind':'implementation',
                      'parent':'','depends_on':[],'issue_ref':'spec-entry','project_entry_ref':'project-entry',
                      'normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],
                      'specification':{'status':'confirmed','decision_ref':'decision','artifact_refs':['demo.tce']},
                      'scope':{'process_ids':['demo.process'],'changed_ids':[],'preserved_ids':[]},
                      'technologies':[],'repositories':[],'checks':[],'gates':[],
                      'compilation':{'schema':'cat-compile/v2','process':'Process.md','pi':'PI.md','tce':'TCE.md',
                                     'domain_specs':['Rule.md'],'model':'Model.json','allow_draft':False,'allow_partial':True}}
                path=root/'Work.json';path.write_text(json.dumps(work),encoding='utf8')
                argv=[sys.executable,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts/cat_flow.py'),
                      'conformance','--work',str(path),'--kind','process-closure']
                run=subprocess.run(argv,capture_output=True,text=True,timeout=75)
                self.assertEqual(run.returncode,0,(run.stdout,run.stderr))
                gate=json.loads(run.stdout);self.assertEqual(gate['status'],expected,gate)
                receipt=root/'.cat-flow/conformance/process-closure.json'
                model=root/'.cat-flow/cache/process-closure.model.json'
                digest=lambda x:hashlib.sha256(x.read_bytes()).hexdigest()
                print('FRESH-OUTPUT-GATE',json.dumps({'status':gate['status'],'exit':run.returncode,
                      'source_sha256':{x.name:digest(x) for x in sources},'receipt_sha256':digest(receipt),
                      'model_sha256':digest(model)},sort_keys=True),flush=True)

    def test_wrong_scope_presence_and_unconfirmed_remain_unproved(self):
        for options in ({'scope':SCOPE.replace('demo.process.pi','demo.other.pi')},
                        {'scope':SCOPE.replace('submit_result','unknown')},
                        {'scope':SCOPE.replace('output.accepted','state.ready')},
                        {'scope':SCOPE.replace(' submit ',' other ')},
                        {'token':'@cat:unknown/v1'}, {'presence':'required'},
                        {'presence':'absent'}, {'presence':'undefined'},
                        {'provide':False}, {'confirmed':False}):
            with self.subTest(options=options),tempfile.TemporaryDirectory() as d:
                p,pi,tce,r=source(Path(d),**options)
                model=load(p,pi,tce,domain_specs=[r],allow_draft=True,allow_partial=True)
                self.assertEqual(model['intrinsic_rule_proofs'],[])
                self.assertIn('demo.output.presence',model['unverified_rule_ids'])

if __name__=='__main__':unittest.main()
