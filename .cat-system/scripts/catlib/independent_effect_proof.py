"""Independent positive Effect-Domain audit over original Source expressions.

This is a second, conservative proof path, not a general Effect solver.
It never calls the Compiler's Effect proof or symbolic containment helpers.
The common expression evaluator and Domain semantics define the notation;
proof selection and the accepted algebraic fragments are separate here.
"""
from __future__ import annotations

import itertools
import math
from catlib import semantic_types as types
from catlib import semantic_subtyping as subtyping
from catlib.independent_coverage import _implies_value
from cat_compile_v2 import Blocked, eval_expr, used_refs


def _source_input_presence(rule, fields, operations, overrides):
    """Independently check Presence across all possible active PI Operations.

    Ambiguous accepted Operations do not erase a valid literal Effect proof.
    For an input read, *every* possible active Operation must guarantee
    required Presence before an unguarded positive proof is admissible.
    """
    trigger=rule['trigger']
    accepted=[op for op in operations
              if op['direction']=='accept' and op.get('trigger')==trigger]
    active={}
    for op in accepted:
        active.setdefault(op['source_pi'],[]).append(op)
    provided={}
    for op in operations:
        if op['direction']=='provide' and op.get('trigger')==trigger:
            provided.setdefault(op['source_pi'],[]).append(op)
    for owner,choices in provided.items():
        if owner not in active:
            active[owner]=choices
    result={}
    for field_id,field in fields.items():
        if field['role']!='input':
            continue
        baseline=field.get('presence','required')
        options=active.get(field.get('source_pi'),[])
        statuses=[]
        for operation in options:
            matches=[item for item in overrides
                     if item['operation']==operation['id']
                     and item['field']==field_id
                     and item.get('source_pi')==field.get('source_pi')]
            if len(matches)>1:
                return None
            statuses.append(matches[0]['presence'] if matches else baseline)
        # The Effect can treat an input as required only if every possible
        # active Operation has that property; otherwise it is conservatively
        # nonrequired. No candidate means the declared PI default applies.
        result[field_id]=('required' if statuses and all(x=='required' for x in statuses)
                          else 'optional' if statuses else baseline)
    return result

def _symbolic(expr, target, fields):
    """An independent sufficient condition for exact integer/Set closure."""
    op=expr.get('op')
    args=expr.get('args',[])
    if op=='add' and isinstance(args,list) and len(args)>=2:
        bounds=[]
        for arg in args:
            if not isinstance(arg,dict):return False
            if set(arg)=={'literal'} and type(arg['literal']) is int:
                value=arg['literal'];bounds.append((value,value))
            elif set(arg)=={'ref'} and arg['ref'] in fields:
                field=fields[arg['ref']]
                domain=field['domain']
                if field['role'] not in ('input','state','observation') or domain.get('type')!='integer':
                    return False
                bounds.append((domain.get('min'),domain.get('max')))
            else:return False
        derived={'type':'integer'}
        for position,key in ((0,'min'),(1,'max')):
            endpoints=[pair[position] for pair in bounds]
            if all(type(x) is int for x in endpoints):
                derived[key]=sum(endpoints)
        return subtyping.subset(derived,target) is True
    def constructed_value_fits(node,domain):
        if set(node)=={'literal'}:return types.contains(domain,node['literal'])
        if set(node)=={'ref'}:
            source=fields.get(node['ref'],{})
            return source.get('role') in ('input','state','observation') and subtyping.subset(source['domain'],domain) is True
        if node.get('op')!='record-value':return False
        while domain.get('type')=='reference' and domain.get('resolved'):domain=domain['of']
        if domain.get('type')!='record' or not domain.get('resolved'):return False
        arguments=node.get('args',[])
        if len(arguments)%2:return False
        result={}
        for k,v in zip(arguments[::2],arguments[1::2]):
            if set(k)!={'literal'} or type(k['literal']) is not str or k['literal'] in result:return False
            result[k['literal']]=v
        for member in domain['fields']:
            name=member['id'];presence=member['presence']
            if name not in result:
                if presence in ('required','undefined'):return False
                continue
            if presence not in ('required','optional') or not constructed_value_fits(result.pop(name),member['domain']):return False
        return not result
    if op=='record-value':return constructed_value_fits(expr,target)
    if op in ('sequence-append','sequence-swap','sequence-replace-member'):
        if not isinstance(args,list) or len(args)!={'sequence-append':2,'sequence-swap':3,'sequence-replace-member':4}[op]:return False
        if set(args[0])!={'ref'} or args[0]['ref'] not in fields:return False
        source=fields[args[0]['ref']]
        if source['role'] not in ('input','state','observation'):return False
        collection=source['domain']
        if collection.get('type')!='sequence' or target.get('type')!='sequence' or subtyping.subset(collection,target) is not True:return False
        if op=='sequence-append':
            return constructed_value_fits(args[1],target['element'])
        # A swap never introduces a new value. Totality of the index
        # arithmetic is derived from its own integer-only expression tree.
        if op=='sequence-replace-member':
            element=collection['element']
            while element.get('type')=='reference' and element.get('resolved'):element=element['of']
            if element.get('type')!='record' or not element.get('resolved') or set(args[2])!={'literal'}:return False
            matches=[f for f in element['fields'] if f['id']==args[2]['literal'] and f['presence']=='required']
            if len(matches)!=1 or not constructed_value_fits(args[3],matches[0]['domain']):return False
        pending=list(args[1:2] if op=='sequence-replace-member' else args[1:])
        while pending:
            node=pending.pop()
            if set(node)=={'literal'} and type(node['literal']) is int:continue
            if set(node)=={'ref'} and node['ref'] in fields:
                field=fields[node['ref']]
                if field['role'] in ('input','state','observation') and field['domain'].get('type')=='integer':continue
            if node.get('op') in ('add','sub') and len(node.get('args',[]))>=2:
                pending.extend(node['args']);continue
            return False
        return True
    if op in ('set-add','set-remove') and isinstance(args,list) and len(args)==2:
        if not all(isinstance(x,dict) and set(x)=={'ref'} and x['ref'] in fields for x in args):
            return False
        owner=fields[args[0]['ref']];item=fields[args[1]['ref']]
        if (owner['role'] not in ('input','state','observation')
                or item['role'] not in ('input','state','observation')):
            return False
        collection=owner['domain']
        if collection.get('type')!='set' or target.get('type')!='set':
            return False
        item_target=(target['element'] if op=='set-add' else collection['element'])
        return (subtyping.subset(collection,target) is True
                and subtyping.subset(item['domain'],item_target) is True)
    return False


def _nonnull_on_true(node, ref):
    # Independently derive the sufficient implication from original Source.
    op=node.get('op'); children=node.get('args',[])
    if op in ('and','or'):
        evidence=[_nonnull_on_true(child,ref) for child in children]
        return any(evidence) if op=='and' else bool(evidence) and all(evidence)
    negated=op=='not' and len(children)==1 and children[0].get('op')=='eq'
    if negated: children=children[0].get('args',[])
    if op!='ne' and not negated: return False
    return len(children)==2 and any(
        a=={'ref':ref} and b=={'literal':None} for a,b in (children,children[::-1]))


def _certifies(rule,write,fields,definitions,presence_map,limit=4096):
    target=fields.get(write.get('target'))
    expr=write.get('expr')
    if not isinstance(target,dict) or not isinstance(expr,dict):return False
    domain=target.get('domain')
    if not isinstance(domain,dict):return False
    try:
        refs=sorted(used_refs(expr,definitions))
        for ref in refs:
            field=fields.get(ref)
            if field is None or field.get('role') not in ('input','state','observation'):
                return False
            if (field['role']=='input' and presence_map.get(ref,field.get('presence','required'))!='required'
                    and not _implies_value(rule['when'],ref)):
                return False
        if 'literal' in expr:
            return types.contains(domain,expr['literal'])
        if set(expr)=={'ref'}:
            source=fields[expr['ref']]['domain']
            if subtyping.subset(source,domain) is True: return True
            return (source.get('type')=='nullable' and _nonnull_on_true(rule['when'],expr['ref'])
                    and subtyping.subset(source['of'],domain) is True)
        if expr.get('op')=='member':
            parent=fields[expr['args'][0]['ref']]
            if parent['role']!='input' or presence_map.get(parent['id'])!='required':return False
            record=parent['domain']
            while record.get('type')=='reference' and record.get('resolved'):record=record['of']
            if record.get('type')!='record' or not record.get('resolved'):return False
            matches=[m for m in record['fields'] if m['id']==expr['args'][1]['literal'] and m['presence']=='required']
            if len(matches)!=1:return False
            member=matches[0]['domain']
            while member.get('type')=='reference' and member.get('resolved'):member=member['of']
            return subtyping.subset(member,domain) is True
        if _symbolic(expr,domain,fields):return True
        dimensions=[]
        for ref in refs:
            values=types.finite_values(fields[ref]['domain'],max_values=limit)
            if values is None or not values:return False
            dimensions.append(values)
        if math.prod(map(len,dimensions))>limit:return False
        for values in itertools.product(*dimensions):
            env=dict(zip(refs,values))
            if not types.contains(domain,eval_expr(expr,env,definitions)):
                return False
        return True
    except (Blocked,types.DomainError,ValueError,TypeError,KeyError,IndexError,OverflowError):
        return False


def unjustified_positive(rules,fields,definitions,compiler_checks,
                         pi_operations=(),operation_presence=()):
    """Return Source Effect IDs that lack a separate positive proof."""
    rejected=[]
    for rule in rules:
        presence_map=_source_input_presence(
            rule,fields,pi_operations,operation_presence)
        for n,outcome in enumerate(rule['allowed'],1):
            for k,write in enumerate(outcome['write'],1):
                ident=f"{rule['source_artifact']}#{rule['id']}:{n}:{k}:{write['target']}"
                if compiler_checks.get(ident,{}).get('result')=='proved':
                    if (presence_map is None or
                            not _certifies(rule,write,fields,definitions,presence_map)):
                        rejected.append(ident)
    return sorted(rejected)
