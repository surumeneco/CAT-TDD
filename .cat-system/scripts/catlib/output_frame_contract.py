"""Explicit per-outcome outbound Operation inventory, distinct from inbound cut.

The declarations describe result-boundary identity, not implementation order,
provider delivery, correlation, or the execution of a particular protocol.
"""
from collections import defaultdict


def declarations(pi_docs):
    return [dict(row,source_pi=fm['id']) for _,fm,pi in pi_docs for row in pi.get('output_frames',[])]


def declared_owners(rows):
    return {row['source_pi'] for row in rows}


def validate_declarations(rows,fields,operations,overrides,rules,triggers):
    if not rows:return
    def require(ok,reason):
        if not ok:raise ValueError('Output frames: '+reason)
    trigger_ids={t['id'] for t in triggers}
    op_by_id={op['id']:op for op in operations}
    expected=defaultdict(set)
    for rule in rules:
        expected[rule['trigger']].update((rule['id'],n) for n in range(1,len(rule['allowed'])+1))
    for owner in declared_owners(rows):
        providers={op['id']:op for op in operations if op['source_pi']==owner and op['direction']=='provide'}
        require(providers and all(op.get('trigger') in trigger_ids for op in providers.values()),'explicit Trigger-bound provider inventory required')
        require(any(f['role']=='output' and f.get('source_pi')==owner for f in fields.values()),'output owner has no output field')
        require(all(ov['operation'] in providers for ov in overrides if ov['source_pi']==owner and fields[ov['field']]['role']=='output'),'outbound Presence override must belong to a provide Operation')
        groups=defaultdict(list); cuts=defaultdict(set)
        for row in rows:
            if row['source_pi']!=owner:continue
            cut=row['trigger']; op=row['operation']
            require(cut in trigger_ids,'undeclared output cut')
            require(op is None or op in providers,'unknown, non-provide or foreign operation')
            groups[cut].append(row)
            if op is not None:cuts[op].add(cut)
        require({op['trigger'] for op in providers.values()}<=groups.keys(),'missing inbound cut inventory')
        require(cuts.keys()==providers.keys() and all(len(c)==1 for c in cuts.values()),'each declared provide Operation needs one explicit outbound cut')
        for cut,group in groups.items():
            keys=[(row['rule'],row['outcome']) for row in group]
            require(len(keys)==len(set(keys)) and set(keys)==expected[cut],'outbound cut must declare every distinct Behavior Outcome exactly once')
            modes={row['mode'] for row in group}
            require(len(modes)==1,'mixed activation modes at one cut')
            mode=next(iter(modes))
            require(mode in ('one','zero-or-one','none'),'unknown activation mode')
            require(all((row['operation'] is not None if mode=='one' else row['operation'] is None if mode=='none' else True) for row in group),'activation cardinality violated')


def active_frames(rows,operations,trigger,rule,outcome):
    ops={op['id']:op for op in operations}
    return {row['source_pi']:ops[row['operation']] for row in rows
            if row['trigger']==trigger and row['rule']==rule and row['outcome']==outcome and row['operation'] is not None}
