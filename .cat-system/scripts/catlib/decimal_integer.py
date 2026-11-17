"""Exact decimal integer interchange without mutating Python's global safety limit.

CAT numeric Domain values are arbitrary precision. Python 3.11+ limits direct
int<->decimal-string conversion; these helpers only bypass that representation
limit for actually parsed decimal literals and CAT JSON serialization. They do
not change a Domain's values or promise unbounded CPU/memory resources.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
from json.encoder import _make_iterencode, encode_basestring, encode_basestring_ascii, INFINITY
import re

_DECIMAL_INTEGER = re.compile(r'[+-]?\d+\Z')
_LIMIT_ERROR = 'Exceeds the limit ('


def parse(token):
    if type(token) is not str or not _DECIMAL_INTEGER.fullmatch(token):
        raise ValueError('invalid decimal integer')
    # Decimal parses digits directly; int(Decimal) remains exact and is not
    # subject to Python's int(string) digit limit.
    try:
        return int(Decimal(token))
    except (InvalidOperation, OverflowError) as exc:
        raise ValueError('invalid decimal integer') from exc


def format_int(value):
    if not isinstance(value, int) or type(value) is bool:
        raise TypeError('integer required')
    if type(value) is not int:
        value = int(value)
    try:
        return str(value)
    except ValueError as exc:
        if _LIMIT_ERROR not in str(exc):
            raise
        # Decimal(integer) preserves the entire arbitrary-precision value.
        return format(Decimal(value), 'f')


class _ExactIntegerEncoder(json.JSONEncoder):
    """Use the stdlib JSON encoder grammar and replace only int formatting.

    Private stdlib generator is used *only* after ordinary dumps actually hit
    Python's digit-limit exception; normal CAT JSON stays byte-for-byte equal.
    """
    def iterencode(self, obj, _one_shot=False):
        markers = {} if self.check_circular else None
        encoder = encode_basestring_ascii if self.ensure_ascii else encode_basestring

        def floatstr(value, allow_nan=self.allow_nan):
            if value != value:
                result = 'NaN'
            elif value == INFINITY:
                result = 'Infinity'
            elif value == -INFINITY:
                result = '-Infinity'
            else:
                return float.__repr__(value)
            if not allow_nan:
                raise ValueError('Out of range float values are not JSON compliant: ' + repr(value))
            return result

        indent = " " * self.indent if isinstance(self.indent, int) else self.indent
        return _make_iterencode(markers, self.default, encoder, indent,
                                floatstr, self.key_separator, self.item_separator,
                                self.sort_keys, self.skipkeys, _one_shot,
                                _intstr=format_int)(obj, 0)


def dumps(obj, **kwargs):
    try:
        return json.dumps(obj, **kwargs)
    except ValueError as exc:
        if _LIMIT_ERROR not in str(exc):
            raise
        return json.dumps(obj, cls=_ExactIntegerEncoder, **kwargs)


def loads(text, **kwargs):
    try:
        return json.loads(text, **kwargs)
    except ValueError as exc:
        if _LIMIT_ERROR not in str(exc):
            raise
        return json.loads(text, parse_int=parse, **kwargs)
