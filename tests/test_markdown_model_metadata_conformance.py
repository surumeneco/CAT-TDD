"""Source-bound Markdown TestModel metadata is not a proof by self-assertion.

All Confirmed labels in these fixtures are synthetic; no product or user
approval is implied. These tests verify the independent Source->Model audit.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / '.cat-system' / 'scripts'), str(ROOT / 'tests')]
from cat_compile_v2 import load, render_model_markdown
from cat_model_conformance import validate
from test_intrinsic_rule_proofs import approve_fixture
from test_pi_constraint_operation_scope import fixture
from test_model_conformance import ModelConformanceTest


def result_time_draft(root: Path):
    process, pis, tce = fixture(root)
    first = pis[0]
    text = first.read_text(encoding='utf-8')
    text = text.replace('demo.caller | receive |', 'demo.caller | bidirectional |')
    text = text.replace('| input.b | receive | boolean | required |',
                        '| input.b | receive | boolean | required |\n'
                        '| output.complete | send | boolean | required |')
    text = text.replace('| `input.a == input.b` |', '| `output.complete == true` |')
    first.write_text(text, encoding='utf-8')
    approve_fixture(first)
    tce.write_text(tce.read_text(encoding='utf-8').replace(
        '| A.done | A | `true` | 1 | `state.done = true` |',
        '| A.done | A | `true` | 1 | `state.done = true; output.complete = true` |'),
        encoding='utf-8')
    approve_fixture(tce)
    model = load(process, pis, tce, allow_draft=True)
    assert model['status']=='draft' and model['coverage_requirement']=='partial'
    return process, pis, tce, render_model_markdown(model)


class MarkdownMetadataConformanceTest(unittest.TestCase):
    def test_draft_metadata_cannot_be_forged_into_confirmed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            process,pis,tce,raw=result_time_draft(root)
            path=root/'Model.md'
            path.write_text(raw,encoding='utf-8')
            self.assertEqual(validate(process,pis,tce,path,allow_draft=True)['status'],'passed')
            forged=raw.replace('status: draft','status: confirmed',1)
            self.assertNotEqual(forged,raw)
            path.write_text(forged,encoding='utf-8')
            result=validate(process,pis,tce,path,allow_draft=True)
            self.assertEqual(result['status'],'blocked',result)

    def test_unbound_result_relation_cannot_claim_closed_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            process,pis,tce,raw=result_time_draft(root)
            path=root/'Model.md'
            original='## Coverage requirement\n\n`partial`'
            self.assertIn(original,raw)
            path.write_text(raw.replace(original,'## Coverage requirement\n\n`closed`'),
                            encoding='utf-8')
            result=validate(process,pis,tce,path,allow_draft=True)
            self.assertEqual(result['status'],'blocked',result)

    def test_frontmatter_authority_schema_process_language_are_source_bound(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            process,pis,tce,raw=result_time_draft(root)
            path=root/'Model.md'
            substitutions={
                'authority':('semantic_authority: cat-markdown/v2',
                             'semantic_authority: arbitrary-claim/v1'),
                'schema':('schema: cat-test-model/v2','schema: forged-model/v1'),
                'process':('process: demo.scope','process: unrelated.process'),
                'language':('language: en','language: ja'),
            }
            for name,(original,modified) in substitutions.items():
                with self.subTest(field=name):
                    self.assertIn(original,raw)
                    path.write_text(raw.replace(original,modified,1),encoding='utf-8')
                    result=validate(process,pis,tce,path,allow_draft=True)
                    self.assertEqual(result['status'],'blocked',result)

    def test_genuine_confirmed_model_metadata_stays_valid(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            process,pi,tce=ModelConformanceTest().confirmed_fixture(root)
            model=load(process,pi,tce,allow_draft=False)
            self.assertEqual(model['status'],'confirmed')
            path=root/'Model.md'
            path.write_text(render_model_markdown(model),encoding='utf-8')
            self.assertEqual(validate(process,pi,tce,path)['status'],'passed')


if __name__=='__main__':
    unittest.main()
