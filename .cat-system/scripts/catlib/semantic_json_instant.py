"""Explicit JSON/instant carriers and codecs; no application admission policy.

Candidate runtime extension. JSON membership, equality and codecs are iterative;
the finite-tree domain has no chosen recursion-depth or binary64 restriction.
Instant values are exact rationals; external wire binding stays explicit.
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import json
import math
import re


class BindingError(ValueError):
    pass


def json_contains(value, object_root=False):
    if object_root and type(value) is not dict:
        return False
    active = set()
    stack = [(False, value)]
    while stack:
        leaving, current = stack.pop()
        kind = type(current)
        if leaving:
            active.remove(id(current))
        elif current is None or kind in (str, bool, int):
            continue
        elif kind is float:
            if not math.isfinite(current):
                return False
        elif kind is Decimal:
            if not current.is_finite():
                return False
        elif kind in (dict, list):
            if id(current) in active:
                return False
            if kind is dict and any(type(key) is not str for key in current):
                return False
            active.add(id(current))
            stack.append((True, current))
            stack.extend((False, item) for item in (current.values() if kind is dict else current))
        else:
            return False
    return True


def _number(value):
    # A float is already a decoded value. This does not recover its input token.
    return Decimal(str(value)) if type(value) is float else Decimal(value)


def json_equal(left, right):
    if not json_contains(left) or not json_contains(right):
        raise BindingError('JSON comparison requires finite JSON trees')
    stack = [(left, right)]
    while stack:
        a, b = stack.pop()
        ta, tb = type(a), type(b)
        if ta in (int, float, Decimal) and tb in (int, float, Decimal):
            if _number(a) != _number(b):
                return False
        elif ta is not tb:
            return False
        elif ta is dict:
            if a.keys() != b.keys():
                return False
            stack.extend((a[key], b[key]) for key in a)
        elif ta is list:
            if len(a) != len(b):
                return False
            stack.extend(zip(a, b))
        elif a != b:
            return False
    return True


def json_loads_exact(text):
    """JSON text decoder with exact numeric tokens and an iterative grammar.

    Duplicate object keys follow the last-member behavior of JSONB. This is a
    codec fact, not a new application permission for duplicate/unknown keys.
    """
    if type(text) is not str:
        raise BindingError('JSON text must be a string')

    def reject_constant(value):
        raise BindingError('non-finite JSON constant: ' + value)

    decoder = json.JSONDecoder(parse_int=Decimal, parse_float=Decimal,
                               parse_constant=reject_constant)
    stack = []
    result = None
    root_set = False
    index = 0

    def whitespace(position):
        while position < len(text) and text[position] in ' \t\r\n':
            position += 1
        return position

    def attach(value):
        nonlocal result, root_set
        if not stack:
            if root_set:
                raise BindingError('multiple JSON roots')
            result, root_set = value, True
        else:
            frame = stack[-1]
            if frame['kind'] == 'array':
                frame['value'].append(value)
            else:
                frame['value'][frame['key']] = value
            frame['state'] = 'comma'

    try:
        while True:
            index = whitespace(index)
            if not stack and root_set:
                if index != len(text):
                    raise BindingError('trailing JSON content')
                return result
            if index >= len(text):
                raise BindingError('incomplete JSON text')
            char = text[index]
            if stack:
                frame = stack[-1]
                state = frame['state']
                if state == 'comma':
                    close = ']' if frame['kind'] == 'array' else '}'
                    if char == close:
                        stack.pop(); index += 1; continue
                    if char != ',':
                        raise BindingError('expected JSON comma or closing delimiter')
                    frame['state'] = 'value' if frame['kind'] == 'array' else 'key'
                    index += 1; continue
                if state in ('first-key', 'key'):
                    if state == 'first-key' and char == '}':
                        stack.pop(); index += 1; continue
                    if char != '"':
                        raise BindingError('JSON object key must be a string')
                    key, index = decoder.raw_decode(text, index)
                    frame['key'], frame['state'] = key, 'colon'
                    continue
                if state == 'colon':
                    if char != ':':
                        raise BindingError('expected JSON colon')
                    frame['state'] = 'value'; index += 1; continue
                if state == 'first-value' and char == ']':
                    stack.pop(); index += 1; continue
            if char in '[{':
                value = [] if char == '[' else {}
                attach(value)
                stack.append({'kind': 'array' if char == '[' else 'object', 'value': value,
                              'state': 'first-value' if char == '[' else 'first-key'})
                index += 1
            else:
                value, index = decoder.raw_decode(text, index)
                if not json_contains(value) or type(value) in (list, dict):
                    raise BindingError('invalid JSON scalar')
                attach(value)
    except (json.JSONDecodeError, InvalidOperation, OverflowError) as exc:
        raise BindingError('invalid JSON text: ' + str(exc)) from exc


def json_dumps_exact(value):
    if not json_contains(value):
        raise BindingError('JSON encoding requires a finite JSON tree')
    output = []
    stack = [('value', value)]
    while stack:
        kind, item = stack.pop()
        if kind == 'raw':
            output.append(item)
        elif item is None:
            output.append('null')
        elif type(item) is bool:
            output.append('true' if item else 'false')
        elif type(item) is str:
            output.append(json.dumps(item, ensure_ascii=True))
        elif type(item) in (int, Decimal):
            output.append(str(Decimal(item)))
        elif type(item) is float:
            output.append(json.dumps(item, allow_nan=False))
        elif type(item) is list:
            output.append('['); stack.append(('raw', ']'))
            for i in range(len(item)-1, -1, -1):
                stack.append(('value', item[i]))
                if i:
                    stack.append(('raw', ','))
        else:
            output.append('{'); stack.append(('raw', '}'))
            keys = sorted(item)
            for i in range(len(keys)-1, -1, -1):
                key = keys[i]
                stack.append(('value', item[key]))
                stack.append(('raw', ':'))
                stack.append(('raw', json.dumps(key, ensure_ascii=True)))
                if i:
                    stack.append(('raw', ','))
    return ''.join(output)


@dataclass(frozen=True, order=True)
class InstantValue:
    seconds: Fraction

    def __post_init__(self):
        if type(self.seconds) is not Fraction:
            raise BindingError('instant carrier requires an exact Fraction')


_OFFSET = re.compile(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})\Z')
_EPOCH_ORDINAL = date(1970, 1, 1).toordinal()


def decode_offset_datetime(text):
    """Explicit example binding: years 0001..9999, known offset, no leap second.

    The abstract InstantValue domain is not restricted to this codec's syntax or
    year range. The RFC 3339 -00:00 convention is outside this known-offset
    binding; it is not a claim that the abstract instant is invalid. Callers
    must choose an owner binding; raw strings are not values
    of the instant domain and this does not change any product API acceptance.
    """
    match = _OFFSET.fullmatch(text) if type(text) is str else None
    if match is None:
        raise BindingError('explicit offset datetime binding required')
    year, month, day, hour, minute, second = map(int, match.groups()[:6])
    fraction, zone = match.groups()[6:]
    if zone == '-00:00':
        raise BindingError('unknown local offset is not a known UTC offset')
    if hour > 23 or minute > 59 or second > 59:
        raise BindingError('unsupported datetime clock value')
    try:
        ordinal = date(year, month, day).toordinal()
    except ValueError as exc:
        raise BindingError('unsupported datetime calendar value') from exc
    offset = 0
    if zone != 'Z':
        zh, zm = map(int, zone[1:].split(':'))
        if zh > 23 or zm > 59:
            raise BindingError('invalid UTC offset')
        offset = (zh*3600 + zm*60) * (1 if zone[0] == '+' else -1)
    whole = (ordinal-_EPOCH_ORDINAL)*86400 + hour*3600 + minute*60 + second-offset
    return InstantValue(Fraction(whole) + (Fraction(Decimal('0.'+fraction)) if fraction else 0))


def decode_aware_datetime(value):
    if type(value) is not datetime or value.utcoffset() is None:
        raise BindingError('aware datetime binding required')
    offset = value.utcoffset()
    seconds = ((value.toordinal()-_EPOCH_ORDINAL)*86400 + value.hour*3600 + value.minute*60 + value.second
               - offset.days*86400 - offset.seconds)
    return InstantValue(Fraction(seconds) + Fraction(value.microsecond-offset.microseconds, 1000000))


def encode_instant_transport(value):
    if type(value) is not InstantValue:
        raise BindingError('instant carrier required')
    return {'$cat_instant': {'n': str(Decimal(value.seconds.numerator)), 'd': str(Decimal(value.seconds.denominator))}}


def decode_instant_transport(value):
    if type(value) is not dict or set(value) != {'$cat_instant'}:
        raise BindingError('invalid typed instant transport')
    pair = value['$cat_instant']
    if (type(pair) is not dict or set(pair) != {'n', 'd'} or type(pair['n']) is not str or type(pair['d']) is not str
            or not re.fullmatch(r'0|-?[1-9][0-9]*', pair['n']) or not re.fullmatch(r'[1-9][0-9]*', pair['d'])):
        raise BindingError('invalid exact instant fraction')
    return InstantValue(Fraction(int(Decimal(pair['n'])), int(Decimal(pair['d']))))
