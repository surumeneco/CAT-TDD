#!/usr/bin/env python3
"""CAT v2 symbolic-IR prototype: explicit semantics only; fail closed on unknowns.

Model preserves predicates/expressions and derived frame conditions. Concrete
vectors and a separate driver are only used in the later test-code phase.
Not a complete CAT solver, arbitrary-process composer or correctness proof.
"""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
import hashlib
import itertools
import io
import json
from pathlib import Path
import re
import sys
import tokenize

from catlib.markdown import parse_frontmatter

ROOT = Path(__file__).resolve().parent.parent

S = 'cat-machine/v2'
M = 'cat-test-model/v2'
D = 'cat-test-driver/v2'
Q = 'cat-tdd-queue/v1'
ID = re.compile(r'^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$')
CODE = re.compile(r'(?ms)^```cat-machine\s*\n(.*?)\n```\s*$')
INT = re.compile(r'^[+-]?(?:0|[1-9][0-9]*)$')
SAFE_INT = 9007199254740991
OPS = {'eq','ne','lt','le','gt','ge','and','or','not','add','sub','mul',
       'div','floor','abs','length','concat','to-int','set-add','set-remove','call'}

class Blocked(ValueError):
    pass

def require(test, message):
    if not test:
        raise Blocked(message)

def check_keys(obj, needed, optional=(), where='object'):
    require(isinstance(obj, dict), f'{where}: object required')
    missing=set(needed)-set(obj); extra=set(obj)-set(needed)-set(optional)
    require(not missing and not extra, f'{where}: missing {sorted(missing)}; unsupported {sorted(extra)}')
    return obj

def unique(items, where):
    require(len(items)==len(set(items)), f'{where}: duplicate identifier')

def ident(s, where):
    require(isinstance(s,str) and ID.fullmatch(s), f'{where}: invalid identifier {s!r}')
    return s


def _markdown_body(path):
    raw=Path(path).read_text(encoding='utf-8-sig')
    end=raw.find('\n---\n',4)
    require(raw.startswith('---\n') and end>=0, f'{path}: invalid front matter')
    return raw[end+5:]


def _section(text, name):
    m=re.search(r'(?ms)^## '+re.escape(name)+r'\s*$\n(.*?)(?=^##\s|\Z)',text)
    return m.group(1).strip() if m else None


def _section_any(text, *names):
    for name in names:
        sec=_section(text,name)
        if sec is not None:return sec
    return None


def _split_md_row(line):
    line=line.strip()
    require(line.startswith('|') and line.endswith('|'),'Markdown table rows must start/end with |')
    cells=[];buf=[];escaped=False
    for ch in line[1:-1]:
        if escaped:
            buf.append(ch);escaped=False;continue
        if ch=='\\':
            escaped=True;buf.append(ch);continue
        if ch=='|':
            cells.append(''.join(buf).strip().replace('\\|','|'));buf=[]
        else:buf.append(ch)
    cells.append(''.join(buf).strip().replace('\\|','|'))
    return cells


def _table_from_section(sec, label, required=True):
    if sec is None:
        require(not required, f'missing ## {label} section')
        return []
    lines=[x for x in sec.splitlines() if x.strip().startswith('|')]
    if not lines:
        require(not required, f'## {label}: table required')
        return []
    header=_split_md_row(lines[0])
    require(len(lines)>=2 and len(_split_md_row(lines[1]))==len(header),'invalid Markdown table header')
    sep=_split_md_row(lines[1])
    require(all(re.fullmatch(r':?-{3,}:?',x.strip()) for x in sep),'invalid Markdown table separator')
    rows=[]
    for line in lines[2:]:
        cells=_split_md_row(line)
        require(len(cells)==len(header),f'## {label}: row width differs from header')
        rows.append(dict(zip(header,cells)))
    return rows


def _table(text, section_name, required=True):
    return _table_from_section(_section(text,section_name),section_name,required)


def _table_any(text, names, required=True):
    sec=_section_any(text,*names)
    return _table_from_section(sec,'/'.join(names),required)


def _cell(row, *names, required=True):
    for n in names:
        if n in row:return row[n].strip()
    require(not required, 'table column required: '+('/'.join(names)))
    return ''


def _canon(value, mapping, where):
    key=value.strip().lower()
    for canonical, aliases in mapping.items():
        if key==canonical.lower() or value.strip() in aliases:return canonical
    raise Blocked(f'{where}: unsupported value {value!r}')


def _bool_text(value, where):
    v=value.strip().lower()
    if v in ('true','yes','1') or value.strip() in ('真','はい'):return True
    if v in ('false','no','0') or value.strip() in ('偽','いいえ'):return False
    raise Blocked(f'{where}: true/false or 真/偽 required')


def semantic_ident(s, where, dotted=True):
    require(isinstance(s,str) and s.strip(), f'{where}: identifier required')
    parts=s.strip().split('.') if dotted else [s.strip()]
    require(all(x.isidentifier() for x in parts), f'{where}: invalid Unicode identifier {s!r}')
    return s.strip()


def _dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _dotted(node.value) + '.' + node.attr
    raise Blocked('field reference must be dotted identifier')

def _unquote_code(value):
    value=value.strip()
    if len(value)>=2 and value[0]=='`' and value[-1]=='`':return value[1:-1].strip()
    return value


def _split_items(text, sep=','):
    out=[];buf=[];quote=None;escaped=False;depth=0
    for ch in text:
        if escaped:buf.append(ch);escaped=False;continue
        if ch=='\\':buf.append(ch);escaped=True;continue
        if quote:
            buf.append(ch)
            if ch==quote:quote=None
            continue
        if ch in ('\"',"'"):
            quote=ch;buf.append(ch);continue
        if ch in '([{':depth+=1
        elif ch in ')]}':depth-=1
        if ch==sep and depth==0:
            out.append(''.join(buf).strip());buf=[]
        else:buf.append(ch)
    out.append(''.join(buf).strip())
    return [x for x in out if x]


def _scalar_token(token):
    token=token.strip()
    if len(token)>=2 and token[0] in ('\"',"'") and token[-1]==token[0]:
        try:return ast.literal_eval(token)
        except (ValueError,SyntaxError) as exc:raise Blocked('invalid quoted enum literal '+token) from exc
    low=token.lower()
    if low=='true':return True
    if low=='false':return False
    if token=='真':return True
    if token=='偽':return False
    if INT.fullmatch(token):return int(token)
    require(bool(token),'empty enum value')
    return token


def parse_domain_text(text):
    text=_unquote_code(text).strip()
    aliases={'真偽':'boolean','整数':'integer','文字列':'string','安全符号付き整数':'safe-signed-integer'}
    for ja,en in aliases.items():text=text.replace(ja,en)
    text=text.replace('集合<','set<').replace('列<','sequence<').replace('列挙{','enum{')
    if text=='boolean':return {'type':'boolean'}
    if text=='integer':return {'type':'integer'}
    m=re.fullmatch(r'integer\[\s*([+-]?\d*)\s*\.\.\s*([+-]?\d*)\s*\]',text)
    if m:
        d={'type':'integer'}
        if m.group(1):d['min']=int(m.group(1))
        if m.group(2):d['max']=int(m.group(2))
        return d
    if text=='string':return {'type':'string'}
    if text=='string<safe-signed-integer>':return {'type':'string','format':'safe-signed-integer'}
    m=re.fullmatch(r'(set|sequence)<(string|integer)>',text)
    if m:return {'type':m.group(1),'element':m.group(2)}
    m=re.fullmatch(r'enum\{(.*)\}',text)
    if m:return {'type':'enum','values':[_scalar_token(x) for x in _split_items(m.group(1))]}
    raise Blocked('unsupported readable domain '+repr(text))


def _normalize_expr_language(text):
    """Translate language aliases token-wise without modifying quoted strings."""
    aliases={'真':'True','偽':'False','なし':'None','かつ':'and','または':'or',
             '長さ':'length','整数化':'to_int','連結':'concat','集合追加':'set_add','集合削除':'set_remove','否定':'not_fn'}
    try:
        tokens=[]
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type==tokenize.NAME and tok.string in aliases:
                tok=tokenize.TokenInfo(tok.type,aliases[tok.string],tok.start,tok.end,tok.line)
            tokens.append(tok)
        return tokenize.untokenize(tokens)
    except tokenize.TokenError as exc:
        raise Blocked('invalid CAT expression tokenization '+repr(text)) from exc


def parse_expr_text(text, params=()):
    text=_normalize_expr_language(_unquote_code(text))
    try:root=ast.parse(text,mode='eval').body
    except SyntaxError as exc:raise Blocked('invalid CAT expression '+repr(text)) from exc
    builtin={'length':'length','len':'length','abs':'abs','floor':'floor','to_int':'to-int',
             'concat':'concat','set_add':'set-add','set_remove':'set-remove','not_fn':'not'}
    compare={ast.Eq:'eq',ast.NotEq:'ne',ast.Lt:'lt',ast.LtE:'le',ast.Gt:'gt',ast.GtE:'ge'}
    binary={ast.Add:'add',ast.Sub:'sub',ast.Mult:'mul',ast.Div:'div'}
    def cv(n):
        if isinstance(n,ast.Constant):
            require(type(n.value) in (str,int,bool,type(None)),'unsupported literal in CAT expression')
            return {'literal':n.value}
        if isinstance(n,ast.List):
            vals=[]
            for e in n.elts:
                x=cv(e);require(set(x)=={'literal'} and type(x['literal']) in (str,int,bool),'list literals must contain scalar literals')
                vals.append(x['literal'])
            return {'literal':vals}
        if isinstance(n,ast.Name):
            low=n.id.lower()
            if low=='true':return {'literal':True}
            if low=='false':return {'literal':False}
            if low in ('null','none'):return {'literal':None}
            if n.id in params:return {'ref':'param.'+n.id}
            raise Blocked('bare name is not a field/parameter: '+n.id)
        if isinstance(n,ast.Attribute):return {'ref':_dotted(n)}
        if isinstance(n,ast.BoolOp):return {'op':'and' if isinstance(n.op,ast.And) else 'or','args':[cv(x) for x in n.values]}
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,ast.Not):return {'op':'not','args':[cv(n.operand)]}
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.USub,ast.UAdd)):
            require(isinstance(n.operand,ast.Constant) and type(n.operand.value) is int,'unary +/- only supported for integer literals')
            return {'literal':(-n.operand.value if isinstance(n.op,ast.USub) else n.operand.value)}
        if isinstance(n,ast.BinOp):
            op=binary.get(type(n.op));require(op is not None,'unsupported binary CAT operator')
            return {'op':op,'args':[cv(n.left),cv(n.right)]}
        if isinstance(n,ast.Compare):
            require(len(n.ops)==1 and len(n.comparators)==1,'chained comparisons are unsupported; combine explicit comparisons with and/かつ')
            op=compare.get(type(n.ops[0]));require(op is not None,'unsupported comparison')
            return {'op':op,'args':[cv(n.left),cv(n.comparators[0])]}
        if isinstance(n,ast.Call):
            require(not n.keywords and isinstance(n.func,ast.Name),'CAT calls use positional arguments and simple names')
            args=[cv(x) for x in n.args];name=n.func.id
            if name in builtin:return {'op':builtin[name],'args':args}
            return {'op':'call','name':name,'args':args}
        raise Blocked('unsupported CAT expression element '+type(n).__name__)
    return cv(root)


def _effect_items(value):
    raw=_unquote_code(value).strip()
    if raw in ('','-','—','none','なし','変更なし','no effect'):return []
    out=[]
    for item in _split_items(raw,sep=';'):
        item=_unquote_code(item).strip()
        m=re.match(r'^(.+?)\s*=\s*(.+)$',item)
        require(m is not None and '==' not in m.group(1),'Effect must be `target = expression`')
        target=semantic_ident(m.group(1).strip(),'Effect target')
        out.append({'target':target,'expr':parse_expr_text(m.group(2).strip())})
    unique([x['target'] for x in out],'Effect targets')
    return out


def _readable_spec_v1(path, kind, fm):
    body=_markdown_body(path)
    require(not CODE.findall(body),f'{path}: markdown-v1 must not contain a second cat-machine authority')
    process=fm.get('process')
    if kind=='process':
        sec=_section(body,'Contract') or ''
        m=re.search(r'(?im)^Closed world:\s*(true|false)\s*$',sec)
        require(m is not None,'Process ## Contract requires Closed world: true|false')
        triggers=[]
        for row in _table(body,'Triggers'):
            triggers.append({'id':_cell(row,'ID','Id','id'),'origin':_cell(row,'Origin','origin')})
        return {'schema':S,'kind':kind,'process':process,'triggers':triggers,'closed_world':m.group(1).lower()=='true'}
    if kind=='pi':
        fields=[]
        for row in _table(body,'Fields'):
            fields.append({'id':_cell(row,'ID','Id','id'),'role':_cell(row,'Role','role'),
                           'domain':parse_domain_text(_cell(row,'Domain','domain'))})
        constraints=[]
        for row in _table(body,'Constraints',required=False):
            constraints.append(parse_expr_text(_cell(row,'Expression','Condition','expression','condition')))
        return {'schema':S,'kind':kind,'process':process,'fields':fields,'constraints':constraints}
    if kind=='tce':
        m=re.search(r'(?im)^Coverage:\s*(closed|partial)\s*$',body)
        require(m is not None,'TCE requires `Coverage: closed|partial`')
        rules=[];by={}
        for row in _table(body,'Rules'):
            rid=_cell(row,'ID','Id','id')
            r={'id':rid,'trigger':_cell(row,'Trigger','trigger'),
               'when':parse_expr_text(_cell(row,'Condition','When','condition','when')),'allowed':[]}
            require(rid not in by,'duplicate readable TCE rule '+rid)
            by[rid]=r;rules.append(r)
        outcomes={}
        for row in _table(body,'Effects'):
            rid=_cell(row,'Rule','Rule ID','rule');require(rid in by,'Effect references unknown rule '+rid)
            raw_out=_cell(row,'Outcome','outcome');require(raw_out.isdigit() and int(raw_out)>=1,'Outcome must be positive integer')
            key=(rid,int(raw_out));out=outcomes.setdefault(key,{'write':[]})
            target=_cell(row,'Target','target');expr=_cell(row,'Expression','Effect','expression','effect')
            if target in ('','-','none'):
                require(expr in ('','-','none'),'no-effect outcome must use -/none in both target and expression')
            else:out['write'].append({'target':target,'expr':parse_expr_text(expr)})
        for rid,r in by.items():
            nums=sorted(n for (rr,n) in outcomes if rr==rid)
            require(nums and nums==list(range(1,max(nums)+1)),f'{rid}: Outcomes must start at 1 and be contiguous')
            r['allowed']=[outcomes[(rid,n)] for n in nums]
        return {'schema':S,'kind':kind,'process':process,'coverage':m.group(1).lower(),'rules':rules}
    if kind=='domain-rule':
        definitions=[]
        for row in _table(body,'Definitions'):
            params_text=_cell(row,'Parameters','Params','parameters','params')
            params=[] if params_text in ('','-','none') else [x.strip() for x in _split_items(params_text)]
            definitions.append({'id':_cell(row,'ID','Id','id'),'params':params,
                                'body':parse_expr_text(_cell(row,'Expression','Body','expression','body'),params)})
        return {'schema':S,'kind':kind,'process':process,'definitions':definitions}
    raise Blocked('markdown-v1 unsupported for kind '+kind)


def _readable_spec_v2(path, kind, fm):
    body=_markdown_body(path)
    require(not CODE.findall(body),f'{path}: markdown-v2 must not contain a second cat-machine authority')
    process=fm.get('process')
    if kind=='process':
        sec=_section_any(body,'Contract','契約') or ''
        m=re.search(r'(?im)^(?:Closed world|閉世界):\s*(.+?)\s*$',sec)
        require(m is not None,'Process 契約/Contract requires 閉世界/Closed world')
        interfaces=[_cell(r,'PI','pi') for r in _table_any(body,('Interfaces','境界'),required=False)]
        state=[]
        for row in _table_any(body,('State','仕様状態'),required=False):
            state.append({'id':semantic_ident(_cell(row,'ID','Id','id'),'State ID'), 'role':'state',
                          'domain':parse_domain_text(_cell(row,'Domain','domain'))})
        observations=[]
        for row in _table_any(body,('Observations','観測能力'),required=False):
            observations.append({'id':semantic_ident(_cell(row,'ID','Id','id'),'Observation ID'),'role':'observation',
                                 'source':_cell(row,'Source','Origin','source','由来','情報源'),
                                 'domain':parse_domain_text(_cell(row,'Domain','domain'))})
        actions=[]
        for row in _table_any(body,('Actions','作用能力'),required=False):
            actions.append({'id':semantic_ident(_cell(row,'ID','Id','id'),'Action ID'),'role':'action',
                            'target':_cell(row,'Target','target','対象'),
                            'domain':parse_domain_text(_cell(row,'Domain','domain'))})
        triggers=[]
        for row in _table_any(body,('Triggers','起点')):
            triggers.append({'id':semantic_ident(_cell(row,'ID','Id','id'),'Trigger ID'),
                             'origin':_cell(row,'Source','Origin','source','origin','由来','起点元')})
        return {'schema':S,'kind':kind,'process':process,'interfaces':interfaces,'triggers':triggers,
                'closed_world':_bool_text(m.group(1),'Closed world'),'state_fields':state,
                'observations':observations,'actions':actions}
    if kind=='pi':
        boundary_rows=_table_any(body,('Boundary','境界'))
        require(len(boundary_rows)==1,'PI Boundary/境界 requires exactly one row')
        br=boundary_rows[0]
        peer=_cell(br,'Peer process','Peer Process','peer','相手Process','相手プロセス')
        direction=_canon(_cell(br,'Direction','direction','方向'),
                         {'receive':{'受信'},'send':{'送信'},'bidirectional':{'双方向'}},'PI boundary direction')
        fields=[]
        for row in _table_any(body,('Fields','項目')):
            require(not any(k in row for k in ('Role','role','役割')),
                    'markdown-v2 PI must not declare Process state via Role/役割; use Process State/仕様状態')
            fdir=_canon(_cell(row,'Direction','direction','方向'),{'receive':{'受信'},'send':{'送信'}},'PI field direction')
            presence=_canon(_cell(row,'Presence','presence','存在'),
                            {'required':{'必須'},'optional':{'任意'},'absent':{'不在'},'undefined':{'未定義'}},'PI field presence')
            fields.append({'id':semantic_ident(_cell(row,'ID','Id','id'),'PI field'),'role':'input' if fdir=='receive' else 'output',
                           'direction':fdir,'presence':presence,'domain':parse_domain_text(_cell(row,'Domain','domain'))})
        operations=[]
        for row in _table_any(body,('Operations','操作'),required=False):
            odir=_canon(_cell(row,'Direction','direction','方向'),{'accept':{'受付'},'provide':{'提供'}},'PI operation direction')
            trig=_cell(row,'Trigger','trigger','起点',required=False)
            operations.append({'id':semantic_ident(_cell(row,'ID','Id','id'),'PI operation ID'),'direction':odir,
                               'trigger':None if trig in ('','-','—','none','なし') else trig})
        constraints=[]
        for row in _table_any(body,('Constraints','制約'),required=False):
            constraints.append(parse_expr_text(_cell(row,'Expression','Condition','expression','condition','式','条件')))
        return {'schema':S,'kind':kind,'process':process,'boundary':{'peer':peer,'direction':direction},
                'fields':fields,'operations':operations,'constraints':constraints}
    if kind=='tce':
        require(_section_any(body,'Rules','Effects') is None,
                'markdown-v2 TCE must use Behaviors/振る舞い; legacy Rules/Effects are markdown-v1 only')
        m=re.search(r'(?im)^(?:Coverage requirement|網羅要求):\s*(.+?)\s*$',body)
        require(m is not None,'TCE requires Coverage requirement/網羅要求')
        coverage=_canon(m.group(1),{'closed':{'閉包'},'partial':{'部分'}},'TCE coverage requirement')
        by={};outcomes={}
        for row in _table_any(body,('Behaviors','振る舞い')):
            rid=semantic_ident(_cell(row,'ID','Id','id'),'Behavior ID')
            trigger=semantic_ident(_cell(row,'Trigger','trigger','起点'),'Behavior trigger')
            when=parse_expr_text(_cell(row,'Condition','When','condition','when','条件'))
            raw_out=_cell(row,'Outcome','outcome','結果');require(raw_out.isdigit() and int(raw_out)>=1,'Outcome/結果 must be positive integer')
            effect_text=_cell(row,'Effects','Effect','effects','effect','効果')
            if rid not in by:by[rid]={'id':rid,'trigger':trigger,'when':when,'allowed':[]}
            else:
                require(by[rid]['trigger']==trigger and by[rid]['when']==when,f'{rid}: repeated behavior rows must keep Trigger/Condition identical')
            key=(rid,int(raw_out));require(key not in outcomes,f'{rid}: duplicate Outcome {raw_out}')
            outcomes[key]={'write':_effect_items(effect_text)}
        rules=[]
        for rid,r in by.items():
            nums=sorted(n for rr,n in outcomes if rr==rid)
            require(nums and nums==list(range(1,max(nums)+1)),f'{rid}: Outcomes must start at 1 and be contiguous')
            r['allowed']=[outcomes[(rid,n)] for n in nums];rules.append(r)
        return {'schema':S,'kind':kind,'process':process,'coverage':coverage,'rules':rules}
    if kind=='domain-rule':
        definitions=[]
        for row in _table_any(body,('Definitions','定義')):
            params_text=_cell(row,'Parameters','Params','parameters','params','引数')
            params=[] if params_text in ('','-','—','none','なし') else [semantic_ident(x.strip(),'DomainRule parameter',False) for x in _split_items(params_text)]
            definitions.append({'id':semantic_ident(_cell(row,'ID','Id','id'),'DomainRule ID',False),'params':params,
                                'body':parse_expr_text(_cell(row,'Expression','Body','expression','body','式'),params)})
        return {'schema':S,'kind':kind,'process':process,'definitions':definitions}
    raise Blocked('markdown-v2 deterministic compiler unsupported for kind '+kind)

def _readable_spec(path, kind, fm):
    body=_markdown_body(path)
    require(not CODE.findall(body),f'{path}: markdown-v1 must not contain a second cat-machine authority')
    process=fm.get('process')
    if kind=='process':
        sec=_section(body,'Contract') or ''
        m=re.search(r'(?im)^Closed world:\s*(true|false)\s*$',sec)
        require(m is not None,'Process ## Contract requires Closed world: true|false')
        triggers=[]
        for row in _table(body,'Triggers'):
            triggers.append({'id':_cell(row,'ID','Id','id'),'origin':_cell(row,'Origin','origin')})
        return {'schema':S,'kind':kind,'process':process,'triggers':triggers,'closed_world':m.group(1).lower()=='true'}
    if kind=='pi':
        fields=[]
        for row in _table(body,'Fields'):
            fields.append({'id':_cell(row,'ID','Id','id'),'role':_cell(row,'Role','role'),
                           'domain':parse_domain_text(_cell(row,'Domain','domain'))})
        constraints=[]
        for row in _table(body,'Constraints',required=False):
            constraints.append(parse_expr_text(_cell(row,'Expression','Condition','expression','condition')))
        return {'schema':S,'kind':kind,'process':process,'fields':fields,'constraints':constraints}
    if kind=='tce':
        m=re.search(r'(?im)^Coverage:\s*(closed|partial)\s*$',body)
        require(m is not None,'TCE requires `Coverage: closed|partial`')
        rules=[];by={}
        for row in _table(body,'Rules'):
            rid=_cell(row,'ID','Id','id')
            r={'id':rid,'trigger':_cell(row,'Trigger','trigger'),
               'when':parse_expr_text(_cell(row,'Condition','When','condition','when')),'allowed':[]}
            require(rid not in by,'duplicate readable TCE rule '+rid)
            by[rid]=r;rules.append(r)
        outcomes={}
        for row in _table(body,'Effects'):
            rid=_cell(row,'Rule','Rule ID','rule');require(rid in by,'Effect references unknown rule '+rid)
            raw_out=_cell(row,'Outcome','outcome');require(raw_out.isdigit() and int(raw_out)>=1,'Outcome must be positive integer')
            key=(rid,int(raw_out));out=outcomes.setdefault(key,{'write':[]})
            target=_cell(row,'Target','target');expr=_cell(row,'Expression','Effect','expression','effect')
            if target in ('','-','none'):
                require(expr in ('','-','none'),'no-effect outcome must use -/none in both target and expression')
            else:out['write'].append({'target':target,'expr':parse_expr_text(expr)})
        for rid,r in by.items():
            nums=sorted(n for (rr,n) in outcomes if rr==rid)
            require(nums and nums==list(range(1,max(nums)+1)),f'{rid}: Outcomes must start at 1 and be contiguous')
            r['allowed']=[outcomes[(rid,n)] for n in nums]
        return {'schema':S,'kind':kind,'process':process,'coverage':m.group(1).lower(),'rules':rules}
    if kind=='domain-rule':
        definitions=[]
        for row in _table(body,'Definitions'):
            params_text=_cell(row,'Parameters','Params','parameters','params')
            params=[] if params_text in ('','-','none') else [x.strip() for x in _split_items(params_text)]
            definitions.append({'id':_cell(row,'ID','Id','id'),'params':params,
                                'body':parse_expr_text(_cell(row,'Expression','Body','expression','body'),params)})
        return {'schema':S,'kind':kind,'process':process,'definitions':definitions}
    raise Blocked('markdown-v1 unsupported for kind '+kind)

def read_artifact(path, kind, allow_draft):
    path=Path(path); fm=parse_frontmatter(path)
    require(fm.get('kind')==kind, f'{path}: expected kind {kind}')
    contract=fm.get('semantic_contract')
    require(contract in ('machine-only','markdown-v1','markdown-v2'),f'{path}: semantic_contract must be markdown-v2 (preferred), markdown-v1 or machine-only (legacy)')
    require(fm.get('status')=='confirmed' or (allow_draft and fm.get('status')=='draft'),
            f'{path}: only confirmed inputs are normative; --allow-draft for evidence examples')
    if fm.get('status')=='confirmed':
        require(bool(fm.get('decision_ref')), f'{path}: confirmed requires decision_ref')
    require(isinstance(fm.get('source_refs'),list) and bool(fm['source_refs']),
            f'{path}: source_refs required')
    if contract=='markdown-v1':
        spec=_readable_spec_v1(path,kind,fm)
    elif contract=='markdown-v2':
        spec=_readable_spec_v2(path,kind,fm)
    else:
        matches=CODE.findall(path.read_text(encoding='utf-8-sig'))
        require(len(matches)==1, f'{path}: exactly one legacy cat-machine JSON block required')
        try: spec=json.loads(matches[0])
        except json.JSONDecodeError as e: raise Blocked(f'{path}: {e}') from e
    check_keys(spec,['schema','kind','process'],
               ['triggers','fields','rules','definitions','closed_world','coverage','constraints',
                'interfaces','state_fields','observations','actions','boundary','operations'],str(path))
    require(spec['schema']==S and spec['kind']==kind and spec['process']==fm.get('process'),
            f'{path}: frontmatter/semantic body mismatch')
    ident(fm.get('id'),'artifact id'); ident(spec['process'],'process id')
    return fm,spec

def validate_domain(d):
    check_keys(d,['type'],['values','min','max','format','element'],'domain')
    t=d['type']; require(t in {'enum','boolean','integer','string','set','sequence'},'unsupported domain type')
    if t=='enum':
        check_keys(d,['type','values'],where='enum domain')
        require(isinstance(d['values'],list) and bool(d['values']), 'enum nonempty values required')
        require(all(isinstance(v,(str,int,bool)) for v in d['values']), 'enum only str/int/bool')
        require(len({json.dumps(x,sort_keys=True) for x in d['values']})==len(d['values']), 'enum duplicate')
    if t=='boolean':check_keys(d,['type'],where='boolean domain')
    if t=='integer':
        check_keys(d,['type'],['min','max'],where='integer domain')
        for v in (d.get('min'),d.get('max')):
            require(v is None or type(v) is int,'integer domain bounds must be integer/null')
        if d.get('min') is not None and d.get('max') is not None:
            require(d['min']<=d['max'], 'empty integer domain')
    if t=='string':
        check_keys(d,['type'],['format'],where='string domain')
        require(d.get('format','any') in ('any','safe-signed-integer'),'unsupported string format')
    if t in ('set','sequence'):
        check_keys(d,['type','element'],where='collection domain')
        require(d['element'] in ('string','integer'),'collection element must be string/integer')
    return d

def safe_integer_text(value):
    return isinstance(value,str) and bool(INT.fullmatch(value)) and len(value.lstrip('+-'))<=16 and abs(int(value))<=SAFE_INT

def same_value(a,b):
    if type(a) is not type(b):return False
    if isinstance(a,list):return len(a)==len(b) and all(same_value(x,y) for x,y in zip(a,b))
    return a==b

def in_domain(d, value):
    t=d['type']
    if t=='enum':return any(type(v)==type(value) and v==value for v in d['values'])
    if t=='boolean':return type(value) is bool
    if t=='integer':return type(value) is int and (d.get('min') is None or value>=d['min']) and (d.get('max') is None or value<=d['max'])
    if t=='string':return isinstance(value,str) and (d.get('format','any')=='any' or safe_integer_text(value))
    if t in ('set','sequence'):
        return isinstance(value,list) and all(type(v) is (str if d['element']=='string' else int) for v in value) and (t!='set' or len(set(value))==len(value))
    raise Blocked('unknown domain')

def literal_type(v):
    if type(v) is bool:return 'boolean'
    if type(v) is int:return 'integer'
    if isinstance(v,str):return 'string'
    if isinstance(v,list):return 'sequence'
    return 'null'

def inspect_expr(expr, fields, definitions, params=(), stack=()):
    """Conservative AST type checker; unsupported conversions fail, never coerce."""
    require(isinstance(expr,dict),'expression must be AST object')
    if 'literal' in expr:
        check_keys(expr,['literal'],where='literal expression')
        require(type(expr['literal']) in (str,int,bool,list,type(None)), 'unsupported literal type')
        return literal_type(expr['literal'])
    if 'ref' in expr:
        check_keys(expr,['ref'],where='reference expression')
        ref=expr['ref']; require(isinstance(ref,str),'reference string required')
        if ref.startswith('param.'):
            key=ref[6:]
            require(key in params, 'unbound function parameter '+ref)
            return params[key] if isinstance(params,dict) else 'parameter'
        require(ref in fields and fields[ref]['role'] in ('input','state','observation'), 'unknown or non-readable ref '+ref)
        return fields[ref]['domain']['type']
    check_keys(expr,['op','args'],['name'],where='operator expression')
    op=expr['op']; require(op in OPS,'unsupported operator '+str(op))
    args=expr['args']; require(isinstance(args,list),'operator args must be array')
    if op=='call':
        check_keys(expr,['op','name','args'],where='domain-rule invocation')
        name=expr['name']; require(name in definitions,'unknown DomainRule '+str(name))
        require(name not in stack,'recursive DomainRule invocation '+str(name))
        defi=definitions[name];require(len(args)==len(defi['params']), 'DomainRule arity mismatch '+name)
        types=[inspect_expr(a,fields,definitions,params,stack) for a in args]
        return inspect_expr(defi['body'],fields,definitions,dict(zip(defi['params'],types)),stack+(name,))
    check_keys(expr,['op','args'],where='operator expression')
    arity={'not':1,'floor':1,'abs':1,'length':1,'to-int':1,'set-add':2,'set-remove':2}
    if op in arity:require(len(args)==arity[op],f'{op} needs {arity[op]} args')
    elif op in ('and','or','concat','add','mul'):require(len(args)>=2,op+' needs >=2 args')
    else:require(len(args)==2,op+' needs exactly 2 args')
    types=[inspect_expr(a,fields,definitions,params,stack) for a in args]
    def types_are(permitted):
        require(all(t in permitted or t=='parameter' for t in types),
                f'{op}: invalid operand types {types}; expected {sorted(permitted)}')
    if op in ('eq','ne'):return 'boolean'
    if op in ('lt','le','gt','ge'):types_are({'integer','real'});return 'boolean'
    if op in ('and','or','not'):types_are({'boolean'});return 'boolean'
    if op in ('add','sub','mul'):types_are({'integer'});return 'integer'
    if op=='div':
        types_are({'integer'})
        require('literal' in args[1] and type(args[1]['literal']) is int and args[1]['literal']!=0,
                'div denominator must be a declared nonzero integer literal; dynamic totality is unproved')
        return 'real'
    if op=='floor':types_are({'integer','real'});return 'integer'
    if op=='abs':types_are({'integer'});return 'integer'
    if op=='length':types_are({'string','set','sequence'});return 'integer'
    if op=='concat':types_are({'string'});return 'string'
    if op in ('set-add','set-remove'):
        require(types[0] in ('set','parameter') and types[1] in ('string','integer','parameter'),
                f'{op}: expected set and element, got {types}')
        return 'set'
    if op=='to-int':
        types_are({'string'})
        v=args[0]
        require(('ref' in v and v['ref'] in fields and fields[v['ref']]['domain'].get('format')=='safe-signed-integer')
                or ('literal' in v and isinstance(v['literal'],str) and safe_integer_text(v['literal'])),
                'to-int requires declared safe-signed-integer PI domain or safe integer literal')
        return 'integer'
    raise Blocked('operator missing return type '+op)

def eval_expr(expr, env, definitions, params=None):
    if 'literal' in expr:return deepcopy(expr['literal'])
    if 'ref' in expr:
        v=expr['ref'];return deepcopy((params or {})[v[6:]] if v.startswith('param.') else env[v])
    op=expr['op'];xs=[eval_expr(x,env,definitions,params) for x in expr['args']]
    if op=='call':
        f=definitions[expr['name']];return eval_expr(f['body'],env,definitions,dict(zip(f['params'],xs)))
    try:
        if op=='eq':return same_value(xs[0],xs[1])
        if op=='ne':return not same_value(xs[0],xs[1])
        if op=='lt':return xs[0]<xs[1]
        if op=='le':return xs[0]<=xs[1]
        if op=='gt':return xs[0]>xs[1]
        if op=='ge':return xs[0]>=xs[1]
        if op=='and':return all(type(x) is bool and x for x in xs)
        if op=='or':return any(type(x) is bool and x for x in xs)
        if op=='not':require(type(xs[0]) is bool,'not requires boolean');return not xs[0]
        if op=='add':require(all(type(x) is int for x in xs),'add requires integer');return sum(xs)
        if op=='sub':require(type(xs[0]) is int and type(xs[1]) is int,'sub requires integer');return xs[0]-xs[1]
        if op=='mul':
            require(all(type(x) is int for x in xs),'mul requires integer')
            a=1
            for x in xs:a*=x
            return a
        if op=='div':require(type(xs[0]) is int and type(xs[1]) is int and xs[1]!=0,'div requires integers and nonzero divisor');return xs[0]/xs[1]
        if op=='floor':import math;return math.floor(xs[0])
        if op=='abs':return abs(xs[0])
        if op=='length':return len(xs[0])
        if op=='to-int':
            require(safe_integer_text(xs[0]),'to-int requires safe canonical signed-integer string')
            return int(xs[0])
        if op=='concat':return ''.join(xs)
        if op=='set-add':
            require(isinstance(xs[0],list),'set-add expects list')
            return sorted(set(xs[0])|{xs[1]})
        if op=='set-remove':
            require(isinstance(xs[0],list),'set-remove expects list')
            return sorted(set(xs[0])-{xs[1]})
    except (TypeError,ValueError,ZeroDivisionError,OverflowError) as ex:
        raise Blocked(f'undefined expression {op}: {ex}') from ex
    raise Blocked('unsupported operator '+op)

def used_refs(expr, definitions, result=None, stack=()):
    result=result if result is not None else set()
    if 'ref' in expr:
        if not expr['ref'].startswith('param.'):result.add(expr['ref'])
    elif 'op' in expr:
        for a in expr['args']:used_refs(a,definitions,result,stack)
        if expr['op']=='call':
            n=expr['name'];require(n not in stack,'recursive definition')
            used_refs(definitions[n]['body'],definitions,result,stack+(n,))
    return result

def load(process_path,pi_path,tce_path,domain_path=None,allow_draft=False):
    pf,p=read_artifact(process_path,'process',allow_draft)
    pif,pi=read_artifact(pi_path,'pi',allow_draft)
    tf,tce=read_artifact(tce_path,'tce',allow_draft)
    dfile,domain=(read_artifact(domain_path,'domain-rule',allow_draft) if domain_path else (None,None))
    files=[(process_path,pf),(pi_path,pif),(tce_path,tf)]
    if dfile:files.append((domain_path,dfile))
    contracts={fm.get('semantic_contract') for _,fm in files}
    require(len(contracts)==1,'all compiled CAT artifacts must use the same semantic_contract')
    contract=next(iter(contracts))
    require(len({a['process'] for a in (p,pi,tce,*([domain] if domain else []))})==1,'different Process IDs in artifacts')
    require(pf['id'] in pif['refs'] and pif['id'] in tf['refs'],'missing Process→PI→TCE references')
    if domain:require(dfile['id'] in tf['refs'],'DomainRule artifact not referenced by TCE')

    process_optional=['interfaces','state_fields','observations','actions'] if contract=='markdown-v2' else []
    check_keys(p,['schema','kind','process','triggers','closed_world'],process_optional,where='Process')
    require(p['closed_world'] is True,'Process must declare explicit closed-world contract')
    require(isinstance(p['triggers'],list) and p['triggers'],'Process triggers required')
    for t in p['triggers']:
        check_keys(t,['id','origin'],where='Trigger');semantic_ident(t['id'],'Trigger');require(isinstance(t['origin'],str) and t['origin'],'Trigger origin required')
    unique([t['id'] for t in p['triggers']],'Triggers')

    if contract=='markdown-v2':
        require(pif['id'] in p.get('interfaces',[]),'Process Interfaces/境界 must reference loaded PI artifact')
        require(len(p.get('interfaces',[]))==len(set(p.get('interfaces',[]))),'duplicate Process Interface reference')
        check_keys(pi,['schema','kind','process','boundary','fields','operations'],['constraints'],where='PI')
        check_keys(pi['boundary'],['peer','direction'],where='PI boundary')
        require(ID.fullmatch(pi['boundary']['peer']) is not None,'PI peer process must use stable Process ID')
        require(pi['boundary']['direction'] in ('receive','send','bidirectional'),'PI boundary direction invalid')
        require(isinstance(pi['operations'],list),'PI operations must be array')
        for op in pi['operations']:
            check_keys(op,['id','direction','trigger'],where='PI operation')
            semantic_ident(op['id'],'PI operation ID')
            require(op['direction'] in ('accept','provide'),'PI operation direction invalid')
            if op['direction']=='accept':
                require(op['trigger'] in {t['id'] for t in p['triggers']},'accepted PI operation must reference declared Process trigger')
            elif op['trigger'] is not None:
                require(op['trigger'] in {t['id'] for t in p['triggers']},'PI operation trigger undeclared')
    else:
        check_keys(pi,['schema','kind','process','fields'],['constraints'],where='PI')

    require(isinstance(pi['fields'],list) and pi['fields'],'PI fields required')
    fields={}
    for field in pi['fields']:
        if contract=='markdown-v2':
            check_keys(field,['id','role','direction','presence','domain'],where='PI field')
            require(field['role'] in ('input','output'),'markdown-v2 PI field role must be boundary input/output')
            require(field['direction'] in ('receive','send'),'PI field direction invalid')
            require(field['presence'] in ('required','optional','absent','undefined'),'PI field presence invalid')
            require(field['presence']=='required','deterministic compiler currently supports required PI presence only; preserve other presence in CAT review instead of shrinking it')
            semantic_ident(field['id'],'PI field')
        else:
            check_keys(field,['id','role','domain'],where='PI field')
            ident(field['id'],'PI field');require(field['role'] in ('input','state','output'),'PI field role invalid')
            require(field['id'].startswith(field['role']+'.'),'markdown-v1 PI field ID must start with role')
        require(field['id'] not in fields,'duplicate PI field')
        validate_domain(field['domain']);fields[field['id']]=field

    pi_fields=dict(fields)

    if contract=='markdown-v2':
        dirs={f['direction'] for f in pi['fields']}
        if pi['boundary']['direction']=='receive':
            require(dirs <= {'receive'},'receive-only PI boundary cannot contain send fields')
        elif pi['boundary']['direction']=='send':
            require(dirs <= {'send'},'send-only PI boundary cannot contain receive fields')

    if contract=='markdown-v2':
        for name,items,role,extra in (
            ('State',p.get('state_fields',[]),'state',()),
            ('Observation',p.get('observations',[]),'observation',('source',)),
            ('Action',p.get('actions',[]),'action',('target',))):
            require(isinstance(items,list),f'Process {name} must be array')
            for field in items:
                check_keys(field,['id','role','domain',*extra],where=f'Process {name}')
                require(field['role']==role,f'Process {name} role invalid')
                semantic_ident(field['id'],f'Process {name} ID')
                require(field['id'] not in fields,f'duplicate specification field {field["id"]}')
                validate_domain(field['domain']);fields[field['id']]=field

    constraints=pi.get('constraints',[])
    require(isinstance(constraints,list),'PI constraints must be array')
    definitions={}
    if domain:
        check_keys(domain,['schema','kind','process','definitions'],where='DomainRule')
        require(isinstance(domain['definitions'],list),'DomainRule definitions required')
        for d in domain['definitions']:
            check_keys(d,['id','params','body'],where='DomainRule definition')
            if contract=='markdown-v2':semantic_ident(d['id'],'DomainRule id',False)
            else:ident(d['id'],'DomainRule id')
            require(d['id'] not in definitions,'duplicate DomainRule')
            require(isinstance(d['params'],list),'DomainRule params array required')
            for param in d['params']:
                (semantic_ident(param,'DomainRule param',False) if contract=='markdown-v2' else ident(param,'DomainRule param'))
            unique(d['params'],'DomainRule params');definitions[d['id']]=d
        for d in definitions.values():inspect_expr(d['body'],fields,definitions,d['params'])
    for predicate in constraints:
        require(inspect_expr(predicate,pi_fields,definitions)=='boolean','PI constraint must be boolean')

    check_keys(tce,['schema','kind','process','coverage','rules'],where='TCE')
    require(tce['coverage'] in ('closed','partial'),'coverage requirement must be closed or partial')
    require(isinstance(tce['rules'],list) and tce['rules'],'TCE behaviors required')
    rules=[]
    for r in tce['rules']:
        check_keys(r,['id','trigger','when','allowed'],where='TCE behavior')
        (semantic_ident(r['id'],'TCE behavior id') if contract=='markdown-v2' else ident(r['id'],'TCE rule id'))
        require(r['trigger'] in {t['id'] for t in p['triggers']},'undeclared trigger '+str(r['trigger']))
        require(inspect_expr(r['when'],fields,definitions)=='boolean','TCE condition must be boolean')
        require(not any(fields[x]['role'] in ('output','action') for x in used_refs(r['when'],definitions)),'Condition reads non-observable output/action')
        require(isinstance(r['allowed'],list) and r['allowed'],'allowed results must be nonempty')
        outcomes=[]
        for outcome in r['allowed']:
            check_keys(outcome,['write'],where='TCE outcome');require(isinstance(outcome['write'],list),'write list required')
            targets=[]
            for e in outcome['write']:
                check_keys(e,['target','expr'],where='Effect')
                require(e['target'] in fields and fields[e['target']]['role'] in ('state','output','action'),'Effect target not declared/actuable '+str(e['target']))
                produced=inspect_expr(e['expr'],fields,definitions)
                expected=fields[e['target']]['domain']['type']
                require(produced==expected or (expected=='enum' and produced in ('string','boolean','integer')),
                        f'Effect {e["target"]}: type mismatch, {produced} -> {expected}')
                if expected=='enum':
                    expr=e['expr']
                    if 'literal' in expr:
                        require(in_domain(fields[e['target']]['domain'],expr['literal']),'enum literal not in Effect target domain')
                    elif 'ref' in expr and expr['ref'] in fields and fields[expr['ref']]['domain']['type']=='enum':
                        require(all(in_domain(fields[e['target']]['domain'],x) for x in fields[expr['ref']]['domain']['values']),'source enum not subset of effect enum')
                    else:
                        raise Blocked('effect enum range not proven; explicit enum mapping required')
                targets.append(e['target'])
            unique(targets,'Effect targets')
            frame=sorted(f for f in fields if fields[f]['role']=='state' and f not in targets)
            absent=sorted(f for f in fields if fields[f]['role'] in ('output','action') and f not in targets)
            outcomes.append({'write':outcome['write'],'unchanged':frame,'absent_outputs':absent})
        rules.append({'id':r['id'],'trigger':r['trigger'],'when':r['when'],'allowed':outcomes})
    unique([r['id'] for r in rules],'TCE behaviors')

    per_trigger={}; triggers=[t['id'] for t in p['triggers']]
    for trigger in triggers:
        rr=[r for r in rules if r['trigger']==trigger]
        relevant=set().union(*(used_refs(r['when'],definitions) for r in rr),*(used_refs(c,definitions) for c in constraints)) if rr or constraints else set()
        finite=all(fields[f]['domain']['type'] in ('enum','boolean') for f in relevant)
        if not finite:
            per_trigger[trigger]={'result':'unproven','reason':'guard reads non-finite-domain field','guard_refs':sorted(relevant)}
            continue
        domainvalues=[fields[f]['domain'].get('values',[False,True]) for f in sorted(relevant)]
        require(__import__('math').prod(len(x) for x in domainvalues)<=65536,'finite closure exceeds configured 65536 combinations')
        gaps=[];overlaps=[];unreachable=set(r['id'] for r in rr)
        for values in itertools.product(*domainvalues):
            env=dict(zip(sorted(relevant),values))
            if not all(eval_expr(c,env,definitions) for c in constraints):
                continue
            hit=[r['id'] for r in rr if eval_expr(r['when'],env,definitions)]
            if not hit:gaps.append(env)
            if len(hit)>1:overlaps.append({'state':env,'rules':hit})
            unreachable-=set(hit)
        require(not overlaps,'overlapping TCE behaviors: '+json.dumps(overlaps[:4],ensure_ascii=False))
        per_trigger[trigger]={'result':'proved' if not gaps else 'uncovered','guard_refs':sorted(relevant),
                              'uncovered':gaps[:64],'uncovered_count':len(gaps),'unreachable_rules':sorted(unreachable),
                              'excluded_by_pi_constraints':True if constraints else False}
        require(not unreachable,'unreachable TCE behavior(s): '+str(sorted(unreachable)))
    coverage_proved = all(x['result']=='proved' for x in per_trigger.values())
    if tce['coverage']=='closed' and not coverage_proved:
        require(allow_draft,
                'closed-world coverage requirement not proved: '+json.dumps(per_trigger,ensure_ascii=False)[:700])

    hashes={fm['kind']:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path,fm in files}
    authority={'markdown-v2':'cat-markdown/v2','markdown-v1':'cat-markdown/v1','machine-only':'cat-machine/v2'}[contract]
    normative_model = all(fm['status']=='confirmed' for _,fm in files) and (tce['coverage']!='closed' or coverage_proved)
    result={'schema':M,'process':p['process'],'status':('confirmed' if normative_model else 'draft'),
            'semantic_authority':authority,'language':tf.get('language','en') if contract=='markdown-v2' else 'en',
            'source_artifacts':[fm['id'] for _,fm in files],
            'source_sha256':hashes,'triggers':p['triggers'],'fields':list(fields.values()),'pi_constraints':constraints,
            'definitions':list(definitions.values()),'coverage_requirement':tce['coverage'],'coverage_checks':per_trigger,'rules':rules,
            'model_type':'symbolic-relation','limits':['finite-guard-closure-only','no-general-reachability-proof','no-process-composition']}
    # Compatibility alias for older downstream readers; it is a requirement, not verification evidence.
    result['coverage_claim']=tce['coverage']
    result['source_semantic_map']={
        'process':{
            'artifact':pf['id'],
            'triggers':[x['id'] for x in p['triggers']],
            'interfaces':list(p.get('interfaces',[])),
            'state':[x['id'] for x in p.get('state_fields',[])],
            'observations':[x['id'] for x in p.get('observations',[])],
            'actions':[x['id'] for x in p.get('actions',[])]},
        'pi':{
            'artifact':pif['id'],
            'fields':[x['id'] for x in pi['fields']],
            'operations':[x['id'] for x in pi.get('operations',[])],
            'constraint_count':len(constraints)},
        'tce':{
            'artifact':tf['id'],
            'rules':[x['id'] for x in rules],
            'outcome_count':sum(len(x['allowed']) for x in rules)},
        'domain_rule':{
            'artifact':dfile['id'] if dfile else None,
            'definitions':sorted(definitions)}}
    if contract=='markdown-v2':
        result['pi_boundary']=pi['boundary'];result['pi_operations']=pi['operations'];result['process_interfaces']=p.get('interfaces',[])
    if contract in ('markdown-v1','markdown-v2'):result['normalized_ir']='cat-machine/v2'
    return result

def match_rules(model, trigger, env):
    defs={d['id']:d for d in model['definitions']}
    matched=[r for r in model['rules'] if r['trigger']==trigger and eval_expr(r['when'],env,defs)]
    require(len(matched)==1,f'test vector has {len(matched)} matching TCE rules at {trigger}')
    return matched[0]

def expand_cases(model, vectors):
    check_keys(vectors,['schema','process','cases'],where='vectors')
    require(vectors['schema']=='cat-test-vectors/v2' and vectors['process']==model['process'],'vector version/Process mismatch')
    fields={f['id']:f for f in model['fields']}
    inputs={f for f in fields if fields[f]['role']=='input'}
    states={f for f in fields if fields[f]['role']=='state'}
    cases=[]
    for test in vectors['cases']:
        check_keys(test,['id','trigger','input','state'],where='test vector')
        ident(test['id'],'test ID');require(test['trigger'] in {t['id'] for t in model['triggers']},'unknown vector trigger')
        env={**test['input'],**test['state']}
        require(set(test['input'])==inputs and set(test['state'])==states,'vector must supply each declared input/state exactly once')
        for name,val in env.items():require(in_domain(fields[name]['domain'],val),f'{test["id"]}: {name} out of declared domain')
        defs={d['id']:d for d in model['definitions']}
        require(all(eval_expr(c,env,defs) for c in model['pi_constraints']),f'{test["id"]}: violates PI combination constraint')
        rule=match_rules(model,test['trigger'],env)
        defs={d['id']:d for d in model['definitions']}
        allowed=[]
        for out in rule['allowed']:
            after=deepcopy(test['state']); emitted={}
            for write in out['write']:
                target=write['target'];val=eval_expr(write['expr'],env,defs)
                require(in_domain(fields[target]['domain'],val),f'{test["id"]}: output {target} out of declared domain')
                if fields[target]['role']=='state':after[target]=val
                else:emitted[target]=val
            allowed.append({'state':after,'output':emitted,'unchanged':out['unchanged'],'absent_outputs':out['absent_outputs']})
        cases.append({'id':test['id'],'source_tce':rule['id'],'trigger':test['trigger'],
                      'input':test['input'],'initial_state':test['state'],'allowed':allowed})
    unique([t['id'] for t in cases],'vector IDs')
    return cases

def _vitest_renderer():
    import importlib.util
    path = ROOT / 'skills' / 'tech-vitest' / 'scripts' / 'cat_vitest_renderer.py'
    require(path.is_file(), 'Vitest generation requires installed tech-vitest Skill renderer')
    spec = importlib.util.spec_from_file_location('_cat_vitest_renderer', path)
    require(spec is not None and spec.loader is not None, 'cannot load tech-vitest renderer')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.render_vitest


def emit_vitest(model,vectors,binding_path):
    require(not any(f['role'] in ('observation','action') for f in model['fields']),
            'test-code generation for explicit observation/action capabilities requires a technology binding extension; TestModel remains valid')
    binding=json.loads(Path(binding_path).read_text(encoding='utf-8'))
    check_keys(binding,['schema','process','driver'],where='driver binding')
    require(binding['schema']==D and binding['process']==model['process'],'driver binding incompatible')
    require(isinstance(binding['driver'],str) and binding['driver'].startswith('./') and not '..' in Path(binding['driver']).parts,
            'driver must be an explicit local relative module')
    cases=expand_cases(model,vectors)
    return _vitest_renderer()(model,cases,binding)




def make_queue(model, vectors, model_bytes, vector_bytes):
    require(model.get('status') == 'confirmed', 'normative Queue requires confirmed TestModel')
    cases = expand_cases(model, vectors)
    require(cases, 'Queue requires at least one concrete vector')
    items = []
    for order, case in enumerate(cases, 1):
        items.append({'id': case['id'], 'model_ref': case['source_tce'], 'vector_ref': case['id'],
                      'order': order, 'status': 'current' if order == 1 else 'pending',
                      'evidence_ref': None})
    return {'schema': Q, 'process': model['process'],
            'model_sha256': hashlib.sha256(model_bytes).hexdigest(),
            'vectors_sha256': hashlib.sha256(vector_bytes).hexdigest(),
            'items': items}


def validate_queue(queue, model, vectors, model_bytes, vector_bytes):
    check_keys(queue, ['schema','process','model_sha256','vectors_sha256','items'], where='TDD Execution Queue')
    require(queue['schema'] == Q and queue['process'] == model['process'], 'Queue version/Process mismatch')
    require(queue['model_sha256'] == hashlib.sha256(model_bytes).hexdigest(), 'Queue is stale: TestModel changed')
    require(queue['vectors_sha256'] == hashlib.sha256(vector_bytes).hexdigest(), 'Queue is stale: vectors changed')
    require(isinstance(queue['items'], list), 'Queue items must be array')
    vector_ids = {x['id'] for x in vectors.get('cases', [])}
    model_rules = {x['id'] for x in model.get('rules', [])}
    seen = set(); current = []
    last_order = 0
    for item in queue['items']:
        check_keys(item, ['id','model_ref','vector_ref','order','status','evidence_ref'], where='Queue item')
        ident(item['id'], 'Queue item ID')
        require(item['id'] not in seen, 'duplicate Queue item ID'); seen.add(item['id'])
        require(item['vector_ref'] in vector_ids, 'Queue item references unknown vector')
        require(item['model_ref'] in model_rules, 'Queue item references unknown TestModel rule')
        require(isinstance(item['order'], int) and item['order'] > last_order, 'Queue order must be strictly increasing')
        last_order = item['order']
        require(item['status'] in ('pending','current','done','blocked'), 'Queue status invalid')
        require(item['evidence_ref'] is None or isinstance(item['evidence_ref'], str), 'Queue evidence_ref invalid')
        if item['status'] == 'current': current.append(item)
    require(len(current) <= 1, 'Queue may contain at most one current item')
    return current[0] if current else None


def current_vectors(model, vectors, queue, model_bytes, vector_bytes):
    current = validate_queue(queue, model, vectors, model_bytes, vector_bytes)
    require(current is not None, 'Queue has no current item')
    chosen = [x for x in vectors['cases'] if x['id'] == current['vector_ref']]
    require(len(chosen) == 1, 'current Queue vector must resolve exactly once')
    probe = expand_cases(model, {'schema': vectors['schema'], 'process': vectors['process'], 'cases': chosen})[0]
    require(probe['source_tce'] == current['model_ref'], 'Queue model_ref does not match vector-derived TestModel rule')
    return {'schema': vectors['schema'], 'process': vectors['process'], 'cases': chosen}

def format_domain(d, language='en'):
    t=d['type']
    names={'ja':{'boolean':'真偽','integer':'整数','string':'文字列','set':'集合','sequence':'列','enum':'列挙'},
           'en':{'boolean':'boolean','integer':'integer','string':'string','set':'set','sequence':'sequence','enum':'enum'}}[language]
    if t=='boolean':return names['boolean']
    if t=='integer':
        if d.get('min') is None and d.get('max') is None:return names['integer']
        return f"{names['integer']}[{'' if d.get('min') is None else d['min']}..{'' if d.get('max') is None else d['max']}]"
    if t=='string':
        if d.get('format','any')=='any':return names['string']
        fmt='安全符号付き整数' if language=='ja' and d['format']=='safe-signed-integer' else d['format']
        return names['string']+'<'+fmt+'>'
    if t in ('set','sequence'):
        element={'string':names['string'],'integer':names['integer']}[d['element']]
        return f"{names[t]}<{element}>"
    if t=='enum':return names['enum']+'{' + ', '.join(_format_literal(v,language) for v in d['values']) + '}'
    raise Blocked('unknown domain for rendering')


def _format_literal(v, language='en'):
    if v is True:return '真' if language=='ja' else 'true'
    if v is False:return '偽' if language=='ja' else 'false'
    if v is None:return 'なし' if language=='ja' else 'null'
    if isinstance(v,str):return json.dumps(v,ensure_ascii=False)
    if isinstance(v,list):return '['+', '.join(_format_literal(x,language) for x in v)+']'
    return str(v)


def format_expr(expr, params=(), language='en'):
    if 'literal' in expr:return _format_literal(expr['literal'],language)
    if 'ref' in expr:
        ref=expr['ref']
        return ref[6:] if ref.startswith('param.') and ref[6:] in params else ref
    op=expr['op'];args=[format_expr(x,params,language) for x in expr['args']]
    symbols={'eq':'==','ne':'!=','lt':'<','le':'<=','gt':'>','ge':'>=','add':'+','sub':'-','mul':'*','div':'/'}
    if op in symbols:return '('+(' '+symbols[op]+' ').join(args)+')'
    if op in ('and','or'):
        word={'and':('かつ' if language=='ja' else 'and'),'or':('または' if language=='ja' else 'or')}[op]
        return '('+(' '+word+' ').join(args)+')'
    if op=='not':return ('否定('+args[0]+')') if language=='ja' else '(not '+args[0]+')'
    funcs_en={'floor':'floor','abs':'abs','length':'length','concat':'concat','to-int':'to_int','set-add':'set_add','set-remove':'set_remove'}
    funcs_ja={'floor':'floor','abs':'abs','length':'長さ','concat':'連結','to-int':'整数化','set-add':'集合追加','set-remove':'集合削除'}
    if op=='call':return expr['name']+'('+', '.join(args)+')'
    funcs=funcs_ja if language=='ja' else funcs_en
    if op in funcs:return funcs[op]+'('+', '.join(args)+')'
    raise Blocked('unknown expression for rendering '+op)


def _md(value):
    return str(value).replace('|','\\|').replace('\n','<br>')


def render_model_markdown(model):
    lang=model.get('language','en')
    ja=lang=='ja'
    title='テストモデル' if ja else 'Test Model'
    lines=['---',f"schema: {model['schema']}",f"process: {model['process']}",f"status: {model['status']}",
           f"semantic_authority: {model['semantic_authority']}",f"language: {lang}",*( [f"normalized_ir: {model['normalized_ir']}"] if model.get('normalized_ir') else []),'---','',f"# {title}: {model['process']}",'']
    h_source=('出典Artifact','Artifact ID','種別','SHA-256') if ja else ('Source artifacts','Artifact ID','Kind','SHA-256')
    lines += [f'## {h_source[0]}','',f'| {h_source[1]} | {h_source[2]} | {h_source[3]} |','| --- | --- | --- |']
    for aid,(kind,digest) in zip(model['source_artifacts'], model['source_sha256'].items()):lines.append(f'| {_md(aid)} | {_md(kind)} | `{digest}` |')
    if model.get('process_interfaces') is not None:
        lines += ['',('## Process境界' if ja else '## Process interfaces'),'', '| PI |','| --- |']
        for ref in model.get('process_interfaces',[]): lines.append(f"| {_md(ref)} |")
    if model.get('pi_boundary'):
        lines += ['',('## PI境界' if ja else '## PI boundary'),'',('| 相手Process | 方向 |' if ja else '| Peer process | Direction |'),'| --- | --- |',
                  f"| {_md(model['pi_boundary']['peer'])} | {_md({'receive':'受信','send':'送信','bidirectional':'双方向'}.get(model['pi_boundary']['direction'],model['pi_boundary']['direction']) if ja else model['pi_boundary']['direction'])} |"]
    if model.get('pi_operations') is not None:
        lines += ['',('## PI操作' if ja else '## PI operations'),'',('| ID | 方向 | 起点 |' if ja else '| ID | Direction | Trigger |'),'| --- | --- | --- |']
        direction_ja={'accept':'受付','provide':'提供'}
        for op in model.get('pi_operations',[]):
            direction=direction_ja.get(op['direction'],op['direction']) if ja else op['direction']
            lines.append(f"| {_md(op['id'])} | {_md(direction)} | {_md(op.get('trigger') or '—')} |")
    lines += ['',('## 起点' if ja else '## Triggers'),'',('| ID | 由来 |' if ja else '| ID | Origin |'),'| --- | --- |']
    for t in model['triggers']:lines.append(f"| {_md(t['id'])} | {_md(t['origin'])} |")
    lines += ['',('## 仕様要素' if ja else '## Fields'),'',('| ID | 役割 | Domain |' if ja else '| ID | Role | Domain |'),'| --- | --- | --- |']
    role_ja={'input':'受信','output':'送信','state':'状態','observation':'観測','action':'作用'}
    for f in model['fields']:lines.append(f"| {_md(f['id'])} | {_md(role_ja.get(f['role'],f['role']) if ja else f['role'])} | `{_md(format_domain(f['domain'],lang))}` |")
    if model['pi_constraints']:
        lines += ['',('## PI制約' if ja else '## PI constraints'),'',('| 式 |' if ja else '| Expression |'),'| --- |']
        for c in model['pi_constraints']:lines.append(f'| `{_md(format_expr(c,language=lang))}` |')
    if model['definitions']:
        lines += ['',('## DomainRule定義' if ja else '## DomainRule definitions'),'',('| ID | 引数 | 式 |' if ja else '| ID | Parameters | Expression |'),'| --- | --- | --- |']
        for d in model['definitions']:lines.append(f"| {_md(d['id'])} | {_md(', '.join(d['params']) or '—')} | `{_md(format_expr(d['body'],d['params'],lang))}` |")
    lines += ['',('## 網羅要求' if ja else '## Coverage requirement'),'','`'+model.get('coverage_requirement',model.get('coverage_claim','partial'))+'`']
    lines += ['',('## 規則' if ja else '## Rules'),'',('| ID | 起点 | 条件 |' if ja else '| ID | Trigger | Condition |'),'| --- | --- | --- |']
    for r in model['rules']:lines.append(f"| {_md(r['id'])} | {_md(r['trigger'])} | `{_md(format_expr(r['when'],language=lang))}` |")
    lines += ['',('## 効果' if ja else '## Effects'),'',('| 規則 | 結果 | 対象 | 式 |' if ja else '| Rule | Outcome | Target | Expression |'),'| --- | ---: | --- | --- |']
    for r in model['rules']:
        for n,out in enumerate(r['allowed'],1):
            if out['write']:
                for w in out['write']:lines.append(f"| {_md(r['id'])} | {n} | {_md(w['target'])} | `{_md(format_expr(w['expr'],language=lang))}` |")
            else:lines.append(f"| {_md(r['id'])} | {n} | — | — |")
    lines += ['',('## 導出された不変条件' if ja else '## Derived frame conditions'),'',('| 規則 | 結果 | 不変状態 | 不在の出力・作用 |' if ja else '| Rule | Outcome | Unchanged state | Absent outputs/actions |'),'| --- | ---: | --- | --- |']
    for r in model['rules']:
        for n,out in enumerate(r['allowed'],1):lines.append(f"| {_md(r['id'])} | {n} | {_md(', '.join(out['unchanged']) or '—')} | {_md(', '.join(out['absent_outputs']) or '—')} |")
    lines += ['',('## 網羅検証' if ja else '## Coverage verification'),'',('| 起点 | 結果 | 参照 | 未被覆数 | 到達不能規則 | 注記 |' if ja else '| Trigger | Result | Guard refs | Uncovered count | Unreachable rules | Note |'),'| --- | --- | --- | ---: | --- | --- |']
    result_ja={'proved':'証明済み','uncovered':'未被覆','unproven':'未証明'}
    for trigger,c in model['coverage_checks'].items():
        result=result_ja.get(c['result'],c['result']) if ja else c['result']
        lines.append(f"| {_md(trigger)} | {_md(result)} | {_md(', '.join(c.get('guard_refs',[])) or '—')} | {c.get('uncovered_count','—')} | {_md(', '.join(c.get('unreachable_rules',[])) or '—')} | {_md(c.get('reason',''))} |")
    examples=[]
    for trigger,c in model['coverage_checks'].items():
        for env in c.get('uncovered',[]):examples.append((trigger,'; '.join(f'{k} = {_format_literal(v,lang)}' for k,v in env.items())))
    if examples:
        lines += ['',('### 未被覆例' if ja else '### Uncovered examples'),'',('| 起点 | 状態 |' if ja else '| Trigger | State |'),'| --- | --- |']
        for trigger,state in examples:lines.append(f'| {_md(trigger)} | `{_md(state)}` |')
    lines += ['',('## 制限' if ja else '## Limits'),'']+[f'- `{x}`' for x in model['limits']]
    return '\n'.join(lines)+'\n'

def _model_content(model, output_path):
    return render_model_markdown(model) if Path(output_path).suffix.lower()=='.md' else json.dumps(model,sort_keys=True,ensure_ascii=False,indent=2)+'\n'

def write(path,content,check):
    p=Path(path);require(not check or (p.exists() and p.read_bytes()==content.encode()),f'{p}: output differs or missing')
    if not check:p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content,encoding='utf-8',newline='\n')

def main(argv=None):
    cli=argparse.ArgumentParser(description=__doc__)
    sub=cli.add_subparsers(dest='command',required=True)
    m=sub.add_parser('model');m.add_argument('process');m.add_argument('pi');m.add_argument('tce');m.add_argument('--domain-rule');m.add_argument('--allow-draft',action='store_true');m.add_argument('--check',action='store_true');m.add_argument('-o','--output',required=True)
    q=sub.add_parser('queue');q.add_argument('model');q.add_argument('vectors');q.add_argument('--process',required=True);q.add_argument('--pi',required=True);q.add_argument('--tce',required=True);q.add_argument('--domain-rule');q.add_argument('--allow-draft',action='store_true');q.add_argument('--check',action='store_true');q.add_argument('-o','--output',required=True)
    t=sub.add_parser('tests');t.add_argument('model');t.add_argument('vectors');t.add_argument('binding');t.add_argument('--queue');t.add_argument('--process',required=True);t.add_argument('--pi',required=True);t.add_argument('--tce',required=True);t.add_argument('--domain-rule');t.add_argument('--allow-draft',action='store_true');t.add_argument('--check',action='store_true');t.add_argument('-o','--output',required=True)
    args=cli.parse_args(argv)
    try:
        if args.command=='model':
            result=load(args.process,args.pi,args.tce,args.domain_rule,args.allow_draft)
            write(args.output,_model_content(result,args.output),args.check)
        else:
            fresh=load(args.process,args.pi,args.tce,args.domain_rule,args.allow_draft)
            model_bytes=Path(args.model).read_bytes()
            if Path(args.model).suffix.lower()=='.md':
                require(model_bytes.decode('utf-8')==render_model_markdown(fresh),
                        'test model does not match current CAT source: regenerate')
                model=fresh
            else:
                model=json.loads(model_bytes.decode('utf-8'))
                require(model.get('schema')==M,'wrong model schema')
                require(model.get('status')=='confirmed' or args.allow_draft,'draft model requires --allow-draft')
                require(model.get('semantic_authority') in (S,'cat-markdown/v1','cat-markdown/v2'),'missing CAT semantic authority')
                require(model==fresh,'test model does not match current CAT source: regenerate')
            vector_bytes=Path(args.vectors).read_bytes()
            vectors=json.loads(vector_bytes.decode('utf-8'))
            if args.command=='queue':
                result=make_queue(model,vectors,model_bytes,vector_bytes)
                write(args.output,json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2)+'\n',args.check)
            else:
                if args.queue:
                    queue=json.loads(Path(args.queue).read_text(encoding='utf-8'))
                    vectors=current_vectors(model,vectors,queue,model_bytes,vector_bytes)
                else:
                    require(args.allow_draft, 'normative test generation requires --queue with exactly one current item')
                write(args.output,emit_vitest(model,vectors,args.binding),args.check)
        return 0
    except (Blocked,TypeError,KeyError,ValueError,FileNotFoundError) as e:
        print('BLOCKED: '+str(e),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
