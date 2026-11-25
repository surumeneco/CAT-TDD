"""Source-bound exact structural equality is not a finite sequence sample."""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / '.cat-system/scripts'
sys.path.insert(0, str(SCRIPTS))
from cat_compile_v2 import load, render_model_markdown, expand_cases, selection_vectors
from cat_model_conformance import validate
from catlib import semantic_json_instant as exact
from decimal import Decimal


def source(kind, suffix, refs, body):
    return (f"---\ncat_version: '0.3'\nkind: {kind}\nid: copyprobe{suffix}\nstatus: confirmed\n"
            'process: copyprobe\nsource_refs: ["synthetic-test-only"]\n'
            f'decision_ref: synthetic-test-only\nrefs: {json.dumps(refs)}\n'
            'semantic_contract: markdown-v2\nlanguage: en\n---\n\n' + body + '\n')


def fixture(root, *, rhs='input.items', relation='after.output.items == input.items',
            second=None, peer='copycaller', operation='request', provide='reply',
            domain='sequence<record<id:integer[1..],enabled:boolean>>', target_domain=None,
            presence='required', token='@cat:structural-copy-relation/v1',
            prefix='structural-copy-relation ', guard='true'):
    p, pi, tce, spec = (root/n for n in ('Process.md','PI.md','TCE.md','Contract.md'))
    p.write_text(source('process','',['copyprobe.pi'],'''# Process
## Contract
Closed world: true
## Interfaces
| PI |
| --- |
| copyprobe.pi |
## State
| ID | Domain |
| --- | --- |
## Observations
| ID | Source | Domain |
| --- | --- | --- |
## Actions
| ID | Target | Domain |
| --- | --- | --- |
## Triggers
| ID | Source |
| --- | --- |
| receive | copyprobe.pi/request |'''),encoding='utf-8')
    pi.write_text(source('pi','.pi',['copyprobe'],f'''# PI
## Boundary
| Peer process | Direction |
| --- | --- |
| copycaller | bidirectional |
## Fields
| ID | Direction | Domain | Presence |
| --- | --- | --- | --- |
| input.items | receive | {domain} | {presence} |
| input.other | receive | {domain} | required |
| output.items | send | {target_domain or domain} | required |
## Operations
| ID | Direction | Trigger |
| --- | --- | --- |
| request | accept | receive |
| reply | provide | receive |
## Constraints
| Expression |
| --- |'''),encoding='utf-8')
    body=f'''# TCE
Coverage requirement: closed
## Behaviors
| ID | Trigger | Condition | Outcome | Effects |
| --- | --- | --- | --- | --- |
| copy | receive | `{guard}` | 1 | `output.items = {rhs}` |'''
    if second is not None:
        body+=f'\n| copy | receive | `{guard}` | 2 | `output.items = {second}` |'
    tce.write_text(source('tce','.tce',['copyprobe.pi'],body),encoding='utf-8')
    scope={'trigger':'receive','pi':'copyprobe.pi','operation':operation,'provide':provide,
           'peer':peer,'when':'true','fields':['output.items'],'relation':relation}
    spec.write_text(source('domain-spec','.contract',[],f'''# Domain Specification
## Targets
| Ref | Aspect |
| --- | --- |
| copyprobe | Exact structural relation |
## Rules
| ID | Condition | Requirement | Verification |
| --- | --- | --- | --- |
| exact-copy | {prefix}{json.dumps(scope,separators=(',',':'))} | {token} | cat:intrinsic-model/v1 |'''),encoding='utf-8')
    work={'schema':'cat-work/v1','id':'copyprobe.work','entry':'confirmed-spec','mode':'implementation','flow':'spec-implementation','work_kind':'implementation','parent':'','depends_on':[],'issue_ref':'spec-entry','project_entry_ref':'project-entry','normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],'specification':{'status':'confirmed','decision_ref':'synthetic-test-only','artifact_refs':['copyprobe.tce']},'scope':{'process_ids':['copyprobe'],'changed_ids':[],'preserved_ids':[]},'technologies':['Vitest'],'repositories':[],'checks':[],'gates':[],'compilation':{'schema':'cat-compile/v2','process':p.name,'pi':pi.name,'tce':tce.name,'domain_specs':[spec.name],'model':'Model.json','vectors':'Vectors.json','queue':'Queue.json','binding':'Binding.json','tests_output':'Generated.test.ts','allow_draft':False,'allow_partial':True}}
    (root/'Work.json').write_text(json.dumps(work),encoding='utf-8')
    (root/'Binding.json').write_text(json.dumps({'schema':'cat-test-driver/v2','process':'copyprobe','driver':'./driver'}),encoding='utf-8')
    return p,pi,tce,spec


def flow(root, *args):
    command=[sys.executable,str(SCRIPTS/'cat_flow.py'),args[0],'--work',str(root/'Work.json'),*args[1:]]
    run=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=30)
    return run, json.loads(run.stdout)


class StructuralCopyTests(unittest.TestCase):
    def test_exact_copy_and_scope_rejections(self):
        variants=[({},'passed'),({'relation':'input.items == after.output.items'},'passed'),
                  ({'second':'input.items'},'passed'),({'rhs':'input.other'},'inconclusive'),
                  ({'second':'input.other'},'inconclusive'),({'peer':'othercaller'},'inconclusive'),
                  ({'operation':'unknown'},'inconclusive'),({'provide':'unknown'},'inconclusive'),
                  ({'relation':'after.output.items == input.items and after.output.items == input.other'},'inconclusive'),
                  ({'target_domain':'sequence<record<id:integer[0..],enabled:boolean>>'},'inconclusive'),
                  ({'token':'@cat:finite-transition-relation/v1','prefix':'transition-relation '},'inconclusive')]
        for variant,expected in variants:
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as td:
                root=Path(td);p,pi,tce,spec=fixture(root,**variant)
                run,result=flow(root,'conformance','--kind','process-closure')
                self.assertEqual(result['status'],expected,(run.stdout,run.stderr))
                self.assertEqual(run.returncode,0,(run.stdout,run.stderr))
                m=load(p,pi,tce,domain_specs=[spec],allow_partial=True)
                for name,body in [('Independent.json',json.dumps(m)),('Independent.md',render_model_markdown(m))]:
                    path=root/name;path.write_text(body,encoding='utf-8')
                    self.assertEqual(validate(p,pi,tce,path,domain_specs=[spec])['status'],'passed')
                self.assertEqual(bool(m['intrinsic_rule_proofs']),expected=='passed')

    def test_top_level_set_copy(self):
        for kw, expected in [({}, 'passed'), ({'rhs':'input.other'}, 'inconclusive'),
                             ({'second':'input.other'}, 'inconclusive'),
                             ({'peer':'wrong'}, 'inconclusive'),
                             ({'domain':'sequence<set<string>>'}, 'inconclusive')]:
            with self.subTest(kw=kw), tempfile.TemporaryDirectory() as td:
                root=Path(td)
                p,pi,tce,spec=fixture(root, **({'domain':'set<string>'}|kw))
                run,result=flow(root,'conformance','--kind','process-closure')
                self.assertEqual(result['status'],expected,(run.stdout,run.stderr))
                if expected!='passed':continue
                m=load(p,pi,tce,domain_specs=[spec]); vectors=selection_vectors(m)
                self.assertEqual(len(vectors['cases'][0]['input']['input.items']),2)
                for kind in ('model','vectors','queue','tests'):
                    run,result=flow(root,'compile','--kind',kind)
                    self.assertEqual(result['status'],'passed',(run.stdout,run.stderr))
                for name,body in [('Independent.json',json.dumps(m)),('Independent.md',render_model_markdown(m))]:
                    path=root/name;path.write_text(body,encoding='utf-8')
                    self.assertEqual(validate(p,pi,tce,path,domain_specs=[spec])['status'],'passed')

    def test_exact_semantic_value_transport(self):
        # Scope proof and technology transport are separate. A valid Source
        # never silently selects a lossy renderer or a product storage format.
        for domain in ('json','json-object','instant'):
            for kw, expected in [({},'passed'),({'rhs':'input.other'},'inconclusive')]:
                with self.subTest(domain=domain,kw=kw),tempfile.TemporaryDirectory() as td:
                    root=Path(td);p,pi,tce,spec=fixture(root,domain=domain,**kw)
                    run,result=flow(root,'conformance','--kind','process-closure')
                    self.assertEqual(result['status'],expected,(run.stdout,run.stderr))
                    if expected!='passed':continue
                    m=load(p,pi,tce,domain_specs=[spec])
                    for name,body in [('Independent.json',json.dumps(m)),('Independent.md',render_model_markdown(m))]:
                        path=root/name;path.write_text(body,encoding='utf-8')
                        self.assertEqual(validate(p,pi,tce,path,domain_specs=[spec])['status'],'passed')
                    for kind in ('model','vectors','queue'):
                        run,result=flow(root,'compile','--kind',kind)
                        self.assertEqual(result['status'],'passed',(run.stdout,run.stderr))
                    run,result=flow(root,'compile','--kind','tests')
                    self.assertEqual(result['status'],'blocked')
                    binding=root/'Binding.json'
                    content=json.loads(binding.read_text());content['semantic_value_transport']='cat-exact-values/v1'
                    binding.write_text(json.dumps(content),encoding='utf-8')
                    for check in ([],['--check']):
                        run,result=flow(root,'compile','--kind','tests',*check)
                        self.assertEqual(result['status'],'passed',(run.stdout,run.stderr))
                    vectors=json.loads((root/'Vectors.json').read_text())
                    case=expand_cases(m,vectors)[0]
                    self.assertEqual(case['input']['input.items'],case['allowed'][0]['output']['output.items'])
                    generated=(root/'Generated.test.ts').read_text()
                    self.assertIn('cat-exact-values/v1',generated)
                    self.assertIn('exactInstant' if domain=='instant' else 'exactJSON',generated)
                    self.assertIn('86400000000123' if domain=='instant' else '9007199254740993.125',generated)
                    content['semantic_value_transport']='unknown'
                    binding.write_text(json.dumps(content),encoding='utf-8')
                    self.assertEqual(flow(root,'compile','--kind','tests')[1]['status'],'blocked')

    def test_exact_wire_values_preserve_native_meaning(self):
        original={'$cat_json': [True,None,Decimal('9007199254740993.125')], 'items':[1,1]}
        decoded=exact.decode_json_transport(exact.encode_json_transport(original))
        self.assertTrue(exact.json_equal(original,decoded))
        self.assertFalse(exact.json_equal(original,{'items':[1,1]}))
        self.assertTrue(exact.json_equal(Decimal('1.0'),Decimal('1e0')))
        self.assertFalse(exact.json_equal(True,1))
        for value in ({'$cat_json':['number','NaN']},{'$cat_json':['number','01']},
                      {'$cat_json':['object',[['a',['null']],['a',['null']]]]},
                      {'$cat_json':['boolean',1]}, {'$cat_json':['null',0]}):
            with self.subTest(value=value),self.assertRaises(exact.BindingError):
                exact.decode_json_transport(value)
        a=exact.decode_offset_datetime('1970-01-02T00:00:00.000000123Z')
        b=exact.decode_offset_datetime('1970-01-02T09:00:00.000000123+09:00')
        c=exact.decode_offset_datetime('1970-01-02T00:00:00.000000124Z')
        self.assertEqual(a,b);self.assertNotEqual(a,c)
        self.assertEqual(exact.decode_instant_transport(exact.encode_instant_transport(a)),a)
        with self.assertRaises(exact.BindingError):
            exact.decode_instant_transport({'$cat_instant':{'n':'1','d':'0'}})

    def test_generation_and_structural_values(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p,pi,tce,spec=fixture(root)
            for kind in ('model','vectors','queue','tests'):
                for check in ([],['--check']):
                    run,result=flow(root,'compile','--kind',kind,*check)
                    self.assertEqual(run.returncode,0,(kind,run.stdout,run.stderr))
                    self.assertEqual(result['status'],'passed')
            smoke=os.environ.get('CAT_STRUCTURAL_COPY_VITEST_SMOKE_DIR')
            if smoke:
                dest=Path(smoke);dest.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(root/'Generated.test.ts',dest/'Generated.test.ts')
                (dest/'driver.ts').write_text("""export function createDriver() {
  return {
    async prepare() {}, async observeState() { return {}; },
    async trigger(_id: string, input: Record<string,unknown>) {
      const items = input['input.items'] as Record<string,unknown>[];
      const mode = process.env.CAT_COPY_MODE;
      if (mode === 'missing') return {};
      const value = mode === 'alternate' ? items.map(item => ({...item}))
        : mode === 'other' ? input['input.other']
        : mode === 'reverse' ? items.slice().reverse()
        : mode === 'drop' ? items.slice(1) : items.slice();
      return {'output.items': value};
    }
  };
}
""",encoding='utf-8')
            m=load(p,pi,tce,domain_specs=[spec]);vectors=selection_vectors(m)
            original=copy.deepcopy(vectors)
            a={'id':1,'enabled':True};b={'id':2,'enabled':False}
            # These are supplemental concrete oracle checks, not a replacement
            # for the deterministic selected vector or the symbolic theorem.
            for value in ([],[a],[a,b],[b,a],[a,a],[a,b]*50):
                with self.subTest(value=value):
                    test=copy.deepcopy(original);test['cases'][0]['input']['input.items']=value
                    test['cases'][0]['input']['input.other']=[] if value else [a]
                    cases=expand_cases(m,test)
                    self.assertEqual(cases[0]['allowed'][0]['output']['output.items'],value)
            # A forged certificate is independently rejected even if its shape
            # is identical to the real certificate.
            fake=copy.deepcopy(m)
            fake['intrinsic_rule_proofs'][0]['source_sha256']='0'*64
            path=root/'Fake.json';path.write_text(json.dumps(fake),encoding='utf-8')
            self.assertNotEqual(validate(p,pi,tce,path,domain_specs=[spec])['status'],'passed')


if __name__=='__main__':unittest.main()
