#!/usr/bin/env python3
"""Correlate a pinned execution trace and Effect receipts against one TestModel.

Only packet identity and reported causality are checked. Neither submitted
trace nor synthetic fixture authenticates external effects, Process closure,
or source-to-verifier semantic equivalence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

import cat_execution_trace_diagnostic as trace_runtime
import cat_external_effect_receipts as effect_runtime

class CorrelationError(ValueError):
    pass


def require(ok,message):
    if not ok:raise CorrelationError(message)


_CORRELATION_KEYS=frozenset(('request_id','transaction_id','target_id'))


def _correlation(record,label):
    if 'correlation' not in record:
        return None
    binding=record['correlation']
    require(isinstance(binding,dict) and set(binding)==_CORRELATION_KEYS,
            label+' correlation must explicitly bind request, transaction and target IDs')
    require(all(isinstance(v,str) and bool(v.strip()) for v in binding.values()),
            label+' correlation IDs must be nonempty strings')
    return binding


def _check_correlations(pairs):
    identities=[(label,_correlation(record,label)) for label,record in pairs]
    if not any(binding is not None for _,binding in identities):
        return
    require(all(binding is not None for _,binding in identities),
            'declared execution correlation must be present on each evidence record')
    anchor=identities[0][1]
    require(all(binding==anchor for _,binding in identities[1:]),
            'request/transaction/target correlation differs within execution')


def correlate(model_bytes,trace,packet,driver_bytes,observation_root,
              repository_root=None,driver_repo_path=None):
    model=json.loads(model_bytes)
    try:
        inspected_trace=trace_runtime.evaluate(model,model_bytes,trace)
        inspected_effects=effect_runtime.inspect(
            model_bytes,packet,driver_bytes,observation_root,
            repository_root,driver_repo_path)
    except (trace_runtime.TraceError,effect_runtime.ReceiptError) as exc:
        raise CorrelationError(str(exc)) from exc
    events={e['event_id']:e for e in trace['events']}
    terminals={e['execution_id']:e for e in trace['events'] if e['kind']=='result'}
    runs={r['execution_id']:r for r in trace['runs']}
    used_event_ids=set()
    unresolved=list(inspected_trace['unresolved'])+list(inspected_effects['unresolved'])
    rows=[]
    for receipt in packet['observations']:
        run=receipt['execution_id']
        require(run in runs,'Effect receipt names an execution absent from trace')
        rid=receipt['rule_id']
        index=receipt['outcome_index']
        target=receipt['effect_target']
        reported=receipt['reported_status']
        event_id=receipt.get('effect_event_id')
        terminal=terminals.get(run)
        # An unobserved side effect still belongs to a specific allowed
        # Rule/Outcome. If the submitted terminal explicitly names another,
        # the packet is contradictory, not merely lacking Effect evidence.
        if terminal is not None:
            # Missing terminal index is an unproved binding, but a present
            # JSON bool/float is not a valid 1-origin integer outcome index.
            if 'outcome_index' in terminal:
                require(type(terminal['outcome_index']) is int
                        and terminal['outcome_index'] >= 1,
                        'terminal outcome index must be a positive integer')
            require(terminal.get('rule_id') in (None,rid),
                    'terminal Rule differs from Effect receipt')
            require(terminal.get('outcome_index') in (None,index),
                    'terminal allowed Outcome differs from Effect receipt')
        if reported=='not-observed':
            # With no Effect event, the receipt remains unproved. However an
            # *explicit* terminal binding still names the same execution and
            # must not contradict the run/receipt correlation. Do not require
            # a terminal correlation when one was not supplied for this
            # unobserved case: missing evidence stays inconclusive.
            identities=[('trace run',runs[run]),('unobserved receipt',receipt)]
            if terminal is not None and 'correlation' in terminal:
                identities.append(('declared terminal',terminal))
            _check_correlations(identities)
            require(event_id in (None,''),'unobserved Effect cannot claim trace event')
            rows.append({'execution_id':run,'rule_id':rid,'effect_target':target,
                         'status':'inconclusive','reason':'effect-not-observed'})
            continue
        require(isinstance(event_id,str) and event_id,
                'observed Effect requires explicit effect_event_id')
        require(event_id not in used_event_ids,'Effect event used by multiple receipts')
        used_event_ids.add(event_id)
        event=events.get(event_id)
        require(event is not None and event['kind'] in ('request','replace','followup'),
                'Effect event missing or not a supported side-effect kind')
        require(event['execution_id']==run,'Effect event belongs to another execution')
        require(type(event.get('outcome_index')) is int
                and event['outcome_index'] >= 1,
                'Effect event outcome index must be a positive integer')
        require(event.get('rule_id')==rid and event.get('outcome_index')==index
                and event.get('effect_target')==target,
                'Effect event Rule/Outcome/target does not match Source-bound receipt')
        identity_records=[('trace run',runs[run]),('Effect receipt',receipt),
                          ('Effect trace event',event)]
        if terminal is not None:
            identity_records.append(('terminal trace event',terminal))
        _check_correlations(identity_records)
        if terminal is None:
            unresolved.append({'execution_id':run,'reason':'terminal-result-not-observed'})
            status='inconclusive'
        elif terminal['outcome']=='unknown' or reported=='unknown':
            unresolved.append({'execution_id':run,'reason':'unknown-terminal-or-effect'})
            status='inconclusive'
        elif terminal.get('rule_id') is None or terminal.get('outcome_index') is None:
            unresolved.append({'execution_id':run,'reason':'terminal Rule/Outcome not explicitly bound'})
            status='inconclusive'
        else:
            # Successful identity only; it says nothing about provider truth.
            status='identity-consistent-only'
        rows.append({'execution_id':run,'rule_id':rid,'outcome_index':index,
                     'effect_target':target,'effect_event_id':event_id,
                     'reported_status':reported,'status':status})
    return {'schema':'cat-effect-trace-correlation/v1',
            'status':'inconclusive' if unresolved else 'identity-consistent-only',
            'normative_status':'inconclusive','formal_gate_status':'not-run',
            'external_effect_proof':'not-run','provider_authentication_status':'not-run',
            'implementation_head_checkout_verified':inspected_effects['implementation_head_checkout_verified'],
            'model_sha256':hashlib.sha256(model_bytes).hexdigest(),
            'trace_sha256':hashlib.sha256(json.dumps(trace,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
            'driver_sha256':hashlib.sha256(driver_bytes).hexdigest(),
            'observations':rows,'unresolved':unresolved,
            'limitations':['trace-record-truth-not-authenticated',
                           'correlation-labels-self-reported-not-provider-authenticated',
                           'submitted-event-order-not-independent-clock-proof',
                           'source-to-rule-predicate-equivalence-unproved',
                           'external-runtime-side-effects-not-verified']}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for opt in ('model','trace','packet','driver','observation-root','output'):
        p.add_argument('--'+opt,required=True,type=Path)
    p.add_argument('--repository-root',type=Path)
    p.add_argument('--driver-repo-path')
    args=p.parse_args(argv)
    try:
        data=correlate(args.model.read_bytes(),json.loads(args.trace.read_bytes()),
                       json.loads(args.packet.read_bytes()),args.driver.read_bytes(),
                       args.observation_root,args.repository_root,args.driver_repo_path)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(data,sort_keys=True,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'status':data['status'],'normative_status':data['normative_status'],
                          'output':str(args.output)}))
        return 0
    except (CorrelationError,ValueError,OSError,TypeError,KeyError,IndexError) as exc:
        print(json.dumps({'status':'blocked','reason':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
