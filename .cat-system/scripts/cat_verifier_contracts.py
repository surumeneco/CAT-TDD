#!/usr/bin/env python3
"""Deterministic rule-level verifier dispatch with traceable, bounded evidence.

No verifier registration or author-supplied result alone constitutes a pass.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from catlib import semantic_types

SCHEMA='cat-verifier-registry/v1'
SUBJECTS={'static','structural','http','dom','database','discord','bluemap',
          'notification','migration','cross-process'}
EXTERNAL=SUBJECTS-{'static','structural'}
OPERATORS={'eq','ne','present','absent','contains','length'}
PATH=re.compile(r'[A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*|\[[0-9]+\])*')
MISSING=object()

class VerifierError(ValueError):
    pass

def digest(data):
    return hashlib.sha256(data).hexdigest()

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def resolve(root,name):
    if not isinstance(name,str) or not name or chr(0) in name:
        raise VerifierError('invalid verifier fixture path')
    root=Path(root).resolve(strict=True)
    target=(root/name).resolve(strict=True)
    if target!=root and root not in target.parents:
        raise VerifierError('verifier path outside registry directory')
    if not target.is_file() or target.is_symlink():
        raise VerifierError('verifier source is not a regular file')
    return target

def value_at(obj,path):
    if not isinstance(path,str) or not PATH.fullmatch(path):
        raise VerifierError('invalid assertion path')
    for segment in re.findall(r'[A-Za-z_][A-Za-z0-9_-]*|\[[0-9]+\]',path):
        if segment.startswith('['):
            index=int(segment[1:-1])
            obj=obj[index] if isinstance(obj,list) and index<len(obj) else MISSING
        else:
            obj=obj.get(segment,MISSING) if isinstance(obj,dict) else MISSING
        if obj is MISSING:break
    return obj

def assertion(assertion_,observed):
    if not isinstance(assertion_,dict) or set(assertion_)-{'id','path','op','expected'}:
        raise VerifierError('invalid assertion object')
    aid=assertion_.get('id')
    op=assertion_.get('op')
    if not isinstance(aid,str) or not aid or op not in OPERATORS:
        raise VerifierError('invalid assertion id/operator')
    actual=value_at(observed,assertion_.get('path'))
    if op in ('eq','ne','contains','length') and 'expected' not in assertion_:
        raise VerifierError('assertion expected value missing')
    expected=assertion_.get('expected')
    if op=='present':ok=actual is not MISSING
    elif op=='absent':ok=actual is MISSING
    elif actual is MISSING:ok=False
    elif op=='eq':ok=semantic_types.same(actual,expected)
    elif op=='ne':ok=not semantic_types.same(actual,expected)
    elif op=='contains':
        ok=isinstance(actual,list) and any(semantic_types.same(v,expected) for v in actual)
    elif op=='length':
        ok=type(expected) is int and isinstance(actual,(dict,list,str)) and len(actual)==expected
    else:raise VerifierError('invalid operator')
    return {'id':aid,'status':'passed' if ok else 'failed','path':assertion_['path'],
            'op':op,'expected':expected,'actual':{'missing':True} if actual is MISSING else actual}

def _scope_check(rule,subject):
    contract=rule.get('verification_contract','').lower()
    # Detect clear responsibility mismatches. Text that is ambiguous needs
    # an explicit binding decision; no positive semantic inference from prose.
    hints={
        'discord':('discord','discord配送','bot配送'),
        'dom':('dom','css','ブラウザ'),
        'database':('database','データベース','sql','db検証'),
        'bluemap':('bluemap',),
    }
    explicit={key for key,words in hints.items() if any(w.lower() in contract for w in words)}
    if subject=='dom' and 'discord' in explicit and 'dom' not in explicit:
        raise VerifierError('DOM verifier cannot prove Discord delivery')
    if subject=='discord' and 'dom' in explicit and 'discord' not in explicit:
        raise VerifierError('Discord verifier cannot prove DOM rendering')

def _run(entry,root,fixture,fixture_sha):
    runner=entry.get('runner')
    if not runner:
        return None,'not-run','verifier has no registered runner'
    if not isinstance(runner,dict) or set(runner)!={'type','path','sha256'}:
        raise VerifierError('runner identity requires type/path/sha256')
    if runner['type']!='python-json-v1':
        raise VerifierError('unsupported verifier runtime')
    script=resolve(root,runner['path'])
    if digest(script.read_bytes())!=runner['sha256']:
        raise VerifierError('verifier runner hash mismatch')
    try:
        completed=subprocess.run([sys.executable,'-I',str(script),str(fixture)],
                                 cwd=root,capture_output=True,text=True,check=False,timeout=60)
    except subprocess.TimeoutExpired:
        return None,'failed','verifier runner timeout'
    if completed.returncode!=0:
        return None,'failed','verifier runner nonzero exit '+str(completed.returncode)
    try:result=json.loads(completed.stdout)
    except (ValueError,TypeError):
        return None,'failed','verifier runner did not produce JSON evidence'
    if not isinstance(result,dict) or set(result)!={'schema','rule_id','subject','fixture_sha256','observed'}:
        raise VerifierError('verifier runner output schema invalid')
    if result['schema']!='cat-verifier-observation/v1' or result['rule_id']!=entry['rule_id'] or result['subject']!=entry['subject'] or result['fixture_sha256']!=fixture_sha:
        raise VerifierError('verifier runner output identity mismatch')
    return result['observed'],'passed','runner executed against fixed fixture'

def evaluate(model_file,registry_file):
    model_file=Path(model_file).resolve(strict=True)
    registry_file=Path(registry_file).resolve(strict=True)
    root=registry_file.parent
    model_bytes=model_file.read_bytes()
    model=json.loads(model_bytes)
    registry=read_json(registry_file)
    if not isinstance(registry,dict) or registry.get('schema')!=SCHEMA:
        raise VerifierError('registry schema mismatch')
    if registry.get('model_sha256')!=digest(model_bytes):
        raise VerifierError('model/registry hash mismatch')
    entries=registry.get('entries')
    if not isinstance(entries,list):
        raise VerifierError('registry entries must be a list')
    # The registry's model hash binds the bytes, not the uniqueness or
    # authenticity of the model inventory. A re-hashed malformed model must
    # never collapse two distinct normative obligations into one rule ID.
    def unique_inventory(items,label):
        if not isinstance(items,list):
            raise VerifierError(label+' inventory must be a list')
        found={}
        for item in items:
            if not isinstance(item,dict) or not isinstance(item.get('id'),str) or not item['id']:
                raise VerifierError(label+' inventory ID missing')
            if item['id'] in found:
                raise VerifierError('duplicate '+label+' ID '+item['id'])
            found[item['id']]=item
        return found
    rules=unique_inventory(model.get('rule_obligations',[]),'normative rule')
    docs=unique_inventory(model.get('normative_rule_inputs',[]),'normative source')
    records=model.get('source_records')
    if records is not None:
        recorded=unique_inventory(records,'source record')
        for source_id,doc in docs.items():
            if source_id not in recorded or recorded[source_id].get('sha256')!=doc.get('sha256'):
                raise VerifierError('source record hash mismatch for '+source_id)
    for rid,rule in rules.items():
        if rule.get('source_artifact') not in docs:
            raise VerifierError('unbound normative rule source '+rid)
    seen=set();out=[]
    for e in entries:
        if not isinstance(e,dict) or not {'rule_id','source_artifact','source_sha256','subject','verifier_id','fixture','assertions'}<=set(e):
            raise VerifierError('malformed registry entry')
        rid=e['rule_id']
        if rid in seen or rid not in rules:
            raise VerifierError('duplicate/unknown rule '+str(rid))
        seen.add(rid)
        rule=rules[rid]
        source=docs.get(e['source_artifact'])
        if rule['source_artifact']!=e['source_artifact'] or source is None or source['sha256']!=e['source_sha256']:
            raise VerifierError('rule/source hash mismatch '+rid)
        subject=e['subject']
        if subject not in SUBJECTS or not isinstance(e['verifier_id'],str) or not e['verifier_id']:
            raise VerifierError('invalid verifier responsibility')
        _scope_check(rule,subject)
        fixture=e['fixture']
        if not isinstance(fixture,dict) or set(fixture)!={'path','sha256'}:
            raise VerifierError('fixture must bind path and SHA256')
        path=resolve(root,fixture['path'])
        fixture_bytes=path.read_bytes()
        if digest(fixture_bytes)!=fixture['sha256']:
            raise VerifierError('fixture hash mismatch '+rid)
        assertions=e['assertions']
        if not isinstance(assertions,list) or not assertions:
            raise VerifierError('each rule requires one or more assertions')
        aids=[a.get('id') for a in assertions]
        if len(aids)!=len(set(aids)):
            raise VerifierError('duplicate assertion ID')
        if 'runner' in e:
            observed,state,reason=_run(e,root,path,fixture['sha256'])
        else:
            # A fixture is authored input, not independently observed evidence.
            # Even static/structural rules need an executable, pinned verifier.
            observed,state,reason=None,'not-run','verifier requires an executable, hash-bound runner'
        checks=[assertion(a,observed) for a in assertions] if state=='passed' else []
        if state=='passed' and any(c['status']=='failed' for c in checks):
            state,reason='failed','one or more deterministic assertions failed'
        out.append({'rule_id':rid,'source_artifact':rule['source_artifact'],'subject':subject,
                    'verifier_id':e['verifier_id'],'status':state,'reason':reason,
                    # Asserted fixture observations are not a semantic proof
                    # of the normative Requirement (nor independent runtime fact).
                    'normative_status':'inconclusive',
                    'verification_scope':'fixture-assertions-only',
                    'fixture_sha256':fixture['sha256'],
                    'runner_sha256':e.get('runner',{}).get('sha256'),
                    'checks':checks})
    for rid in sorted(set(rules)-seen):
        out.append({'rule_id':rid,'source_artifact':rules[rid]['source_artifact'],
                    'status':'not-run','reason':'no registered verifier for normative rule'})
    statuses=[e['status'] for e in out]
    if 'failed' in statuses:status='failed'
    elif 'not-run' in statuses:status='inconclusive'
    elif statuses and all(s=='passed' for s in statuses):status='passed'
    else:status='inconclusive'
    return {'schema':'cat-verifier-result/v1','status':status,
            # The status above is only the fixture assertion verdict.
            # No arbitrary runner/registry can prove source-text equivalence.
            'normative_status':'inconclusive',
            'verification_scope':'fixture-assertions-only',
            'model_sha256':digest(model_bytes),
            'registry_sha256':digest(registry_file.read_bytes()),
            'results':out}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',required=True)
    p.add_argument('--registry',required=True)
    p.add_argument('--output',required=True)
    args=p.parse_args(argv)
    try:
        result=evaluate(args.model,args.registry)
        dest=Path(args.output)
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2,default=str)+'\n',encoding='utf-8')
        print(json.dumps({'status':result['status'],'result':str(dest)},ensure_ascii=False))
        return 2 if result['status']=='failed' else 0
    except (VerifierError,ValueError,OSError,KeyError) as exc:
        print(json.dumps({'status':'blocked','error':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
