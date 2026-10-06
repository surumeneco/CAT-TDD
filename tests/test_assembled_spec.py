from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.cat-system' / 'scripts'))

import cat_compile_v2 as compiler
import cat_model_conformance as validator


class AssembledSpecificationTest(unittest.TestCase):
    def sources(self, root: Path):
        fixture = ROOT / 'tests' / 'fixtures' / 'minimal'
        process = root / 'Process.md'
        pi = root / 'PI.md'
        for source, dest in ((fixture / 'Process.md', process), (fixture / 'PI.md', pi)):
            text = source.read_text(encoding='utf-8')
            text = text.replace('status: draft', 'status: confirmed')
            text = text.replace("decision_ref: ''", 'decision_ref: https://example.org/decision')
            dest.write_text(text, encoding='utf-8')

        original = (fixture / 'TCE.md').read_text(encoding='utf-8')
        original = original.replace('status: draft', 'status: confirmed')
        original = original.replace("decision_ref: ''", 'decision_ref: https://example.org/decision')
        original = original.replace('網羅要求: closed', '網羅要求: partial')

        a = root / 'TCE-A.md'
        b = root / 'TCE-B.md'
        a_text = original.replace('id: demo.process.tce', 'id: demo.process.tce-a')
        b_text = original.replace('id: demo.process.tce', 'id: demo.process.tce-b')
        a_text = '\n'.join(line for line in a_text.splitlines() if 'demo.reject' not in line) + '\n'
        b_text = '\n'.join(line for line in b_text.splitlines() if 'demo.accept' not in line) + '\n'
        a.write_text(a_text, encoding='utf-8')
        b.write_text(b_text, encoding='utf-8')
        return process, pi, a, b

    def test_partial_tces_can_assemble_to_closed_process(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            process, pi, a, b = self.sources(root)
            model = compiler.load(process, pi, [a, b], allow_draft=False)
            self.assertEqual(model['status'], 'confirmed')
            self.assertEqual(model['coverage_requirement'], 'closed')
            self.assertEqual(model['local_coverage_requirements'], {
                'demo.process.tce-a': 'partial',
                'demo.process.tce-b': 'partial',
            })
            self.assertEqual(model['coverage_checks']['送信']['result'], 'proved')
            self.assertEqual({r['source_artifact'] for r in model['rules']},
                             {'demo.process.tce-a', 'demo.process.tce-b'})

            model_path = root / 'Model.md'
            model_path.write_text(compiler.render_model_markdown(model), encoding='utf-8')
            result = validator.validate(process, pi, [a, b], model_path)
            self.assertEqual(result['status'], 'passed', result)

    def test_uncovered_assembled_process_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            process, pi, a, _ = self.sources(root)
            with self.assertRaisesRegex(compiler.Blocked, 'assembled Process closed-world coverage not proved'):
                compiler.load(process, pi, [a], allow_draft=False)


if __name__ == '__main__':
    unittest.main()
