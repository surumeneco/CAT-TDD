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
            self.assertIn('violations',tech,tech)
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
            self.assertIn('violations',tech,tech)
            self.assertTrue(any(x.get('item')=='undocumentedInterface' for x in tech['violations']))

    def test_declared_interface_with_no_external_capability_passes_inspector(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo=root/'app';self.write_api(repo)
            process,pi,_=self.confirmed_sources(root)
            binding=self.binding(root)
            result=inspector.inspect(repo,binding,process,pi)
            self.assertEqual(result['status'],'passed',result)
            self.assertEqual(set(result['covered_obligation_ids']),
                             {'interface.送信要求','interface.結果提供'})
            skeleton=obligations.generate(process,pi,[self.confirmed_sources(root)[2]],
                                          technologies=['TypeScript'])
            evaluated=obligations.aggregate(
                skeleton,technology_results=[{'technology':'TypeScript',**result}])
            interfaces=[x for x in evaluated['items'] if x['category']=='interface']
            self.assertTrue(interfaces)
            self.assertTrue(all(x['status']=='passed' for x in interfaces),interfaces)
            self.assertTrue(all(x['status']=='inconclusive'
                                for x in evaluated['items'] if x['category'] in
                                ('cross-process','implementation-constraint')))

    def test_technology_conformance_does_not_skip_other_declared_skills(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo=root/'app';self.write_api(repo)
            process,pi,tce=self.confirmed_sources(root)
            binding=self.binding(root);obs=self.passed_obligations(root)
            w=self.work(root,process,pi,tce,binding,obs)
            wp=root/'Work.json';wp.write_bytes(flow.json_bytes(w))
            typescript_only=flow.technology_conformance(wp,w,w['compilation'])
            self.assertEqual(typescript_only['status'],'passed',typescript_only)
            self.assertEqual({x['technology'] for x in typescript_only['results']}, {'TypeScript'})
            # A successful TypeScript interface inspection cannot prove that
            # an independently declared Docker/JUnit skill was also inspected.
            for extra in ('Docker','JUnit'):
                with self.subTest(extra=extra):
                    w['technologies']=['TypeScript',extra]
                    result=flow.technology_conformance(wp,w,w['compilation'])
                    self.assertEqual(result['status'],'inconclusive',result)
                    by_name={x['technology']:x for x in result['results']}
                    self.assertEqual(by_name['TypeScript']['status'],'passed')
                    self.assertEqual(by_name[extra]['status'],'inconclusive')
                    self.assertIn('inspector',by_name[extra]['reason'])

    def test_technology_results_account_for_every_declared_skill_even_when_binding_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            process, pi, tce = self.confirmed_sources(root)
            binding = self.binding(root)
            obligations_file = self.passed_obligations(root)
            w = self.work(root, process, pi, tce, binding, obligations_file)
            wp = root / 'Work.json'
            wp.write_bytes(flow.json_bytes(w))
            conf = dict(w['compilation'])
            conf.pop('conformance_binding')
            w['technologies'] = ['TypeScript', 'JUnit', 'Docker']
            result = flow.technology_conformance(wp, w, conf)
            self.assertEqual(result['status'], 'inconclusive')
            self.assertEqual({entry['technology'] for entry in result['results']},
                             {'TypeScript', 'JUnit', 'Docker'}, result)
            self.assertTrue(all(entry['status'] == 'inconclusive'
                                for entry in result['results']))

            w['technologies'] = ['Docker']
            unsupported = flow.technology_conformance(wp, w, conf)
            self.assertEqual(unsupported['status'], 'inconclusive')
            self.assertEqual([entry['technology'] for entry in unsupported['results']],
                             ['Docker'])
            w['technologies'] = []
            absent = flow.technology_conformance(wp, w, conf)
            self.assertEqual(absent['status'], 'passed')
            self.assertEqual(absent['results'], [])

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
            verified_green={r['id']:['evidence:green:'+r['id']] for r in model['rules']}
            evaluated=obligations.aggregate(
                skeleton,queue,tech,
                {'status':'passed','evidence':'evidence:model-conformance'},
                verified_green=verified_green)
            status_by_category={}
            for obligation in evaluated['items']:
                status_by_category.setdefault(obligation['category'],set()).add(obligation['status'])
            for category in ('behavior','invariant','domain'):
                self.assertEqual(status_by_category[category],{'passed'})
            self.assertEqual(status_by_category['implementation-constraint'],{'inconclusive'})
            for category in ('interface','capability','cross-process'):
                self.assertEqual(status_by_category[category],{'inconclusive'})
            self.assertTrue(all(x['limitation'] for x in evaluated['items']))
            self.assertTrue(all(x.get('evidence') for x in evaluated['items'] if x['status']=='passed'))
            self.assertTrue(all(x.get('reason') for x in evaluated['items'] if x['status']=='inconclusive'))

    def test_tampered_obligation_skeleton_is_blocked_before_gate_evaluation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo=root/'app';self.write_api(repo)
            process,pi,tce=self.confirmed_sources(root)
            binding=self.binding(root)
            target=root/'obligations.json'
            generated=obligations.generate(process,pi,[tce],technologies=['TypeScript'])
            generated['items'][0]['method']='manually-overridden'
            target.write_text(json.dumps(generated,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
            w=self.work(root,process,pi,tce,binding,target)
            wp=root/'Work.json';wp.write_bytes(flow.json_bytes(w))
            result=flow.conformance_work(wp,w,'implementation-conformance')
            self.assertEqual(result['status'],'blocked',result)
            self.assertIn('obligation',result['reason'].lower())


    def test_published_typescript_inspector_preserves_canonical_evidence_contract(self):
        # The distributable Skill and the runtime must not provide divergent
        # PI operation scopes or claim different covered obligations.
        import runpy
        canonical = ROOT / '.cat-system' / 'skills' / 'tech-typescript' / 'scripts' / 'cat_typescript_conformance.py'
        distributed = ROOT / '.github' / 'skills' / 'tech-typescript' / 'scripts' / 'cat_typescript_conformance.py'
        self.assertEqual(distributed.read_bytes(), canonical.read_bytes())
        # Direct invocation must resolve the core parser from the repository,
        # without relying on an inherited PYTHONPATH.
        import subprocess
        cli = subprocess.run(
            [sys.executable, '-I', str(distributed), '--help'],
            cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertIn('--pi-extra', cli.stdout)
        published = runpy.run_path(str(distributed), run_name='published_typescript_inspector')

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / 'app'
            process, pi, _ = self.confirmed_sources(root)
            binding = self.binding(root)
            self.write_api(repo)
            for source, expected_status in (
                ('', 'passed'),
                ('export * from "./other";', 'inconclusive'),
                ('export async function internalNetwork() { return fetch("https://example.invalid"); }', 'blocked'),
            ):
                with self.subTest(expected_status=expected_status):
                    self.write_api(repo, extra=source)
                    actual = published['inspect'](repo, binding, process, pi, pi_extras=())
                    expected = inspector.inspect(repo, binding, process, pi, pi_extras=())
                    self.assertEqual(actual, expected)
                    self.assertEqual(actual['status'], expected_status)
                    if expected_status != 'passed':
                        self.assertEqual(actual['covered_obligation_ids'], [])


if __name__=='__main__':
    unittest.main()
