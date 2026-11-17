"""W06 regression: real domains must not cast arbitrary-precision integers to float."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.cat-system' / 'scripts'))
from catlib import semantic_types as types, semantic_subtyping as sub


class RealLargeIntegerBoundaryTests(unittest.TestCase):
    def test_real_accepts_arbitrary_size_integer_without_float_conversion(self):
        huge = 10 ** 400
        self.assertTrue(types.contains(types.parse('real'), huge))
        self.assertTrue(types.contains(types.parse('real'), -huge))
        self.assertFalse(types.contains(types.parse('real'), float('inf')))
        self.assertFalse(types.contains(types.parse('real'), float('nan')))

    def test_real_integer_bounds_are_validated_without_float_conversion(self):
        huge = 10 ** 400
        domain = types.validate({'type': 'real', 'min': huge, 'max': huge + 2})
        self.assertTrue(types.contains(domain, huge + 1))
        self.assertFalse(types.contains(domain, huge - 1))
        self.assertFalse(types.contains(domain, huge + 3))
        with self.assertRaises(types.DomainError):
            types.validate({'type': 'real', 'min': float('inf')})

    def test_enum_to_real_inclusion_handles_large_integer(self):
        huge = 10 ** 400
        self.assertIs(sub.subset({'type': 'enum', 'values': [huge]},
                                 types.parse('real')), True)
        self.assertIs(sub.subset({'type': 'enum', 'values': [True]},
                                 types.parse('real')), False)


if __name__ == '__main__':
    unittest.main()
