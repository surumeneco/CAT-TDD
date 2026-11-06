#!/usr/bin/env python3
"""Generate traceable implementation-conformance obligations from confirmed CAT semantics."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from cat_compile_v2 import Blocked, load, read_artifact


def item(identifier, category, source_ref, method):
    return {
        'id': identifier,
        'category': category,
        'source_ref': source_ref,
        'method': method,
        'status': 'not-run',
        'reason': 'verification evidence not collected',
        'limitation': 'verification has not yet established this obligation',
    }


def generate(process_path, pi_path, tce_paths, domain_path=None, technologies=(),
             common_rules=(), domain_specs=(), allow_draft=False, verifier_contracts=None):
    pi_paths=list(pi_path) if isinstance(pi_path,(list,tuple)) else [pi_path]
    model = load(process_path, pi_paths, tce_paths, domain_path, allow_draft=allow_draft,
                 common_rule_paths=common_rules,domain_spec_paths=domain_specs,
                 verifier_contracts_path=verifier_contracts)
    pf, process = read_artifact(process_path, 'process', allow_draft)
    pis=[read_artifact(path,'pi',allow_draft) for path in pi_paths]
    pif,pi=pis[0]
    obligations = []

    for fm,pispec in pis:
        operations=pispec.get('operations',[])
        if operations:
            for op in operations:
                obligations.append(item('interface.'+op['id'],'interface',
                                        fm['id']+'#'+op['id'],'technology-inspector:public-interface'))
        else:
            obligations.append(item('interface.'+fm['id'],'interface',fm['id'],
                                    'technology-inspector:public-interface'))

    capabilities = list(process.get('observations', [])) + list(process.get('actions', []))
    for cap in capabilities:
        obligations.append(item(
            'capability.' + cap['id'],
            'capability',
            pf['id'] + '#' + cap['id'],
            'technology-inspector:capability',
        ))
    obligations.append(item(
        'capability.closed-set',
        'capability',
        pf['id'],
        'technology-inspector:capability-closed-set',
    ))

    for rule in model['rules']:
        source = rule.get('source_artifact') or pf['id']
        obligations.append(item(
            'behavior.' + rule['id'],
            'behavior',
            source + '#' + rule['id'],
            'generated-test',
        ))
        for n, _ in enumerate(rule['allowed'], 1):
            obligations.append(item(
                'invariant.' + rule['id'] + '.' + str(n),
                'invariant',
                source + '#' + rule['id'] + ':outcome:' + str(n),
                'generated-test-frame',
            ))

    for fm,pispec in pis:
        for boundary in pispec.get('boundaries',[pispec.get('boundary')]):
            if boundary is None:continue
            obligations.append(item('cross-process.'+fm['id']+'.'+boundary['peer'],
                                    'cross-process',fm['id']+'#'+boundary['peer'],
                                    'integration-contract'))

    if model.get('definitions'):
        for definition in model['definitions']:
            obligations.append(item(
                'domain.' + definition['id'],
                'domain',
                (model.get('source_semantic_map', {}).get('domain_rule', {}).get('artifact') or pf['id']) + '#' + definition['id'],
                'deterministic-domain-verifier',
            ))
    else:
        obligations.append(item(
            'domain.semantic-map',
            'domain',
            pf['id'],
            'model-conformance',
        ))

    # Do not turn an authored normative rule, opaque type or external effect
    # into a passing implementation obligation without a bound verifier result.
    for rule in model.get('normative_rules',[]):
        ob=item('domain.rule.'+rule['id'],'domain',
                rule['source_artifact']+'#'+rule['id'],'verifier-contract:'+rule['id'])
        ob['requirement']=rule['requirement']
        ob['verifier_hint']=rule['verifier_hint']
        ob['limitation']='authored rule mapping is not independent execution evidence'
        obligations.append(ob)
    for sec in model.get('normative_sections',[]):
        ob=item('domain.section.'+sec['source_artifact']+'.'+sec['sha256'][:16],'domain',
                sec['source_artifact']+'#'+sec['sha256'],'normative-section-verifier')
        ob['limitation']='uninterpreted normative clause; no verified semantic translation'
        obligations.append(ob)
    for typ in model.get('type_obligations',[]):
        ob=item('domain.type.'+typ['field'],'domain',pf['id']+'#'+typ['field'],'type-schema-verifier')
        ob['limitation']='opaque type requires a concrete semantic schema'
        obligations.append(ob)
    if model.get('rule_conflicts'):
        for issue in model['rule_conflicts']:
            ob=item('domain.conflict.'+issue['rule_id'],'domain',
                    ','.join(issue['sources']),'conflict-resolution-authority')
            ob['limitation']='normative conflict is not resolved by an AI/compiler default'
            obligations.append(ob)
    techs = sorted(set(technologies))
    if techs:
        for tech in techs:
            safe = ''.join(ch if ch.isalnum() else '-' for ch in tech).strip('-').lower()
            obligations.append(item(
                'implementation-constraint.' + (safe or 'technology'),
                'implementation-constraint',
                'technology:' + tech,
                'technology-skill:' + tech,
            ))
    else:
        obligations.append(item(
            'implementation-constraint.none-declared',
            'implementation-constraint',
            'technology:none-declared',
            'project-constraint-review',
        ))

    source_records = model.get('source_records', [])
    return {
        'schema': 'cat-implementation-obligations/v1',
        'process': model['process'],
        'source_sha256': {x['id']: x['sha256'] for x in source_records},
        'model_semantic_authority': model.get('semantic_authority'),
        'model_status':model.get('status'),
        'coverage_requirement':model.get('coverage_requirement'),
        'nonartifact_source_sha256':model.get('nonartifact_source_sha256',{}),
        'items': obligations,
    }



def aggregate(document, queue=None, technology_results=(), model_conformance=None):
    """Derive evaluated obligation state from script/provider-owned evidence without mutating the skeleton."""
    result=json.loads(json.dumps(document))
    items=result.get('items',[])
    done_by_rule={}
    if queue:
        for q in queue.get('items',[]):
            if q.get('status')=='done' and q.get('evidence_ref'):
                done_by_rule.setdefault(q.get('model_ref'),[]).append(q.get('evidence_ref'))
    tech=list(technology_results or [])
    tech_pass=bool(tech) and all(x.get('status')=='passed' for x in tech)
    model_pass=bool(model_conformance and model_conformance.get('status')=='passed')
    model_evidence=(model_conformance or {}).get('evidence','')
    for ob in items:
        method=ob.get('method','')
        source=ob.get('source_ref','')
        evidence=[]
        limitation=''
        if method in ('generated-test','generated-test-frame'):
            rule=source.split('#',1)[1].split(':outcome:',1)[0] if '#' in source else ''
            evidence=done_by_rule.get(rule,[])
            if evidence:
                ob.update(status='passed',evidence=';'.join(sorted(set(evidence))))
                ob.pop('reason',None)
                limitation='finite deterministic selected-vector evidence; not a general proof over all executions'
            else:
                ob.update(status='inconclusive',reason='no completed Queue evidence for referenced TestModel rule')
                ob.pop('evidence',None)
                limitation='behavior remains unverified for the current implementation state'
        elif method.startswith('technology-inspector:'):
            if tech_pass:
                ob.update(status='passed',evidence='technology-inspector')
                ob.pop('reason',None)
                limitation='bounded to configured technology inspector source/binding coverage'
            else:
                ob.update(status='inconclusive',reason='technology inspector evidence is absent or non-passing')
                ob.pop('evidence',None)
                limitation='technology-specific implementation boundary is not fully established'
        elif method in ('model-conformance','deterministic-domain-verifier'):
            if model_pass:
                ob.update(status='passed',evidence=model_evidence or 'model-conformance')
                ob.pop('reason',None)
                limitation='proves semantic mapping/domain relation, not arbitrary runtime implementation behavior'
            else:
                ob.update(status='inconclusive',reason='model-conformance evidence is absent or non-passing')
                ob.pop('evidence',None)
                limitation='semantic mapping cannot substitute for implementation evidence'
        elif method=='integration-contract':
            if model_pass and tech_pass:
                ob.update(status='passed',evidence='model-conformance;technology-inspector')
                ob.pop('reason',None)
                limitation='local contract/boundary conformance only; deployment/integration evidence remains a separate Gate'
            else:
                ob.update(status='inconclusive',reason='cross-process local contract evidence is incomplete')
                ob.pop('evidence',None)
                limitation='does not establish remote peer availability or deployed integration'
        elif method.startswith('technology-skill:'):
            tech_name=method.split(':',1)[1]
            matched=[x for x in tech if x.get('technology')==tech_name]
            if matched and all(x.get('status')=='passed' for x in matched):
                ob.update(status='passed',evidence='technology-inspector:'+tech_name)
                ob.pop('reason',None)
                limitation='bounded to checks implemented by the selected technology Skill'
            else:
                ob.update(status='inconclusive',reason='selected technology has no passing deterministic constraint evidence')
                ob.pop('evidence',None)
                limitation='technology constraint coverage is incomplete'
        else:
            ob.update(status='inconclusive',reason='verification method has no deterministic aggregator')
            ob.pop('evidence',None)
            limitation='requires an explicit deterministic verifier or conditional reviewer'
        ob['limitation']=limitation
    result['evaluation']='deterministic-aggregate/v1'
    return result

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('process')
    ap.add_argument('pi')
    ap.add_argument('tce', nargs='+')
    ap.add_argument('--domain-rule')
    ap.add_argument('--pi',dest='extra_pi',action='append',default=[])
    ap.add_argument('--common-rule',action='append',default=[])
    ap.add_argument('--domain-spec',action='append',default=[])
    ap.add_argument('--verifier-contracts')
    ap.add_argument('--allow-draft',action='store_true')
    ap.add_argument('--technology', action='append', default=[])
    ap.add_argument('-o', '--output', required=True)
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args(argv)
    try:
        result = generate(args.process, [args.pi,*args.extra_pi], args.tce, args.domain_rule, args.technology,
                          args.common_rule,args.domain_spec,args.allow_draft,args.verifier_contracts)
        content = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
        path = Path(args.output)
        if args.check:
            if not path.is_file() or path.read_text(encoding='utf-8') != content:
                raise Blocked('implementation obligations differ or are missing')
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        print(json.dumps({'status': 'passed', 'output': str(path), 'items': len(result['items'])},
                         ensure_ascii=False, sort_keys=True))
        return 0
    except (Blocked, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({'status': 'blocked', 'error': str(exc)}, ensure_ascii=False), file=__import__('sys').stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
