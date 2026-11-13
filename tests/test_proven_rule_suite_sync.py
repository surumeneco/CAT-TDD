"""W03/W08: source-bound intrinsic Rule and every PI survive spec-test-sync."""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
import cat_compile_v2 as compiler
import cat_spec_test_sync as sync
from test_cat_compile_readable import fm
from test_typed_spec_test_sync import prepare,approve_fixture


def add_rule(root,paths,process,tce,requirement='@cat:field-domains-resolved/v1',
             verification='cat:intrinsic-model/v1'):
    cr=root/'CommonRule.md'
    cr.write_text(fm('common-rule','demo.common.proof',[],language='en')+
        '\n## Rules\n| ID | Condition | Requirement | Verification |\n'
        '| --- | --- | --- | --- |\n'
        f'| demo.common.check | assembled-process | {requirement} | {verification} |\n',
        encoding='utf-8')
    approve_fixture(cr)
    paths['common_rules']=[str(cr)]
    model=compiler.load(process,paths.get('pis') or [paths['pi']],tce,
                        allow_draft=requirement!='@cat:field-domains-resolved/v1',
                        domain_specs=paths['domain_specs'],common_rules=[cr])
    Path(paths['model']).write_text(json.dumps(model,ensure_ascii=False,sort_keys=True),encoding='utf-8')
    if model['status']=='confirmed':
        Path(paths['vectors']).write_text(
            json.dumps(compiler.selection_vectors(model),ensure_ascii=False,sort_keys=True),encoding='utf-8')
    return cr,model


class ProvenRuleSuiteSyncTests(unittest.TestCase):
    def test_confirmed_intrinsic_common_rule_and_domain_type_sync_deterministically(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            _,paths,tces=prepare(root)
            cr,model=add_rule(root,paths,paths['process'],tces)
            self.assertEqual(model['status'],'confirmed')
            self.assertEqual([p['rule_id'] for p in model['intrinsic_rule_proofs']],['demo.common.check'])
            with patch.object(sync,'source_paths',return_value=(paths,tces,None)):
                a=sync.render_suite(root/'Work.json',{},'tests/generated/')
                b=sync.render_suite(root/'Work.json',{},'tests/generated/')
            self.assertEqual(a,b)
            desired,rendered,inputs=a
            self.assertEqual(len(desired),2)
            self.assertEqual(len(rendered),2)
            self.assertEqual(len(inputs['source_sha256']),64)
            cr.write_text(cr.read_text(encoding='utf-8')+'\n',encoding='utf-8')
            with patch.object(sync,'source_paths',return_value=(paths,tces,None)):
                with self.assertRaises((sync.Blocked,compiler.Blocked)):
                    sync.render_suite(root/'Work.json',{},'tests/generated/')

    def test_free_text_rule_cannot_enter_spec_test_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            _,paths,tces=prepare(root)
            cr,m=add_rule(root,paths,paths['process'],tces,
                          requirement='Notify users on Discord',
                          verification='discord')
            self.assertEqual(m['status'],'draft')
            with patch.object(sync,'source_paths',return_value=(paths,tces,None)):
                with self.assertRaises((sync.Blocked,compiler.Blocked)):
                    sync.render_suite(root/'Work.json',{},'tests/generated/')

    def test_extra_pi_is_both_compiled_and_hashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            _,paths,tces=prepare(root)
            pi2=root/'PI-extra.md'
            pi2.write_text(fm('pi','demo.process.pi.extra',['demo.process.contract'],language='en')+
                '\n# PI: extra\n## Boundary\n'
                '| Peer process | Direction |\n| --- | --- |\n| demo.user | receive |\n'
                '## Fields\n| ID | Direction | Domain | Presence |\n| --- | --- | --- | --- |\n'
                '| input.extra | receive | boolean | required |\n'
                '## Operations\n| ID | Direction | Trigger |\n| --- | --- | --- |\n'
                '## Constraints\n| Expression |\n| --- |\n',encoding='utf-8')
            approve_fixture(pi2)
            process=Path(paths['process'])
            old=process.read_text(encoding='utf-8')
            before='## Interfaces\n| PI |\n| --- |\n| demo.process.pi |\n'
            self.assertIn(before,old)
            process.write_text(old.replace(before,before+'| demo.process.pi.extra |\n'),encoding='utf-8')
            paths['pis']=[paths['pi'],str(pi2)]
            model=compiler.load(paths['process'],paths['pis'],tces,
                                domain_specs=paths['domain_specs'])
            self.assertEqual(model['status'],'confirmed')
            Path(paths['model']).write_text(json.dumps(model,ensure_ascii=False,sort_keys=True),encoding='utf-8')
            Path(paths['vectors']).write_text(
                json.dumps(compiler.selection_vectors(model),ensure_ascii=False,sort_keys=True),
                encoding='utf-8')
            with patch.object(sync,'source_paths',return_value=(paths,tces,None)):
                desired,rendered,inputs=sync.render_suite(root/'Work.json',{},'tests/generated/')
            self.assertEqual(len(desired),2)
            self.assertEqual(len(rendered),2)
            pi2.write_text(pi2.read_text(encoding='utf-8')+'\n',encoding='utf-8')
            with patch.object(sync,'source_paths',return_value=(paths,tces,None)):
                with self.assertRaises((sync.Blocked,compiler.Blocked)):
                    sync.render_suite(root/'Work.json',{},'tests/generated/')


if __name__=='__main__':unittest.main()
