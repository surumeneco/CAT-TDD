"""U03: CommonRule/DomainSpec source text must not lose literal escape sequences."""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
from catlib import semantic_rules
from cat_compile_v2 import load, render_model_markdown
import cat_model_conformance as independent
from test_intrinsic_rule_proofs import build


class RuleMarkdownEscapeTests(unittest.TestCase):
    def test_backslash_before_ordinary_letter_is_not_discarded(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            requirement=r'Match \d{2} and \w+; do not replace with d{2} or w+'
            verification=r'Read C:\temp\audit.json and match \d{2}'
            p,pi,t,r=build(root, requirement=requirement, verification=verification)
            parsed=semantic_rules.load(r,'demo.process')['rules'][0]
            self.assertEqual(parsed['requirement'], requirement)
            self.assertEqual(parsed['verification_contract'], verification)
            model=load(p,pi,t,common_rules=[r],allow_draft=True)
            self.assertEqual(model['rule_obligations'][0]['requirement'],requirement)
            self.assertEqual(model['rule_obligations'][0]['verification_contract'],verification)
            self.assertEqual(model['unverified_rule_ids'],['demo.rule.check'])
            path=root/'Model.json';path.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            self.assertEqual(independent.validate(p,pi,[t],path,common_rules=[r])['status'],'passed')

    def test_escaped_process_dot_must_not_turn_into_explicit_scope_proof(self):
        # Before the fix the parser discarded \. from the Source condition,
        # creating a syntactically valid *different* Process ID and waiving
        # the current Process Rule as `not-applicable` without authorization.
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            condition=r'demo.process\.other'
            p,pi,t,r=build(root,condition=condition)
            doc=semantic_rules.load(r,'demo.process')
            self.assertEqual(doc['rules'][0]['condition'],condition)
            model=load(p,pi,t,common_rules=[r],allow_draft=True)
            self.assertEqual(model['rule_obligations'][0]['verification_status'],'unverified')
            self.assertEqual(model['unverified_rule_ids'],['demo.rule.check'])

    def test_domain_spec_uses_the_same_lossless_rule_table_parser(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            requirement=r'Preserve \d{4} in rule text'
            p,pi,t,r=build(root,requirement=requirement,
                           verification=r'Inspect C:\temp\source.json')
            source=r.read_text(encoding='utf-8')
            self.assertIn('kind: common-rule',source)
            r.write_text(source.replace('kind: common-rule','kind: domain-spec'),
                         encoding='utf-8')
            rule=semantic_rules.load(r,'demo.process')['rules'][0]
            self.assertEqual(rule['requirement'],requirement)
            self.assertEqual(rule['verification_contract'],r'Inspect C:\temp\source.json')
            model=load(p,pi,t,domain_specs=[r],allow_draft=True)
            self.assertEqual(model['unverified_rule_ids'],['demo.rule.check'])
            target=root/'Model.json'
            target.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            self.assertEqual(independent.validate(p,pi,[t],target,
                           domain_specs=[r])['status'],'passed')

    def test_markdown_escaped_pipe_and_backslash_still_parse_as_one_cell(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            # In Markdown, \\| is an escaped table pipe, and \\\\ is one literal slash.
            p,pi,t,r=build(root,requirement=r'Keep left \| right and literal \\ path',
                           verification=r'Test \w+ with a \| b')
            parsed=semantic_rules.load(r,'demo.process')['rules'][0]
            self.assertEqual(parsed['requirement'],r'Keep left | right and literal \ path')
            self.assertEqual(parsed['verification_contract'],r'Test \w+ with a | b')
            model=load(p,pi,t,common_rules=[r],allow_draft=True)
            self.assertEqual(model['rule_obligations'][0]['requirement'],parsed['requirement'])

            markdown=root/'Model.md'
            markdown.write_text(render_model_markdown(model),encoding='utf-8')
            self.assertIn(r'Keep left \| right and literal \ path',markdown.read_text(encoding='utf-8'))
            self.assertEqual(independent.validate(p,pi,[t],markdown,
                                                 common_rules=[r],allow_draft=True)['status'],'passed')

    def test_japanese_markdown_retains_rule_condition_and_unverified_state(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            from test_cat_compile_readable import write_v2
            from test_intrinsic_rule_proofs import approve_fixture
            p,pi,t,r=build(root,requirement=r'検証\dの結果を保持',
                           verification=r'外部観測\wの結果',
                           condition='demo.process.other')
            p,pi,t=write_v2(root,True)
            for item in (p,pi,t):approve_fixture(item)
            model=load(p,pi,t,common_rules=[r])
            self.assertEqual(model['language'],'ja')
            path=root/'TestModel.md'
            rendered=render_model_markdown(model)
            self.assertIn('## 規範Rule出典',rendered)
            self.assertIn('## 規範Rule義務',rendered)
            path.write_text(rendered,encoding='utf-8')
            self.assertEqual(independent.validate(p,pi,[t],path,common_rules=[r])['status'],'passed')



if __name__=='__main__':unittest.main()
