#!/usr/bin/env python3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'skills' / 'cat-artifacts' / 'scripts'))
sys.path.insert(0, str(ROOT / 'skills' / 'cat-specification-gate' / 'scripts'))

from cat_artifact_scaffold import KINDS, render
from cat_artifact_lint import artifact_errors


class ArtifactScaffoldTests(unittest.TestCase):
    def test_every_semantic_kind_renders_lintable_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for kind in KINDS:
                path = root / f'{kind}.md'
                path.write_text(render(kind, f'demo.{kind}', 'demo.process', 'decision:test', 'ja'), encoding='utf-8')
                self.assertEqual(artifact_errors(files=[path]), [], kind)

    def test_scaffold_contains_explicit_placeholders_not_invented_semantics(self):
        text = render('tce', 'demo.rule', 'demo.process', 'decision:test', 'en')
        self.assertIn('TO_BE_DEFINED', text)
        self.assertIn('Coverage requirement: partial', text)
        self.assertIn('status: candidate', text)


if __name__ == '__main__':
    unittest.main()
