"""Required record projections keep wire values and typed member bindings."""
import json,sys,tempfile,unittest,subprocess,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts'))
from test_cat_compile_readable import write_v2
from cat_compile_v2 import Blocked,load,selection_vectors,expand_cases,render_model_markdown,emit_vitest
from cat_model_conformance import validate

class RequiredRecordMemberTests(unittest.TestCase):
    def source(self,root,domain='record<id:string,expected_version:integer[1..]>',presence='required',member='expected_version',other='state.version',confirmed=True):
        p,pi,tce=write_v2(root,False)
        p.write_text(p.read_text(encoding='utf8').replace('| state.ready | boolean |','| state.ready | boolean |\n| state.version | integer[1..] |'),encoding='utf8')
        pi.write_text(pi.read_text(encoding='utf8').replace('| input.enabled | receive | boolean | required |',f'| input.request | receive | {domain} | {presence} |'),encoding='utf8')
        tce.write_text(tce.read_text(encoding='utf8').replace('`input.enabled`',f'`input.request.{member} == {other}`').replace('`not input.enabled`',f'`input.request.{member} != {other}`'),encoding='utf8')
        if confirmed:
            for path in (p,pi,tce):path.write_text(path.read_text(encoding='utf8').replace('status: draft','status: confirmed').replace("decision_ref: ''",'decision_ref: synthetic-test-only'),encoding='utf8')
        return p,pi,tce
    def test_record_member_version_equality_and_vectors(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);sources=self.source(root);model=load(*sources,allow_partial=True)
            self.assertEqual(model['status'],'confirmed',model['coverage_checks'])
            self.assertEqual(model['coverage_checks']['submit']['proof_method'],'required-record-member-partition/v1')
            self.assertNotIn('input.request.expected_version',{f['id'] for f in model['fields']})
            for name,content in [('Model.json',json.dumps(model)),('Model.md',render_model_markdown(model))]:
                out=root/name;out.write_text(content,encoding='utf8');self.assertEqual(validate(*sources,out)['status'],'passed')
            vectors=selection_vectors(model);cases=expand_cases(model,vectors)
            self.assertEqual(len(cases),2)
            for case in vectors['cases']:
                value=case['input']['input.request']['expected_version'];before=case['state']['state.version']
                self.assertEqual(value==before,'demo.accept' in case['id'])
            binding=root/'Binding.json';binding.write_text(json.dumps({'schema':'cat-test-driver/v2','process':model['process'],'driver':'./driver'}),encoding='utf8')
            generated=emit_vitest(model,vectors,binding)
            self.assertIn('expected_version',generated)
            self.assertIn('input.request',generated)
            for invalid in ({}, {'input.request':{'id':'a'}},{'input.request':{'id':'a','expected_version':'1'}}):
                bad=json.loads(json.dumps(vectors));bad['cases'][0]['input']=invalid
                with self.assertRaises(Blocked):expand_cases(model,bad)
            forged=json.loads(json.dumps(model));forged['rules'][0]['when']['args'][0]['args'][1]['literal']='id'
            out=root/'forged.json';out.write_text(json.dumps(forged),encoding='utf8');self.assertEqual(validate(*sources,out)['status'],'blocked')
            forged=json.loads(json.dumps(model));forged['rules'][0]['when']['args'][0]={'ref':'member[input.request, \"expected_version\"]'}
            out.write_text(json.dumps(forged),encoding='utf8');self.assertEqual(validate(*sources,out)['status'],'blocked')
    def test_id_and_version_relation_with_direct_member_effect(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p,pi,tce=self.source(root)
            p.write_text(p.read_text(encoding='utf8').replace('| state.version | integer[1..] |','| state.version | integer[1..] |\n| state.target_id | string |'),encoding='utf8')
            pi.write_text(pi.read_text(encoding='utf8').replace('| output.accepted | send | boolean | required |','| output.accepted | send | boolean | required |\n| output.version | send | integer[1..] | required |'),encoding='utf8')
            text=tce.read_text(encoding='utf8').replace('`input.request.expected_version == state.version`','`input.request.id == state.target_id and input.request.expected_version == state.version`').replace('`input.request.expected_version != state.version`','`input.request.id == state.target_id and input.request.expected_version != state.version`')
            text=text.replace('output.accepted = true`','output.accepted = true; output.version = input.request.expected_version`').replace('output.accepted = false`','output.accepted = false; output.version = input.request.expected_version`')
            text+='| demo.different | submit | `input.request.id != state.target_id` | 1 | `output.accepted = false; output.version = input.request.expected_version` |\n'
            tce.write_text(text,encoding='utf8')
            model=load(p,pi,tce,allow_partial=True);self.assertEqual(model['status'],'confirmed',model['coverage_checks'])
            out=root/'Model.json';out.write_text(json.dumps(model),encoding='utf8');self.assertEqual(validate(p,pi,tce,out)['status'],'passed')
            for case in expand_cases(model,selection_vectors(model)):
                parent=case['input']['input.request'];state=case['initial_state']
                self.assertEqual(case['allowed'][0]['output']['output.version'],parent['expected_version'])
                accepted=parent['id']==state['state.target_id'] and parent['expected_version']==state['state.version']
                self.assertEqual(case['allowed'][0]['output']['output.accepted'],accepted)
            # Formal Gate consumes the same Source-bound model and independent receipt.
            work={'schema':'cat-work/v1','id':'demo.record.work','entry':'confirmed-spec',
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
            for gap in (False,True):
                if gap:tce.write_text('\n'.join(line for line in text.split('\n') if not line.startswith('| demo.different |')),encoding='utf8')
                run=subprocess.run(argv,capture_output=True,text=True,timeout=75)
                self.assertEqual(run.returncode,0,(run.stdout,run.stderr));gate=json.loads(run.stdout)
                self.assertEqual(gate['status'],'inconclusive' if gap else 'passed',gate)
                digest=lambda x:hashlib.sha256(x.read_bytes()).hexdigest()
                print('RECORD-PROJECTION-GATE',json.dumps({'status':gate['status'],'exit':run.returncode,
                    'source_sha256':{x.name:digest(x) for x in (p,pi,tce)},
                    'receipt_sha256':digest(root/'.cat-flow/conformance/process-closure.json'),
                    'model_sha256':digest(root/'.cat-flow/cache/process-closure.model.json')},sort_keys=True),flush=True)

    def test_operation_override_blocks_projection(self):
        with tempfile.TemporaryDirectory() as d:
            p,pi,tce=self.source(Path(d))
            pi.write_text(pi.read_text(encoding='utf8')+'\n## Operation presence\n| Operation | Field | Presence |\n| --- | --- | --- |\n| submit_op | input.request | optional |\n',encoding='utf8')
            with self.assertRaisesRegex(Blocked,'nonrequired'):load(p,pi,tce,allow_partial=True)

    def test_reject_missing_optional_and_mistyped(self):
        for opts in ({'member':'unknown'}, {'presence':'optional'}, {'domain':'record<id:string,expected_version[optional]:integer[1..]>'},{'domain':'record<id:string,expected_version:nullable<integer>>'},{'other':'"wrong"'}):
            with self.subTest(opts=opts),tempfile.TemporaryDirectory() as d:
                with self.assertRaises(Blocked):load(*self.source(Path(d),**opts),allow_partial=True)
if __name__=='__main__':unittest.main()
