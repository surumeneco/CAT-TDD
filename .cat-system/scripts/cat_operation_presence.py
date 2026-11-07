#!/usr/bin/env python3
"""Operation-scoped presence diagnostics; never substitutes for normative TCE vectors.

Reads compiler-owned TestModel; preserves missing, undefined, null and actual
values as distinct observations. No positive contract proof is inferred from
an operation being listed, or from a same-named field on a different PI.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
from catlib import semantic_types as types

SCHEMA='cat-operation-presence-probes/v1'

class PresenceError(ValueError):
    pass


def nominal(d):
    t=d.get('type')
    if t=='nullable':return nominal(d['of'])
    if t=='union':return nominal(d['variants'][0])
    if t=='boolean':return False
    if t=='integer':return d.get('min',0)
    if t=='real':return float(d.get('min',0.0))
    if t=='string':return '0' if d.get('format')=='safe-signed-integer' else ''
    if t=='bytes':return []
    if t in ('set','sequence'):return []
    if t=='enum':return d['values'][0]
    if t=='record' and not d.get('resolved'):
        raise PresenceError('record shape unresolved')
    if t=='record':return {f['id']:nominal(f['domain']) for f in d['fields'] if f['presence']=='required'}
    raise PresenceError('domain has no deterministic representative')


def probe(domain,presence,kind,value):
    try:
        state,ok=types.check_presence(domain,presence,value)
        return {'kind':kind,'observed_state':state,'type_accepts':ok}
    except types.DomainError as exc:
        return {'kind':kind,'status':'inconclusive','reason':str(exc)}


def diagnostics(model,raw):
    if not isinstance(model,dict) or not isinstance(model.get('pi_operations'),list) or not isinstance(model.get('fields'),list):
        raise PresenceError('model requires PI operations and fields')
    ops=model['pi_operations']; fields=model['fields']
    declared=model.get('operation_presence',[])
    if not isinstance(declared,list):raise PresenceError('operation_presence must be list')
    lookup={};op_ids={o['id']:o for o in ops}
    if len(op_ids)!=len(ops):raise PresenceError('duplicate PI operation ID')
    field_ids={f['id']:(f.get('source_pi'),f.get('role')) for f in fields}
    if len(field_ids)!=len(fields):raise PresenceError('duplicate PI field ID')
    for e in declared:
        key=(e['operation'],e['field'])
        if key in lookup or e['operation'] not in op_ids:
            raise PresenceError('duplicate or unknown operation presence binding')
        owner=op_ids[e['operation']].get('source_pi')
        if field_ids.get(e['field']) not in ((owner,'input'),(owner,'output')):
            raise PresenceError('operation presence references field outside owning PI')
        if e.get('source_pi')!=owner:
            raise PresenceError('operation presence has mismatched source PI')
        lookup[key]=e
    output=[]
    for op in ops:
        for field in fields:
            if field.get('source_pi')!=op.get('source_pi') or field.get('role') not in ('input','output'):
                continue
            bound=lookup.get((op['id'],field['id']))
            if bound and bound.get('source_pi')!=op['source_pi']:
                raise PresenceError('operation presence crosses PI owner')
            presence=bound['presence'] if bound else field.get('presence','required')
            if presence not in ('required','optional','absent','undefined'):
                raise PresenceError('unsupported presence')
            domain=field['domain']; cases=[]
            for kind,v in [('missing',types.MISSING),('undefined',types.UNDEFINED),('null',None)]:
                cases.append(probe(domain,presence,kind,v))
            try:
                sample=nominal(domain)
                cases.append(probe(domain,presence,'representative-value',sample))
                if domain['type']=='boolean':
                    cases.append(probe(domain,presence,'numeric-zero',0))
            except (PresenceError,types.DomainError,KeyError) as exc:
                cases.append({'kind':'representative-value','status':'inconclusive','reason':str(exc)})
            output.append({'pi':op['source_pi'],'operation':op['id'],'field':field['id'],
                           'presence':presence,'binding':'operation-explicit' if bound else 'PI-field-default',
                           'cases':cases})
    return {'schema':SCHEMA,'status':'candidate','conformance_status':'not-run',
            'test_execution_status':'not-run','model_sha256':hashlib.sha256(raw).hexdigest(),
            'meaning':'diagnostic probes only: TCE guards, effects and code are not verified',
            'probes':output}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',required=True);p.add_argument('--output',required=True)
    a=p.parse_args(argv)
    try:
        raw=Path(a.model).read_bytes();res=diagnostics(json.loads(raw),raw)
        out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(res,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf8')
        print(json.dumps({'status':res['status'],'probes':len(res['probes']),'output':str(out)}))
        return 0
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps({'status':'blocked','reason':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
