"""Source-preserving CommonRule and DomainSpec inventory.

A textual contract creates an unresolved obligation, not a verified predicate.
"""
import hashlib
from pathlib import Path
from catlib.markdown import parse_frontmatter

class RuleError(ValueError):
    pass

def _row(text):
    if not text.startswith('|') or not text.endswith('|'):
        raise RuleError('invalid Markdown table')
    result=[];part=[];escape=False
    for ch in text[1:-1]:
        if escape:part.append(ch);escape=False
        elif ch==chr(92):escape=True
        elif ch=='|':result.append(''.join(part).strip());part=[]
        else:part.append(ch)
    result.append(''.join(part).strip())
    return result

def load(path, process, allow_draft=False):
    path=Path(path)
    fm=parse_frontmatter(path)
    if fm.get('kind') not in ('domain-spec','common-rule') or fm.get('semantic_contract')!='markdown-v2':
        raise RuleError('invalid CommonRule/DomainSpec: '+str(path))
    if fm.get('status')=='confirmed':
        if not fm.get('decision_ref'):raise RuleError('missing decision_ref')
    elif not (allow_draft and fm.get('status') in ('candidate','draft')):
        raise RuleError('unconfirmed normative input')
    if not isinstance(fm.get('source_refs'),list) or not fm['source_refs']:
        raise RuleError('source_refs required')
    raw=path.read_bytes()
    rules=[];heading=False;header=None
    for line in raw.decode('utf-8-sig').splitlines():
        line=line.strip()
        if line.startswith('## '):
            heading=line[3:] in ('規則','Rules');header=None
            continue
        if not heading or not line.startswith('|'):continue
        cells=_row(line)
        if all(c.replace(':','').strip('-')=='' for c in cells):continue
        if header is None:header=cells;continue
        if cells==header:continue
        if len(cells)!=len(header):raise RuleError('rule table width mismatch')
        row={k.lower():v for k,v in zip(header,cells)}
        rid=row.get('id')
        condition=row.get('条件') or row.get('適用対象') or row.get('condition')
        requirement=row.get('要求') or row.get('requirement')
        verification=row.get('検証') or row.get('verification')
        if not all((rid,condition,requirement,verification)):
            raise RuleError('rule must have ID/scope/requirement/verification')
        if any(r['id']==rid for r in rules):raise RuleError('duplicate rule '+rid)
        rules.append({'id':rid,'condition':condition,'requirement':requirement,
                      'verification_contract':verification,'verification_status':'unverified',
                      'source_artifact':fm['id'],'source_kind':fm['kind']})
    if not rules:raise RuleError('no rules found')
    scope=fm.get('process')
    if not isinstance(scope,str) or not scope:raise RuleError('missing scope')
    return {'id':fm['id'],'kind':fm['kind'],'process':scope,
            'scope_verified':process==scope or process.startswith(scope+'.'),
            'status':fm['status'],'source_refs':fm['source_refs'],
            'sha256':hashlib.sha256(raw).hexdigest(),'rules':rules}

def load_many(paths, process, allow_draft=False):
    result=[];ids=set();seen={}
    for path in paths:
        doc=load(path,process,allow_draft)
        if not doc['scope_verified'] and not allow_draft:
            raise RuleError('normative rule input outside Process scope: '+doc['id'])
        if doc['id'] in ids:raise RuleError('duplicate rule input '+doc['id'])
        ids.add(doc['id'])
        for rule in doc['rules']:
            prior=seen.get(rule['id'])
            if prior:
                keys=('condition','requirement','verification_contract')
                if any(prior[k]!=rule[k] for k in keys):
                    raise RuleError('conflicting rule '+rule['id']+' from '+prior['source_artifact']+' / '+rule['source_artifact'])
                raise RuleError('duplicate normative rule ID '+rule['id']+' in '+prior['source_artifact']+' / '+rule['source_artifact'])
            seen[rule['id']]=rule
        result.append(doc)
    return result
