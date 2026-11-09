"""Non-normative candidate regression: protect IDs owned by handwritten tests."""
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".cat-system" / "scripts"))
from cat_suite_plan_candidate import plan_suite

S, M, V, H = 'a' * 64, 'b' * 64, 'c' * 64, '1' * 64


def desired(test_id='vector-01', path='generated-tests/new.py'):
    return {'test_id': test_id, 'model_ref': 'model#rule-01',
            'vector_ref': test_id, 'path': path, 'content_sha256': H}


def owned(test_id, owner='handwritten'):
    return {'test_id': test_id, 'owner': owner, 'file_sha256': H,
            'source_sha256': S, 'model_sha256': M, 'vectors_sha256': V,
            'renderer_version': 'python-v1', 'binding_version': 'pytest-v1'}


def plan(items, disk=None, manifest=None):
    return plan_suite(source_sha256=S, model_sha256=M, vectors_sha256=V,
                      selection_rule='model-selection/v1', renderer_version='python-v1',
                      binding_version='pytest-v1', repo_revision='example-sha',
                      allowed_prefix='generated-tests/', desired=items,
                      disk_hashes=disk or {}, manifest=manifest or {})


class ManifestIdentityCollision(unittest.TestCase):
    def test_handwritten_id_elsewhere_blocks_new_generated_test(self):
        path = 'generated-tests/handwritten.py'
        result = plan([desired()], {path: H}, {path: owned('vector-01')})
        self.assertEqual(result['entries'][1]['action'], 'blocked')
        self.assertEqual(result['entries'][1]['reason'], 'test-id-owned-at-another-path')

    def test_repeated_handwritten_manifest_id_is_not_accepted(self):
        paths = ['generated-tests/manual_a.py', 'generated-tests/manual_b.py']
        with self.assertRaisesRegex(ValueError, 'multiple locations'):
            plan([], {p: H for p in paths}, {p: owned('manual-id') for p in paths})

    def test_generated_and_handwritten_manifest_id_collision_is_rejected(self):
        one, two = 'generated-tests/manual.py', 'generated-tests/owned.py'
        with self.assertRaisesRegex(ValueError, 'multiple locations'):
            plan([], {one: H, two: H}, {one: owned('same-id'), two: owned('same-id', 'generated')})

    def test_distinct_handwritten_record_does_not_block_creation(self):
        manual = 'generated-tests/manual.py'
        result = plan([desired()], {manual: H}, {manual: owned('independent')})
        self.assertEqual({entry['path']: entry['action'] for entry in result['entries']},
                         {manual: 'retain', 'generated-tests/new.py': 'create'})


if __name__ == '__main__':
    unittest.main()
