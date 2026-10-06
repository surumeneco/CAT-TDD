from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.cat-system' / 'scripts'))

import cat_compile_v2 as compiler
import cat_model_conformance as validator


class ModelConformanceTest(unittest.TestCase):
    def confirmed_fixture(self, root: Path):
        fixture = ROOT / 'tests' / 'fixtures' / 'minimal'
        paths = []
        for name in ('Process.md', 'PI.md', 'TCE.md'):
            dest = root / name
            text = (fixture / name).read_text(encoding='utf-8')
            text = text.replace('status: draft', 'status: confirmed')
            text = text.replace("decision_ref: ''", 'decision_ref: https://example.org/decision')
            dest.write_text(text, encoding='utf-8')
            paths.append(dest)
        return tuple(paths)

    def test_independent_validator_accepts_generated_model(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            process, pi, tce = self.confirmed_fixture(root)
            model = compiler.load(process, pi, tce, allow_draft=False)
            model_path = root / 'Model.md'
            model_path.write_text(compiler.render_model_markdown(model), encoding='utf-8')
            result = validator.validate(process, pi, tce, model_path)
            self.assertEqual(result['status'], 'passed', result)

    def test_missing_allowed_outcome_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            process, pi, tce = self.confirmed_fixture(root)
            model = compiler.load(process, pi, tce, allow_draft=False)
            rule = next(r for r in model['rules'] if r['id'] == 'demo.accept')
            rule['allowed'] = []
            model_path = root / 'Model.json'
            model_path.write_text(json.dumps(model, ensure_ascii=False), encoding='utf-8')
            result = validator.validate(process, pi, tce, model_path)
            self.assertEqual(result['status'], 'blocked')
            self.assertIn('effects', result['mismatches'])

    def test_extra_model_outcome_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            process, pi, tce = self.confirmed_fixture(root)
            model = compiler.load(process, pi, tce, allow_draft=False)
            rule = next(r for r in model['rules'] if r['id'] == 'demo.accept')
            rule['allowed'].append({
                'write': [{'target': '出力.受理', 'expr': {'literal': False}}],
                'unchanged': ['状態.準備'],
                'absent_outputs': []
            })
            model_path = root / 'Model.json'
            model_path.write_text(json.dumps(model, ensure_ascii=False), encoding='utf-8')
            result = validator.validate(process, pi, tce, model_path)
            self.assertEqual(result['status'], 'blocked')
            self.assertTrue({'effects', 'frames'} & set(result['mismatches']))


if __name__ == '__main__':
    unittest.main()
