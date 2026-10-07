#!/usr/bin/env python3
"""Promote one reviewed local Semantic Artifact using an explicit normative decision.

This tool does not decide semantics. It only changes status/decision_ref and moves
an already-reviewed Draft/Candidate into the caller-selected confirmed location.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from catlib.common import Blocked, require
from catlib.markdown import parse_frontmatter

SEMANTIC_KINDS={'process','pi','tce','common-rule','domain-rule','domain-spec'}


def promote(source: Path, output: Path, decision_ref: str):
    source=source.resolve();output=output.resolve()
    require(source.is_file(),'promotion source missing')
    require(source != output,'promotion must move Draft/Candidate to a distinct confirmed location')
    require(not output.exists(),'promotion output already exists')
    require(isinstance(decision_ref,str) and decision_ref.strip(),'normative decision reference required')
    fm=parse_frontmatter(source)
    require(fm.get('kind') in SEMANTIC_KINDS,'promotion source is not a supported Semantic Artifact')
    require(fm.get('status') in ('draft','candidate'),'only draft/candidate Semantic Artifact may be promoted')
    raw=source.read_text(encoding='utf-8-sig')
    end=raw.find('\n---\n',4)
    require(raw.startswith('---\n') and end>=0,'invalid front matter')
    front=raw[4:end]
    body=raw[end+5:]
    require(re.search(r'(?m)^status:\s*[^\n]+$',front) is not None,'front matter status missing')
    front=re.sub(r'(?m)^status:\s*[^\n]+$',"status: confirmed",front,count=1)
    if re.search(r'(?m)^decision_ref:\s*[^\n]*$',front):
        front=re.sub(r'(?m)^decision_ref:\s*[^\n]*$',"decision_ref: "+decision_ref.strip(),front,count=1)
    else:
        front += '\ndecision_ref: '+decision_ref.strip()
    promoted='---\n'+front+'\n---\n'+body
    output.parent.mkdir(parents=True,exist_ok=True)
    temp=output.with_name(output.name+'.promotion.tmp')
    require(not temp.exists(),'promotion temp already exists')
    temp.write_text(promoted,encoding='utf-8',newline='\n')
    os.replace(temp,output)
    source.unlink()
    return {'status':'passed','source':str(source),'output':str(output),
            'decision_ref':decision_ref.strip(),'artifact_id':fm.get('id')}


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',required=True)
    ap.add_argument('--output',required=True)
    ap.add_argument('--decision-ref',required=True)
    args=ap.parse_args(argv)
    try:
        result=promote(Path(args.source),Path(args.output),args.decision_ref)
        import json
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        return 0
    except (Blocked,OSError,ValueError) as exc:
        import json
        print(json.dumps({'status':'blocked','error':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
