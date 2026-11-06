"""Deterministic verifier contracts with explicit capability ownership.

An authored contract is never evidence. A result counts only for the exact
source, fixture, rule and capability; network/delivery capabilities require a
registered external verifier and cannot be discharged by a DOM check.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

CAPABILITIES=frozenset({
    'http','dom','db','discord-delivery','bluemap','migration','source-structure',
    'filesystem','integration','multi-run','type-projection'})

class ContractError(ValueError):pass

def digest(raw):return hashlib.sha256(raw).hexdigest()

def canonical(data):return json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')

def _require(ok,msg):
    if not ok:raise ContractError(msg)

def inspect_contracts(path,rule_ids,strict=True):
    path=Path(path);raw=path.read_bytes();data=json.loads(raw)
    schema=data.get('schema')
    _require(schema in ('cat-verifier-registry/v1','cat-review-verifier-contracts/v1'),'unsupported verifier contract schema')
    entries=data.get('entries',[])
    _require(isinstance(entries,list),'verifier contracts entries must be a list')
    obligations=[];seen=set();out_of_scope=[]
    for entry in entries:
        rid=entry.get('id') or entry.get('rule_id')
        _require(isinstance(rid,str) and rid,'verifier contract needs rule ID')
        _require(rid not in seen,'duplicate verifier contract '+rid)
        seen.add(rid)
        if rid not in rule_ids:
            if strict:raise ContractError('verifier contract is not associated with a declared normative rule: '+rid)
            out_of_scope.append(rid);continue
        owner=entry.get('capability')
        _require(owner is None or owner in CAPABILITIES,'unsupported verifier capability')
        _require(isinstance(entry.get('requirement'),str) and entry['requirement'],'verifier requirement required')
        declared=entry.get('execution_status','not-run')
        _require(declared in ('not-run','inconclusive','failed','passed'),'invalid author status')
        # An authored 'passed' must not be accepted as verification evidence.
        obligations.append({'rule_id':rid,'capability':owner,'status':'not-run',
                            'source_ids':entry.get('source_ids',[]),
                            'requirement':entry['requirement'],
                            'verifier_hint':entry.get('method',''),
                            'source_artifact':entry.get('artifact'),
                            'reason':('unassigned verifier capability' if owner is None
                                      else 'no independently verified execution evidence')})
    return {'schema':'cat-verifier-plan/v1','registry_sha256':digest(raw),
            'contracts':obligations,'out_of_scope_contracts':out_of_scope,
            'status':'inconclusive' if obligations else 'not-applicable'}


def verify_evidence(contract,evidence):
    """Check evidence binding and subject/result without trusting author assertions.

    Real-world capability outcomes require an independently supplied adapter
    attestation; bare JSON fixture comparisons are never accepted for those.
    """
    rule_id=contract['rule_id'];cap=contract.get('capability')
    if cap not in CAPABILITIES:raise ContractError('unassigned verifier capability')
    for key in ('rule_id','capability','source_sha256','fixture_sha256','verifier_id','result','assertions'):
        _require(key in evidence,'missing evidence binding '+key)
    _require(evidence['rule_id']==rule_id and evidence['capability']==cap,
             'verifier ownership mismatch for '+rule_id)
    _require(evidence['result'] in ('passed','failed','inconclusive','not-run'),'invalid evidence result')
    _require(isinstance(evidence['verifier_id'],str) and evidence['verifier_id'],'verifier identity required')
    _require(isinstance(evidence['source_sha256'],str) and len(evidence['source_sha256'])==64,'source hash required')
    _require(isinstance(evidence['fixture_sha256'],str) and len(evidence['fixture_sha256'])==64,'fixture hash required')
    _require(isinstance(evidence['assertions'],list) and evidence['assertions'],'assertions required')
    if cap in ('discord-delivery','bluemap','db','http','multi-run','integration'):
        _require(evidence.get('subject_kind')==cap,
                 'external effect cannot be proven by a different capability such as DOM')
    for a in evidence['assertions']:
        _require(isinstance(a,dict) and 'expected' in a and 'observed' in a,'assertion needs expected and observed')
        if a['expected']!=a['observed']:
            return {'rule_id':rule_id,'status':'failed','evidence_sha256':digest(canonical(evidence)),
                    'reason':'an explicit expected/observed assertion disagrees'}
    # Static equality alone proves only the supplied snapshot. For dynamic
    # effects require runner-origin output with a matching observed input hash.
    if cap not in ('source-structure','type-projection','filesystem') and not evidence.get('external_attestation'):
        return {'rule_id':rule_id,'status':'inconclusive','evidence_sha256':digest(canonical(evidence)),
                'reason':'external verifier attestation is absent'}
    _require(evidence['result']=='passed','verified assertions do not match claimed result')
    return {'rule_id':rule_id,'status':'passed','evidence_sha256':digest(canonical(evidence)),
            'verifier_id':evidence['verifier_id'],'capability':cap}


def evaluate_registry(registry_path,evidence_path,rule_sources):
    plan=inspect_contracts(registry_path,set(rule_sources))
    raw=Path(evidence_path).read_bytes();submitted=json.loads(raw)
    _require(submitted.get('schema')=='cat-verifier-evidence/v1','invalid verifier evidence schema')
    entries={}
    for item in submitted.get('entries',[]):
        rid=item.get('rule_id')
        _require(rid not in entries,'duplicate verifier evidence '+str(rid))
        entries[rid]=item
    outcomes=[]
    for contract in plan['contracts']:
        rid=contract['rule_id'];ev=entries.get(rid)
        if not ev:
            outcomes.append({'rule_id':rid,'status':'not-run','reason':'no evidence supplied'});continue
        if ev.get('source_sha256')!=rule_sources[rid]:
            outcomes.append({'rule_id':rid,'status':'failed','reason':'source hash does not match compiled Artifact'});continue
        outcomes.append(verify_evidence(contract,ev))
    return {'schema':'cat-verifier-results/v1','registry_sha256':plan['registry_sha256'],
            'evidence_sha256':digest(raw),'results':outcomes,
            'status':('failed' if any(x['status']=='failed' for x in outcomes)
                      else 'passed' if outcomes and all(x['status']=='passed' for x in outcomes)
                      else 'inconclusive')}
