#!/usr/bin/env python3
"""Read-only, hash-recorded regression for a review-package Process assembly.

This is a compiler and semantic inventory test, NOT Process Closure, CAT
approval, TDD Green, or implementation conformance. Candidate inputs remain
candidates; generated models are placed in a temporary directory only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import sys
from cat_compile_v2 import load, Blocked
import cat_model_conformance

SCHEMA='cat-assembly-regression/v1'


def sha(raw):return hashlib.sha256(raw).hexdigest()


def safe(root,rel):
    if not isinstance(rel,str) or not rel or chr(0) in rel:
        raise Blocked('assembly requires a safe relative path')
    relative=Path(rel)
    if relative.is_absolute() or '..' in relative.parts or '\\' in rel:
        raise Blocked('assembly path escapes review package')
    root=root.resolve(strict=True)
    cursor=root
    for segment in relative.parts:
        cursor=cursor/segment
        if cursor.is_symlink():
            raise Blocked('assembly source cannot traverse a symbolic link')
    path=cursor.resolve(strict=True)
    if root not in path.parents or not path.is_file():
        raise Blocked('assembly source is not a regular file under package root')
    return path


def review(root,assembly,allow_draft=False):
    root=Path(root).resolve(strict=True)
    assembly=safe(root,assembly)
    raw=assembly.read_bytes();data=json.loads(raw)
    if data.get('schema')!='cat-reviewed-source-assembly/v1' or not isinstance(data.get('processes'),list):
        raise Blocked('review assembly schema invalid')
    seen=set();rows=[]
    with tempfile.TemporaryDirectory(prefix='cat-assembly-regression-') as td:
        for entry in data['processes']:
            if not isinstance(entry,dict) or not isinstance(entry.get('owner'),str) or not entry['owner']:
                raise Blocked('assembly Process entry must have owner')
            if entry['owner'] in seen:raise Blocked('duplicate assembly owner')
            seen.add(entry['owner'])
            inputs={}
            for key in ('process','pis','tces','domain_specs','common_rules','domain_rules'):
                value=entry.get(key)
                if key=='process':
                    inputs[key]=safe(root,value)
                else:
                    if not isinstance(value,list):raise Blocked('assembly '+key+' must be an array')
                    inputs[key]=[safe(root,x) for x in value]
            if not inputs['pis'] or not inputs['tces'] or len(inputs['domain_rules'])>1:
                raise Blocked('assembly must include PI/TCE and at most one DomainRule')
            domain=inputs['domain_rules'][0] if inputs['domain_rules'] else None
            all_paths=[inputs['process'],*inputs['pis'],*inputs['tces'],*inputs['domain_specs'],*inputs['common_rules'],*inputs['domain_rules']]
            local_shas={str(p.relative_to(root)):sha(p.read_bytes()) for p in all_paths}
            try:
                model=load(inputs['process'],inputs['pis'],inputs['tces'],domain,
                           allow_draft=allow_draft,common_rules=inputs['common_rules'],
                           domain_specs=inputs['domain_specs'],allow_partial=True)
                out=Path(td)/(entry['owner']+'.json')
                out.write_text(json.dumps(model,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
                check=cat_model_conformance.validate(inputs['process'],inputs['pis'],inputs['tces'],out,
                    domain,inputs['common_rules'],inputs['domain_specs'],allow_draft)
                if check['status']!='passed':
                    raise Blocked('Model Conformance mismatches '+str(check['mismatches']))
                rows.append({'owner':entry['owner'],'status':'passed','model_status':model['status'],
                    'coverage_claim':model['coverage_claim'],
                    'source_count':len(model['source_records']),
                    'unverified_rule_count':len(model.get('unverified_rule_ids',[])),
                    'model_sha256':sha(out.read_bytes()),'input_sha256':local_shas,
                    'process_closure':'not-run','implementation_conformance':'not-run'})
            except (Blocked,ValueError,TypeError,KeyError,OSError) as exc:
                row={'owner':entry['owner'],'status':'blocked','reason':str(exc),
                     'input_sha256':local_shas,
                     'process_closure':'not-run','implementation_conformance':'not-run'}
                # A separate diagnostic subset can isolate a shared DomainRule
                # binding error. It NEVER changes the full-assembly verdict.
                if allow_draft and inputs['domain_rules']:
                    try:
                        subset=load(inputs['process'],inputs['pis'],inputs['tces'],None,
                                    allow_draft=True,common_rules=inputs['common_rules'],
                                    domain_specs=inputs['domain_specs'],allow_partial=True)
                        subfile=Path(td)/(entry['owner']+'-subset.json')
                        subfile.write_text(json.dumps(subset,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
                        check=cat_model_conformance.validate(inputs['process'],inputs['pis'],inputs['tces'],subfile,
                            None,inputs['common_rules'],inputs['domain_specs'],True)
                        row['diagnostic_subset']={
                            'status':check['status'],
                            'excluded_input_sha256':{str(x.relative_to(root)):sha(x.read_bytes()) for x in inputs['domain_rules']},
                            'model_status':subset['status'],
                            'source_count':len(subset['source_records']),
                            'model_conformance_mismatches':check['mismatches'],
                            'note':'incomplete normative input; this subset is not an acceptance result',
                        }
                    except (Blocked,ValueError,TypeError,KeyError,OSError) as subset_exc:
                        row['diagnostic_subset']={'status':'blocked','reason':str(subset_exc)}
                rows.append(row)
    return {'schema':SCHEMA,'assembly_sha256':sha(raw),'process_count':len(rows),
            'status':'passed' if rows and all(x['status']=='passed' for x in rows) else 'blocked',
            'meaning':'compiler and independent Model Conformance ONLY; no normative approval or runtime proof',
            'results':rows}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True)
    p.add_argument('--assembly',required=True)
    p.add_argument('--allow-draft',action='store_true')
    p.add_argument('--output',required=True)
    args=p.parse_args(argv)
    try:
        result=review(args.root,args.assembly,args.allow_draft)
        out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf8')
        print(json.dumps({'status':result['status'],'count':result['process_count'],'output':str(out)}))
        return 0 if result['status']=='passed' else 2
    except (Blocked,ValueError,TypeError,KeyError,OSError) as exc:
        print(json.dumps({'status':'blocked','reason':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
