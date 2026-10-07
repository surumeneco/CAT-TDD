from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.cat-system' / 'scripts'))
sys.path.insert(0, str(ROOT / '.cat-system' / 'skills' / 'tech-typescript' / 'scripts'))

import cat_flow as flow
import cat_compile_v2 as compiler
import cat_implementation_obligations as obligations
import cat_typescript_conformance as inspector


CATEGORIES = ('interface','capability','behavior','invariant',
              'cross-process','domain','implementation-constraint')


class TypeScriptImplementationConformanceTest(unittest.TestCase):
    def confirmed_sources(self, root: Path):
        fixture = ROOT / 'tests' / 'fixtures' / 'minimal'
        result = []
        for name in ('Process.md','PI.md','TCE.md'):
            dest = root / name
            text = (fixture / name).read_text(encoding='utf-8')
            text = text.replace('status: draft','status: confirmed')
            text = text.replace("decision_ref: ''",'decision_ref: https://example.org/decision')
            dest.write_text(text,encoding='utf-8')
            result.append(dest)
        return tuple(result)

    def binding(self, root: Path):
        data = {
            'schema':'cat-typescript-conformance-binding/v1',
            'repository':'app',
            'source_globs':['src/**/*.ts'],
            'public_entrypoints':['src/api.ts'],
            'interface_symbols':{
                'submit':'送信要求',
                'provideResult':'結果提供',
            },
            'capabilities':{},
        }
        path=root/'conformance-binding.json'
        path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        return path

    def passed_obligations(self, root: Path):
        items=[]
        for category in CATEGORIES:
            items.append({
                'id':'demo.'+category,
                'category':category,
                'source_ref':'demo#'+category,
                'method':'fixture',
                'status':'passed',
                'evidence':'fixture:'+category,
                'limitation':'fixture-only',
            })
        path=root/'obligations.json'
        path.write_text(json.dumps({'schema':'cat-implementation-obligations/v1','items':items},
                                   ensure_ascii=False),encoding='utf-8')
        return path

    def work(self, root: Path, process, pi, tce, binding, obligation_path):
        return {
            'schema':'cat-work/v1','id':'demo.typescript.conformance',
            'entry':'confirmed-spec','mode':'implementation',
            'flow':'spec-implementation','work_kind':'implementation',
            'parent':'','depends_on':[],
            'issue_ref':'spec','project_entry_ref':'project',
            'normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],
            'specification':{'status':'confirmed','decision_ref':'decision','artifact_refs':['demo.process.tce']},
            'scope':{'process_ids':['demo.process'],'changed_ids':[],'preserved_ids':[]},
            'technologies':['TypeScript'],
            'repositories':[{
                'name':'app','path':'./app','allowed_paths':['src/**'],
                'production_paths':['src/**'],'test_paths':[]
            }],
            'checks':[],'gates':[],
            'compilation':{
                'schema':'cat-compile/v2',
                'process':str(process.name),'pi':str(pi.name),'tce':str(tce.name),
                'tces':[str(tce.name)],'model':'Model.md',
                'obligations':str(obligation_path.name),
                'conformance_binding':str(binding.name),
                'allow_draft':False,
            }
        }

    def write_api(self, repo: Path, extra='', capability=''):
        src=repo/'src';src.mkdir(parents=True,exist_ok=True)
        text='''export function submit() { return true; }
export function provideResult() { return false; }
'''
        if capability:
            text += capability + '\n'
        if extra:
            text += extra + '\n'
        (src/'api.ts').write_text(text,encoding='utf-8')

    def test_undeclared_network_capability_blocks_gate_even_when_obligations_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo=root/'app';self.write_api(
                repo,capability='export async function internalNetwork() { return fetch("https://example.invalid"); }')
            process,pi,tce=self.confirmed_sources(root)
            binding=self.binding(root);obs=self.passed_obligations(root)
            w=self.work(root,process,pi,tce,binding,obs)
            wp=root/'Work.json';wp.write_bytes(flow.json_bytes(w))
            result=flow.conformance_work(wp,w,'implementation-conformance')
            self.assertEqual(result['status'],'blocked')
            tech=result['technology_results'][0]
            self.assertTrue(any(x.get('item')=='network' for x in tech['violations']))

    def test_public_interface_not_in_pi_blocks_gate(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo=root/'app';self.write_api(
                repo,extra='export function undocumentedInterface() { return 1; }')
            process,pi,tce=self.confirmed_sources(root)
            binding=self.binding(root);obs=self.passed_obligations(root)
            w=self.work(root,process,pi,tce,binding,obs)
            wp=root/'Work.json';wp.write_bytes(flow.json_bytes(w))
            result=flow.conformance_work(wp,w,'implementation-conformance')
            self.assertEqual(result['status'],'blocked')
            tech=result['technology_results'][0]
            self.assertTrue(any(x.get('item')=='undocumentedInterface' for x in tech['violations']))

    def test_declared_interface_with_no_external_capability_passes_inspector(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo=root/'app';self.write_api(repo)
            process,pi,_=self.confirmed_sources(root)
            binding=self.binding(root)
            result=inspector.inspect(repo,binding,process,pi)
            self.assertEqual(result['status'],'passed',result)

    def test_obligation_generator_derives_all_categories_and_starts_not_run(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);process,pi,tce=self.confirmed_sources(root)
            result=obligations.generate(process,pi,[tce],technologies=['TypeScript'])
            self.assertEqual(result['schema'],'cat-implementation-obligations/v1')
            self.assertEqual({x['category'] for x in result['items']},set(CATEGORIES))
            self.assertTrue(all(x['status']=='not-run' for x in result['items']))
            self.assertTrue(all(x['source_ref'] and x['method'] for x in result['items']))


    def test_flow_generates_obligation_skeleton_without_claiming_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo=root/'app';self.write_api(repo)
            process,pi,tce=self.confirmed_sources(root)
            binding=self.binding(root)
            target=root/'obligations.json'
            w=self.work(root,process,pi,tce,binding,target)
            wp=root/'Work.json';wp.write_bytes(flow.json_bytes(w))
            result=flow.obligations_work(wp,w,False)
            self.assertEqual(result['status'],'passed',result)
            data=json.loads(target.read_text(encoding='utf-8'))
            self.assertEqual({x['category'] for x in data['items']},set(CATEGORIES))
            self.assertTrue(all(x['status']=='not-run' for x in data['items']))

    def test_obligation_aggregator_uses_queue_and_technology_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);process,pi,tce=self.confirmed_sources(root)
            model=compiler.load(process,pi,[tce],allow_draft=False)
            skeleton=obligations.generate(process,pi,[tce],technologies=['TypeScript'])
            queue={'schema':'cat-tdd-queue/v1','process':model['process'],'items':[
                {'id':'case.'+r['id'],'model_ref':r['id'],'vector_ref':'case.'+r['id'],
                 'order':i+1,'status':'done','evidence_ref':'evidence:green:'+r['id']}
                for i,r in enumerate(model['rules'])
            ]}
            tech=[{'technology':'TypeScript','status':'passed','checks':[]}]
            evaluated=obligations.aggregate(
                skeleton,queue,tech,
                {'status':'passed','evidence':'evidence:model-conformance'})
            self.assertTrue(all(x['status']=='passed' for x in evaluated['items']),evaluated)
            self.assertTrue(all(x['limitation'] for x in evaluated['items']))
            self.assertTrue(all(x.get('evidence') for x in evaluated['items']))


if __name__=='__main__':
    unittest.main()
