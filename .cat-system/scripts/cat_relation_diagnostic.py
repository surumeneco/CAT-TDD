#!/usr/bin/env python3
"""Source-pinned, fixture-only relational inspection for marker/style projections.

The probe can reject internally inconsistent fixture values. It does not prove
that an arbitrary Source Rule has the same meaning as this fixed predicate, nor
that the fixture arose from actual HOCON, HTTP, database, or rendered geometry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from catlib import semantic_types


class RelationError(ValueError):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, reason):
    if not condition:
        raise RelationError(reason)


def source_id(source_text):
    match=re.search(r'(?m)^id:\s*[\'"]?([^\s\'"#]+)',source_text)
    require(match is not None, 'Source Artifact ID absent')
    return match.group(1)


def source_status(source_text):
    match=re.search(r'(?m)^status:\s*[\'"]?([a-z-]+)',source_text)
    require(match is not None, 'Source status absent')
    return match.group(1)


def _lookup(container, path):
    item=container
    for segment in path.split('.'):
        if not isinstance(item,dict) or segment not in item:
            return None
        item=item[segment]
    return item


def inspect(source_bytes, fixture_bytes, contract):
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
    require(source_id(source_text)==contract['source_artifact'],
            'Source Artifact ID mismatch')
    source_kind=re.search(r'(?m)^kind:\s*([a-z-]+)',source_text)
    require(source_kind and source_kind.group(1)=='domain-spec',
            'relation Source must be a DomainSpec')
    # Identity check only: finding a Rule ID in Source does not approve
    # the semantics of the verifier's built-in predicate.
    lines=source_text.splitlines()
    rule_present=any(line.strip().startswith('|') and
                     [cell.strip() for cell in line.split('|')[1:-1]][0:1]==[contract['rule_id']]
                     for line in lines)
    require(rule_present, 'source Rule ID absent')
    require(contract['relation']=='marker-style-references/v1',
            'unsupported relation predicate')

    inspected=_lookup(fixture,'validated')
    result={'schema':'cat-relation-probe-result/v1',
            'source_artifact':contract['source_artifact'],
            'source_sha256':contract['source_sha256'],
            'rule_id':contract['rule_id'],
            'source_status':source_status(source_text),
            'fixture_sha256':contract['fixture_sha256'],
            'relation':contract['relation'],
            'verification_scope':'fixture-relational-integrity-only',
            'normative_status':'inconclusive',
            'formal_gate_status':'not-run',
            'external_hocon_status':'not-run',
            'unverified':['normative-predicate-equivalence','fixture-authenticity',
                          'effective-hocon-inheritance','approved-color-policy',
                          'category-semantics','external-effect-and-transport']}
    if inspected is None:
        result.update({'status':'inconclusive','checks':[],
                       'reason':'validated projection not present in fixture'})
        return result
    require(isinstance(inspected,dict),'validated projection must be an object')
    for field in ('api_markers','api_styles','marker_styles'):
        require(isinstance(inspected.get(field),list),
                'validated '+field+' must be an array')
    markers,styles,links=(inspected[field]
                          for field in ('api_markers','api_styles','marker_styles'))
    errors=[]
    marker_by_id={}
    for index,marker in enumerate(markers):
        require(isinstance(marker,dict),'marker record must be an object')
        marker_id=marker.get('id')
        require(isinstance(marker_id,str) and marker_id,'marker ID missing')
        if marker_id in marker_by_id:
            errors.append({'reason':'duplicate-marker-id','marker_id':marker_id,'index':index})
        else:
            marker_by_id[marker_id]=marker
    link_by_id={}
    for index,link in enumerate(links):
        require(isinstance(link,dict),'marker style link must be an object')
        target=link.get('marker_id')
        require(isinstance(target,str) and target,'marker style link missing marker_id')
        if target in link_by_id:
            errors.append({'reason':'duplicate-marker-style-link','marker_id':target,'index':index})
            continue
        link_by_id[target]=link
        marker=marker_by_id.get(target)
        if marker is None:
            errors.append({'reason':'unknown-marker-reference','marker_id':target})
            continue
        style=link.get('style')
        if not isinstance(style,dict):
            errors.append({'reason':'missing-style-object','marker_id':target})
            continue
        if not any(semantic_types.same(style,candidate) for candidate in styles):
            errors.append({'reason':'style-not-declared-in-api-styles','marker_id':target})
        marker_owner=_lookup(marker,'owner.kind')
        if (not isinstance(marker_owner,str) or not marker_owner
                or style.get('owner_kind')!=marker_owner):
            errors.append({'reason':'owner-kind-mismatch','marker_id':target})
    for target in marker_by_id:
        if target not in link_by_id:
            errors.append({'reason':'marker-without-style-link','marker_id':target})
    result.update({'status':'failed' if errors else 'passed-fixture-only',
                   'errors':errors,
                   'marker_count':len(markers),'style_count':len(styles),
                   'link_count':len(links)})
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--contract',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    opts=parser.parse_args(argv)
    try:
        report=inspect(opts.source.read_bytes(),opts.fixture.read_bytes(),
                       json.loads(opts.contract.read_text(encoding='utf-8')))
        opts.output.parent.mkdir(parents=True,exist_ok=True)
        opts.output.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'status':report['status'],
                          'normative_status':report['normative_status'],
                          'path':str(opts.output)}))
        return 2 if report['status']=='failed' else 0
    except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:
        print(json.dumps({'status':'blocked','reason':str(exc)}),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
