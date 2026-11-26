"""Source-conformed finite correlated output tuples must satisfy receiving PI constraints."""
import hashlib, json, subprocess, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts'))
from test_cat_compile_readable import write_v2
from cat_compile_v2 import load
from cat_process_composition import compose, CompositionError


def fixture(root,wrong=False):
    models=[];assemblies={}
    for name in ('producer','consumer'):
        folder=root/name;folder.mkdir();p,pi,t=write_v2(folder,False)
        for f in (p,pi,t):f.write_text(f.read_text().replace('demo.process',f'demo.{name}').replace('demo.user','demo.consumer' if name=='producer' else 'demo.producer').replace('status: draft','status: confirmed').replace("decision_ref: ''",'decision_ref: synthetic-test-only'),encoding='utf8')
        if name=='producer':
            pi.write_text(pi.read_text().replace('| output.accepted | send | boolean | required |','| output.accepted | send | boolean | required |\n| output.copy | send | boolean | required |').replace('| submit_op | accept | submit |','| submit_op | accept | submit |\n| reply_op | provide | submit |'),encoding='utf8')
            t.write_text(t.read_text().replace('output.accepted = true','output.accepted = true; output.copy = '+('false' if wrong else 'true')).replace('output.accepted = false','output.accepted = false; output.copy = false'),encoding='utf8')
        else:
            pi.write_text(pi.read_text().replace('bidirectional','receive').replace('| output.accepted | send | boolean | required |','| input.copy | receive | boolean | required |')+'\n| `input.enabled == input.copy` |\n',encoding='utf8')
            t.write_text(t.read_text().replace('state.ready = true; output.accepted = true','state.ready = true').replace('output.accepted = false','state.ready = false'),encoding='utf8')
        model=folder/'Model.json';model.write_text(json.dumps(load(p,pi,t)),encoding='utf8');models.append(model)
        def entry(f):return {'path':f.relative_to(root).as_posix(),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
        assemblies['demo.'+name]={'process':entry(p),'pis':[entry(pi)],'tces':[entry(t)]}
    binding={'schema':'cat-process-bindings/v1','model_sha256':{'demo.'+name:hashlib.sha256(model.read_bytes()).hexdigest() for name,model in zip(('producer','consumer'),models)},'source_assemblies':assemblies,'links':[{'source_process':'demo.producer','source_pi':'demo.producer.pi','source_operation':'reply_op','target_process':'demo.consumer','target_pi':'demo.consumer.pi','target_operation':'submit_op','field_links':[{'source_field':'output.accepted','target_field':'input.enabled'},{'source_field':'output.copy','target_field':'input.copy'}]}]}
    path=root/'Bindings.json';path.write_text(json.dumps(binding),encoding='utf8');return models,path,binding

class SourceBoundCompositionRelation(unittest.TestCase):
    def test_joint_relation_and_counterexample(self):
        for wrong in (False,True):
            with self.subTest(wrong=wrong),tempfile.TemporaryDirectory() as d:
                models,binding,_=fixture(Path(d),wrong);result=compose(models,binding)
                link=result['bindings'][0];self.assertEqual(link['status'],'structurally-matched')
                self.assertEqual(link['relation_status'],'refuted' if wrong else 'proved')
                self.assertEqual(result['status'],'blocked' if wrong else 'inconclusive')
                if wrong:self.assertEqual(link['relation_counterexample'],{'input.enabled':True,'input.copy':False})
                self.assertEqual(set(result['source_conformance']),{'demo.producer','demo.consumer'})
    def test_canonical_gate_keeps_interleaving_open_and_rejects_bad_tuple(self):
        for wrong in (False,True):
            with self.subTest(wrong=wrong),tempfile.TemporaryDirectory() as d:
                root=Path(d);models,path,_=fixture(root,wrong)
                work={'schema':'cat-work/v1','id':'demo.composition.work','entry':'confirmed-spec','mode':'implementation','flow':'spec-implementation','work_kind':'implementation','parent':'','depends_on':[],'issue_ref':'spec-entry','project_entry_ref':'project-entry','normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],'specification':{'status':'confirmed','decision_ref':'decision','artifact_refs':['demo.tce']},'scope':{'process_ids':['demo.producer','demo.consumer'],'changed_ids':[],'preserved_ids':[]},'technologies':[],'repositories':[],'checks':[],'gates':[],'compilation':{'schema':'cat-compile/v2','process':'producer/Process.md','pi':'producer/PI.md','tce':'producer/TCE.md','model':'producer/Model.json','allow_draft':False,'allow_partial':True,'composition_models':[x.relative_to(root).as_posix() for x in models],'composition_binding':'Bindings.json'}}
                w=root/'Work.json';w.write_text(json.dumps(work),encoding='utf8')
                run=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts/cat_flow.py'),'conformance','--work',str(w),'--kind','process-closure'],text=True,capture_output=True,timeout=75)
                self.assertEqual(run.returncode,2 if wrong else 0,run.stderr)
                gate=json.loads(run.stdout);self.assertEqual(gate['status'],'blocked' if wrong else 'inconclusive',gate)
                receipt=json.loads((root/'.cat-flow/cache/process-composition.json').read_text())
                self.assertEqual(receipt['bindings'][0]['relation_status'],'refuted' if wrong else 'proved')
                print('COMPOSITION-RELATION-GATE',json.dumps({'status':gate['status'],'relation_status':receipt['bindings'][0]['relation_status'],'binding_sha256':receipt['binding_sha256'],'model_sha256':receipt['model_sha256'],'receipt_sha256':hashlib.sha256((root/'.cat-flow/cache/process-composition.json').read_bytes()).hexdigest()},sort_keys=True),flush=True)

    def test_explicit_execution_origin_conditional_relation(self):
        for wrong in (False,True):
            with self.subTest(wrong=wrong),tempfile.TemporaryDirectory() as d:
                root=Path(d);models,path,binding=fixture(root,wrong)
                pi=root/'consumer/PI.md';pi.write_text(pi.read_text().replace('| demo.producer | receive |','| @execution-origin | receive |'),encoding='utf8')
                model=models[1];model.write_text(json.dumps(load(root/'consumer/Process.md',pi,root/'consumer/TCE.md')),encoding='utf8')
                binding['source_assemblies']['demo.consumer']['pis'][0]['sha256']=hashlib.sha256(pi.read_bytes()).hexdigest()
                binding['model_sha256']['demo.consumer']=hashlib.sha256(model.read_bytes()).hexdigest()
                link=binding['links'][0]
                link['execution_origin']={'process':'demo.producer','request_source_operation':'reply_op','request_target_operation':'submit_op'}
                path.write_text(json.dumps(binding),encoding='utf8')
                result=compose(models,path)
                self.assertEqual(result['bindings'][0]['relation_status'],'refuted' if wrong else 'proved')
                self.assertEqual(result['status'],'blocked' if wrong else 'inconclusive')
                self.assertFalse(result['bindings'][0]['external_effects_verified'])
                for key,val in [('process','demo.other'),('request_target_operation','wrong')]:
                    context=link['execution_origin'];old=context[key];context[key]=val
                    path.write_text(json.dumps(binding),encoding='utf8')
                    with self.assertRaisesRegex(CompositionError,'scope mismatch'):compose(models,path)
                    context[key]=old

    def test_no_model_only_relation_claim_and_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);models,path,binding=fixture(root)
            source=binding.pop('source_assemblies');path.write_text(json.dumps(binding),encoding='utf8')
            self.assertNotIn('relation_status',compose(models,path)['bindings'][0])
            binding['source_assemblies']=source;path.write_text(json.dumps(binding),encoding='utf8')
            f=root/'producer'/'TCE.md';f.write_text(f.read_text()+'\n',encoding='utf8')
            with self.assertRaisesRegex(CompositionError,'Source hash'):compose(models,path)
            source['demo.producer']['tces'][0]['sha256']=hashlib.sha256(f.read_bytes()).hexdigest();path.write_text(json.dumps(binding),encoding='utf8')
            with self.assertRaisesRegex(CompositionError,'Source-to-Model'):compose(models,path)
if __name__=='__main__':unittest.main()
