#!/usr/bin/env python3
"""CAT rule Verifier Gate: bound, auditable outcomes with immutable source/fixture hashes.

This entry point refuses to prove an external effect from a static check.
Evidence submitted by authors is not a trusted independent verifier.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from catlib import verifier_contracts as vc

SCHEMA='cat-verifier-gate/v1'


def _sha(data):return hashlib.sha256(data).hexdigest()


def _canon(payload):return json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2)+'\n'


def _inside(root,rel):
    if not isinstance(rel,str) or not rel or Path(rel).is_absolute():
        raise ValueError('fixture path must be a nonempty root-relative string')
    path=(root/rel).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('fixture path escapes explicitly authorized fixture root')
    if not path.is_file():raise ValueError('fixture not found: '+rel)
    return path


def execute_static(contract,fixture_root):
    """Three bounded adapters with deterministic fixture/result evidence.

    Capabilities are not interchangeable. No shell, network, database, DOM,
    Discord, process launch or arbitrary import is performed here.
    """
    rid=contract['rule_id'];cap=contract['capability'];exe=contract.get('execution')
    if not exe:
        return {'rule_id':rid,'status':'not-run','reason':'no executable adapter/fixture bound to rule'}
    allowed={
        'file-sha256':{'source-structure','filesystem'},
        'text-contains':{'source-structure'},
        'json-equals':{'source-structure','type-projection'},
    }
    adapter=exe.get('adapter') if isinstance(exe,dict) else None
    if adapter not in allowed:
        return {'rule_id':rid,'status':'inconclusive','reason':'no registered deterministic adapter for '+str(adapter)}
    if cap not in allowed[adapter]:
        return {'rule_id':rid,'status':'inconclusive','reason':'adapter cannot verify declared capability '+str(cap)}
    try:
        path=_inside(fixture_root,exe.get('fixture'))
        raw=path.read_bytes();digest=_sha(raw)
        if adapter=='file-sha256':
            expected=exe.get('expected_sha256')
            if not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected):
                raise ValueError('file-sha256 expected_sha256 must be 64 lowercase hex chars')
            observed=digest
        elif adapter=='text-contains':
            expected=exe.get('expected')
            if not isinstance(expected,str) or not expected:
                raise ValueError('text-contains expected text required')
            observed=(expected in raw.decode('utf-8'))
            expected=True
        else:
            expected=exe.get('expected')
            observed=json.loads(raw)
        status='passed' if observed==expected else 'failed'
        return {'rule_id':rid,'status':status,'capability':cap,'verifier_id':adapter,
                'fixture':str(path.relative_to(fixture_root.resolve()).as_posix()),
                'fixture_sha256':digest,'assertions':[{'expected':expected,'observed':observed}],
                'evidence_sha256':_sha(vc.canonical({'rule_id':rid,'capability':cap,
                                                      'fixture_sha256':digest,'expected':expected,
                                                      'observed':observed,'adapter':adapter}))}
    except (UnicodeError,json.JSONDecodeError,ValueError,TypeError,OSError) as exc:
        return {'rule_id':rid,'status':'failed','reason':'deterministic verifier failed: '+str(exc)}


def evaluate(model_path,registry_path=None,evidence_path=None,fixture_root=None):
    mraw=Path(model_path).read_bytes();model=json.loads(mraw)
    if model.get('schema')!='cat-test-model/v2':raise ValueError('expected canonical CAT TestModel')
    rules=model.get('normative_rules',[])
    if not isinstance(rules,list):raise ValueError('invalid normative rule inventory')
    ids=[r['id'] for r in rules]
    if len(set(ids))!=len(ids):raise ValueError('ambiguous duplicate normative rule IDs')
    input_shas={'model':_sha(mraw)}
    contract_by_id={};out_of_scope=[]
    if registry_path:
        raw=Path(registry_path).read_bytes();data=json.loads(raw)
        if data.get('schema') not in ('cat-verifier-registry/v1','cat-review-verifier-contracts/v1'):
            raise ValueError('invalid registry schema')
        for entry in data.get('entries',[]):
            rid=entry.get('rule_id') or entry.get('id')
            if rid in contract_by_id:raise ValueError('duplicate contract for '+str(rid))
            if rid not in ids:
                out_of_scope.append(rid)
                continue
            if entry.get('capability') not in vc.CAPABILITIES and entry.get('capability') is not None:
                raise ValueError('unknown verifier capability for '+rid)
            contract_by_id[rid]={'rule_id':rid,'capability':entry.get('capability'),
                                 'requirement':entry.get('requirement'),
                                 'execution':entry.get('execution')}
        input_shas['registry']=_sha(raw)
    external={}
    if evidence_path:
        raw=Path(evidence_path).read_bytes();data=json.loads(raw)
        if data.get('schema')!='cat-verifier-evidence/v1':raise ValueError('invalid evidence schema')
        for entry in data.get('entries',[]):
            rid=entry.get('rule_id')
            if rid in external:raise ValueError('duplicate evidence for '+str(rid))
            external[rid]=entry
        input_shas['evidence']=_sha(raw)
    by_artifact={rec['id']:rec['sha256'] for rec in model.get('source_records',[])}
    outcomes=[]
    for rule in rules:
        rid=rule['id'];source=rule['source_artifact'];digest=by_artifact.get(source)
        if not digest:raise ValueError('rule source is missing hash: '+rid)
        contract=contract_by_id.get(rid)
        if contract is None:
            result={'rule_id':rid,'status':'not-run','reason':'no bound verifier contract for rule'}
        elif contract['capability'] is None:
            result={'rule_id':rid,'status':'inconclusive','reason':'verifier capability not assigned'}
        elif rid in external:
            evidence=external[rid]
            if evidence.get('source_sha256')!=digest:
                result={'rule_id':rid,'status':'failed','reason':'external evidence source SHA mismatch'}
            else:
                result=vc.verify_evidence(contract,evidence)
        elif fixture_root:
            result=execute_static(contract,Path(fixture_root).resolve())
        else:
            result={'rule_id':rid,'status':'not-run','reason':'no fixture/external execution evidence'}
        outcomes.append({**result,'source_artifact':source,'source_sha256':digest})
    opaque=model.get('type_obligations',[])
    sections=model.get('normative_sections',[])
    conflicts=model.get('rule_conflicts',[])
    if conflicts or any(x['status']=='failed' for x in outcomes):status='blocked'
    elif (model.get('status')!='confirmed' or model.get('coverage_requirement')!='closed'
          or opaque or sections or any(x['status']!='passed' for x in outcomes)
          or out_of_scope):status='inconclusive'
    else:status='passed'
    return {'schema':SCHEMA,'status':status,'process':model['process'],
            'input_sha256':input_shas,'outcomes':outcomes,'unmapped_contracts':out_of_scope,
            'uninterpreted_sections':[{'source':s['source_artifact'],'sha256':s['sha256']}
                                      for s in sections],
            'type_obligations':[x['field'] for x in opaque],
            'conflicts':conflicts,
            'reason':('all registered normative rule evidence verified and complete closed-world model'
                      if status=='passed' else 'partial/unverified/failed rules or model proof obligations remain')}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',required=True)
    parser.add_argument('--registry')
    parser.add_argument('--evidence')
    parser.add_argument('--fixture-root')
    parser.add_argument('-o','--output',required=True)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args(argv)
    try:
        obj=evaluate(args.model,args.registry,args.evidence,args.fixture_root)
        out=_canon(obj);path=Path(args.output)
        if args.check:
            if path.read_text(encoding='utf-8')!=out:raise ValueError('stale verifier Gate evidence')
        else:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(out,encoding='utf-8')
        print(json.dumps({'status':obj['status'],'output':str(path),
                          'outcomes':len(obj['outcomes'])},ensure_ascii=False))
        return 2 if obj['status']=='blocked' else 0
    except (OSError,ValueError,KeyError,vc.ContractError) as exc:
        print(json.dumps({'status':'blocked','error':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
