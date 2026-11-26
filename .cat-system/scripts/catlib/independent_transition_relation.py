"""Recompute exact transition projection from Source, never a Model certificate."""
from itertools import product

from catlib import semantic_types as typed, semantic_structural_copy as copy_relation
from catlib import semantic_collection_relation as collection_relation
from catlib import semantic_frame_footprint as frame_relation
from catlib.semantic_transition_relation import prepare


def verify(scope,fields,pi_docs,tces,checks,rejected,invariants=(),observation_relations=None):
    from cat_compile_v2 import eval_expr, Blocked
    if scope.startswith(frame_relation.PREFIX):
        return frame_relation.verify(scope,fields,pi_docs,tces,checks,rejected)
    if scope.startswith(collection_relation.PREFIX):
        return collection_relation.verify(scope,fields,pi_docs,tces,checks,rejected,invariants)
    if scope.startswith(copy_relation.PREFIX):
        return copy_relation.verify(scope,fields,pi_docs,tces,checks,rejected,invariants)
    rules=[{**r,'source_artifact':fm['id']} for _,fm,tce in tces for r in tce['rules']]
    resolved=prepare(scope,fields,pi_docs,rules,checks,rejected,invariants,independent=True,observation_relations=observation_relations)
    if resolved is None:return False
    names,dimensions,subjects,target_domains,condition,relation,constraints,rows=resolved
    seen=False
    try:
        for values in product(*dimensions):
            before=dict(zip(names,values))
            if any(eval_expr(c,before,{}) is not True for c in constraints):continue
            if eval_expr(condition,before,{}) is not True:continue
            seen=True
            selected=None
            for row in rows:
                if eval_expr(row['when'],before,{}) is not True:continue
                if selected is not None:return False
                selected=row
            if selected is None or not selected['allowed']:return False
            observed=[]
            for outcome in selected['allowed']:
                post={k:before[k] for k in subjects if k in before}
                for write in outcome['write']:
                    if write['target'] in subjects:post[write['target']]=eval_expr(write['expr'],before,{})
                if set(post)!=set(subjects) or any(not typed.contains(fields[k]['domain'],v) for k,v in post.items()):return False
                if eval_expr(relation,{**before,**{'after.'+k:v for k,v in post.items()}},{}) is not True:return False
                observed.append(post)
            for values_after in product(*target_domains):
                candidate=dict(zip(subjects,values_after))
                admitted=eval_expr(relation,{**before,**{'after.'+k:v for k,v in candidate.items()}},{}) is True
                declared=any(typed.same(candidate,value) for value in observed)
                if admitted!=declared:return False
        return seen
    except (Blocked,ValueError,KeyError,TypeError,ArithmeticError):return False
