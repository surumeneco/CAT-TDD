"""Lossless CAT data domains and presence semantics.

All nested type expressions retain their original shape; a named record without
field definitions remains opaque and cannot be pronounced value-validated.
"""
from __future__ import annotations

import ast
import base64
import json
import math
import re
from typing import Any

class DomainError(ValueError):
    pass

class _Sentinel:
    def __init__(self, name): self.name=name
    def __repr__(self): return self.name

MISSING = _Sentinel('missing')
UNDEFINED = _Sentinel('undefined')

_ALIASES = {'真偽':'boolean','整数':'integer','文字列':'string','集合':'set',
            '列':'sequence','列挙':'enum','レコード':'record','実数':'real',
            'バイト列':'bytes','非負有限実数':'real[0..]',
            '安全符号付き整数':'safe-signed-integer','可空':'nullable',
            '直和':'union'}

def split_top(source:str, delimiter:str=',')->list[str]:
    items=[]; depth=0; quote=None; start=0
    closes={'<':'>','{':'}','[':']','(':')'}; stack=[]
    for i,ch in enumerate(source):
        if quote:
            if ch==quote and (i==0 or source[i-1]!='\\'):quote=None
            continue
        if ch in ('"',"'"):quote=ch;continue
        if ch in closes:stack.append(closes[ch]);continue
        if stack and ch==stack[-1]:stack.pop();continue
        if ch==delimiter and not stack:
            items.append(source[start:i].strip()); start=i+1
    if stack or quote:raise DomainError('unbalanced nested domain syntax')
    items.append(source[start:].strip())
    if any(not item for item in items):raise DomainError('empty type component')
    return items

def _or_split(source:str)->list[str]:
    # 'AまたはB' acts as union only between top-level type expressions.
    parts=[];stack=[];start=0;i=0
    while i<len(source):
        ch=source[i]
        if ch in '<[{(':stack.append({'<':'>','[':']','{':'}','(':')'}[ch])
        elif stack and ch==stack[-1]:stack.pop()
        elif not stack and source.startswith('または',i):
            parts.append(source[start:i].strip());i+=3;start=i;continue
        i+=1
    parts.append(source[start:].strip())
    return parts

def parse_domain(text:str)->dict[str,Any]:
    if not isinstance(text,str):raise DomainError('type expression must be text')
    text=text.strip().strip('`').strip()
    if not text:raise DomainError('empty domain')
    parts=_or_split(text)
    if len(parts)>1:
        if any(not x for x in parts):raise DomainError('empty union branch')
        return {'type':'union','variants':[parse_domain(x) for x in parts]}
    for ja,en in _ALIASES.items():
        if text==ja:text=en;break
        if text.startswith(ja+'<') or text.startswith(ja+'{') or text.startswith(ja+'['):
            text=en+text[len(ja):];break
    low=text.lower()
    if low in ('boolean','integer','string','bytes','real','null'):
        return {'type':low}
    if low in ('null','none'):return {'type':'null'}
    if low=='string<safe-signed-integer>':return {'type':'string','format':'safe-signed-integer'}
    m=re.fullmatch(r'(integer|real)\[\s*([+-]?(?:\d+(?:\.\d+)?))?\s*\.\.\s*([+-]?(?:\d+(?:\.\d+)?))?\s*\]',low)
    if m:
        typ=m.group(1);d={'type':typ}
        if m.group(2) is not None:d['min']=int(m.group(2)) if typ=='integer' else float(m.group(2))
        if m.group(3) is not None:d['max']=int(m.group(3)) if typ=='integer' else float(m.group(3))
        return d
    m=re.fullmatch(r'(set|sequence|nullable)<(.*)>',text,re.S|re.I)
    if m:
        typ=m.group(1).lower();inner=parse_domain(m.group(2))
        return {'type':'nullable','of':inner} if typ=='nullable' else {'type':typ,'element':inner}
    m=re.fullmatch(r'union<(.*)>',text,re.S|re.I)
    if m:return {'type':'union','variants':[parse_domain(x) for x in split_top(m.group(1))]}
    m=re.fullmatch(r'enum\{(.*)\}',text,re.S|re.I)
    if m:
        vals=[]
        for x in split_top(m.group(1)):
            try:
                v=ast.literal_eval(x)
            except (SyntaxError,ValueError):
                if x in ('真','true'):v=True
                elif x in ('偽','false'):v=False
                elif re.fullmatch(r'[+-]?\d+',x):v=int(x)
                else:v=x
            if type(v) not in (str,bool,int):raise DomainError('enum must consist of scalar values')
            vals.append(v)
        return {'type':'enum','values':vals}
    m=re.fullmatch(r'record<(.*)>',text,re.S|re.I)
    if m:
        parts=split_top(m.group(1))
        if all(':' in p for p in parts):
            members={}
            for p in parts:
                name,domain=p.split(':',1);name=name.strip()
                optional=name.endswith('?');name=name[:-1] if optional else name
                if not name or name in members:raise DomainError('invalid or duplicate record field')
                members[name]={'domain':parse_domain(domain),'presence':'optional' if optional else 'required'}
            return {'type':'record','fields':members}
        if any(':' in p for p in parts):raise DomainError('mixed named and structural record fields')
        return {'type':'record','symbol':','.join(parts)}
    raise DomainError('unsupported domain expression: '+text)


def validate_domain(domain:dict)->dict:
    if not isinstance(domain,dict) or not isinstance(domain.get('type'),str):raise DomainError('domain object/type required')
    t=domain['type']
    allowed={
        'boolean':{'type'},'null':{'type'},'integer':{'type','min','max'},
        'real':{'type','min','max'},'string':{'type','format'},'bytes':{'type','min_length','max_length'},
        'enum':{'type','values'},'set':{'type','element'},'sequence':{'type','element'},
        'nullable':{'type','of'},'union':{'type','variants'},'record':{'type','fields','symbol'}
    }
    if t not in allowed:raise DomainError('unsupported domain type: '+str(t))
    if set(domain)-allowed[t]:raise DomainError('unsupported domain properties: '+str(sorted(set(domain)-allowed[t])))
    if t in ('integer','real'):
        for k in ('min','max'):
            if k in domain:
                v=domain[k]
                if (t=='integer' and type(v) is not int) or (t=='real' and (type(v) not in (float,int) or not math.isfinite(v))):
                    raise DomainError('invalid numeric bound')
        if 'min' in domain and 'max' in domain and domain['min']>domain['max']:raise DomainError('inverted domain bounds')
    elif t=='string':
        if domain.get('format','any') not in ('any','safe-signed-integer'):raise DomainError('unknown string format')
    elif t=='bytes':
        for k in ('min_length','max_length'):
            if k in domain and (type(domain[k]) is not int or domain[k]<0):raise DomainError('invalid byte length bound')
        if domain.get('min_length',0)>domain.get('max_length',float('inf')):raise DomainError('invalid byte length range')
    elif t=='enum':
        vals=domain.get('values')
        if not isinstance(vals,list) or not vals:raise DomainError('enum values required')
        if any(type(x) not in (str,bool,int) for x in vals):raise DomainError('invalid enum value')
        if len(set(json.dumps(x,ensure_ascii=False) for x in vals))!=len(vals):raise DomainError('duplicate enum value')
    elif t in ('set','sequence'):
        elem=domain.get('element')
        # Older machine-only domains encode element as primitive string.
        if isinstance(elem,str):elem={'type':elem}
        validate_domain(elem)
    elif t=='nullable':validate_domain(domain.get('of'))
    elif t=='union':
        variants=domain.get('variants')
        if not isinstance(variants,list) or len(variants)<2:raise DomainError('union requires at least two variants')
        for v in variants:validate_domain(v)
        if len({json.dumps(v,sort_keys=True,ensure_ascii=False) for v in variants})!=len(variants):raise DomainError('duplicate union variant')
    elif t=='record':
        fields=domain.get('fields');symbol=domain.get('symbol')
        if (fields is None)==(symbol is None):raise DomainError('record requires exactly one of fields or symbol')
        if symbol is not None and (not isinstance(symbol,str) or not symbol):raise DomainError('invalid record name')
        if fields is not None:
            if not isinstance(fields,dict) or not fields:raise DomainError('record fields required')
            for k,f in fields.items():
                if not isinstance(k,str) or not k or not isinstance(f,dict):raise DomainError('invalid record field')
                if set(f)!={'domain','presence'} or f['presence'] not in ('required','optional','absent','undefined'):
                    raise DomainError('invalid record presence')
                validate_domain(f['domain'])
    return domain


def same_value(a,b)->bool:
    if type(a) is not type(b):return False
    if isinstance(a,dict):return a.keys()==b.keys() and all(same_value(v,b[k]) for k,v in a.items())
    if isinstance(a,list):return len(a)==len(b) and all(same_value(x,y) for x,y in zip(a,b))
    return a==b


def check_presence(presence:str, value:Any, domain:dict)->bool:
    if presence=='absent':return value is MISSING
    if presence=='undefined':return value is UNDEFINED
    if value is MISSING:return presence=='optional'
    if value is UNDEFINED:return False
    return in_domain(domain,value)


def in_domain(domain:dict,value:Any)->bool:
    t=domain['type']
    if t=='null':return value is None
    if t=='nullable':return value is None or in_domain(domain['of'],value)
    if t=='union':return any(in_domain(v,value) for v in domain['variants'])
    if t=='boolean':return type(value) is bool
    if t=='integer':return type(value) is int and value>=domain.get('min',-float('inf')) and value<=domain.get('max',float('inf'))
    if t=='real':return type(value) in (int,float) and math.isfinite(value) and domain.get('min',-float('inf'))<=value<=domain.get('max',float('inf'))
    if t=='string':
        if not isinstance(value,str):return False
        if domain.get('format','any')=='any':return True
        return bool(re.fullmatch(r'[+-]?(?:0|[1-9]\d*)',value)) and len(value.lstrip('+-'))<=16 and abs(int(value))<=9007199254740991
    if t=='bytes':
        if not isinstance(value,(bytes,bytearray)):return False
        return domain.get('min_length',0)<=len(value)<=domain.get('max_length',float('inf'))
    if t=='enum':return any(same_value(v,value) for v in domain['values'])
    if t in ('set','sequence'):
        if not isinstance(value,list):return False
        elem=domain['element'];elem=elem if isinstance(elem,dict) else {'type':elem}
        if not all(in_domain(elem,v) for v in value):return False
        if t=='set' and any(same_value(value[i],value[j]) for i in range(len(value)) for j in range(i+1,len(value))):return False
        return True
    if t=='record':
        if 'symbol' in domain:return False # opaque named records require a concrete schema/verifier
        if not isinstance(value,dict):return False
        fields=domain['fields']
        return set(value)<=set(fields) and all(check_presence(f['presence'],value.get(k,MISSING),f['domain']) for k,f in fields.items())
    raise DomainError('unknown domain '+str(t))


def is_fully_interpreted(domain:dict)->bool:
    typ=domain['type']
    if typ=='record':return 'fields' in domain and all(is_fully_interpreted(v['domain']) for v in domain['fields'].values())
    if typ in ('set','sequence'):
        x=domain['element'];return is_fully_interpreted(x if isinstance(x,dict) else {'type':x})
    if typ=='nullable':return is_fully_interpreted(domain['of'])
    if typ=='union':return all(is_fully_interpreted(x) for x in domain['variants'])
    return True