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

from catlib import peer_binding

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
        if (not isinstance(peers,list) or not peers
                or any(not isinstance(x,str) or not x for x in peers)
                or len(set(peers))!=len(peers)
                or bound.get('peer')!=peers[0]):
            raise CompositionError('invalid PI peer specification')
        for peer in peers:
            directions=('send','receive') if bound['direction']=='bidirectional' else (bound['direction'],)
            for direction in directions:
                out.append({'source_process':model['process'],'source_pi':bound['artifact'],
                            'target_process':peer,'direction':direction})
    return out

def _bound(model,pi,peer,direction):
    return any(x['source_pi']==pi and x['target_process'] in (peer,peer_binding.ORIGIN)
               and x['direction']==direction for x in _bounds(model))

def _field(model,id_,role,pi):
    entries=[f for f in model.get('fields',[])
             if f.get('id')==id_ and f.get('role')==role and f.get('source_pi')==pi]
    if len(entries)!=1:
        raise CompositionError('missing/ambiguous '+role+' field '+id_+
                               ' owned by PI '+pi+' in '+model['process'])
    return entries[0]

def _operation(model,id_,source_pi,role,peer):
    # Static operations identify one peer; @execution-origin resolves to the
    # initiating Process of each run. Static composition alone cannot prove it.
    matches=[x for x in model.get('pi_operations',[])
             if x.get('id')==id_ and x.get('source_pi')==source_pi
             and x.get('direction')==role]
    boundaries=[b for b in model.get('pi_boundaries',[])
                if b.get('artifact')==source_pi]
    if len(matches)!=1 or len(boundaries)!=1:
        return False
    bound=boundaries[0]
    peers=bound.get('peers',[bound.get('peer')])
    if (not isinstance(peers,list) or not peers or len(peers)!=len(set(peers))
            or bound.get('peer')!=peers[0]):
        return False
    return peer_binding.match_operation(peers,matches[0].get('peer'),peer)

def _effective_presence(model, operation, field):
    """Read the Presence of a field for the *linked* PI Operation.

    A PI-wide Presence is only the default. The compiler keeps explicit
    Operation Presence separately in `operation_presence`, so treating the
    base Field row as the transferred value can accept a missing required
    value (or falsely reject an optional receiver).
    """
    matches=[row for row in model.get('operation_presence', [])
             if row.get('source_pi')==field.get('source_pi')
             and row.get('operation')==operation
             and row.get('field')==field.get('id')]
    if len(matches)>1:
        raise CompositionError('ambiguous operation Presence for '+field['id'])
    return matches[0]['presence'] if matches else field.get('presence','required')


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
    source_binding=_operation(source,source_op,a,'provide',target['process'])
    if not source_binding:
        raise CompositionError('source operation is not provided by its PI or assigned to peer')
    target_binding=_operation(target,target_op,b,'accept',source['process'])
    if not target_binding:
        raise CompositionError('target operation is not accepted by its PI or assigned to peer')
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
        f_presence=_effective_presence(source,source_op,f)
        t_presence=_effective_presence(target,target_op,t)
        # Presence is independent of type/nullability: a producer's possible
        # states must be accepted by the consumer, including missing/undefined.
        states={'required':{'value'},'optional':{'missing','value'},
                'absent':{'missing'},'undefined':{'undefined'}}
        if f_presence not in states or t_presence not in states:
            raise CompositionError('unsupported boundary presence')
        presences_ok=states[f_presence].issubset(states[t_presence])
        # Absence-only/undefined-only sources have no value to type-check.
        # Their declared Domains are irrelevant, not mutually incompatible.
        transfers_value='value' in states[f_presence]
        inclusion=_type_subset(f['domain'],t['domain']) if transfers_value else True
        if inclusion is False or not presences_ok:
            raise CompositionError('typed/presence mismatch on '+pair[0]+' -> '+pair[1])
        proof='matched' if inclusion is True else 'inconclusive'
        checks.append({'source_field':f['id'],'target_field':t['id'],
                       'type':f['domain'],'target_type':t['domain'],
                       'presence':(f_presence,t_presence),'status':proof,
                       'value_domain_proof':('proved' if transfers_value and inclusion is True
                                             else 'not-applicable' if not transfers_value
                                             else 'inconclusive')})
    # A field link is a declared connection, not an implicit projection. The
    # receiver's unbound Inputs and the producer's unbound Outputs must both
    # remain visible unless the linked Operation guarantees they are absent.
    # In particular, an extra required/optional/undefined output cannot be
    # silently omitted merely because all receiver Inputs are bound.
    seen_sources={source_id for source_id,_ in seen}
    unmapped_source_fields=sorted(f['id'] for f in source.get('fields',[])
        if f.get('role')=='output' and f.get('source_pi')==a
        and _effective_presence(source,source_op,f)!='absent'
        and f.get('id') not in seen_sources)
    unmapped_target_fields=sorted(f['id'] for f in target.get('fields',[])
        if f.get('role')=='input' and f.get('source_pi')==b
        and _effective_presence(target,target_op,f)!='absent'
        and f.get('id') not in seen_targets)
    return {'source_process':source['process'],'target_process':target['process'],
            'source_pi':a,'target_pi':b,'source_operation':source_op,
            'target_operation':target_op,'field_links':checks,
            'unmapped_target_fields':unmapped_target_fields,
            'unmapped_source_fields':unmapped_source_fields,
            'operation_peer_binding':{'source':source_binding,'target':target_binding},
            'status':'structurally-matched' if not unmapped_source_fields and not unmapped_target_fields
                    and source_binding=='static' and target_binding=='static'
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

def _unverified_external_action_effects(model):
    """Find Source-model Action writes, not observed external completions.

    The local Effect proof checks only declared Domain membership; it never
    verifies the external target performed the action. Inspect declared writes
    rather than all Action capabilities, some of which are intentionally unused.
    """
    actions={f.get('id') for f in model.get('fields',[])
             if isinstance(f,dict) and f.get('role')=='action'}
    result=[]
    for rule in model.get('rules',[]):
        if not isinstance(rule,dict):
            continue
        for outcome_index,outcome in enumerate(rule.get('allowed',[]),1):
            if not isinstance(outcome,dict):
                continue
            for write_index,write in enumerate(outcome.get('write',[]),1):
                if isinstance(write,dict) and write.get('target') in actions:
                    result.append(f"{rule.get('source_artifact')}#{rule.get('id')}:{outcome_index}:{write_index}:{write['target']}")
    return sorted(result)


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
        if edge['target_process']==peer_binding.ORIGIN:
            unresolved.append({**edge,'reason':'dynamic execution-origin requires runtime binding'})
        elif edge['target_process'] not in models:
            unresolved.append({**edge,'reason':'peer outside assembled Process set'})
        elif reciprocal not in peer_edge_pairs:
            unresolved.append({**edge,'reason':'counterpart PI lacks reciprocal boundary'})
        elif key in pending_pairs:
            unresolved.append({**edge,'reason':'PI binding exists but structural proof is inconclusive'})
        elif key not in bound_pairs:
            unresolved.append({**edge,'reason':'PI connection/effect lacks explicit binding'})
    # A single proven operation must not discharge a whole PI when the same
    # PI declares additional operations to the same peer. Keep missing
    # operations separate from an absent boundary or an unproved effect.
    proven_operations=set()
    for link in proven:
        if link['status']!='structurally-matched':
            continue
        proven_operations.add((link['source_process'],link['source_pi'],
                               link['source_operation'],link['target_process'],'send'))
        proven_operations.add((link['target_process'],link['target_pi'],
                               link['target_operation'],link['source_process'],'receive'))
    for process,model in models.items():
        boundaries={b['artifact']:b for b in model.get('pi_boundaries',[])}
        for op in model.get('pi_operations',[]):
            pi=op.get('source_pi')
            if pi not in boundaries:
                continue
            boundary=boundaries[pi]
            declared_peers=boundary.get('peers',[boundary.get('peer')])
            peer=op.get('peer')
            candidates=([peer] if peer is not None else
                        declared_peers[:1] if len(declared_peers)==1 else declared_peers)
            direction='send' if op.get('direction')=='provide' else 'receive'
            for target in candidates:
                edge=(process,pi,target,direction)
                operation=(process,pi,op.get('id'),target,direction)
                if edge in bound_pairs and operation not in proven_operations:
                    unresolved.append({'source_process':process,'source_pi':pi,
                                       'target_process':target,'direction':direction,
                                       'operation':op.get('id'),
                                       'reason':'PI operation lacks explicit binding'})
    unproved_local=[]
    unverified_external_effects=[]
    for p,model in models.items():
        if not _local_claim_consistent(model):
            unproved_local.append(p)
        unverified_external_effects.extend(
            {'process':p,'effect':effect}
            for effect in _unverified_external_action_effects(model))
    # A locally type-correct Action write is not a receipt of external
    # execution, including when no PI links were declared for this assembly.
    statuses='inconclusive' if (unresolved or unproved_local or unverified_external_effects
                                or any(not x['external_effects_verified'] for x in proven)) else 'passed'
    reason=('typed connections match where bound; cross-Process effect/interleaving proof still required'
            if statuses=='inconclusive' else 'all declared boundaries and external effects proved')
    if unverified_external_effects:
        reason+='; external Action writes have no independent execution receipt'
    return {'schema':'cat-process-composition/v1','status':statuses,
            'model_sha256':hashes,'binding_sha256':binding_hash,
            'bindings':proven,'unresolved_connections':unresolved,
            'unproved_local_processes':unproved_local,
            'unverified_external_effects':unverified_external_effects,
            'reason':reason}

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
