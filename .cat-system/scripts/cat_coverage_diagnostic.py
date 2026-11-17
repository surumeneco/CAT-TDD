#!/usr/bin/env python3
"""Classify *existing* local coverage and rule nonproofs without changing verdicts.

A diagnostic over the exact submitted TestModel bytes, not independent
Source→Model Conformance, an infinite-domain solver, or a CAT Gate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

SCHEMA='cat-coverage-diagnostic/v1'
LIMIT=65536

class CoverageDiagnosticError(ValueError):
    pass


def require(value, message):
    if not value:
        raise CoverageDiagnosticError(message)


def _domain_reasons(domain, path=''):
    """Conservative domain diagnosis; uncertain cases remain unresolved."""
    if not isinstance(domain,dict):
        return [{'kind':'malformed-domain','path':path}]
    kind=domain.get('type')
    if kind=='reference':
        if not domain.get('resolved') or 'of' not in domain:
            return [{'kind':'unresolved-type-reference','path':path,
                     'type_name':domain.get('name')}]
        return _domain_reasons(domain['of'],path)
    if kind=='record':
        if not domain.get('resolved'):
            return [{'kind':'unresolved-record-shape','path':path}]
        causes=[]
        for field in domain.get('fields',[]):
            if not isinstance(field,dict):
                causes.append({'kind':'malformed-record-field','path':path})
                continue
            nested=path+'.'+field.get('id','?') if path else field.get('id','?')
            presence=field.get('presence','required')
            if presence=='undefined':
                causes.append({'kind':'undefined-presence-not-enumerable','path':nested})
            elif presence!='absent':
                causes.extend(_domain_reasons(field.get('domain'),nested))
        return causes
    if kind=='integer':
        low,high=domain.get('min'),domain.get('max')
        if type(low) is not int or type(high) is not int:
            return [{'kind':'nonfinite-integer-range','path':path}]
        if high>=low and high-low+1>LIMIT:
            return [{'kind':'finite-cardinality-cap','path':path,'lower_bound':high-low+1}]
        return []
    if kind=='enum':
        values=domain.get('values',[])
        if isinstance(values,list) and len(values)>LIMIT:
            return [{'kind':'finite-cardinality-cap','path':path,'lower_bound':len(values)}]
        return []
    if kind in ('boolean','null'):
        return []
    if kind in ('real','string','bytes','sequence','set'):
        return [{'kind':'nonfinite-domain','path':path,'domain_kind':kind}]
    if kind=='nullable':
        return _domain_reasons(domain.get('of'),path)
    if kind=='union':
        return [cause for idx,part in enumerate(domain.get('variants',[]))
                for cause in _domain_reasons(part,f'{path}|{idx}')]
    return [{'kind':'unsupported-domain','path':path,'domain_kind':kind}]


def explain(model,raw):
    require(isinstance(raw,bytes) and isinstance(model,dict),'exact TestModel JSON bytes required')
    require(model.get('schema')=='cat-test-model/v2','unsupported TestModel schema')
    fields=model.get('fields')
    checks=model.get('coverage_checks')
    require(isinstance(fields,list) and isinstance(checks,dict),
            'missing finite coverage/fields inventory')
    registry={}
    for field in fields:
        require(isinstance(field,dict) and isinstance(field.get('id'),str),
                'invalid field inventory')
        key=field['id']
        require(key not in registry,'duplicate field identity')
        registry[key]=field
    rule_items=model.get('rule_obligations',[])
    rule_registry={}
    for rule in rule_items:
        require(isinstance(rule,dict) and isinstance(rule.get('id'),str),
                'invalid Rule obligation inventory')
        rid=rule['id']
        require(rid not in rule_registry,'duplicate Rule obligation ID')
        rule_registry[rid]=rule
    sources={}
    for entry in model.get('normative_rule_inputs',[]):
        require(isinstance(entry,dict) and isinstance(entry.get('id'),str),
                'invalid normative Rule Source inventory')
        require(entry['id'] not in sources,'duplicate normative Rule Source')
        sources[entry['id']]=entry.get('sha256')
    source_record={}
    for record in model.get('source_records',[]):
        require(isinstance(record,dict) and isinstance(record.get('id'),str),
                'invalid source record')
        require(record['id'] not in source_record,'duplicate Source record')
        source_record[record['id']]=record.get('sha256')
    for rid,sha in sources.items():
        require(source_record.get(rid)==sha,'Source Rule input identity mismatch')

    outputs=[]
    for trigger,check in sorted(checks.items()):
        require(isinstance(check,dict) and check.get('result') in
                ('proved','uncovered','conflict','unproven'),
                'invalid local coverage verdict')
        verdict=check['result']
        reason=check.get('reason','')
        categories=[]
        if verdict=='proved':categories=[{'kind':'finite-local-guard-proved'}]
        elif verdict=='uncovered':categories=[{'kind':'finite-guard-gap',
                                               'count':check.get('uncovered_count')}]
        elif verdict=='conflict':categories=[{'kind':'guard-overlap',
                                              'count':check.get('overlap_count')}]
        elif 'Effect reads a non-required PI input' in reason:
            categories=[{'kind':'unsafe-presence-read'}]
        elif 'finite closure exceeds configured' in reason:
            categories=[{'kind':'finite-product-cap',
                         'combination_count':check.get('combination_count'),
                         'configured_limit':LIMIT}]
        elif 'guard reads non-finite or too-large domain/Presence' in reason:
            refs=check.get('guard_refs',[])
            for ref in refs:
                field=registry.get(ref)
                if field is None:
                    categories.append({'kind':'unknown-guard-field','field':ref})
                    continue
                for cause in _domain_reasons(field.get('domain'),ref):
                    categories.append({'field':ref,**cause})
            if not categories:
                categories=[{'kind':'finite-domain-not-enumerated',
                             'reason':'combination bound or unsupported Presence; exact cause not independently established'}]
        elif reason:
            categories=[{'kind':'unsupported-or-ambiguous-guard-proof',
                         'compiler_reason':reason}]
        else:
            categories=[{'kind':'missing-nonproof-reason'}]
        outputs.append({'trigger':trigger,'compiler_verdict':verdict,
                        'compiler_reason':reason if reason else None,
                        'reason_categories':categories,
                        'guard_refs':check.get('guard_refs',[]),
                        'uncovered_count':check.get('uncovered_count'),
                        'unreachable_rules':check.get('unreachable_rules',[])})

    unverified=model.get('unverified_rule_ids',[])
    require(isinstance(unverified,list) and len(unverified)==len(set(unverified)),
            'invalid unverified Rule inventory')
    rule_reasons=[]
    for rid in sorted(unverified):
        rule=rule_registry.get(rid)
        require(rule is not None, 'unverified Rule missing obligation '+rid)
        source_id=rule.get('source_artifact')
        require(source_id in sources,'unbound Rule Source '+rid)
        rule_reasons.append({'rule_id':rid,'source_artifact':source_id,
                             'source_sha256':sources[source_id],
                             'category':'unverified-normative-rule',
                             'verification_status':rule.get('verification_status','unverified'),
                             'verification_contract':rule.get('verification_contract')})
    return {'schema':SCHEMA,'status':'diagnostic',
            'model_sha256':hashlib.sha256(raw).hexdigest(),
            'formal_gate_status':'not-run','source_conformance_status':'not-run',
            'process_closure_status':'not-run',
            'meaning':'classifies existing compiler receipts only; no verdict promotion',
            'closed_world_requested':model.get('closed_world'),
            'local_coverage':outputs,'unverified_rules':rule_reasons,
            'unresolved_effects':model.get('unverified_effect_ids',[]),
            'unresolved_interfaces':model.get('unresolved_interfaces',[]),
            'unresolved_domains':model.get('unresolved_domains',[])}


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--model',required=True,type=Path)
    ap.add_argument('--output',required=True,type=Path)
    a=ap.parse_args(argv)
    try:
        raw=a.model.read_bytes()
        output=explain(json.loads(raw),raw)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(output,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'status':'diagnostic','triggers':len(output['local_coverage']),
                          'unverified_rules':len(output['unverified_rules']),
                          'output':str(a.output)},ensure_ascii=False))
        return 0
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print(json.dumps({'status':'blocked','reason':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
