#!/usr/bin/env python3
"""Validate TDD Queue Green receipts against exact model/vectors and pre-transition hashes.

Queue items are lifecycle references, not execution proof. Do not accept a
"done" flag or user-supplied evidence_ref as sufficient proof of Green.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import cat_compile_v2 as compiler
import cat_queue
from catlib.common import Blocked, require, json_bytes, sha


def verify(work_id,queue_path,model_path,vectors_path,evidence_root):
    qpath,q=cat_queue.load(queue_path)
    model_bytes=Path(model_path).read_bytes()
    vectors_bytes=Path(vectors_path).read_bytes()
    model=json.loads(model_bytes)
    vectors=json.loads(vectors_bytes)
    compiler.validate_queue(q,model,vectors,model_bytes,vectors_bytes)
    cases=compiler.expand_cases(model,vectors)
    refs={c['id']:c['source_tce'] for c in cases}
    require(len(refs)==len(cases),'duplicate derived vector ID')
    for entry in q['items']:
        require(refs.get(entry['vector_ref'])==entry['model_ref'],
                'Queue model_ref does not match actual vector oracle')
    evidence_dir=Path(evidence_root).resolve(strict=True)
    require(evidence_dir.is_dir(),'script-owned Green evidence directory missing')
    items=q['items']
    verified={}
    seen_not_done=False
    for index,item in enumerate(items):
        if item['status']!='done':
            seen_not_done=True
            continue
        require(not seen_not_done,'Queue done items must be an ordered prefix')
        ref=item.get('evidence_ref')
        require(isinstance(ref,str) and ref,'done Queue item lacks evidence_ref')
        original=Path(ref)
        require(original.is_file() and not original.is_symlink(),
                'Green evidence file missing or not regular')
        path=original.resolve(strict=True)
        require(path.is_relative_to(evidence_dir),
                'Green evidence outside script-owned evidence directory')
        raw=path.read_bytes()
        try:receipt=json.loads(raw)
        except (ValueError,TypeError) as exc:raise Blocked('Green evidence is not JSON') from exc
        require(isinstance(receipt,dict) and receipt.get('schema')=='cat-flow-evidence/v1',
                'wrong Green evidence schema')
        require(receipt.get('work_id')==work_id and receipt.get('stage')=='green'
                and receipt.get('verdict')=='passed',
                'Green evidence does not prove passed work stage')
        previous=deepcopy(q)
        for n,entry in enumerate(previous['items']):
            if n<index:continue
            entry['status']='current' if n==index else 'pending'
            entry['evidence_ref']=None
        ctx=receipt.get('queue_context') or {}
        require(ctx.get('current_item_id')==item['id'] and
                ctx.get('sha256')==sha(json_bytes(previous)),
                'Green evidence does not match Queue pre-transition content')
        verified.setdefault(item['model_ref'],[]).append(
            str(path)+'#sha256='+hashlib.sha256(raw).hexdigest())
    return verified
