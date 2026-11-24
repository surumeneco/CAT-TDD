"""Assembly paths and receipts use canonical POSIX spelling on every host."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path, PureWindowsPath
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.cat-system' / 'scripts'))
import cat_assembly_regression as regression
from cat_compile_v2 import Blocked
from test_cat_compile_readable import fm, write_v2


class AssemblyNestedPathsTests(unittest.TestCase):
    def test_nested_exclusion_and_reference_contract(self):
        for windows in (False, True):
            for nested, referenced, excluded in ((False, False, True), (True, False, True),
                                                  (True, True, True), (True, True, False)):
                with self.subTest(windows=windows, nested=nested, referenced=referenced, excluded=excluded), tempfile.TemporaryDirectory() as td:
                    root = Path(td).resolve()
                    process, pi, tce = write_v2(root, False)
                    folder = root / 'nested' if nested else root
                    folder.mkdir(exist_ok=True)
                    domain = folder / 'Domain.md'
                    domain.write_text(fm('domain-rule', 'demo.process.library', [], language='en') +
                                      '\n## Definitions\n| ID | Parameters | Expression |\n'
                                      '| --- | --- | --- |\n| identity | x | `x` |\n', encoding='utf8')
                    if referenced:
                        tce.write_text(tce.read_text(encoding='utf8').replace(
                            '  - demo.process.pi\n', '  - demo.process.pi\n  - demo.process.library\n'), encoding='utf8')
                    path = domain.relative_to(root).as_posix()
                    source = {'id': 'demo.process.library', 'kind': 'domain-rule', 'path': path,
                              'sha256': hashlib.sha256(domain.read_bytes()).hexdigest()}
                    (root / 'Assembly.json').write_text(json.dumps({
                        'schema': 'cat-reviewed-source-assembly/v1', 'selected': [source],
                        'unassembled_sources': [source] if excluded else [],
                        'processes': [{'owner': 'minimal', 'process': process.name, 'pis': [pi.name],
                                       'tces': [tce.name], 'domain_specs': [], 'common_rules': [],
                                       'domain_rules': [path]}]}), encoding='utf8')
                    original = type(root).relative_to

                    def relative_to(self, other, *args, **kwargs):
                        result = original(self, other, *args, **kwargs)
                        return PureWindowsPath(*result.parts) if windows and other == root else result

                    # Exercise Windows spelling even when the runner is POSIX;
                    # real filesystem resolution and compiler/validator stay intact.
                    with mock.patch.object(type(root), 'relative_to', relative_to):
                        if referenced and excluded:
                            with self.assertRaisesRegex(Blocked, 'referenced'):
                                regression.review(root, 'Assembly.json', True)
                        else:
                            result = regression.review(root, 'Assembly.json', True)
                            self.assertEqual(result['status'], 'passed', result)
                            row = result['results'][0]
                            self.assertEqual(row['input_sha256'][path], source['sha256'])
                            self.assertEqual(row['unassembled_domain_rules'], [path] if excluded else [])
                            self.assertTrue(all('\\' not in key for key in row['input_sha256']))


if __name__ == '__main__':
    unittest.main()
