#!/usr/bin/env python3
"""Fail-closed identity checks for a submitted external Effect evidence envelope.

Verifies *receipt integrity*, not the truth of a claim about the environment.
No literal 'success' from a fixture becomes CAT conformance or provider proof.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

SCHEMA='cat-external-effect-receipts/v1'

class ReceiptError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, message):
    if not ok:
        raise ReceiptError(message)


def _sha(value):
    return isinstance(value,str) and bool(re.fullmatch('[0-9a-f]{64}',value))


def _local(root,name):
    require(isinstance(name,str) and bool(name), 'observation file path required')
    root=Path(root).resolve(strict=True)
    candidate=Path(name)
    require(not candidate.is_absolute() and '..' not in candidate.parts,
            'observation path must remain under evidence root')
    full=(root/candidate).resolve(strict=True)
    require(full!=root and root in full.parents and full.is_file() and not full.is_symlink(),
            'observation path outside evidence root or invalid file')
    return full


def _model_sources(model):
    sources={}
    for entry in model.get('source_records',[]):
        require(isinstance(entry,dict), 'invalid model source record')
        sid=entry.get('id')
        sha=entry.get('sha256')
        require(isinstance(sid,str) and sid and _sha(sha), 'invalid model source identity')
        require(sid not in sources, 'duplicate model source ID')
        sources[sid]=sha
    require(bool(sources), 'model must retain source identities')
    return sources


def _rules(model,sources):
    rules={}
    for rule in model.get('rules',[]):
        require(isinstance(rule,dict) and isinstance(rule.get('id'),str),
                'invalid model Rule record')
        rid=rule['id']
        require(rid not in rules, 'duplicate Rule ID')
        require(rule.get('source_artifact') in sources, 'Rule has no identified TCE source')
        allowed=rule.get('allowed')
        require(isinstance(allowed,list) and bool(allowed),
                'Rule requires explicit allowed outcomes')
        for outcome in allowed:
            require(isinstance(outcome,dict) and isinstance(outcome.get('write'),list),
                    'Rule has invalid Effect inventory')
            targets=[]
            for write in outcome['write']:
                target=write.get('target') if isinstance(write,dict) else None
                require(isinstance(target,str) and target, 'Effect target not declared')
                require(target not in targets, 'duplicate Effect target within outcome')
                targets.append(target)
        rules[rid]=rule
    return rules


def inspect(model_bytes,packet,driver_bytes,observation_root):
    require(isinstance(model_bytes,bytes) and isinstance(driver_bytes,bytes),
            'actual model/driver bytes required')
    require(isinstance(packet,dict) and packet.get('schema')==SCHEMA,
            'invalid external Effect receipt schema')
    require(packet.get('model_sha256')==digest(model_bytes),
            'stale or rebinding Model SHA')
    require(packet.get('driver_sha256')==digest(driver_bytes),
            'stale or rebinding Driver SHA')
    require(isinstance(packet.get('implementation_head'),str)
            and re.fullmatch('[0-9a-f]{40}',packet['implementation_head']),
            'implementation HEAD must be an exact 40-hex commit ID')
    model=json.loads(model_bytes)
    require(isinstance(model,dict) and model.get('schema')=='cat-test-model/v2',
            'requires cat-test-model/v2')
    sources=_model_sources(model)
    require(packet.get('source_sha256')==sources, 'Source identity mismatch')
    rules=_rules(model,sources)
    records=packet.get('observations')
    require(isinstance(records,list), 'observations must be an array')
    seen=set();out=[];inconclusive=[]
    for entry in records:
        require(isinstance(entry,dict), 'observation receipt required')
        rid=entry.get('rule_id')
        rule=rules.get(rid)
        require(rule is not None, 'unknown Rule in Effect evidence')
        index=entry.get('outcome_index')
        require(type(index) is int and 1<=index<=len(rule['allowed']),
                'outcome index outside Source-bound Rule')
        target=entry.get('effect_target')
        require(isinstance(target,str) and any(
            write['target']==target for write in rule['allowed'][index-1]['write']),
            'Effect target not declared for selected outcome')
        run=entry.get('execution_id')
        require(isinstance(run,str) and run, 'missing observation execution ID')
        key=(run,rid,index,target)
        require(key not in seen,'duplicate observation receipt')
        seen.add(key)
        status=entry.get('reported_status')
        require(status in ('succeeded','failed','unknown','not-observed'),
                'unsupported reported Effect status')
        path=entry.get('observation_file')
        if status!='not-observed':
            raw=_local(observation_root,path).read_bytes()
            require(entry.get('observation_sha256')==digest(raw),
                    'observation file SHA mismatch')
            observation=json.loads(raw)
            require(isinstance(observation,dict)
                    and observation.get('schema')=='cat-effect-observation/v1',
                    'invalid observation payload')
            for field,expected in [('rule_id',rid),('outcome_index',index),
                                   ('effect_target',target),('execution_id',run),
                                   ('reported_status',status)]:
                require(observation.get(field)==expected,
                        'observation identity/status mismatch: '+field)
        else:
            require(path in (None,'') and entry.get('observation_sha256') in (None,''),
                    'not-observed must not masquerade as an observed receipt')
        if status in ('unknown','not-observed'):
            inconclusive.append({'execution_id':run,'rule_id':rid,
                                 'effect_target':target,'reason':status})
        out.append({'execution_id':run,'rule_id':rid,
                    'source_artifact':rule['source_artifact'],
                    'source_sha256':sources[rule['source_artifact']],
                    'outcome_index':index,'effect_target':target,
                    'reported_status':status,
                    'observation_sha256':entry.get('observation_sha256'),
                    'verification_status':'receipt-identity-only'
                        if status in ('succeeded','failed') else 'inconclusive'})
    return {'schema':'cat-external-effect-receipt-diagnostic/v1',
            'status':'inconclusive' if inconclusive else 'consistent-receipts-only',
            'normative_status':'inconclusive',
            'formal_gate_status':'not-run',
            'implementation_conformance_status':'not-run',
            'provider_authentication_status':'not-run',
            'external_effect_proof':'not-run',
            'model_sha256':packet['model_sha256'],
            'source_sha256':sources,
            'driver_sha256':packet['driver_sha256'],
            'implementation_head_claim':packet['implementation_head'],
            'implementation_head_checkout_verified':False,
            'receipts':out,'unresolved':inconclusive,
            'limitations':['synthetic-fixtures-do-not-prove-real-effects',
                           'no-observation-provider-authentication',
                           'no-implementation-tree-attestation',
                           'no-normative-source-verifier-equivalence',
                           'no-external-side-effect-or-atomicity-proof']}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--packet',type=Path,required=True)
    p.add_argument('--driver',type=Path,required=True)
    p.add_argument('--observation-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        result=inspect(args.model.read_bytes(),
                       json.loads(args.packet.read_text(encoding='utf-8')),
                       args.driver.read_bytes(),args.observation_root)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'status':result['status'],
                          'normative_status':result['normative_status'],
                          'path':str(args.output)}))
        return 0
    except (ReceiptError,ValueError,KeyError,OSError,TypeError,IndexError) as exc:
        print(json.dumps({'status':'blocked','reason':str(exc)}),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
