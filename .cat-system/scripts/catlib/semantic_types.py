"""Recursive CAT type domains: preserve structured meaning and missing/null separation."""
from __future__ import annotations
import math
import re
import json

class DomainError(ValueError):
    pass

MISSING=object()
UNDEFINED=object()

def _parts(value):
    depth=0;start=0;out=[]
    for i,ch in enumerate(value):
        if ch in '<{[':depth+=1
        elif ch in '>}]':
            depth-=1
            if depth<0:raise DomainError('unbalanced domain delimiters')
        elif ch==',' and depth==0:
            out.append(value[start:i].strip());start=i+1
    if depth:raise DomainError('unbalanced domain delimiters')
    out.append(value[start:].strip())
    if not all(out):raise DomainError('empty domain component')
    return out

def parse(text):
    if not isinstance(text,str) or not text.strip():raise DomainError('empty domain')
    text=text.strip().strip(chr(96))
    aliases={'文字列':'string','整数':'integer','真偽':'boolean','バイト列':'bytes',
             '実数':'real','安全符号付き整数':'string<safe-signed-integer>'}
    text=aliases.get(text,text)
    if text in ('string','integer','boolean','bytes','real'):return {'type':text}
    if text=='string<safe-signed-integer>':return {'type':'string','format':'safe-signed-integer'}
    if text.endswith('またはnull'):
        return {'type':'nullable','of':parse(text[:-len('またはnull')].strip())}
    for prefix in ('nullable<','Nullable<'):
        if text.startswith(prefix) and text.endswith('>'):
            return {'type':'nullable','of':parse(text[len(prefix):-1])}
    for prefix in ('union<','Union<'):
        if text.startswith(prefix) and text.endswith('>'):
            variants=[parse(v) for v in _parts(text[len(prefix):-1])]
            if len(variants)<2:raise DomainError('union needs >=2 variants')
            return {'type':'union','variants':variants}
    for prefix,kind in (('集合<','set'),('set<','set'),('列<','sequence'),('sequence<','sequence')):
        if text.startswith(prefix) and text.endswith('>'):
            return {'type':kind,'element':parse(text[len(prefix):-1])}
    for prefix in ('レコード<','record<','Record<'):
        if text.startswith(prefix) and text.endswith('>'):
            components=_parts(text[len(prefix):-1])
            if len(components)==1 and ':' not in components[0]:
                return {'type':'record','name':components[0],'resolved':False}
            fields=[];seen=set()
            for component in components:
                key,has_type,definition=component.partition(':')
                key=key.strip()
                if not re.fullmatch(r'[\w-]+',key,flags=re.UNICODE) or key in seen:
                    raise DomainError('invalid/duplicate record field '+key)
                seen.add(key)
                fields.append({'id':key,
                               'domain':parse(definition) if has_type else {'type':'unknown'},
                               'presence':'required'})
            return {'type':'record','fields':fields,
                    'resolved':all(f['domain']['type']!='unknown' for f in fields)}
    for pattern,kind,cast in (
        (r'(?:整数|integer)\[\s*([+-]?\d+)?\s*\.\.\s*([+-]?\d+)?\s*\]','integer',int),
        (r'(?:実数|real)\[\s*([+-]?(?:\d+(?:\.\d+)?))?\s*\.\.\s*([+-]?(?:\d+(?:\.\d+)?))?\s*\]','real',float)):
        m=re.fullmatch(pattern,text)
        if m:
            d={'type':kind}
            for key,val in zip(('min','max'),m.groups()):
                if val is not None:d[key]=cast(val)
            return d
    raise DomainError('unsupported domain '+repr(text))

def _keys(d,required,optional=frozenset()):
    if not isinstance(d,dict) or required-set(d) or set(d)-required-optional:
        raise DomainError('unexpected domain keys')

def validate(d):
    if not isinstance(d,dict):raise DomainError('domain object required')
    t=d.get('type')
    if t in ('boolean','bytes'):_keys(d,{'type'})
    elif t in ('integer','real'):
        _keys(d,{'type'},{'min','max'})
        for key in ('min','max'):
            if key in d and (type(d[key]) not in ((int,) if t=='integer' else (int,float))
                              or t=='real' and not math.isfinite(d[key])):
                raise DomainError('invalid numeric bound')
        if 'min' in d and 'max' in d and d['min']>d['max']:
            raise DomainError('empty numeric domain')
    elif t=='string':
        _keys(d,{'type'},{'format'})
        if d.get('format','any') not in ('any','safe-signed-integer'):
            raise DomainError('unsupported string format')
    elif t in ('set','sequence'):
        _keys(d,{'type','element'});validate(d['element'])
    elif t=='nullable':
        _keys(d,{'type','of'});validate(d['of'])
    elif t=='union':
        _keys(d,{'type','variants'})
        if not isinstance(d['variants'],list) or len(d['variants'])<2:
            raise DomainError('union needs >=2 variants')
        for v in d['variants']:validate(v)
    elif t=='record':
        _keys(d,{'type','resolved'},{'name','fields'})
        if 'name' in d:
            if not isinstance(d['name'],str) or not d['name'] or d.get('resolved') is not False:
                raise DomainError('unresolved nominal record required')
        else:
            if not isinstance(d.get('fields'),list) or not d['fields']:
                raise DomainError('record fields required')
            names=set()
            for field in d['fields']:
                _keys(field,{'id','domain','presence'})
                if field['id'] in names:raise DomainError('duplicate record field')
                names.add(field['id'])
                if field['presence'] not in ('required','optional','absent','undefined'):
                    raise DomainError('invalid nested presence')
                if field['domain']!={'type':'unknown'}:validate(field['domain'])
            if d.get('resolved') is True and any(f['domain']=={'type':'unknown'} for f in d['fields']):
                raise DomainError('record falsely resolved')
    else:raise DomainError('unsupported type '+repr(t))
    return d

def _signature(value):
    if isinstance(value,list):return ('list',tuple(_signature(x) for x in value))
    if isinstance(value,dict):return ('record',tuple(sorted((k,_signature(v)) for k,v in value.items())))
    if isinstance(value,(bytes,bytearray)):return ('bytes',bytes(value))
    return (type(value).__name__,value)

def same(a,b):return _signature(a)==_signature(b)

def check_presence(domain,presence,value=MISSING):
    if presence not in ('required','optional','absent','undefined'):
        raise DomainError('unsupported presence')
    if value is MISSING:return ('missing',presence in ('optional','absent'))
    if value is UNDEFINED:return ('undefined',presence=='undefined')
    if presence in ('absent','undefined'):return ('value',False)
    if value is None:return ('null',contains(domain,None))
    valid=contains(domain,value)
    return ('value' if valid else 'out-of-domain',valid)

def contains(d,value):
    t=d['type']
    if t=='nullable':return value is None or contains(d['of'],value)
    if t=='union':return any(contains(v,value) for v in d['variants'])
    if t=='integer':
        return type(value) is int and (d.get('min') is None or value>=d['min']) and (d.get('max') is None or value<=d['max'])
    if t=='real':
        return type(value) in (int,float) and math.isfinite(value) and (d.get('min') is None or value>=d['min']) and (d.get('max') is None or value<=d['max'])
    if t=='boolean':return type(value) is bool
    if t=='string':
        if type(value) is not str:return False
        if d.get('format','any')=='any':return True
        return bool(re.fullmatch(r'[+-]?(?:0|[1-9][0-9]*)',value)) and abs(int(value))<=9007199254740991
    if t=='bytes':
        return isinstance(value,(bytes,bytearray)) or (isinstance(value,list) and all(type(v) is int and 0<=v<=255 for v in value))
    if t in ('set','sequence'):
        if not isinstance(value,list) or not all(contains(d['element'],v) for v in value):return False
        return t=='sequence' or len({_signature(v) for v in value})==len(value)
    if t=='record':
        if not d.get('resolved'):raise DomainError('unresolved record shape')
        if type(value) is not dict:return False
        if set(value)-{f['id'] for f in d['fields']}:return False
        return all(check_presence(f['domain'],f['presence'],value.get(f['id'],MISSING))[1] for f in d['fields'])
    raise DomainError('cannot validate type '+repr(t))

def set_add(values,element):
    out=list(values)
    if not any(same(v,element) for v in out):out.append(element)
    return sorted(out,key=lambda x:json.dumps(_signature(x),ensure_ascii=False,default=str))

def set_remove(values,element):
    return sorted((v for v in values if not same(v,element)),
                  key=lambda x:json.dumps(_signature(x),ensure_ascii=False,default=str))
