"""Source→Markdown Model must not erase duplicate semantic evidence rows."""
from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
from cat_compile_v2 import Blocked,load,render_model_markdown
from cat_model_conformance import validate
from test_cat_compile_readable import fm,write_v2


class MarkdownDuplicateInventoryTests(unittest.TestCase):
    def test_duplicate_source_operation_trigger_rule_effect_frame_are_rejected(self):
        headings={
            False:('Source artifacts','PI operations','Triggers','Rules','Effects','Derived frame conditions'),
            True:('出典Artifact','PI操作','起点','規則','効果','導出された不変条件'),
        }
        for ja in (False,True):
            with tempfile.TemporaryDirectory() as td:
                root=Path(td)
                p,pi,tce=write_v2(root,ja)
                model=load(p,pi,tce,allow_draft=True)
                original=render_model_markdown(model)
                path=root/'Model.md'
                path.write_text(original,encoding='utf-8')
                self.assertEqual(validate(p,pi,[tce],path,allow_draft=True)['status'],'passed')
                for heading in headings[ja]:
                    with self.subTest(ja=ja,heading=heading):
                        start=original.index('## '+heading+'\n')
                        end=original.find('\n## ',start+3)
                        section=original[start:end if end>=0 else None]
                        rows=[line for line in section.splitlines() if line.startswith('| ') and not line.startswith('| ---')]
                        self.assertGreaterEqual(len(rows),2,heading)
                        first=rows[1]
                        changed=original[:start]+section.replace(first+'\n',first+'\n'+first+'\n',1)+original[start+len(section):]
                        self.assertNotEqual(original,changed)
                        path.write_text(changed,encoding='utf-8')
                        try:
                            result=validate(p,pi,[tce],path,allow_draft=True)
                        except Blocked:
                            continue
                        self.assertEqual(result['status'],'blocked',f'{heading}: {result}')


    def test_duplicate_domain_rule_definition_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p,pi,tce=write_v2(root,False)
            domain=root/'DomainRule.md'
            domain.write_text(fm('domain-rule','demo.domain.rule',
                     ['demo.process.contract'],language='en')+
                     '\n## Definitions\n| ID | Parameters | Expression |\n'
                     '| --- | --- | --- |\n| plus_one | value | `value + 1` |\n',encoding='utf-8')
            tce.write_text(tce.read_text(encoding='utf-8').replace(
                '  - demo.process.pi\n','  - demo.process.pi\n  - demo.domain.rule\n'),
                encoding='utf-8')
            model=load(p,pi,tce,domain_path=domain,allow_draft=True)
            original=render_model_markdown(model)
            dest=root/'Model.md';dest.write_text(original,encoding='utf-8')
            self.assertEqual(validate(p,pi,[tce],dest,domain_rule=domain,
                                      allow_draft=True)['status'],'passed')
            row='| plus_one | value | `(value + 1)` |'
            self.assertIn(row,original)
            dest.write_text(original.replace(row+'\n',row+'\n'+row+'\n'),encoding='utf-8')
            with self.assertRaisesRegex(Blocked,'duplicate Markdown DomainRule definition'):
                validate(p,pi,[tce],dest,domain_rule=domain,allow_draft=True)


if __name__=='__main__':unittest.main()
