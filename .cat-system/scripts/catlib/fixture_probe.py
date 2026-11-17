"""Identity and provenance checks for fixture-only diagnostic profiles.

This module does not interpret any product projection or prove that the named
Source rule is equivalent to a diagnostic predicate. A profile must validate
its own fixture shape and may only report fixture-level results.
"""
from __future__ import annotations

import hashlib
import json
import re


class RelationError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise RelationError(reason)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def _source_property(source_text, name):
    match=re.search(r'(?m)^'+re.escape(name)+r':\s*[\'\"]?([^\s\'\"#]+)',source_text)
    require(match is not None, 'Source '+name+' absent')
    return match.group(1)


def verify_identity(source_bytes, fixture_bytes, contract, *, expected_relation=None):
    """Check exact Source/fixture binding before a separate profile runs.

    Returns the fixture and evidence envelope, not a verdict. The profile
    is solely responsible for any fixture consistency decision.
    """
    require(isinstance(source_bytes,bytes) and isinstance(fixture_bytes,bytes),
            'exact Source and fixture bytes required')
    require(isinstance(contract,dict) and contract.get('schema')=='cat-relation-probe/v1',
            'unsupported relation probe contract')
    required=('source_artifact','source_sha256','rule_id','fixture_sha256','relation')
    require(all(isinstance(contract.get(key),str) and contract[key] for key in required),
            'incomplete relation probe identity')
    require(contract['source_sha256']==sha256(source_bytes), 'Source SHA-256 mismatch')
    require(contract['fixture_sha256']==sha256(fixture_bytes), 'fixture SHA-256 mismatch')
    try:
        source_text=source_bytes.decode('utf-8')
        fixture=json.loads(fixture_bytes)
    except (UnicodeError,ValueError) as exc:
        raise RelationError('Source/fixture cannot be decoded') from exc
    require(_source_property(source_text,'id')==contract['source_artifact'],
            'Source Artifact ID mismatch')
    require(_source_property(source_text,'kind')=='domain-spec',
            'relation Source must be a DomainSpec')
    # Existence only: matching the ID does not approve a machine predicate.
    rule_present=any(line.strip().startswith('|') and
                     [cell.strip() for cell in line.split('|')[1:-1]][0:1]==[contract['rule_id']]
                     for line in source_text.splitlines())
    require(rule_present, 'source Rule ID absent')
    if expected_relation is not None:
        require(contract['relation']==expected_relation, 'unsupported relation predicate')
    envelope={'schema':'cat-relation-probe-result/v1',
              'source_artifact':contract['source_artifact'],
              'source_sha256':contract['source_sha256'],
              'rule_id':contract['rule_id'],
              'source_status':_source_property(source_text,'status'),
              'fixture_sha256':contract['fixture_sha256'],
              'relation':contract['relation'],
              'verification_scope':'fixture-relational-integrity-only',
              'normative_status':'inconclusive',
              'formal_gate_status':'not-run'}
    return fixture,envelope
