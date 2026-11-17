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

    def test_real_textual_integral_bounds_preserve_large_exact_values(self):
        # Numeric range membership is defined over exact integer values.
        # Parsing an integer-looking bound through binary64 loses information.
        boundary = 9007199254740993
        domain = types.validate(types.parse(f'real[{boundary}..{boundary}]'))
        self.assertIs(type(domain['min']), int)
        self.assertEqual(domain['min'], boundary)
        self.assertEqual(domain['max'], boundary)
        self.assertTrue(types.contains(domain, boundary))
        self.assertFalse(types.contains(domain, boundary - 1))
        self.assertIs(sub.subset({'type': 'enum', 'values': [boundary]}, domain), True)
        self.assertIs(sub.subset({'type': 'enum', 'values': [boundary - 1]}, domain), False)

        from catlib import decimal_integer
        decimal_digits = '9' * 5000
        huge = decimal_integer.parse(decimal_digits)
        wide = types.validate(types.parse('real[-' + decimal_digits + '..' + decimal_digits + ']'))
        self.assertIs(type(wide['max']), int)
        self.assertEqual(wide['max'], huge)
        self.assertEqual(wide['min'], -huge)
        self.assertTrue(types.contains(wide, huge))
        self.assertTrue(types.contains(wide, -huge))
        self.assertFalse(types.contains(wide, huge + 1))
        self.assertFalse(types.contains(wide, -huge - 1))

        # Fractional literals retain their existing binary64 parser path.
        self.assertEqual(types.parse('real[0.125..1.5]'),
                         {'type': 'real', 'min': 0.125, 'max': 1.5})

    def test_enum_to_real_inclusion_handles_large_integer(self):
        huge = 10 ** 400
        self.assertIs(sub.subset({'type': 'enum', 'values': [huge]},
                                 types.parse('real')), True)
        self.assertIs(sub.subset({'type': 'enum', 'values': [True]},
                                 types.parse('real')), False)


if __name__ == '__main__':
    unittest.main()
