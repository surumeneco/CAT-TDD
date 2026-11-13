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
             common_rules=(), domain_specs=()):
    # Do not skip declared normative inputs, and never infer closed coverage
    # from a partially specified or open-world Process.
    model = load(process_path, pi_path, tce_paths, domain_path,
                 common_rules=common_rules, domain_specs=domain_specs,
                 allow_draft=False, allow_partial=True)
    pf, process = read_artifact(process_path, 'process', False)
    pi_paths=list(pi_path) if isinstance(pi_path,(list,tuple)) else [pi_path]
    pi_docs=[read_artifact(path, 'pi', False) for path in pi_paths]
    obligations = []
    # Alternative frames are source-to-model correspondence metadata.
    # They are NOT independent runtime reachability obligations.
    model_outcome_frames = []

    for pif,pi in pi_docs:
        operations = pi.get('operations', [])
        if operations:
            for op in operations:
                obligations.append(item(
                    'interface.' + op['id'], 'interface',
                    pif['id'] + '#' + op['id'],
                    'technology-inspector:public-interface',
                ))
        else:
            obligations.append(item(
                'interface.boundary.' + pif['id'], 'interface',
                pif['id'], 'technology-inspector:public-interface',
            ))

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
        obligations.append(item(
            'invariant.' + rule['id'] + '.allowed-set',
            'invariant',
            source + '#' + rule['id'],
            'generated-test-allowed-set',
        ))
        for n, _ in enumerate(rule['allowed'], 1):
            model_outcome_frames.append({
                'rule_id': rule['id'],
                'outcome': n,
                'source_ref': source + '#' + rule['id'] + ':outcome:' + str(n),
                'semantic_role': 'source-to-model-frame-correspondence',
            })

    for pif,pi in pi_docs:
        boundary=pi.get('boundary')
        peers=boundary.get('peers',[boundary['peer']]) if boundary else [None]
        for peer in peers:
            obligations.append(item(
                'cross-process.boundary.' + pif['id'] + ('.'+peer if peer else ''),
                'cross-process',
                pif['id'] + (('#'+peer) if peer else ''),
                'integration-contract',
            ))

    # These rules have meaning independent of TCE tests; preserve each as a
    # first-class implementation obligation with source attribution.
    for rule in model.get('rule_obligations',[]):
        obligations.append(item(
            'normative-rule.' + rule['id'], 'domain',
            rule['source_artifact']+'#'+rule['id'],
            'normative-rule-verifier',
        ))

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

    identifiers=[x['id'] for x in obligations]
    if len(identifiers)!=len(set(identifiers)):
        raise Blocked('duplicate implementation obligation ID')
    source_records = model.get('source_records', [])
    return {
        'schema': 'cat-implementation-obligations/v1',
        'process': model['process'],
        'source_sha256': {x['id']: x['sha256'] for x in source_records},
        'model_semantic_authority': model.get('semantic_authority'),
        'model_status': model.get('status'),
        'unresolved_rule_ids': model.get('unverified_rule_ids',[]),
        # Script-owned, source-digest-bound structural proofs. Observed runner
        # assertions are separate evidence and cannot self-promote free text.
        'intrinsic_rule_proofs': model.get('intrinsic_rule_proofs',[]),
        'model_outcome_frames': model_outcome_frames,
        'items': obligations,
    }



def aggregate(document, queue=None, technology_results=(), model_conformance=None,
              rule_verification=None, verified_green=None):
    """Aggregate only independently checked Green receipts; Queue flags are not proof."""
    result=json.loads(json.dumps(document))
    items=result.get('items',[])
    # The caller must verify model/vectors hashes, pre-transition Queue SHA and
    # the script-owned Green receipt before passing this evidence map.
    done_by_rule=verified_green or {}
    tech=list(technology_results or [])
    tech_pass=bool(tech) and all(x.get('status')=='passed' for x in tech)
    model_pass=bool(model_conformance and model_conformance.get('status')=='passed')
    model_evidence=(model_conformance or {}).get('evidence','')
    for ob in items:
        method=ob.get('method','')
        source=ob.get('source_ref','')
        evidence=[]
        limitation=''
        if method=='normative-rule-verifier':
            source_artifact,rid=(source.split('#',1)+[''])[:2]
            source_hash=result.get('source_sha256',{}).get(source_artifact)
            proofs=[p for p in result.get('intrinsic_rule_proofs',[])
                    if p.get('rule_id')==rid
                    and p.get('source_artifact')==source_artifact
                    and p.get('source_sha256')==source_hash
                    and p.get('proof_method')=='cat:intrinsic-model/v1'
                    and p.get('verification_contract')=='cat:intrinsic-model/v1'
                    and p.get('scope')=='assembled-process'
                    and p.get('status')=='passed']
            if model_pass and source_hash and len(proofs)==1:
                ob.update(status='passed',evidence='cat:intrinsic-model/v1:'+rid)
                ob.pop('reason',None)
                limitation='source-bound model predicate only; no external implementation effect is proved'
            else:
                observed=next((r for r in (rule_verification or {}).get('results',[])
                               if r.get('rule_id')==rid and r.get('source_artifact')==source_artifact),None)
                detail=('runner observation passed but normative predicate equivalence is unproved'
                        if observed and observed.get('status')=='passed'
                        else 'missing or non-passing source-bound rule verification')
                ob.update(status='inconclusive',reason=detail)
                ob.pop('evidence',None)
                limitation='fixture/runner evidence cannot discharge free-text semantics without a source-bound proof'
        elif method in ('generated-test','generated-test-allowed-set'):
            rule=source.split('#',1)[1] if '#' in source else ''
            evidence=done_by_rule.get(rule,[])
            if evidence and (method=='generated-test' or model_pass):
                proof=';'.join(sorted(set(evidence)))
                if method=='generated-test-allowed-set':
                    proof+=';'+(model_evidence or 'model-conformance')
                ob.update(status='passed',evidence=proof)
                ob.pop('reason',None)
                limitation=('observed output was a member of the declared allowed set for a selected vector; '
                            'neither every alternative being reached nor all executions is proved'
                            if method=='generated-test-allowed-set' else
                            'finite deterministic selected-vector evidence; not a general proof over all executions')
            else:
                detail=('independent source-to-model conformance and a verified selected-vector Green required'
                        if method=='generated-test-allowed-set' else
                        'no completed Queue evidence for referenced TestModel rule')
                ob.update(status='inconclusive',reason=detail)
                ob.pop('evidence',None)
                limitation='absence of an outcome observation is not a proof of impossibility or a reachability requirement'
        elif method=='generated-test-frame':
            # Historical v1 skeletons must not self-upgrade each alternative
            # to a separate observed/reachable outcome on rule-level Green.
            ob.update(status='inconclusive',
                      reason='legacy per-outcome invariant cannot be discharged by rule-level Green')
            ob.pop('evidence',None)
            limitation='alternative frame source mapping belongs to Model Conformance; occurrence was not established'
        elif method.startswith('technology-inspector:'):
            # A global inspector success is not proof that this particular
            # interface/capability was inspected. Require explicit coverage.
            matched=[x for x in tech if x.get('status')=='passed'
                     and ob['id'] in x.get('covered_obligation_ids',[])]
            if matched:
                ob.update(status='passed',evidence=';'.join('technology-inspector:'+x.get('technology','unknown')
                                                         for x in matched))
                ob.pop('reason',None)
                limitation='proof is limited to the explicitly named inspector obligation and current source state'
            else:
                ob.update(status='inconclusive',reason='technology inspection did not cover this specific obligation')
                ob.pop('evidence',None)
                limitation='generic inspector success does not establish the public interface/capability'
        elif method=='model-conformance':
            if model_pass:
                ob.update(status='passed',evidence=model_evidence or 'model-conformance')
                ob.pop('reason',None)
                limitation='proves semantic mapping/domain relation, not arbitrary runtime implementation behavior'
            else:
                ob.update(status='inconclusive',reason='model-conformance evidence is absent or non-passing')
                ob.pop('evidence',None)
                limitation='semantic mapping cannot substitute for implementation evidence'
        elif method=='deterministic-domain-verifier':
            ob.update(status='inconclusive',reason='domain definition requires separately bound runtime verifier')
            ob.pop('evidence',None)
            limitation='model correspondence is not runtime domain-function verification'
        elif method=='integration-contract':
            # Two local checks cannot prove externally observable ordering,
            # delivery, or partner Process effects.
            ob.update(status='inconclusive',reason='independent cross-process runtime evidence required')
            ob.pop('evidence',None)
            limitation='model/technology inspection is not remote integration evidence'
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
    ap.add_argument('--pi-extra', action='append', default=[])
    ap.add_argument('--common-rule', action='append', default=[])
    ap.add_argument('--domain-spec', action='append', default=[])
    ap.add_argument('--technology', action='append', default=[])
    ap.add_argument('-o', '--output', required=True)
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args(argv)
    try:
        result = generate(args.process, [args.pi,*args.pi_extra], args.tce, args.domain_rule,
                          args.technology,args.common_rule,args.domain_spec)
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
