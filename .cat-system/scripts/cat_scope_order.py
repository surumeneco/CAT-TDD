#!/usr/bin/env python3
"""Compute dependency-safe deepest-first Work ordering."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from catlib.work import work_file

def build(paths, completed):
    nodes={}
    for raw in paths:
        p,w=work_file(raw)
        if w['id'] in nodes: raise ValueError('duplicate Work id: '+w['id'])
        nodes[w['id']]={'id':w['id'],'path':str(p),'parent':w.get('parent') or None,
                        'depends_on':list(w.get('depends_on',[])),'flow':w.get('flow'),'work_kind':w.get('work_kind')}
    deps={k:set(v['depends_on']) for k,v in nodes.items()}
    for child,n in nodes.items():
        if n['parent'] in nodes: deps[n['parent']].add(child)
        elif n['parent'] and n['parent'] not in completed: raise ValueError(f"{child}: unknown parent {n['parent']}")
        for dep in n['depends_on']:
            if dep not in nodes and dep not in completed: raise ValueError(f"{child}: unknown dependency {dep}")
    visiting=set();done=set()
    def visit(k, trail):
        if k in done:return
        if k in visiting: raise ValueError('dependency cycle: '+' -> '.join(trail+[k]))
        visiting.add(k)
        for d in sorted(deps[k]):
            if d in nodes: visit(d,trail+[k])
        visiting.remove(k);done.add(k)
    for k in sorted(nodes): visit(k,[])
    def depth(k):
        d=0;seen=set()
        while nodes[k]['parent'] in nodes:
            k=nodes[k]['parent']
            if k in seen: raise ValueError('parent cycle')
            seen.add(k);d+=1
        return d
    ready=[]
    for k,n in nodes.items():
        if k in completed:
            continue
        if all(d in completed for d in deps[k]):
            ready.append({**n,'depth':depth(k)})
    if ready:
        maximum=max(x['depth'] for x in ready)
        ready=[x for x in ready if x['depth']==maximum]
    return {'status':'passed','nodes':len(nodes),'completed':sorted(completed),'ready':sorted(ready,key=lambda x:x['id'])}

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('work',nargs='+');ap.add_argument('--completed',action='append',default=[])
    args=ap.parse_args(argv)
    try:
        print(json.dumps(build(args.work,set(args.completed)),ensure_ascii=False,sort_keys=True))
        return 0
    except (OSError,ValueError) as exc:
        print(json.dumps({'status':'blocked','error':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__': raise SystemExit(main())
