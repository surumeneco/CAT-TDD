#!/usr/bin/env python3
"""Produce typed boundary probes without fabricating TCE witnesses or test oracles.

This is an auxiliary compiler diagnostic, not a normative vector/TDD-Queue stage.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
from catlib import semantic_types as types

SCHEMA='cat-type-probes/v1'

class ProbeError(ValueError):
    pass

def nominal(d):
    t=d['type']
    if t=='nullable':return nominal(d['of'])
    if t=='union':return nominal(d['variants'][0])
    if t=='boolean':return False
    if t=='integer':return d.get('min',0) if d.get('min',0)<=d.get('max',float('inf')) else 0
    if t=='real':return float(d.get('min',0.0)) if d.get('min',0.0)<=d.get('max',float('inf')) else 0.0
    if t=='string':return '0' if d.get('format')=='safe-signed-integer' else ''
    if t=='bytes':return []
    if t in ('set','sequence'):return []
    if t=='enum':return d['values'][0]
    if t=='record':
        if not d.get('resolved'):raise ProbeError('nominal or untyped record requires field schema')
        return {f['id']:nominal(f['domain']) for f in d['fields'] if f['presence']=='required'}
    raise ProbeError('cannot derive representative value for '+str(t))

def typed_result(d,presence,value,kind):
    if kind=='missing':state,ok=types.check_presence(d,presence,types.MISSING)
    elif kind=='undefined':state,ok=types.check_presence(d,presence,types.UNDEFINED)
    else:state,ok=types.check_presence(d,presence,value)
    return {'kind':kind,'presence_result':state,'type_accepts':ok,
            **({'value':value} if kind not in ('missing','undefined') else {})}

def diagnostics(model,raw):
    if not isinstance(model,dict) or not isinstance(model.get('fields'),list):
        raise ProbeError('TestModel fields required')
    outputs=[]
    for field in model['fields']:
        d=field['domain'];presence=field.get('presence','required')
        item={'field':field['id'],'role':field['role'],'domain':d,'presence':presence,'status':'candidate',
              'cases':[]}
        item['cases'].append(typed_result(d,presence,None,'missing'))
        item['cases'].append(typed_result(d,presence,None,'null'))
        item['cases'].append(typed_result(d,presence,None,'undefined'))
        try:
            value=nominal(d)
            item['cases'].append(typed_result(d,presence,value,'representative-value'))
            for name,other in (('empty-string',''),('numeric-zero',0),('boolean-false',False)):
                item['cases'].append(typed_result(d,presence,other,name))
            if d['type']=='set' and d['element']['type']!='unknown':
                element=nominal(d['element'])
                item['cases'].append(typed_result(d,presence,[element,element],'duplicate-set-element'))
            if d['type']=='sequence' and d['element']['type']!='unknown':
                element=nominal(d['element'])
                item['cases'].append(typed_result(d,presence,[element,element],'duplicate-sequence-element'))
            if d['type']=='bytes':
                item['cases'].append({'kind':'bytes-octets','value':{'$cat_type':'bytes','octets':[0,255]},
                                      'type_accepts':types.contains(d,[0,255])})
                item['cases'].append({'kind':'invalid-octet','value':{'$cat_type':'bytes','octets':[256]},
                                      'type_accepts':types.contains(d,[256])})
            if d['type']=='real':
                item['cases'].append({'kind':'nonfinite-real','value':{'$cat_type':'real','value':'NaN'},
                                      'type_accepts':False})
                item['cases'].append({'kind':'infinite-real','value':{'$cat_type':'real','value':'Infinity'},
                                      'type_accepts':False})
        except (ProbeError,types.DomainError,KeyError) as exc:
            item['status']='inconclusive'
            item['reason']=str(exc)
        outputs.append(item)
    return {'schema':SCHEMA,'status':'candidate','conformance_status':'not-run','test_execution_status':'not-run',
            'meaning':'type/presence probes only; not rule witnesses or asserted product behavior',
            'process':model.get('process'),'model_sha256':hashlib.sha256(raw).hexdigest(),
            'rule_ids':sorted(x['id'] for x in model.get('rule_obligations',[])),
            'unresolved_fields':sorted(x['field'] for x in outputs if x['status']=='inconclusive'),
            'fields':outputs}

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--model',required=True)
    ap.add_argument('--output',required=True)
    args=ap.parse_args(argv)
    try:
        raw=Path(args.model).read_bytes()
        result=diagnostics(json.loads(raw),raw)
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'status':result['status'],'unresolved_fields':len(result['unresolved_fields']),'path':str(path)}))
        return 0
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'status':'blocked','reason':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
