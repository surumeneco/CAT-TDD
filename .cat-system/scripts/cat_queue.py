#!/usr/bin/env python3
"""Deterministic TDD Execution Queue state manager.

Queue holds lifecycle references only. It never stores scenarios, expected results or oracle text.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

Q = 'cat-tdd-queue/v1'
STATUSES = ('pending','current','done','blocked')

class Blocked(ValueError):
    pass

def require(ok, msg):
    if not ok:
        raise Blocked(msg)

def load(path):
    p=Path(path)
    q=json.loads(p.read_text(encoding='utf-8'))
    require(isinstance(q,dict) and q.get('schema')==Q,'wrong Queue schema')
    require(isinstance(q.get('items'),list),'Queue items must be array')
    seen=set();current=[];orders=[]
    forbidden={'scenario','expected','oracle','condition','effect','allowed','input','state','output'}
    for item in q['items']:
        require(isinstance(item,dict),'Queue item must be object')
        require(set(item)=={'id','model_ref','vector_ref','order','status','evidence_ref'},
                'Queue item may contain lifecycle references/status only')
        require(not (forbidden & set(item)),'Queue contains semantic fields')
        require(isinstance(item['id'],str) and item['id'] and item['id'] not in seen,'invalid/duplicate Queue item id')
        seen.add(item['id'])
        require(isinstance(item['model_ref'],str) and item['model_ref'],'model_ref required')
        require(isinstance(item['vector_ref'],str) and item['vector_ref'],'vector_ref required')
        require(isinstance(item['order'],int) and item['order']>0,'positive integer order required')
        orders.append(item['order'])
        require(item['status'] in STATUSES,'invalid Queue status')
        require(item['evidence_ref'] is None or isinstance(item['evidence_ref'],str),'invalid evidence_ref')
        if item['status']=='current':current.append(item)
    require(len(set(orders))==len(orders) and orders==sorted(orders),'Queue order must be unique and sorted')
    require(len(current)<=1,'Queue may contain at most one current item')
    return p,q

def save(path,q):
    Path(path).write_text(json.dumps(q,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8',newline='\n')

def current(q):
    hit=[x for x in q['items'] if x['status']=='current']
    return hit[0] if hit else None

def activate_next(q):
    require(current(q) is None,'cannot activate next while a current item exists')
    pending=[x for x in q['items'] if x['status']=='pending']
    if pending:
        pending[0]['status']='current'
        return pending[0]
    return None

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--queue',required=True)
    sub=ap.add_subparsers(dest='command',required=True)
    sub.add_parser('status')
    done=sub.add_parser('done');done.add_argument('--id',required=True);done.add_argument('--evidence',required=True)
    block=sub.add_parser('block');block.add_argument('--id',required=True);block.add_argument('--evidence',required=True)
    resume=sub.add_parser('resume');resume.add_argument('--id',required=True)
    args=ap.parse_args(argv)
    try:
        path,q=load(args.queue)
        before=hashlib.sha256(path.read_bytes()).hexdigest()
        if args.command=='status':
            result={'status':'passed','current':current(q),'remaining':sum(x['status'] in ('pending','current','blocked') for x in q['items']),
                    'queue_sha256':before}
        elif args.command in ('done','block'):
            item=current(q)
            require(item is not None and item['id']==args.id,'only the current item can transition')
            item['status']='done' if args.command=='done' else 'blocked'
            item['evidence_ref']=args.evidence
            nxt=None if args.command=='block' else activate_next(q)
            save(path,q)
            result={'status':'passed','transitioned':args.id,'new_status':item['status'],'current':nxt,
                    'queue_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        else:
            target=next((x for x in q['items'] if x['id']==args.id),None)
            require(target is not None and target['status']=='blocked','resume requires a blocked item')
            require(current(q) is None,'another current item exists')
            target['status']='current';target['evidence_ref']=None;save(path,q)
            result={'status':'passed','current':target,'queue_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        print(json.dumps(result,ensure_ascii=False,sort_keys=True)+'\n',end='')
        return 0
    except (Blocked,OSError,ValueError,json.JSONDecodeError) as exc:
        print(json.dumps({'status':'blocked','error':str(exc)},ensure_ascii=False)+'\n',file=sys.stderr,end='')
        return 2

if __name__=='__main__':
    raise SystemExit(main())
