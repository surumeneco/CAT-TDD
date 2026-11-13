"""Recursive CAT type domains: preserve structured meaning and missing/null separation."""
from __future__ import annotations
import math
import re
import json
import ast

class DomainError(ValueError):
    pass

MISSING=object()
UNDEFINED=object()

def _parts(value):
    """Split generic/enum items, ignoring commas or delimiters in literals."""
    depth=0; start=0; out=[]; quote=None; escaped=False
    for i,ch in enumerate(value):
        if quote:
            if escaped:escaped=False
            elif ch=='\\':escaped=True
            elif ch==quote:quote=None
            continue
        if ch in ('"',"'"):
            quote=ch
        elif ch in '<{[':depth+=1
        elif ch in '>}]':
            depth-=1
            if depth<0:raise DomainError('unbalanced domain delimiters')
        elif ch==',' and depth==0:
            out.append(value[start:i].strip());start=i+1
    if quote:raise DomainError('unclosed quoted domain literal')
    if depth:raise DomainError('unbalanced domain delimiters')
    out.append(value[start:].strip())
    if not all(out):raise DomainError('empty domain component')
    return out


def _enum_scalar(token):
    token=token.strip()
    if token.startswith(('"',"'")):
        try:value=ast.literal_eval(token)
        except (SyntaxError,ValueError) as exc:raise DomainError('invalid quoted enum literal') from exc
        if type(value) is not str:raise DomainError('enum quoted literal must be string')
        return value
    if token.lower()=='true' or token=='真':return True
    if token.lower()=='false' or token=='偽':return False
    if re.fullmatch(r'[+-]?(?:0|[1-9][0-9]*)',token):return int(token)
    if not token or '\\' in token or any(ch in token for ch in ('"',"'",'{','}','<','>')):
        raise DomainError('invalid enum literal')
    return token


def parse(text):
    if not isinstance(text,str) or not text.strip():raise DomainError('empty domain')
    text=text.strip().strip(chr(96))
    aliases={'文字列':'string','整数':'integer','真偽':'boolean','バイト列':'bytes',
             '実数':'real','安全符号付き整数':'string<safe-signed-integer>'}
    text=aliases.get(text,text)
    if text in ('string','integer','boolean','bytes','real'):return {'type':text}
    if text=='string<safe-signed-integer>':return {'type':'string','format':'safe-signed-integer'}
    if (text.startswith('enum{') or text.startswith('列挙{')) and text.endswith('}'):
        opening=text.index('{')
        values=[_enum_scalar(item) for item in _parts(text[opening+1:-1])]
        result={'type':'enum','values':values}
        validate(result)
        return result
    if text.endswith('|null'):
        return {'type':'nullable','of':parse(text[:-len('|null')].strip())}
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
                match=re.fullmatch(
                    r'(?P<name>[\w-]+)(?:\[(?P<presence>required|optional|absent|undefined)\])?',
                    key,flags=re.UNICODE)
                if match is None:
                    raise DomainError('invalid record field or Presence '+key)
                name=match.group('name')
                if name in seen:
                    raise DomainError('duplicate record field '+name)
                seen.add(name)
                fields.append({'id':name,
                               'domain':parse(definition) if has_type else {'type':'unknown'},
                               'presence':match.group('presence') or 'required'})
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
    elif t=='enum':
        _keys(d,{'type','values'})
        values=d['values']
        if not isinstance(values,list) or not values or any(type(v) not in (str,int,bool) for v in values):
            raise DomainError('enum requires nonempty scalar values')
        if len({_signature(v) for v in values})!=len(values):
            raise DomainError('duplicate enum value')
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
        _keys(d,{'type','resolved'},{'name','fields','definition_source','definition_sha256'})
        if 'name' in d and not d.get('resolved',False):
            if not isinstance(d['name'],str) or not d['name'] or 'fields' in d:
                raise DomainError('unresolved nominal record required')
        else:
            if 'name' in d:
                if not isinstance(d['name'],str) or not d['name'] or not d.get('resolved'):
                    raise DomainError('invalid resolved nominal record')
                for name in ('definition_source','definition_sha256'):
                    if not isinstance(d.get(name),str) or not d[name]:
                        raise DomainError('missing named type provenance')
                _keys(d,{'type','resolved','name','fields','definition_source','definition_sha256'})
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
    if t=='union':
        unknown=None
        for variant in d['variants']:
            try:
                if contains(variant,value):return True
            except DomainError as exc:
                unknown=exc
        if unknown is not None:raise unknown
        return False
    if t=='enum':return any(same(value,v) for v in d['values'])
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
        if not isinstance(value,list):return False
        if t=='set' and len({_signature(v) for v in value})!=len(value):return False
        unknown=None
        for element in value:
            try:
                if not contains(d['element'],element):return False
            except DomainError as exc:
                unknown=exc
        if unknown is not None:raise unknown
        return True
    if t=='record':
        # Record shape is irrelevant for values that cannot be records.
        # Unknown field schemas are inconclusive only for record-shaped values.
        if type(value) is not dict:return False
        if not d.get('resolved'):raise DomainError('unresolved record shape')
        if set(value)-{f['id'] for f in d['fields']}:return False
        unknown=None
        for field in d['fields']:
            try:
                if not check_presence(field['domain'],field['presence'],value.get(field['id'],MISSING))[1]:
                    return False
            except DomainError as exc:
                unknown=exc
        if unknown is not None:raise unknown
        return True
    raise DomainError('cannot validate type '+repr(t))


def finite_values(domain,max_values=65536):
    """Enumerate an exact finite domain, or return None; never guess witnesses."""
    if type(max_values) is not int or max_values<1:
        raise DomainError('finite-domain cap must be positive integer')
    validate(domain)
    t=domain['type']
    if t=='boolean':return [False,True] if max_values>=2 else None
    if t=='enum':
        return list(domain['values']) if len(domain['values'])<=max_values else None
    if t=='integer':
        low=domain.get('min');high=domain.get('max')
        if low is None or high is None or high-low+1>max_values:return None
        return list(range(low,high+1))
    if t=='nullable':
        values=finite_values(domain['of'],max_values-1) if max_values>1 else None
        return [None,*values] if values is not None else None
    if t=='union':
        values=[]
        for v in domain['variants']:
            part=finite_values(v,max_values)
            if part is None:return None
            for item in part:
                if not any(same(item,old) for old in values):
                    values.append(item)
                    if len(values)>max_values:return None
        return values
    if t=='record':
        if not domain.get('resolved') or any(f['presence']!='required' for f in domain['fields']):
            return None
        from itertools import product
        dimensions=[]
        capacity=1
        for field in domain['fields']:
            cases=finite_values(field['domain'],max_values)
            if cases is None:return None
            capacity*=len(cases)
            if capacity>max_values:return None
            dimensions.append(cases)
        return [{f['id']:v for f,v in zip(domain['fields'],values)}
                for values in product(*dimensions)]
    # Arbitrary-length sequences, real, text, bytes and unbounded sets
    # remain unproven, even when a representative sample could be constructed.
    return None



def set_add(values,element):
    out=list(values)
    if not any(same(v,element) for v in out):out.append(element)
    return sorted(out,key=lambda x:json.dumps(_signature(x),ensure_ascii=False,default=str))

def set_remove(values,element):
    return sorted((v for v in values if not same(v,element)),
                  key=lambda x:json.dumps(_signature(x),ensure_ascii=False,default=str))
