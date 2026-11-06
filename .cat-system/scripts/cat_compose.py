#!/usr/bin/env python3
"""Conservative Process-to-Process composition graph over compiled TestModels.

An edge in a Process PI does not prove a compatible peer or effect delivery.
Only explicitly declared two-sided boundaries are connected; missing peers,
ambiguous operations, and external effects remain open proof obligations.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

SCHEMA='cat-process-composition/v1'

def canonical(obj):return json.dumps(obj,sort_keys=True,ensure_ascii=False,indent=2)+'\n'

def sha(data):return hashlib.sha256(data).hexdigest()

def compose(items):
    models={}
    hashes={}
    for path in items:
        p=Path(path);raw=p.read_bytes();m=json.loads(raw)
        if m.get('schema')!='cat-test-model/v2':raise ValueError('not a CAT v2 TestModel: '+str(p))
        ident=m.get('process')
        if not ident or ident in models:raise ValueError('missing or duplicate Process ID: '+repr(ident))
        models[ident]=m;hashes[ident]=sha(raw)
    if len(models)<2:raise ValueError('composition requires two or more independent Process models')
    peers={}
    for ident,m in models.items():
        bindings=[]
        if m.get('pi_boundaries'):
            for b in m['pi_boundaries']:
                bindings.append({'pi':b['artifact'],'peer':b['peer'],'direction':b['direction']})
        elif m.get('pi_boundary'):
            bindings=[{'pi':m.get('source_semantic_map',{}).get('pi',{}).get('artifact'),
                       **m['pi_boundary']}]
        peers[ident]=bindings
    edges=[];errors=[];unresolved=[]
    pairset=set()
    for ident,boundaries in peers.items():
        for b in boundaries:
            peer=b['peer']
            if peer not in models:
                unresolved.append({'process':ident,'pi':b['pi'],'peer':peer,'reason':'peer Process not in composition set'})
                continue
            pair=tuple(sorted([ident,peer]));
            if pair in pairset:continue
            pairset.add(pair)
            forward=[x for x in peers[ident] if x['peer']==peer]
            reverse=[x for x in peers[peer] if x['peer']==ident]
            if not reverse:
                unresolved.append({'process':ident,'peer':peer,'reason':'reverse Process boundary not declared'})
                continue
            compatible=[]
            for a in forward:
                for b2 in reverse:
                    lhs=a['direction'];rhs=b2['direction']
                    if (lhs=='send' and rhs=='send') or (lhs=='receive' and rhs=='receive'):
                        errors.append({'process':ident,'peer':peer,'pi':[a['pi'],b2['pi']],
                                       'reason':'incompatible mirrored PI directions'})
                    else:compatible.append({'from':a,'to':b2})
            if compatible:
                edges.append({'processes':pair,'boundaries':compatible,
                              'status':'unproven',
                              'reason':'field projection, state transition and external effect composition not proved'})
    for ident,m in models.items():
        if m.get('coverage_requirement')!='closed' or m.get('status')!='confirmed':
            unresolved.append({'process':ident,'reason':'local Process closure is partial or unconfirmed'})
        if m.get('normative_rules') or m.get('normative_sections') or m.get('type_obligations'):
            unresolved.append({'process':ident,'reason':'local normative or typed obligations have no verified evidence'})
    return {'schema':SCHEMA,'status':'blocked' if errors else 'inconclusive',
            'process_models_sha256':hashes,'edges':edges,'unresolved':unresolved,
            'conflicts':errors,'limits':['no-implicit-dataflow-binding','no-runtime-peer-observation','no-product-code-mutation']}


def main(args=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('models',nargs='+');ap.add_argument('-o','--output',required=True);ap.add_argument('--check',action='store_true')
    opts=ap.parse_args(args)
    try:
        res=compose(opts.models);out=canonical(res);p=Path(opts.output)
        if opts.check:
            if not p.exists() or p.read_text(encoding='utf-8')!=out:raise ValueError('stale Process composition evidence')
        else:
            p.parent.mkdir(parents=True,exist_ok=True);p.write_text(out,encoding='utf-8')
        print(json.dumps({'status':res['status'],'evidence':str(p),'edges':len(res['edges']),
                          'unresolved':len(res['unresolved']),'conflicts':len(res['conflicts'])},ensure_ascii=False))
        return 2 if res['status']=='blocked' else 0
    except (OSError,ValueError,KeyError) as exc:
        print(json.dumps({'status':'blocked','error':str(exc)},ensure_ascii=False),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
