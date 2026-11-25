from __future__ import annotations
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.cat-system' / 'scripts'))
import cat_project_typecheck as checker
import cat_flow as flow
import cat_implementation_obligations as obligations


class ProjectTypecheckTest(unittest.TestCase):
    def setup_repo(self, root):
        root = Path(root)
        (root / 'src').mkdir()
        (root / 'src/api.ts').write_text('export const value: boolean = true;\n',encoding='utf-8')
        (root / 'src/other.ts').write_text('export const other: boolean = false;\n',encoding='utf-8')
        (root / 'tsconfig.json').write_text(json.dumps({'compilerOptions':{'strict':True},'files':['src/api.ts']}),encoding='utf-8')
        (root / 'binding.json').write_text(json.dumps({'schema':checker.SCHEMA,'repository':'app','projects':[{'config':'tsconfig.json','compiler':'tsc'}]}),encoding='utf-8')
        return root

    def result(self, repo, paths, techs=('TypeScript',)):
        return checker.inspect(repo,repo/'binding.json',paths,techs)

    def test_missing_toolchain_or_unselected_files_never_pass(self):
        with tempfile.TemporaryDirectory() as td:
            repo=self.setup_repo(td)
            self.assertEqual(self.result(repo,['src/api.ts'])[0]['status'],'inconclusive')
            (repo/'package-lock.json').write_text('{}',encoding='utf-8')
            self.assertEqual(self.result(repo,['src/api.ts'])[0]['status'],'inconclusive')
            with patch.object(checker,'compiler_command',return_value=(['node','tsc'],{})), patch.object(checker.subprocess,'run',side_effect=[
                SimpleNamespace(returncode=0,stdout='{"compilerOptions":{"strict":true,"noEmit":true}}',stderr=''),
                SimpleNamespace(returncode=0,stdout=str(repo/'src/api.ts')+'\n',stderr='')]):
                result=self.result(repo,['src/api.ts','src/other.ts'])[0]
                self.assertEqual(result['status'],'inconclusive',result)
                self.assertEqual(result['missing_sources'],['src/other.ts'])
                self.assertEqual(result['covered_obligation_ids'],[])

    def test_compiler_diagnostic_and_non_strict_configuration_are_not_passed(self):
        with tempfile.TemporaryDirectory() as td:
            repo=self.setup_repo(td)
            (repo/'package-lock.json').write_text('{}',encoding='utf-8')
            with patch.object(checker,'compiler_command',return_value=(['node','tsc'],{})), patch.object(checker.subprocess,'run',side_effect=[
                SimpleNamespace(returncode=0,stdout='{"compilerOptions":{"strict":true,"noEmit":true}}',stderr=''),
                SimpleNamespace(returncode=2,stdout='src/api.ts(1,1): error TS2322',stderr='')]):
                result=self.result(repo,['src/api.ts'])[0]
                self.assertEqual(result['status'],'blocked',result)
                self.assertEqual(result['covered_obligation_ids'],[])
            with patch.object(checker,'compiler_command',return_value=(['node','tsc'],{})), patch.object(checker.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='{"compilerOptions":{"strict":false,"noEmit":true}}',stderr='')):
                self.assertEqual(self.result(repo,['src/api.ts'])[0]['status'],'inconclusive')

    def test_plain_typescript_does_not_discharge_vue_constraint(self):
        with tempfile.TemporaryDirectory() as td:
            repo=self.setup_repo(td)
            (repo/'src/View.vue').write_text('<template>test</template>',encoding='utf-8')
            (repo/'package-lock.json').write_text('{}',encoding='utf-8')
            with patch.object(checker,'compiler_command',return_value=(['node','tsc'],{})), patch.object(checker.subprocess,'run',side_effect=[
                SimpleNamespace(returncode=0,stdout='{"compilerOptions":{"strict":true,"noEmit":true}}',stderr=''),
                SimpleNamespace(returncode=0,stdout=str(repo/'src/api.ts')+'\n'+str(repo/'src/View.vue')+'\n',stderr='')]):
                result=self.result(repo,['src/api.ts','src/View.vue'],('TypeScript','Vue'))
                self.assertTrue(all(x['status']=='inconclusive' for x in result),result)

    def test_real_installed_compiler(self):
        # Real compiler test is enabled by a host with the official npm package.
        # No synthetic command is used in this integration test.
        source=os.environ.get('CAT_TEST_TYPESCRIPT_PACKAGE')
        if not source:
            self.skipTest('set CAT_TEST_TYPESCRIPT_PACKAGE to installed official TypeScript package')
        source=Path(source)
        with tempfile.TemporaryDirectory() as td:
            repo=self.setup_repo(td)
            target=repo/'node_modules/typescript'
            shutil.copytree(source,target)
            version=json.loads((target/'package.json').read_text())['version']
            (repo/'package-lock.json').write_text(json.dumps({'packages':{'node_modules/typescript':{'version':version}}}),encoding='utf-8')
            result=self.result(repo,['src/api.ts'])[0]
            self.assertEqual(result['status'],'passed',result)
            self.assertEqual(result['covered_obligation_ids'],['implementation-constraint.typescript'])
            self.assertEqual(self.result(repo,['src/api.ts','src/other.ts'])[0]['status'],'inconclusive')
            (repo/'src/api.ts').write_text('export const value: boolean = "wrong";\n',encoding='utf-8')
            self.assertEqual(self.result(repo,['src/api.ts'])[0]['status'],'blocked')

    def test_explicit_source_opt_out_is_not_proof(self):
        with tempfile.TemporaryDirectory() as td:
            repo=self.setup_repo(td)
            (repo/'package-lock.json').write_text('{}',encoding='utf-8')
            (repo/'src/api.ts').write_text('// @ts-nocheck\nexport const value: boolean = "wrong";',encoding='utf-8')
            with patch.object(checker,'compiler_command',return_value=(['node','tsc'],{})):
                result=self.result(repo,['src/api.ts'])[0]
                self.assertEqual(result['status'],'inconclusive',result)
                self.assertIn('opt-out',result['reason'])
                self.assertEqual(result['covered_obligation_ids'],[])

    def test_binding_path_is_parsed_and_hashed(self):
        with tempfile.TemporaryDirectory() as td:
            repo=self.setup_repo(td)
            w={'id':'demo','repositories':[{'name':'app','path':'.','production_paths':['src/api.ts']}],
               'technologies':['TypeScript'],'compilation':{'technology_constraints':'binding.json','tce':'binding.json'},
               'specification':{},'scope':{}}
            path=repo/'work.json'
            result=flow.technology_conformance(path,w,w['compilation'])
            self.assertEqual(result['status'],'inconclusive')
            self.assertEqual(flow.conformance_input_hashes(path,w,'implementation-conformance')['technology_constraints']['sha256'],checker.digest(repo/'binding.json'))
            orig=flow.conformance_context_sha(w)
            w['technologies']=['Vue']
            self.assertNotEqual(orig,flow.conformance_context_sha(w))

if __name__=='__main__':
    unittest.main()
