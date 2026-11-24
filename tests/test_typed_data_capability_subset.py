from __future__ import annotations
import json, os, shutil, tempfile, unittest
from pathlib import Path
from test_typescript_capability_subset import PROCESS, PI, inspector

class TypedDataCapabilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler=os.environ.get('CAT_TEST_TYPESCRIPT_PACKAGE')
        if not compiler or not shutil.which('node'):
            raise unittest.SkipTest('official TypeScript package not staged')
        cls.temp=tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.temp.cleanup)
        cls.root=Path(cls.temp.name); cls.repo=cls.root/'app'; cls.repo.mkdir()
        shutil.copytree(compiler, cls.repo/'node_modules/typescript')
        cls.version=json.loads((cls.repo/'node_modules/typescript/package.json').read_text())['version']
        (cls.repo/'package.json').write_text('{"type":"module"}')
        (cls.root/'Process.md').write_text(PROCESS,encoding='utf-8')
        (cls.root/'PI.md').write_text(PI,encoding='utf-8')
        (cls.repo/'record.ts').write_text('export interface RecordData { id: string; name: string }')

    def observe(self, code, version=None):
        (self.repo/'package-lock.json').write_text(json.dumps({'packages':{'node_modules/typescript':{'version':version or self.version}}}))
        (self.repo/'api.ts').write_text(code,encoding='utf-8')
        binding={'schema':'cat-typescript-conformance-binding/v1','repository':'app','source_globs':['api.ts'],'public_entrypoints':['api.ts'],'interface_symbols':{'check':'check'},'capabilities':{},'capability_analysis':'typed-data-functions/v1'}
        (self.root/'binding.json').write_text(json.dumps(binding))
        return inspector.inspect(self.repo,self.root/'binding.json',self.root/'Process.md',self.root/'PI.md')

    def test_data_functions(self):
        for code in [
            'export function check<T>(items:readonly T[],i:number):T[]{const copy=[...items];if(!Number.isInteger(i)||i<0||i+1>=copy.length)return copy;[copy[i],copy[i+1]]=[copy[i+1]!,copy[i]!];return copy;}',
            "export function check(a:{title:string},b:{title:string}):number{return a.title.localeCompare(b.title,'ja');}",
            "import type {RecordData} from './record.js';\nexport function check(id:string, rows:readonly RecordData[]):string {const r=rows.find(x=>x.id===id);return Boolean(r)?r!.name:'';}",
        ]:
            with self.subTest(code=code):
                r=self.observe(code); self.assertIn('capability.closed-set',r['covered_obligation_ids'],r)
                self.assertEqual(r['capability_analysis']['compiler']['version'],self.version)
                if 'RecordData' in code:self.assertIn('record.ts',r['capability_analysis']['source_sha256'])

    def test_unsupported_or_external(self):
        for code in [
            'export function check(a:number[]){a[0]=1;return a;}',
            'export function check(a:number[]){const b=a;[b[0]]=[1];return b;}',
            'export function check(a:{get():number}){return a.get();}',
            'export function check(a:any){return a.value;}',
            'export function check(a:string){return a.localeCompare(a);}',
            'export function check(a:boolean){return globalThis.Boolean(a);}',
            'export function check(a:boolean):boolean{return check(a);}',
            "import './record.js';\nexport function check(a:boolean){return a;}",
        ]:
            with self.subTest(code=code):
                r=self.observe(code);self.assertNotIn('capability.closed-set',r['covered_obligation_ids'],r)
    def test_lock_mismatch(self):
        r=self.observe('export function check(a:boolean){return a;}','0.0.0')
        self.assertNotIn('capability.closed-set',r['covered_obligation_ids'],r)
        self.assertIn('lockfile',r['capability_analysis']['reason'])
