"""Source-bound exact relation proofs, independent of product implementation."""
import json
import tempfile
import unittest
from pathlib import Path
from test_projection_unused_typed_sibling import fixture
from test_scoped_output_presence import artifact, gate
from cat_compile_v2 import load, render_model_markdown
from cat_model_conformance import validate

OBS='@cat:observed-transition-relation/v1'
STRUCT='@cat:finite-structural-transition-relation/v1'
OLD='@cat:finite-transition-relation/v1'

def source(root, profile, variant='direct', mutation=None):
    p,pi,t=fixture(root,'string')
    binding={'trigger':'compare','pi':'probe.presence.pi','operation':'request','peer':'probe.caller','cut':'trigger-entry','source':'synthetic.received-result'}
    scope={'trigger':'compare','pi':'probe.presence.pi','operation':'request','peer':'probe.caller','provide':'reply','when':'true','fields':['output.answer']}
    def replace(path,old,new):
        s=path.read_text(encoding='utf8');assert old in s,(old,path);path.write_text(s.replace(old,new),encoding='utf8')
    def rows(text):
        s=t.read_text(encoding='utf8').split('\n| equal |')[0];t.write_text(s+'\n'+text+'\n',encoding='utf8')
    extra_rules=''
    extra_types=''
    if profile==OBS:
        replace(pi,'record<version:integer,metadata:string>','boolean')
        if mutation=='peer':binding['peer']='probe.other'
        if mutation=='owner':binding['pi']='probe.other.pi'
        if mutation=='cut':binding['cut']='future'
        if mutation=='operation':binding['operation']='other'
        origin='same-execution-observation '+json.dumps(binding,separators=(',',':'))
        if mutation=='unbound':origin='synthetic.received-result'
        availability='' if mutation=='availability' else 'compare'
        replace(p,'| ID | Source | Domain |\n| --- | --- | --- |',f'| ID | Source | Domain | Available on |\n| --- | --- | --- | --- |\n| observation.received | {origin} | boolean | {availability} |')
        scope.update(observations=['observation.received'],relation='after.output.answer == observation.received')
        if variant=='branch':
            replace(t,'input.request.version == state.version','observation.received')
        elif variant=='nondeterministic':
            rows('| choice | compare | `true` | 1 | `output.answer = observation.received` |\n| choice | compare | `true` | 2 | `output.answer = not observation.received` |')
            scope['relation']='after.output.answer == observation.received or after.output.answer != observation.received'
        else:rows('| direct | compare | `true` | 1 | `output.answer = observation.received` |')
        if variant=='restricted':
            replace(p,'state.version | integer','state.version | boolean')
            scope['relation']='after.output.answer == state.version'
            expr='observation.received == state.version' if mutation!='wrong-constraint' else 'observation.received != state.version'
            if mutation!='missing-constraint':extra_rules=f'\n| relation.valid-observation | observation-relation compare {expr} | @cat:trigger-observation-relation/v1 | cat:intrinsic-model/v1 |'
        if mutation=='inventory':scope['observations']=[]
        if mutation=='reverse':scope['relation']='after.output.answer != observation.received'
        if mutation=='extra':scope['relation']='after.output.answer == observation.received or after.output.answer != observation.received'
        if mutation=='missing-result':scope['relation']='after.output.answer == observation.received'
    elif profile==STRUCT:
        domain={'nullable':'nullable<boolean>','union':'union<boolean,enum{red,blue}>','named':'ref<ProbeRecord>','members':'record<flag:boolean,mode:boolean>'}.get(variant,'record<flag:boolean,detail[optional]:nullable<boolean>>')
        if variant=='named':extra_types='\n## Types\n| ID | Domain |\n| --- | --- |\n| ProbeRecord | record<flag:boolean,detail[optional]:nullable<boolean>> |'
        replace(pi,'record<version:integer,metadata:string>',domain)
        replace(pi,'| output.answer | send | boolean |',f'| output.answer | send | {domain} |')
        if variant=='reordered':replace(pi,f'| output.answer | send | {domain} |','| output.answer | send | record<detail[optional]:nullable<boolean>,flag:boolean> |')
        if variant=='branch':rows('| yes | compare | `input.request.flag` | 1 | `output.answer = input.request` |\n| no | compare | `not input.request.flag` | 1 | `output.answer = input.request` |')
        else:rows('| direct | compare | `true` | 1 | `output.answer = input.request` |')
        scope['relation']='after.output.answer == input.request'
        if variant=='members':scope['relation']='after.output.answer.flag == input.request.flag and after.output.answer.mode == input.request.mode'
        if mutation=='partial-members':scope['relation']='after.output.answer.flag == input.request.flag'
        if mutation=='reverse':scope['relation']='after.output.answer != input.request'
        if mutation=='extra':scope['relation']='true'
    else:
        replace(pi,'record<version:integer,metadata:string>','boolean')
        replace(t,'input.request.version == state.version','input.request')
        scope['relation']='after.output.answer == input.request'
    if mutation=='empty-when':scope['when']='false'
    prefix={OLD:'transition-relation',OBS:'observed-transition-relation',STRUCT:'finite-structural-transition-relation'}[profile]
    if mutation=='token':prefix='transition-relation'
    condition=prefix+' '+json.dumps(scope,separators=(',',':'))
    r=root/'Rule.md';r.write_text(artifact('domain-spec','probe.presence.relation',[],f'''# Domain Specification
## Targets
| Ref | Aspect |
| --- | --- |
| probe.presence | Result relation |
## Rules
| ID | Condition | Requirement | Verification |
| --- | --- | --- | --- |
| relation.rule | {condition} | {profile} | cat:intrinsic-model/v1 |{extra_rules}{extra_types}'''),encoding='utf8')
    return p,pi,t,r

class ExactRelationTests(unittest.TestCase):
    def check(self,profile,variant='direct',mutation=None,expected=True):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p,pi,t,r=source(root,profile,variant,mutation)
            run=gate(root)
            if run.returncode!=0:
                self.assertFalse(expected,(run.stdout,run.stderr));return
            status=json.loads(run.stdout)['status']
            self.assertEqual(status=='passed',expected,(variant,mutation,run.stdout))
            m=load(p,pi,t,domain_specs=[r],allow_partial=True)
            self.assertEqual(any(x['rule_id']=='relation.rule' for x in m['intrinsic_rule_proofs']),expected)
            for name,body in [('Check.json',json.dumps(m)),('Check.md',render_model_markdown(m))]:
                out=root/name;out.write_text(body,encoding='utf8')
                self.assertEqual(validate(p,pi,t,out,domain_specs=[r])['status'],'passed')
            if expected:
                from cat_implementation_obligations import generate,aggregate
                obligations=generate(p,pi,t,domain_specs=[r])
                aggregated=aggregate(obligations,model_conformance=validate(p,pi,t,out,domain_specs=[r]))
                norm=next(x for x in aggregated['items'] if x['id']=='normative-rule.relation.rule')
                self.assertEqual(norm['status'],'passed')
                without_evidence=aggregate(obligations)
                self.assertEqual(next(x for x in without_evidence['items'] if x['id']=='normative-rule.relation.rule')['status'],'inconclusive')
                m['intrinsic_rule_proofs'][0]['source_sha256']='0'*64
                out=root/'Forged.json';out.write_text(json.dumps(m),encoding='utf8')
                self.assertNotEqual(validate(p,pi,t,out,domain_specs=[r])['status'],'passed')
    def test_old(self):self.check(OLD)
    def test_observation_equivalent_forms(self):
        for variant in ('direct','branch','nondeterministic'):
            with self.subTest(variant=variant):self.check(OBS,variant)
    def test_structural_equivalent_forms(self):
        for variant in ('direct','branch','reordered','nullable','union','named','members'):
            with self.subTest(variant=variant):self.check(STRUCT,variant)
    def test_negative_observation(self):
        for mutation in ('peer','owner','cut','operation','unbound','inventory','reverse','extra','token','availability','empty-when'):
            with self.subTest(mutation=mutation):self.check(OBS,mutation=mutation,expected=False)
        self.check(OBS,'nondeterministic','missing-result',False)
    def test_observation_constraint(self):
        self.check(OBS,'restricted')
        for mutation in ('missing-constraint','wrong-constraint'):
            with self.subTest(mutation=mutation):self.check(OBS,'restricted',mutation,False)
    def test_negative_structural(self):
        for mutation in ('reverse','extra','token','empty-when'):
            with self.subTest(mutation=mutation):self.check(STRUCT,mutation=mutation,expected=False)

        self.check(STRUCT,'members','partial-members',False)

    def test_changed_source_invalidates_receipt_and_model(self):
        from cat_flow import conformance_evidence_status
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p,pi,t,r=source(root,OBS)
            run=gate(root);self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(json.loads(run.stdout)['status'],'passed')
            work=root/'Work.json';w=json.loads(work.read_text(encoding='utf8'))
            self.assertEqual(conformance_evidence_status(work,w,'process-closure')['status'],'passed')
            model=root/'.cat-flow/cache/process-closure.model.json'
            self.assertTrue(model.is_file())
            p.write_text(p.read_text(encoding='utf8').replace('trigger-entry','future'),encoding='utf8')
            self.assertEqual(conformance_evidence_status(work,w,'process-closure')['status'],'stale')
            self.assertNotEqual(validate(p,pi,t,model,domain_specs=[r])['status'],'passed')
            self.assertNotEqual(json.loads(gate(root).stdout)['status'],'passed')

    def test_observation_vectors_and_queue(self):
        from copy import deepcopy
        from cat_compile_v2 import (selection_vectors, expand_cases, make_queue,
                                    validate_queue, Blocked, emit_vitest, emit_junit, _vitest_renderer)
        for variant in ('direct','branch','nondeterministic','restricted'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as td:
                root=Path(td);p,pi,t,r=source(root,OBS,variant)
                self.assertEqual(json.loads(gate(root).stdout)['status'],'passed')
                m=load(p,pi,t,domain_specs=[r])
                v=selection_vectors(m)
                cases=expand_cases(m,v)
                self.assertTrue(cases)
                for c in cases:
                    self.assertEqual(set(c['observations']),{'observation.received'})
                    self.assertNotIn('observation.received',c['input'])
                    value=c['observations']['observation.received']
                    if variant=='nondeterministic':
                        self.assertEqual({a['output']['output.answer'] for a in c['allowed']},{True,False})
                    else:
                        self.assertEqual({a['output']['output.answer'] for a in c['allowed']},{value})
                    if variant=='restricted':self.assertEqual(value,c['initial_state']['state.version'])
                vitest=root/'VitestBinding.json';vitest.write_text(json.dumps({'schema':'cat-test-driver/v2','process':m['process'],'driver':'./driver'}))
                junit=root/'JUnitBinding.json';junit.write_text(json.dumps({'schema':'cat-junit-driver-binding/v1','process':m['process'],'test_package':'probe','test_class':'ProbeTest','driver_class':'probe.Driver','capability_scope':{'kind':'pi-only-unverified','observations':['observation.received'],'actions':[]}}))
                with self.assertRaisesRegex(Blocked,'observation/action'):emit_vitest(m,v,vitest)
                with self.assertRaisesRegex(Blocked,'observed test environment'):emit_junit(m,v,junit)
                with self.assertRaisesRegex(ValueError,'observed test environment'):_vitest_renderer()(m,cases,{'driver':'./driver'})
                mb=json.dumps(m).encode();vb=json.dumps(v).encode()
                q=make_queue(m,v,mb,vb);validate_queue(q,m,v,mb,vb)
                for mutation in ('missing','extra','wrong-type','caller-input','unproved','future','wrong-owner','constraint'):
                    if mutation=='constraint' and variant!='restricted':continue
                    bad=deepcopy(v);bad_model=deepcopy(m);c=bad['cases'][0]
                    if mutation=='missing':del c['observations']
                    elif mutation=='extra':c['observations']['other']=True
                    elif mutation=='wrong-type':c['observations']['observation.received']=1
                    elif mutation=='caller-input':c['input']['observation.received']=True
                    elif mutation=='unproved':bad_model['intrinsic_rule_proofs']=[]
                    elif mutation in ('future','wrong-owner'):
                        f=next(f for f in bad_model['fields'] if f['id']=='observation.received')
                        f['source']=f['source'].replace('trigger-entry','future') if mutation=='future' else f['source'].replace('probe.presence.pi','other.pi')
                    elif mutation=='constraint':c['observations']['observation.received']=not c['state']['state.version']
                    with self.subTest(mutation=mutation), self.assertRaises(Blocked):expand_cases(bad_model,bad)
