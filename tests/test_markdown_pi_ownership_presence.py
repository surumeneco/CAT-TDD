"""Markdown Source→Model must preserve PI field Presence and ownership."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.cat-system' / 'scripts'))
from cat_compile_v2 import Blocked, load, render_model_markdown
from cat_model_conformance import validate
from test_cat_compile_readable import write_v2
from test_operation_presence import OperationPresenceTests


class MarkdownPIOwnershipPresenceTests(unittest.TestCase):
    def model(self, p, pis, t, dest, **options):
        m = load(p, pis, t, allow_draft=True, **options)
        text = render_model_markdown(m)
        dest.write_text(text, encoding='utf-8')
        self.assertEqual(validate(p, pis, [t], dest, allow_draft=True)['status'], 'passed')
        return text

    def test_base_field_presence_and_pi_owner_are_verifiable_in_both_languages(self):
        for ja in (False, True):
            with self.subTest(ja=ja), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                p, pi, t = write_v2(root, ja)
                dest = root / 'Model.md'
                text = self.model(p, pi, t, dest)
                role = '受信' if ja else 'input'
                domain = '真偽' if ja else 'boolean'
                row = f'| input.enabled | {role} | `{domain}` | required | demo.process.pi |'
                self.assertIn(row, text)
                state = f'| state.ready | {"状態" if ja else "state"} | `{domain}` | — | — |'
                self.assertIn(state, text)
                for modified, mismatch in (
                    (text.replace(row, row.replace('required', 'optional'), 1), 'presence'),
                    (text.replace(row, row.replace('demo.process.pi', 'other.pi'), 1), 'field_owners'),
                    (text.replace(state, state.replace('| — | — |', '| required | other.pi |'), 1), 'invalid'),
                ):
                    self.assertNotEqual(modified, text)
                    dest.write_text(modified, encoding='utf-8')
                    try:
                        result = validate(p, pi, [t], dest, allow_draft=True)
                    except Blocked:
                        continue
                    self.assertEqual(result['status'], 'blocked', result)
                    if mismatch != 'invalid':
                        self.assertIn(mismatch, result['mismatches'])

    def test_pi_operation_owner_is_checked_against_source(self):
        for ja in (False, True):
            with self.subTest(ja=ja), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                p, pi, t = write_v2(root, ja)
                dest = root / 'Model.md'
                text = self.model(p, pi, t, dest)
                direction = '受付' if ja else 'accept'
                row = f'| submit_op | {direction} | submit | demo.process.pi |'
                self.assertIn(row, text)
                dest.write_text(text.replace(row, row.replace('demo.process.pi', 'other.pi'), 1), encoding='utf-8')
                result = validate(p, pi, [t], dest, allow_draft=True)
                self.assertEqual(result['status'], 'blocked', result)
                self.assertIn('operation_owners', result['mismatches'])

    def test_multi_pi_ownership_and_operation_overrides_remain_distinct(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p, first, second, t, _, _ = OperationPresenceTests().create(root)
            dest = root / 'Model.md'
            text = self.model(p, [first, second], t, dest)
            self.assertIn('## Operation presence', text)
            self.assertIn('| op.first | input.ready | optional |', text)
            for op in ('op.first', 'op.other'):
                line = next(line for line in text.splitlines() if line.startswith(f'| {op} |') and 'accept' in line)
                self.assertTrue(line.endswith(' | demo.process.first |'), line)
                dest.write_text(text.replace(line, line.replace('demo.process.first', 'demo.process.second'), 1), encoding='utf-8')
                self.assertIn('operation_owners', validate(p, [first, second], [t], dest, allow_draft=True)['mismatches'])


if __name__ == '__main__':
    unittest.main()
