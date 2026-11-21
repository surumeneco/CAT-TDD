"""Rule source kind is an independently checked, per-obligation provenance fact."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
from cat_compile_v2 import Blocked,load,render_model_markdown
from cat_model_conformance import validate
from test_intrinsic_rule_proofs import build,approve_fixture,PROOF,CONTRACT
from test_cat_compile_readable import write_v2,fm


class RuleSourceKindConformanceTests(unittest.TestCase):
    def fixture(self,root,free_text,ja=False,kind='common-rule'):
        if not ja:
            args={'requirement':'Deliver an external notification',
                  'verification':'provider runtime contract'} if free_text else {}
            p,pi,t,r=build(root,**args)
            if kind=='domain-spec':
                r.write_text(r.read_text(encoding='utf-8').replace('kind: common-rule',
                                 'kind: domain-spec'),encoding='utf-8')
            return p,pi,t,r
        p,pi,t=write_v2(root,True)
        r=root/'CommonRule.md'
        req='Deliver an external notification' if free_text else PROOF
        ver='provider runtime contract' if free_text else CONTRACT
        r.write_text(fm(kind,'demo.rule.document',
                        ['demo.process.contract'],language='ja')+
            '\n## 規則\n| ID | 条件 | 要求 | 検証 |\n| --- | --- | --- | --- |\n'
            f'| demo.rule.check | assembled-process | {req} | {ver} |\n',encoding='utf-8')
        for path in (p,pi,t,r):approve_fixture(path)
        return p,pi,t,r

    def sources(self,kind,path):
        return {'common_rules':[path]} if kind=='common-rule' else {'domain_specs':[path]}

    def test_json_origin_kind_wrong_or_missing_blocks_source_model(self):
        for kind in ('common-rule','domain-spec'):
            for free_text in (False,True):
                with self.subTest(kind=kind,free_text=free_text),tempfile.TemporaryDirectory() as tmp:
                    root=Path(tmp)
                    p,pi,t,r=self.fixture(root,free_text,kind=kind)
                    model=load(p,pi,t,**self.sources(kind,r),allow_draft=True)
                    dest=root/'Model.json'
                    dest.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
                    self.assertEqual(validate(p,pi,[t],dest,**self.sources(kind,r),allow_draft=True)['status'],'passed')
                    for variant in ('wrong-kind','missing-kind'):
                        with self.subTest(variant=variant):
                            altered=json.loads(json.dumps(model))
                            obligation=altered['rule_obligations'][0]
                            if variant=='wrong-kind':obligation['source_kind']='domain-spec' if kind=='common-rule' else 'common-rule'
                            else:obligation.pop('source_kind')
                            dest.write_text(json.dumps(altered,ensure_ascii=False),encoding='utf-8')
                            result=validate(p,pi,[t],dest,**self.sources(kind,r),allow_draft=True)
                            self.assertEqual(result['status'],'blocked',result)
                            self.assertIn('rule_obligations',result['mismatches'])

    def test_markdown_origin_kind_wrong_missing_or_omitted_blocks(self):
        for ja in (False,True):
            for kind in ('common-rule','domain-spec'):
                for free_text in (False,True):
                    with self.subTest(ja=ja,kind=kind,free_text=free_text),tempfile.TemporaryDirectory() as tmp:
                        root=Path(tmp)
                        p,pi,t,r=self.fixture(root,free_text,ja,kind)
                        model=load(p,pi,t,**self.sources(kind,r),allow_draft=True)
                        dest=root/'Model.md'
                        original=render_model_markdown(model)
                        dest.write_text(original,encoding='utf-8')
                        name='出典種別' if ja else 'Source kind'
                        self.assertIn(' | '+name+' |',original)
                        self.assertEqual(validate(p,pi,[t],dest,**self.sources(kind,r),allow_draft=True)['status'],'passed')
                        rule_row=next(row for row in original.splitlines() if row.startswith('| demo.rule.check |'))
                        self.assertIn('| '+kind+' |',rule_row)
                        for variant,changed in (
                            ('wrong-kind',rule_row.replace('| '+kind+' |','| '+('domain-spec' if kind=='common-rule' else 'common-rule')+' |')),
                            ('missing-kind',rule_row.replace('| '+kind+' |','| — |')),
                        ):
                            with self.subTest(variant=variant):
                                dest.write_text(original.replace(rule_row,changed),encoding='utf-8')
                                result=validate(p,pi,[t],dest,**self.sources(kind,r),allow_draft=True)
                                self.assertEqual(result['status'],'blocked',result)
                                self.assertIn('rule_obligations',result['mismatches'])
                        # Old Markdown without per-obligation kind must be stale,
                        # rather than silently recover source_kind from another table.
                        dest.write_text(original.replace(' | '+name+' |',' | '),encoding='utf-8')
                        with self.assertRaisesRegex(Blocked,'Rule|scope|table'):
                            validate(p,pi,[t],dest,**self.sources(kind,r),allow_draft=True)

if __name__=='__main__':unittest.main()
