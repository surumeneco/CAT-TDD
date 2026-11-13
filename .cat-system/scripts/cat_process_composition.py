#!/usr/bin/env python3
"""Cross-Process typed composition check, independent from local Process closure.

Bindings are explicit. No edge, operation, field or effect is invented from
similar names. Unmapped external peers and unproved effects stay inconclusive.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

class CompositionError(ValueError):
    pass

def digest(data):
    return hashlib.sha256(data).hexdigest()

def _load(path):
    return json.loads(Path(path).read_bytes())

def _bounds(model):
    out=[]
    for bound in model.get('pi_boundaries',[]):
        peers=bound.get('peers',[bound.get('peer')])
        if not isinstance(peers,list) or any(not isinstance(x,str) or not x for x in peers):
            raise CompositionError('invalid PI peer specification')
        for peer in peers:
            directions=('send','receive') if bound['direction']=='bidirectional' else (bound['direction'],)
            for direction in directions:
                out.append({'source_process':model['process'],'source_pi':bound['artifact'],
                            'target_process':peer,'direction':direction})
    return out

def _bound(model,pi,peer,direction):
    return any(x['source_pi']==pi and x['target_process']==peer and
               x['direction']==direction for x in _bounds(model))

def _field(model,id_,role,pi):
    entries=[f for f in model.get('fields',[])
             if f.get('id')==id_ and f.get('role')==role and f.get('source_pi')==pi]
    if len(entries)!=1:
        raise CompositionError('missing/ambiguous '+role+' field '+id_+
                               ' owned by PI '+pi+' in '+model['process'])
    return entries[0]

def _operation(model,id_,source_pi,role):
    return any(x['id']==id_ and x.get('source_pi')==source_pi and x['direction']==role
               for x in model.get('pi_operations',[]))

# Re-export for compatibility with existing composition callers/tests.
from catlib.semantic_subtyping import subset as _type_subset


def _link(binding,models):
    source=models.get(binding['source_process'])
    target=models.get(binding['target_process'])
    if source is None or target is None:raise CompositionError('binding targets a missing Process')
    a=binding['source_pi'];b=binding['target_pi']
    if not _bound(source,a,target['process'],'send'):
        raise CompositionError('source PI has no declared send boundary')
    if not _bound(target,b,source['process'],'receive'):
        raise CompositionError('target PI has no declared receive boundary')
    source_op=binding.get('source_operation')
    target_op=binding.get('target_operation')
    if source_op is None or target_op is None:
        raise CompositionError('connection must name both source and target operations')
    if not _operation(source,source_op,a,'provide'):
        raise CompositionError('source operation is not provided by its PI')
    if not _operation(target,target_op,b,'accept'):
        raise CompositionError('target operation is not accepted by its PI')
    fields=binding.get('field_links')
    if not isinstance(fields,list) or not fields:
        raise CompositionError('connection requires typed field links')
    seen=set();seen_targets=set();checks=[]
    for mapping in fields:
        if not isinstance(mapping,dict) or set(mapping)!={'source_field','target_field'}:
            raise CompositionError('field link must identify both endpoints')
        pair=(mapping['source_field'],mapping['target_field'])
        if pair in seen:raise CompositionError('duplicate field binding')
        if pair[1] in seen_targets:
            raise CompositionError('ambiguous target field binding')
        seen.add(pair);seen_targets.add(pair[1])
        f=_field(source,pair[0],'output',a)
        t=_field(target,pair[1],'input',b)
        inclusion=_type_subset(f['domain'],t['domain'])
        f_presence=f.get('presence','required')
        t_presence=t.get('presence','required')
        # Presence is independent of type/nullability: a producer's possible
        # states must be accepted by the consumer, including missing/undefined.
        states={'required':{'value'},'optional':{'missing','value'},
                'absent':{'missing'},'undefined':{'undefined'}}
        if f_presence not in states or t_presence not in states:
            raise CompositionError('unsupported boundary presence')
        presences_ok=states[f_presence].issubset(states[t_presence])
        if inclusion is False or not presences_ok:
            raise CompositionError('typed/presence mismatch on '+pair[0]+' -> '+pair[1])
        proof='matched' if inclusion is True else 'inconclusive'
        checks.append({'source_field':f['id'],'target_field':t['id'],
                       'type':f['domain'],'target_type':t['domain'],
                       'presence':(f_presence,t_presence),'status':proof})
    # Partial field links cannot prove the receiver PI boundary. There is no
    # authorized operation-to-field projection in this schema; any value-
    # capable receiver field left unmapped remains inconclusive.
    unmapped_target_fields=sorted(f['id'] for f in target.get('fields',[])
        if f.get('role')=='input' and f.get('source_pi')==b
        and f.get('presence','required')!='absent'
        and f.get('id') not in seen_targets)
    return {'source_process':source['process'],'target_process':target['process'],
            'source_pi':a,'target_pi':b,'source_operation':source_op,
            'target_operation':target_op,'field_links':checks,
            'unmapped_target_fields':unmapped_target_fields,
            'status':'structurally-matched' if not unmapped_target_fields
                    and all(c['status']=='matched' for c in checks) else 'inconclusive',
            'external_effects_verified':False}

def _effect_claim_consistent(model):
    """Require exact declared Effect receipts before accepting local closure.

    This checks internal receipt consistency only, not independent source-to-
    model or implementation conformance. Missing/foreign/extra proof keys are
    not evidence of a locally closed Process.
    """
    rules=model.get('rules',[])
    if not isinstance(rules,list):
        return False
    expected=[]
    for rule in rules:
        if not isinstance(rule,dict) or not isinstance(rule.get('source_artifact'),str) or not isinstance(rule.get('id'),str):
            return False
        outcomes=rule.get('allowed')
        if not isinstance(outcomes,list):
            return False
        for outcome_number,outcome in enumerate(outcomes,1):
            if not isinstance(outcome,dict):
                return False
            writes=outcome.get('write',[])
            if not isinstance(writes,list):
                return False
            for write_number,write in enumerate(writes,1):
                if not isinstance(write,dict) or not isinstance(write.get('target'),str):
                    return False
                expected.append(f"{rule['source_artifact']}#{rule['id']}:{outcome_number}:{write_number}:{write['target']}")
    if len(expected)!=len(set(expected)):
        return False
    proofs=model.get('effect_checks')
    unresolved=model.get('unverified_effect_ids')
    if not expected and proofs is None and unresolved is None:
        return True  # legacy synthetic models with no declared Effects
    return (isinstance(proofs,dict)
            and set(proofs)==set(expected)
            and all(isinstance(proofs[key],dict) and proofs[key].get('result')=='proved'
                    for key in expected)
            and unresolved==[])


def _local_claim_consistent(model):
    """Check local closure receipts for internal contradictions, not Source conformance.

    Full Process Closure and independent Source->Model Conformance must be
    checked separately; this structural composition does not replace them.
    """
    checks=model.get('coverage_checks')
    return (model.get('status')=='confirmed'
            and model.get('coverage_requirement')=='closed'
            and model.get('coverage_claim')=='closed'
            and isinstance(checks,dict) and bool(checks)
            and all(isinstance(v,dict) and v.get('result')=='proved'
                    for v in checks.values())
            and model.get('unverified_rule_ids')==[]
            and _effect_claim_consistent(model)
            and model.get('unresolved_domains')==[]
            and model.get('unresolved_interfaces',[])==[]
            and model.get('presence_unproven')==[])

def compose(model_paths,binding_path=None):
    if len(model_paths)<2:raise CompositionError('composition requires >=2 Processes')
    models={};hashes={}
    for path in model_paths:
        raw=Path(path).read_bytes();model=json.loads(raw)
        pid=model.get('process')
        if not isinstance(pid,str) or not pid or pid in models:
            raise CompositionError('duplicate or missing Process ID')
        models[pid]=model;hashes[pid]=digest(raw)
    binding={'schema':'cat-process-bindings/v1','links':[]}
    binding_hash=None
    if binding_path is not None:
        raw=Path(binding_path).read_bytes();binding=json.loads(raw)
        binding_hash=digest(raw)
    if binding.get('schema')!='cat-process-bindings/v1' or not isinstance(binding.get('links'),list):
        raise CompositionError('invalid composition binding schema')
    if binding.get('model_sha256',hashes)!=hashes:
        raise CompositionError('composition model hash mismatch')
    edges=[]
    for model in models.values():edges.extend(_bounds(model))
    unresolved=[];proven=[];seen=set()
    for link in binding['links']:
        if not isinstance(link,dict):
            raise CompositionError('link record required')
        key=(link.get('source_process'),link.get('source_pi'),link.get('target_process'),
             link.get('target_pi'),link.get('source_operation'),link.get('target_operation'))
        if key in seen:raise CompositionError('duplicate connection link')
        seen.add(key)
        proven.append(_link(link,models))
    # Each validated link discharges both the sender's outgoing declaration
    # and the receiver's incoming declaration; neither proves external effects.
    bound_pairs=set()
    pending_pairs=set()
    for x in proven:
        pairs=((x['source_process'],x['source_pi'],x['target_process'],'send'),
               (x['target_process'],x['target_pi'],x['source_process'],'receive'))
        if x['status']=='structurally-matched':
            bound_pairs.update(pairs)
        else:
            pending_pairs.update(pairs)
    peer_edge_pairs={(x['source_process'],x['target_process'],x['direction'])
                     for x in edges}
    for edge in edges:
        key=edge['source_process'],edge['source_pi'],edge['target_process'],edge['direction']
        reverse='receive' if edge['direction']=='send' else 'send'
        reciprocal=(edge['target_process'],edge['source_process'],reverse)
        if edge['target_process'] not in models:
            unresolved.append({**edge,'reason':'peer outside assembled Process set'})
        elif reciprocal not in peer_edge_pairs:
            unresolved.append({**edge,'reason':'counterpart PI lacks reciprocal boundary'})
        elif key in pending_pairs:
            unresolved.append({**edge,'reason':'PI binding exists but structural proof is inconclusive'})
        elif key not in bound_pairs:
            unresolved.append({**edge,'reason':'PI connection/effect lacks explicit binding'})
    unproved_local=[]
    for p,model in models.items():
        if not _local_claim_consistent(model):
            unproved_local.append(p)
    # This proves typed links only. External effects, ordering and interleaving
    # are never proved merely by matching source/target schemas.
    statuses='inconclusive' if unresolved or unproved_local or any(not x['external_effects_verified'] for x in proven) else 'passed'
    return {'schema':'cat-process-composition/v1','status':statuses,
            'model_sha256':hashes,'binding_sha256':binding_hash,
            'bindings':proven,'unresolved_connections':unresolved,
            'unproved_local_processes':unproved_local,
            'reason':'typed connections match where bound; cross-Process effect/interleaving proof still required'
                     if statuses=='inconclusive' else 'all declared boundaries and external effects proved'}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',action='append',required=True)
    p.add_argument('--binding')
    p.add_argument('--output',required=True)
    a=p.parse_args(argv)
    try:
        result=compose(a.model,a.binding)
        path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'status':result['status'],'path':str(path)},ensure_ascii=False))
        return 0
    except (CompositionError,ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'status':'blocked','reason':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
