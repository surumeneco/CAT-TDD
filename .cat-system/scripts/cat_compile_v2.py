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
from catlib import semantic_types as typed
from catlib import semantic_json_instant as json_time
from catlib import semantic_rules
from catlib import semantic_intrinsic_rules
from catlib import semantic_named_types as named_types
from catlib import semantic_subtyping
from catlib import semantic_collection_relation as collection_relation
from catlib import semantic_interval_partition
from catlib import semantic_string_partition
from catlib import decimal_integer
from catlib import peer_binding

ROOT = Path(__file__).resolve().parent.parent

S = 'cat-machine/v2'
M = 'cat-test-model/v2'
D = 'cat-test-driver/v2'
Q = 'cat-tdd-queue/v1'
V = 'cat-test-vectors/v2'
ID = re.compile(r'^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$')
CODE = re.compile(r'(?ms)^```cat-machine\s*\n(.*?)\n```\s*$')
INT = re.compile(r'^[+-]?(?:0|[1-9][0-9]*)$')
SAFE_INT = 9007199254740991
OPS = {'eq','ne','lt','le','gt','ge','and','or','not','add','sub','mul',
       'div','floor','abs','length','concat','to-int','set-add','set-remove','sequence-append','sequence-swap','sequence-replace-member','record-value','call',
       'is-missing','is-undefined','is-present','member','filter-by','stable-sort-by'}

_PRESENT_GUARD_VALUE=object()

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
    for i,line in enumerate(lines[2:],2):
        cells=_split_md_row(line)
        require(len(cells)==len(header),f'## {label}: row width differs from header')
        if cells==header:
            require(i+1<len(lines) and all(re.fullmatch(r':?-{3,}:?',x.strip()) for x in _split_md_row(lines[i+1])),
                    f'## {label}: repeated header without separator')
            continue
        if all(re.fullmatch(r':?-{3,}:?',x.strip()) for x in cells):
            require(_split_md_row(lines[i-1])==header,f'## {label}: stray separator')
            continue
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
    require(all(all(part.isidentifier() for part in x.split('-')) for x in parts), f'{where}: invalid Unicode identifier {s!r}')
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
    if INT.fullmatch(token):return decimal_integer.parse(token)
    require(bool(token),'empty enum value')
    return token


def parse_domain_text(text):
    text=_unquote_code(text).strip()
    # Recursive enum parsing must precede legacy substitutions, which would
    # corrupt quoted enum values such as "整数".
    if any(marker in text for marker in ('enum{','列挙{','型参照<','ref<','Ref<')):
        try:return typed.parse(text)
        except typed.DomainError as exc:raise Blocked(str(exc)) from exc
    aliases={'真偽':'boolean','整数':'integer','文字列':'string','安全符号付き整数':'safe-signed-integer'}
    for ja,en in aliases.items():text=text.replace(ja,en)
    text=text.replace('集合<','set<').replace('列<','sequence<').replace('列挙{','enum{')
    if text=='boolean':return {'type':'boolean'}
    if text=='integer':return {'type':'integer'}
    m=re.fullmatch(r'integer\[\s*([+-]?\d*)\s*\.\.\s*([+-]?\d*)\s*\]',text)
    if m:
        d={'type':'integer'}
        if m.group(1):d['min']=decimal_integer.parse(m.group(1))
        if m.group(2):d['max']=decimal_integer.parse(m.group(2))
        return d
    if text=='string':return {'type':'string'}
    if text=='string<safe-signed-integer>':return {'type':'string','format':'safe-signed-integer'}
    # Scalar collection elements must be structured Domain nodes too;
    # the recursive parser below owns sets/sequences of every supported type.
    m=re.fullmatch(r'enum\{(.*)\}',text)
    if m:return {'type':'enum','values':[_scalar_token(x) for x in _split_items(m.group(1))]}
    try:return typed.parse(text)
    except typed.DomainError as exc:raise Blocked(str(exc)) from exc


def _normalize_expr_language(text):
    """Translate language aliases token-wise without modifying quoted strings."""
    aliases={'真':'True','偽':'False','なし':'None','かつ':'and','または':'or',
             '長さ':'length','整数化':'to_int','連結':'concat','集合追加':'set_add','集合削除':'set_remove','列追加':'sequence_append','列交換':'sequence_swap','列項目更新':'sequence_replace_member','否定':'not_fn'}
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
             'concat':'concat','set_add':'set-add','set_remove':'set-remove','sequence_append':'sequence-append','sequence_swap':'sequence-swap','sequence_replace_member':'sequence-replace-member','not_fn':'not',
             'is_missing':'is-missing','is_undefined':'is-undefined','is_present':'is-present',
             'filter_by':'filter-by','stable_sort_by':'stable-sort-by'}
    compare={ast.Eq:'eq',ast.NotEq:'ne',ast.Lt:'lt',ast.LtE:'le',ast.Gt:'gt',ast.GtE:'ge'}
    binary={ast.Add:'add',ast.Sub:'sub',ast.Mult:'mul',ast.Div:'div'}
    def cv(n):
        if isinstance(n,ast.Constant):
            require(type(n.value) in (str,int,float,bool,type(None)),'unsupported literal in CAT expression')
            return {'literal':n.value}
        if isinstance(n,ast.List):
            vals=[]
            for e in n.elts:
                x=cv(e);require(set(x)=={'literal'} and type(x['literal']) in (str,int,bool),'list literals must contain scalar literals')
                vals.append(x['literal'])
            return {'literal':vals}
        if isinstance(n,ast.Dict):
            args=[];keys=set()
            for k,v in zip(n.keys,n.values):
                require(isinstance(k,ast.Constant) and type(k.value) is str and k.value not in keys,'record-value keys must be distinct string literals')
                keys.add(k.value);args.extend(({'literal':k.value},cv(v)))
            return {'op':'record-value','args':args}
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
            require(isinstance(n.operand,ast.Constant) and type(n.operand.value) in (int,float),'unary +/- requires numeric literal')
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
            # Optional exact Trigger binding. Missing column preserves legacy
            # unqualified observations; no temporal ordering is inferred from
            # source prose, names, or a technology-specific clock.
            availability=_cell(row,'Available on','利用可能Trigger',required=False)
            triggers_available=([semantic_ident(item,'Observation availability Trigger')
                                 for item in _split_items(availability)]
                                if availability not in ('','-','—','none','なし') else None)
            observations.append({'id':semantic_ident(_cell(row,'ID','Id','id'),'Observation ID'),'role':'observation',
                                 'source':_cell(row,'Source','Origin','source','由来','情報源'),
                                 'domain':parse_domain_text(_cell(row,'Domain','domain')),
                                 **({'available_on':triggers_available} if triggers_available is not None else {})})
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
        require(bool(boundary_rows),'PI Boundary/境界 requires at least one row')
        br=boundary_rows[0]
        peer=peer_binding.normalize_peer(_cell(br,'Peer process','Peer Process','peer','相手Process','相手プロセス'))
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
            operation_peer=peer_binding.normalize_peer(_cell(row,'Peer process','Peer Process','peer','相手Process','相手プロセス',required=False))
            operations.append({'id':semantic_ident(_cell(row,'ID','Id','id'),'PI operation ID'),'direction':odir,
                               'trigger':None if trig in ('','-','—','none','なし') else trig,
                               **({'peer':operation_peer} if operation_peer not in ('','-','—','none','なし') else {})})
        operation_presence=[]
        for row in _table_any(body,('Operation presence','操作別存在'),required=False):
            operation_presence.append({
                'operation':semantic_ident(_cell(row,'Operation','操作'),'Operation presence operation'),
                'field':semantic_ident(_cell(row,'Field','項目'),'Operation presence field'),
                'presence':_canon(_cell(row,'Presence','存在'),
                                  {'required':{'必須'},'optional':{'任意'},'absent':{'不在'},
                                   'undefined':{'未定義'}},'Operation presence state')})
        frame_rows=_section_any(body,'Output frames','提供出力フレーム')
        output_frames=[]
        if frame_rows is not None:
            for row in _table_any(body,('Output frames','提供出力フレーム')):
                number=_cell(row,'Outcome','結果')
                require(number.isdigit() and int(number)>0,'Output frame Outcome must be positive integer')
                operation=_cell(row,'Operation','操作')
                output_frames.append({'trigger':semantic_ident(_cell(row,'Trigger','起点'),'Output frame Trigger'),
                    'rule':semantic_ident(_cell(row,'Behavior','振る舞い'),'Output frame Behavior'),
                    'outcome':int(number),'operation':None if operation=='—' else semantic_ident(operation,'Output frame Operation'),
                    'mode':_canon(_cell(row,'Mode','活性'),{'one':{'必ず一つ'},'zero-or-one':{'零または一つ'},'none':{'非活性'}},'Output frame mode')})
            require(output_frames,'explicit Output frames section must not be empty')
        constraints=[]
        for row in _table_any(body,('Constraints','制約'),required=False):
            constraints.append(parse_expr_text(_cell(row,'Expression','Condition','expression','condition','式','条件')))
        extra_peers=[peer_binding.normalize_peer(_cell(row,'Peer process','Peer Process','peer','相手Process','相手プロセス')) for row in boundary_rows]
        for row in boundary_rows:
            require(_canon(_cell(row,'Direction','direction','方向'),
                           {'receive':{'受信'},'send':{'送信'},'bidirectional':{'双方向'}},'PI boundary direction') == direction,
                    'PI boundary mixed direction requires explicit per-peer operation semantics')
        return {'schema':S,'kind':kind,'process':process,'boundary':{'peer':peer,'direction':direction,**({'peers':extra_peers} if len(extra_peers)>1 else {})},
                'fields':fields,'operations':operations,'operation_presence':operation_presence,
                **({'output_frames':output_frames} if frame_rows is not None else {}),'constraints':constraints}
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
    require(fm.get('status')=='confirmed' or (allow_draft and fm.get('status') in ('draft','candidate')),
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
                'interfaces','state_fields','observations','actions','boundary','operations','operation_presence','output_frames'],str(path))
    require(spec['schema']==S and spec['kind']==kind and spec['process']==fm.get('process'),
            f'{path}: frontmatter/semantic body mismatch')
    ident(fm.get('id'),'artifact id'); ident(spec['process'],'process id')
    return fm,spec

def validate_domain(d):
    t=d.get('type')
    if t not in {'enum','boolean','integer','string','set','sequence'} or (t in ('set','sequence') and isinstance(d.get('element'),dict)):
        try:return typed.validate(d)
        except typed.DomainError as exc:raise Blocked(str(exc)) from exc
    check_keys(d,['type'],['values','min','max','format','element'],'domain')
    if t=='enum':
        check_keys(d,['type','values'],where='enum domain')
        require(isinstance(d['values'],list) and bool(d['values']), 'enum nonempty values required')
        require(all(isinstance(v,(str,int,bool)) for v in d['values']), 'enum only str/int/bool')
        require(len({decimal_integer.dumps(x,sort_keys=True) for x in d['values']})==len(d['values']), 'enum duplicate')
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
    return typed.same(a,b)

def in_domain(d, value):
    t=d['type']
    if t=='enum':return any(type(v)==type(value) and v==value for v in d['values'])
    if t=='boolean':return type(value) is bool
    if t=='integer':return type(value) is int and (d.get('min') is None or value>=d['min']) and (d.get('max') is None or value<=d['max'])
    if t=='string':return isinstance(value,str) and (d.get('format','any')=='any' or safe_integer_text(value))
    if t in ('set','sequence') and isinstance(d.get('element'),str):
        # Legacy machine-only format used a scalar element type name. Current
        # recursive typed IR stores a Domain node instead; never treat its
        # dictionary as a signal that collection elements must be integers.
        return isinstance(value,list) and all(type(v) is (str if d['element']=='string' else int) for v in value) and (t!='set' or len(set(value))==len(value))
    try:return typed.contains(d,value)
    except typed.DomainError as exc:raise Blocked(str(exc)) from exc

def literal_type(v):
    if type(v) is bool:return 'boolean'
    if type(v) is int:return 'integer'
    if type(v) is float:return 'real'
    if type(v) is dict:return 'record'
    if isinstance(v,str):return 'string'
    if isinstance(v,list):return 'sequence'
    return 'null'

def _record_shape(domain):
    while domain.get('type')=='reference' and domain.get('resolved'):
        domain=domain['of']
    return domain if domain.get('type')=='record' and domain.get('resolved') else None


def _member_domain(expr,fields):
    if expr.get('op')!='member':return None
    args=expr.get('args',[])
    require(set(expr)=={'op','args'} and len(args)==2 and set(args[0])=={'ref'}
            and set(args[1])=={'literal'} and isinstance(args[1]['literal'],str),'invalid member projection')
    parent=fields.get(args[0]['ref'])
    require(parent and parent['role']=='input' and parent.get('presence','required')=='required',
            'member projection requires declared required PI input record')
    record=_record_shape(parent['domain'])
    require(record is not None,'member projection requires resolved record')
    member=next((f for f in record['fields'] if f['id']==args[1]['literal']),None)
    require(member and member['presence']=='required','member projection requires declared required member')
    domain=member['domain']
    while domain.get('type')=='reference' and domain.get('resolved'):domain=domain['of']
    require(domain.get('type') in ('boolean','integer','real','string','enum'),
            'member projection supports only nonnullable scalar Domain')
    return domain


def _bind_member_refs(expr,fields):
    # Existing exact field IDs have precedence. A projection is one member
    # level, explicitly bound to the parent field, not another wire field.
    if set(expr)=={'ref'} and expr['ref'] not in fields and not expr['ref'].startswith('param.'):
        parent,sep,member=expr['ref'].rpartition('.')
        if sep and parent in fields and _record_shape(fields[parent]['domain']) is not None:
            bound={'op':'member','args':[{'ref':parent},{'literal':member}]}
            _member_domain(bound,fields)
            expr.clear();expr.update(bound);return
    for arg in expr.get('args',[]):_bind_member_refs(arg,fields)


def _member_parents(expr):
    if expr.get('op')=='member':return {expr['args'][0]['ref']}
    return set().union(*(_member_parents(a) for a in expr.get('args',[]))) if expr.get('args') else set()


def _comparison_value_refs(expr, definitions):
    # A validated scalar member reads its own Domain, not the parent record's
    # sibling values. Keep used_refs unchanged for provenance and ownership.
    if expr.get('op')=='member':return set()
    if 'ref' in expr or expr.get('op')=='call':return used_refs(expr,definitions)
    return set().union(*(_comparison_value_refs(a,definitions) for a in expr.get('args',[])))


def inspect_expr(expr, fields, definitions, params=(), stack=()):
    """Conservative AST type checker; unsupported conversions fail, never coerce."""
    require(isinstance(expr,dict),'expression must be AST object')
    if 'literal' in expr:
        check_keys(expr,['literal'],where='literal expression')
        require(type(expr['literal']) in (str,int,float,bool,list,dict,type(None)), 'unsupported literal type')
        return literal_type(expr['literal'])
    if 'ref' in expr:
        check_keys(expr,['ref'],where='reference expression')
        ref=expr['ref']; require(isinstance(ref,str),'reference string required')
        if ref.startswith('param.'):
            key=ref[6:]
            require(key in params, 'unbound function parameter '+ref)
            return params[key] if isinstance(params,dict) else 'parameter'
        require(ref in fields and fields[ref]['role'] in ('input','state','observation','output'), 'unknown or non-readable ref '+ref)
        return fields[ref]['domain']['type']
    check_keys(expr,['op','args'],['name'],where='operator expression')
    op=expr['op']; require(op in OPS,'unsupported operator '+str(op))
    args=expr['args']; require(isinstance(args,list),'operator args must be array')
    if op=='member':return _member_domain(expr,fields)['type']
    if op in collection_relation.OPERATORS:
        result=collection_relation.operator_domain(expr,fields)
        require(result is not None,'unsupported or ill-typed collection relation')
        return result['type']
    if op=='record-value':
        require(len(args)%2==0 and all(set(x)=={'literal'} and type(x['literal']) is str for x in args[::2]),'record-value keys must be string literals')
        require(len({x['literal'] for x in args[::2]})==len(args)//2,'duplicate record-value key')
        for a in args[1::2]:inspect_expr(a,fields,definitions,params,stack)
        return 'record'
    if op in ('is-missing','is-undefined','is-present'):
        require(len(args)==1 and isinstance(args[0],dict) and set(args[0])=={'ref'},
                op+' requires exactly one direct PI field reference')
        ref=args[0]['ref']
        require(ref in fields and fields[ref]['role']=='input',
                op+' is only defined for declared PI input fields')
        return 'boolean'
    if op=='call':
        check_keys(expr,['op','name','args'],where='domain-rule invocation')
        name=expr['name']; require(name in definitions,'unknown DomainRule '+str(name))
        require(not any(ref in fields and typed.has_semantic_domain(fields[ref]['domain'])
                        for ref in used_refs(expr,definitions)),
                'typed JSON/instant expression requires explicit domain binding')
        require(name not in stack,'recursive DomainRule invocation '+str(name))
        defi=definitions[name];require(len(args)==len(defi['params']), 'DomainRule arity mismatch '+name)
        types=[inspect_expr(a,fields,definitions,params,stack) for a in args]
        return inspect_expr(defi['body'],fields,definitions,dict(zip(defi['params'],types)),stack+(name,))
    check_keys(expr,['op','args'],where='operator expression')
    arity={'not':1,'floor':1,'abs':1,'length':1,'to-int':1,'set-add':2,'set-remove':2,'sequence-append':2,'sequence-swap':3,'sequence-replace-member':4}
    if op in arity:require(len(args)==arity[op],f'{op} needs {arity[op]} args')
    elif op in ('and','or','concat','add','mul'):require(len(args)>=2,op+' needs >=2 args')
    else:require(len(args)==2,op+' needs exactly 2 args')
    types=[inspect_expr(a,fields,definitions,params,stack) for a in args]
    def types_are(permitted):
        require(all(t in permitted or t=='parameter' for t in types),
                f'{op}: invalid operand types {types}; expected {sorted(permitted)}')
    if op in ('eq','ne'):
        if any(_member_parents(a) for a in args):
            def comparable(a,t):
                d=_member_domain(a,fields) if a.get('op')=='member' else fields.get(a.get('ref'),{}).get('domain',{})
                if d and d.get('type')=='enum':
                    kinds={literal_type(x) for x in d['values']}
                    require(len(kinds)==1,'heterogeneous enum member comparison unsupported')
                    return next(iter(kinds))
                return t
            require(comparable(args[0],types[0])==comparable(args[1],types[1]),'member comparison type mismatch')
        require(not any(ref in fields and typed.has_semantic_domain(fields[ref]['domain'])
                        for ref in _comparison_value_refs(expr,definitions)),
                'typed JSON/instant expression requires explicit domain binding')
        return 'boolean'
    if op in ('lt','le','gt','ge'):
        types_are({'integer','real'})
        if any(_member_parents(a) for a in args):require(types[0]==types[1],'member comparison type mismatch')
        return 'boolean'
    if op in ('and','or','not'):types_are({'boolean'});return 'boolean'
    if op in ('add','sub','mul'):
        types_are({'integer','real'});return 'real' if 'real' in types else 'integer'
    if op=='div':
        types_are({'integer','real'})
        require('literal' in args[1] and type(args[1]['literal']) in (int,float) and args[1]['literal']!=0,
                'div denominator must be a declared nonzero integer literal; dynamic totality is unproved')
        return 'real'
    if op=='floor':types_are({'integer','real'});return 'integer'
    if op=='abs':types_are({'integer','real'});return types[0]
    if op=='length':types_are({'string','set','sequence','bytes'});return 'integer'
    if op=='concat':types_are({'string'});return 'string'
    if op in ('set-add','set-remove'):
        require(types[0] in ('set','parameter') and types[1] in ('string','integer','record','parameter'),
                f'{op}: expected set and element, got {types}')
        return 'set'
    if op=='sequence-append':
        require(types[0]=='sequence','sequence-append requires a sequence')
        return 'sequence'
    if op=='sequence-swap':
        require(types==['sequence','integer','integer'],'sequence-swap requires a sequence and two integer indices')
        return 'sequence'
    if op=='sequence-replace-member':
        require(types[:3]==['sequence','integer','string'] and set(args[2])=={'literal'},'sequence-replace-member requires a sequence, integer index and literal member key')
        return 'sequence'
    if op=='to-int':
        types_are({'string'})
        v=args[0]
        require(('ref' in v and v['ref'] in fields and fields[v['ref']]['domain'].get('format')=='safe-signed-integer')
                or ('literal' in v and isinstance(v['literal'],str) and safe_integer_text(v['literal'])),
                'to-int requires declared safe-signed-integer PI domain or safe integer literal')
        return 'integer'
    raise Blocked('operator missing return type '+op)

def _linear_order_atom(expr):
    """Recognize only direct order comparison of two distinct numeric refs
    added/subtracted against an integer literal. Never reinterpret equality.
    """
    if expr.get('op') not in ('lt','le','gt','ge') or len(expr.get('args',[]))!=2:return None
    for index in (0,1):
        term,limit=expr['args'][index],expr['args'][1-index]
        if (term.get('op') not in ('add','sub') or len(term.get('args',[]))!=2
                or set(limit)!={'literal'} or type(limit['literal']) is not int):continue
        a,b=term['args']
        if set(a)==set(b)=={'ref'} and a['ref']!=b['ref']:
            return term,limit['literal'],index
    return None


def _linear_order_values(fields,names,predicates,presence,definitions):
    """Order-cell witnesses for one scalar sum/difference over two intervals.

    Every observed atom of the pair must depend on the same exact term.
    Its image is an interval (integer lattice or real interval); we only
    certify when a legal, exactly representable preimage of every cell exists.
    """
    from fractions import Fraction
    terms=[]
    def collect(node):
        if node.get('op') in ('and','or','not'):
            for arg in node['args']:collect(arg)
        else:
            atom=_linear_order_atom(node)
            if atom:terms.append(atom)
    for pred in predicates:collect(pred)
    if not terms:return {}
    term=terms[0][0];a,b=(x['ref'] for x in term['args']);group={a,b}
    if not group<=set(names):return {}
    def legal(node):
        if node.get('op')=='call':return False
        if not group.intersection(used_refs(node,definitions)):return True
        if node.get('op') in ('and','or','not'):return all(legal(x) for x in node['args'])
        atom=_linear_order_atom(node)
        return atom is not None and atom[0]==term
    if not all(legal(p) for p in predicates):return {}
    domains=[fields[n]['domain'] for n in (a,b)]
    kind=domains[0].get('type')
    if kind not in ('integer','real') or domains[1].get('type')!=kind:return {}
    if any(n in presence and presence[n]!='required' for n in group):return {}
    bounds=[(d.get('min'),d.get('max')) for d in domains]
    if any(v is not None and type(v) is not int for pair in bounds for v in pair):return {}
    (al,ah),(bl,bh)=bounds
    negative=term['op']=='sub'
    if negative:bl,bh=(-bh if bh is not None else None),(-bl if bl is not None else None)
    lower=al+bl if al is not None and bl is not None else None
    upper=ah+bh if ah is not None and bh is not None else None
    cuts=sorted({x for x in [*(t[1] for t in terms if t[0]==term),lower,upper]
                 if x is not None and (lower is None or x>=lower) and (upper is None or x<=upper)})
    targets=[]
    if not cuts:targets=[0]
    else:
        if lower is None:targets.append(cuts[0]-1)
        for i,cut in enumerate(cuts):
            targets.append(cut)
            if i+1<len(cuts):
                right=cuts[i+1]
                if cut+1<right:targets.append(cut+1)
                elif kind=='real':targets.append(Fraction(cut+right,2))
        if upper is None:targets.append(cuts[-1]+1)
    values={a:set(),b:set()}
    for z in targets:
        lows=[x for x in (al,z-bh if bh is not None else None) if x is not None]
        highs=[x for x in (ah,z-bl if bl is not None else None) if x is not None]
        lo=max(lows) if lows else None;hi=min(highs) if highs else None
        if lo is not None and hi is not None and lo>hi:return {}
        x=lo if lo is not None else min(0,hi) if hi is not None else 0
        y=z-x
        if negative:y=-y
        for name,value,domain in zip((a,b),(x,y),domains):
            f=Fraction(value)
            try:concrete=int(f) if f.denominator==1 else float(f)
            except OverflowError:return {}
            if Fraction(concrete)!=f or not typed.contains(domain,concrete):return {}
            values[name].add(concrete)
    return {n:sorted(v) for n,v in values.items()} if all(values.values()) else {}


def eval_expr(expr, env, definitions, params=None):
    if 'literal' in expr:return deepcopy(expr['literal'])
    if 'ref' in expr:
        v=expr['ref']
        if v.startswith('param.'):return deepcopy((params or {})[v[6:]])
        require(v in env and env[v] is not typed.MISSING and env[v] is not typed.UNDEFINED,
                'ordinary expression reads missing/undefined field '+v)
        return deepcopy(env[v])
    op=expr['op']
    if op in ('is-missing','is-undefined','is-present'):
        require(len(expr['args'])==1 and set(expr['args'][0])=={'ref'},
                'invalid Presence predicate shape')
        ref=expr['args'][0]['ref']
        value=env.get(ref,typed.MISSING)
        if op=='is-missing':return value is typed.MISSING
        if op=='is-undefined':return value is typed.UNDEFINED
        return value is not typed.MISSING and value is not typed.UNDEFINED
    if op in ('and','or'):
        for part in expr['args']:
            value=eval_expr(part,env,definitions,params)
            require(type(value) is bool,op+' requires boolean')
            if op=='and' and not value:return False
            if op=='or' and value:return True
        return op=='and'
    # This exact order fragment compares mathematical numeric values, not a
    # rounded intermediate binary64 sum. Integer/float inputs retain their
    # represented values; general arithmetic and Effect values are unchanged.
    atom=_linear_order_atom(expr)
    if atom is not None:
        from fractions import Fraction
        import math
        term,limit,index=atom
        operands=[eval_expr(x,env,definitions,params) for x in term['args']]
        require(all(type(x) is int or type(x) is float and math.isfinite(x) for x in operands),
                'linear order requires finite numeric operands')
        a,b=map(Fraction,operands)
        value=a+b if term['op']=='add' else a-b
        left,right=(value,limit) if index==0 else (limit,value)
        return {'lt':lambda:left<right,'le':lambda:left<=right,
                'gt':lambda:left>right,'ge':lambda:left>=right}[op]()
    xs=[eval_expr(x,env,definitions,params) for x in expr['args']]
    if op in collection_relation.OPERATORS:return collection_relation.evaluate(op,xs)
    if op=='member':
        require(len(xs)==2 and isinstance(xs[0],dict) and isinstance(xs[1],str) and xs[1] in xs[0]
                and xs[0][xs[1]] is not typed.MISSING and xs[0][xs[1]] is not typed.UNDEFINED,
                'required record member absent')
        return deepcopy(xs[0][xs[1]])
    if op=='record-value':return {key:deepcopy(value) for key,value in zip(xs[::2],xs[1::2])}
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
        if op=='add':require(all(type(x) in (int,float) for x in xs),'add requires number');return sum(xs)
        if op=='sub':require(all(type(x) in (int,float) for x in xs),'sub requires number');return xs[0]-xs[1]
        if op=='mul':
            require(all(type(x) in (int,float) for x in xs),'mul requires number')
            a=1
            for x in xs:a*=x
            return a
        if op=='div':require(all(type(x) in (int,float) for x in xs) and xs[1]!=0,'div requires numbers and nonzero divisor');return xs[0]/xs[1]
        if op=='floor':import math;return math.floor(xs[0])
        if op=='abs':return abs(xs[0])
        if op=='length':return len(xs[0])
        if op=='to-int':
            require(safe_integer_text(xs[0]),'to-int requires safe canonical signed-integer string')
            return int(xs[0])
        if op=='concat':return ''.join(xs)
        if op=='sequence-append':
            require(isinstance(xs[0],list),'sequence-append expects list')
            return deepcopy(xs[0]+[xs[1]])
        if op=='sequence-swap':
            require(isinstance(xs[0],list) and all(type(x) is int for x in xs[1:]),'sequence-swap expects list and integer indices')
            result=deepcopy(xs[0]);i,j=xs[1:]
            if 0<=i<len(result) and 0<=j<len(result):result[i],result[j]=result[j],result[i]
            return result
        if op=='sequence-replace-member':
            require(isinstance(xs[0],list) and type(xs[1]) is int and type(xs[2]) is str,'sequence-replace-member expects list, integer and member key')
            result=deepcopy(xs[0]);i,key,value=xs[1:]
            if 0<=i<len(result):
                require(type(result[i]) is dict and key in result[i],'sequence-replace-member requires existing record member')
                result[i][key]=deepcopy(value)
            return result
        if op=='set-add':
            require(isinstance(xs[0],list),'set-add expects list')
            return typed.set_add(xs[0],xs[1])
        if op=='set-remove':
            require(isinstance(xs[0],list),'set-remove expects list')
            return typed.set_remove(xs[0],xs[1])
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

def _unresolved_domain(d):
    t=d['type']
    if t=='reference':return (not d.get('resolved') or _unresolved_domain(d['of']))
    if t=='record':
        return not d.get('resolved',False) or any(_unresolved_domain(f['domain']) for f in d.get('fields',[]))
    if t in ('set','sequence'):return isinstance(d['element'],dict) and _unresolved_domain(d['element'])
    if t=='nullable':return _unresolved_domain(d['of'])
    if t=='union':return any(_unresolved_domain(x) for x in d['variants'])
    return False

def _guard_reads_value_before_presence(node, field):
    if not isinstance(node,dict):return False
    if node.get('op') in ('is-present','is-missing','is-undefined'):
        return False  # Presence tests inspect state, not a present value.
    if node.get('op')=='call':
        return True  # Unknown function-body evaluation order.
    return node.get('ref')==field or any(
        _guard_reads_value_before_presence(arg,field) for arg in node.get('args',[]))


def _guard_guarantees_nonnull(expr, field):
    """Sufficient truth implication for a direct, same-cut nullable read."""
    op=expr.get('op'); args=expr.get('args',[])
    if op=='and': return any(_guard_guarantees_nonnull(x,field) for x in args)
    if op=='or': return bool(args) and all(_guard_guarantees_nonnull(x,field) for x in args)
    if op=='not' and len(args)==1 and args[0].get('op')=='eq':
        args=args[0].get('args',[]); op='ne'
    return op=='ne' and (args==[{'ref':field},{'literal':None}] or args==[{'literal':None},{'ref':field}])


def _guarded_source_domain(domain, guard, field):
    if domain.get('type')=='nullable' and _guard_guarantees_nonnull(guard,field):
        return domain['of']
    return domain


def _guard_guarantees_present(expr, field):
    """Sound, evaluation-order-aware Guard truth implies value Presence."""
    if expr.get('op')=='is-present' and expr.get('args')==[{'ref':field}]:
        return True
    if expr.get('op')=='and':
        prefix=[]
        for part in expr['args']:
            if (_guard_guarantees_present(part,field)
                    and not any(_guard_reads_value_before_presence(x,field)
                                for x in prefix)):
                return True
            prefix.append(part)
    if expr.get('op')=='or':
        return all(_guard_guarantees_present(x,field) for x in expr['args'])
    return False


def _presence_only_guard_use(expr, field):
    """Only direct Presence predicates may inspect a partitioned value."""
    if not isinstance(expr,dict):return False
    if expr.get('op') in ('is-present','is-missing','is-undefined'):
        return expr.get('args')==[{'ref':field}] or field not in used_refs(expr,{})
    if expr.get('op')=='call':return False
    if expr.get('ref')==field:return False
    if 'args' in expr:
        return all(_presence_only_guard_use(a,field) for a in expr['args'])
    return True


def _symbolic_effect_containment(expr, target_domain, fields):
    """Prove only exact, total integer addition and typed Set insertion/removal.

    No representative values, floating-point arithmetic, implicit casts,
    nominal alias guesses, or arbitrary function-body assumptions are used.
    None means this fragment cannot establish the proof.
    """
    op=expr.get('op')
    args=expr.get('args',[])
    if op in collection_relation.OPERATORS:
        domain=collection_relation.operator_domain(expr,fields)
        return domain is not None and semantic_subtyping.subset(domain,target_domain) is True
    if op=='member':
        try:return semantic_subtyping.subset(_member_domain(expr,fields),target_domain) is True
        except Blocked:return None
    if op=='add' and len(args)>=2:
        domains=[]
        for arg in args:
            if set(arg)=={'literal'} and type(arg['literal']) is int:
                domains.append({'type':'integer','min':arg['literal'],'max':arg['literal']})
            elif set(arg)=={'ref'} and arg['ref'] in fields:
                field=fields[arg['ref']]
                if field['role'] not in ('input','state','observation'):
                    return None
                domains.append(field['domain'])
            else:
                return None
        if any(d.get('type')!='integer' for d in domains):
            return None
        if any(_unresolved_domain(d) for d in domains):
            return None
        # Python integer arithmetic has no overflow; the interval endpoints
        # are exact integers. An absent endpoint represents infinity.
        inferred={'type':'integer'}
        for endpoint in ('min','max'):
            endpoints=[d.get(endpoint) for d in domains]
            if all(type(value) is int for value in endpoints):
                inferred[endpoint]=sum(endpoints)
        return semantic_subtyping.subset(inferred,target_domain) is True
    def constructed_value_fits(node,domain):
        if set(node)=={'literal'}:return typed.contains(domain,node['literal'])
        if set(node)=={'ref'}:
            f=fields.get(node['ref'],{})
            return f.get('role') in ('input','state','observation') and semantic_subtyping.subset(f['domain'],domain) is True
        if node.get('op')!='record-value':return False
        shape=_record_shape(domain)
        if shape is None:return False
        terms=node['args'];values={k['literal']:v for k,v in zip(terms[::2],terms[1::2])}
        members={f['id']:f for f in shape['fields']}
        if set(values)-set(members):return False
        for name,member in members.items():
            presence=member['presence']
            if name in values:
                if presence not in ('required','optional') or not constructed_value_fits(values[name],member['domain']):return False
            elif presence in ('required','undefined'):return False
        return True
    if op=='record-value':return constructed_value_fits(expr,target_domain)
    if op in ('sequence-append','sequence-swap','sequence-replace-member'):
        if len(args)!={'sequence-append':2,'sequence-swap':3,'sequence-replace-member':4}[op] or set(args[0])!={'ref'}:return None
        source=fields.get(args[0]['ref'],{})
        if source.get('role') not in ('input','state','observation'):return None
        collection=source['domain']
        if collection.get('type')!='sequence' or target_domain.get('type')!='sequence':return None
        if semantic_subtyping.subset(collection,target_domain) is not True:return None
        if op=='sequence-append':
            return constructed_value_fits(args[1],target_domain['element'])
        def integer_index(node):
            if set(node)=={'literal'}:return type(node['literal']) is int
            if set(node)=={'ref'}:
                field=fields.get(node['ref'],{})
                return field.get('role') in ('input','state','observation') and field.get('domain',{}).get('type')=='integer'
            if node.get('op') in ('add','sub') and len(node.get('args',[]))>=2:
                return all(integer_index(x) for x in node['args'])
            return False
        if op=='sequence-replace-member':
            shape=_record_shape(collection['element'])
            if shape is None or not integer_index(args[1]) or set(args[2])!={'literal'}:return None
            member=next((x for x in shape['fields'] if x['id']==args[2]['literal']),None)
            return bool(member and member['presence']=='required' and constructed_value_fits(args[3],member['domain']))
        return all(integer_index(x) for x in args[1:])
    if op=='set-add' and len(args)==2 and all(set(a)=={'ref'} for a in args):
        set_ref,item_ref=(a['ref'] for a in args)
        if set_ref not in fields or item_ref not in fields:
            return None
        collection=fields[set_ref]; item=fields[item_ref]
        if collection['role'] not in ('input','state','observation') or item['role'] not in ('input','state','observation'):
            return None
        source=collection['domain']
        if source.get('type')!='set' or target_domain.get('type')!='set':
            return None
        if _unresolved_domain(source) or _unresolved_domain(item['domain']):
            return None
        return (semantic_subtyping.subset(source,target_domain) is True
                and semantic_subtyping.subset(item['domain'],target_domain['element']) is True)
    if op=='set-remove' and len(args)==2 and all(set(a)=={'ref'} for a in args):
        set_ref,item_ref=(a['ref'] for a in args)
        if set_ref not in fields or item_ref not in fields:
            return None
        collection=fields[set_ref];item=fields[item_ref]
        if collection['role'] not in ('input','state','observation') or item['role'] not in ('input','state','observation'):
            return None
        source=collection['domain']
        if source.get('type')!='set' or target_domain.get('type')!='set':
            return None
        if (_unresolved_domain(source) or _unresolved_domain(item['domain'])
                or _unresolved_domain(target_domain)):
            return None
        # Deletion never adds an element. The source collection must fit
        # the target Set, and the removal key must belong to the source
        # element Domain so typed comparison is well defined.
        return (semantic_subtyping.subset(source,target_domain) is True
                and semantic_subtyping.subset(item['domain'],source['element']) is True)
    return None


def _effect_totality_checks(rules, fields, definitions, max_combinations=4096,
                             pi_operations=(), operation_presence=()):
    """Prove Effect target containment separately from Guard closure.

    A direct reference uses structural Domain inclusion. A narrow set of
    integer and typed-set operators permits exact, non-enumerative closure.
    Other operators require exhaustive finite Domain enumeration. A positive
    input-Presence Guard may justify an otherwise unsafe Effect input read,
    but Guard coverage and external Effect authenticity are separate duties.
    Unsupported, nonfinite or exhausted cases remain unproven.
    """
    checks={}
    declared_fields=fields
    for rule in rules:
        # A Guard with ambiguous accepted Operations is already unproven.
        # For Effect input reads, nevertheless inspect *every* such Operation:
        # silently falling back to the base PI Presence can produce a false
        # positive Effect proof that the independent Source audit rejects.
        accepted=[op for op in pi_operations
                  if op['direction']=='accept' and op.get('trigger')==rule['trigger']]
        bindings=_input_operation_bindings(pi_operations,rule['trigger'])
        def input_presence(field):
            if len(accepted)>1:
                # The referenced PI input must be available under every
                # candidate accepted Operation. A different owning PI or any
                # optional/absent/undefined override prevents positive proof.
                return ('required' if all(
                    op['source_pi']==field.get('source_pi') and
                    _presence_for_field(field,op,operation_presence)=='required'
                    for op in accepted) else 'optional')
            return _trigger_input_presence(field,bindings,operation_presence)
        fields={key:({**field,'presence':input_presence(field)}
                     if field['role']=='input' else field)
                for key,field in declared_fields.items()}
        for outcome_number,outcome in enumerate(rule['allowed'],1):
            for write_number,write in enumerate(outcome['write'],1):
                target=write['target'];expr=write['expr']
                ident=f"{rule['source_artifact']}#{rule['id']}:{outcome_number}:{write_number}:{target}"
                domain=fields[target]['domain']
                if _unresolved_domain(domain):
                    checks[ident]={'result':'unproven','reason':'Effect target Domain unresolved'}
                    continue
                if 'literal' in expr:
                    checks[ident]={'result':'proved'}  # checked against full Domain during parsing
                    continue
                if 'ref' in expr and expr['ref'] in fields:
                    source_field=fields[expr['ref']]
                    if source_field['role'] in ('output','action'):
                        checks[ident]={'result':'unproven','reason':'Effect reads an unavailable source field'}
                    elif (source_field['role']=='input' and
                          source_field.get('presence','required')!='required' and
                          not _guard_guarantees_present(rule['when'],expr['ref'])):
                        checks[ident]={'result':'unproven','reason':'Effect reads nonrequired input without a Presence proof'}
                    else:
                        proof=semantic_subtyping.subset(source_field['domain'],domain)
                        if proof is not True:
                            proof=semantic_subtyping.subset(_guarded_source_domain(source_field['domain'],rule['when'],expr['ref']),domain)
                        checks[ident]=({'result':'proved'} if proof is True
                                      else {'result':'unproven','reason':'Effect source Domain unresolved or inclusion unproved'})
                    continue
                # Exact algebraic fragments can prove membership even for
                # infinite Domains. Unsupported expressions keep the existing
                # exhaustive finite checker; they never become assumed total.
                if _symbolic_effect_containment(expr,domain,fields) is True:
                    # A non-required input remains unsafe until the Guard
                    # separately establishes that the field is present.
                    refs=used_refs(expr,definitions)
                    if not any(fields[ref]['role']=='input' and
                               fields[ref].get('presence','required')!='required' and
                               not _guard_guarantees_present(rule['when'],ref)
                               for ref in refs if ref in fields):
                        checks[ident]={'result':'proved','proof_method':'typed-domain-closure/v1'}
                        continue
                refs=sorted(used_refs(expr,definitions))
                values=[];reason=None
                for ref in refs:
                    f=fields.get(ref)
                    if f is None or f['role'] in ('output','action'):
                        reason='Effect expression reads an unavailable field';break
                    if (f['role']=='input' and f.get('presence','required')!='required'
                            and not _guard_guarantees_present(rule['when'],ref)):
                        reason='Effect expression reads nonrequired input without a Presence proof';break
                    try:
                        vals=typed.finite_values(f['domain'],max_values=max_combinations)
                    except typed.DomainError:
                        vals=None
                    if vals is None:
                        reason='Effect expression depends on nonfinite or unresolved Domain';break
                    values.append(vals)
                if reason is None and __import__('math').prod(len(v) for v in values)>max_combinations:
                    reason='Effect expression proof exceeds finite enumeration limit'
                if reason is None:
                    for concrete in itertools.product(*values):
                        env=dict(zip(refs,concrete))
                        try:
                            output=eval_expr(expr,env,definitions)
                            accepted=typed.contains(domain,output)
                        except (Blocked,typed.DomainError,ValueError,TypeError):
                            reason='Effect expression totality or output Domain unproved';break
                        if not accepted:
                            reason='Effect expression can produce a value outside the declared Domain';break
                checks[ident]=({'result':'proved'} if reason is None
                               else {'result':'unproven','reason':reason})
    return checks


def _string_reference_values(fields,names,predicates,presence):
    group={n for n in names if fields.get(n,{}).get('domain')=={'type':'string'}
           and presence.get(n,'required')=='required'}
    if len(group)<2:return {}
    palette=semantic_string_partition.reference_palette(group,predicates)
    return {n:palette for n in group} if palette is not None else {}


def _integer_reference_equality_values(fields, names, predicates, input_presence, definitions):
    """Exact weak-order Guard classes for 2..5 same-Domain integer references.

    Direct pairwise ==/!=/</<=/>/>= predicates under Boolean composition
    depend only on the references' total preorder (including ties). Every
    such preorder of N integers can be represented by N consecutive Domain
    values, or by *all* Domain values if a finite interval is shorter.
    The 2-reference v1 proof identity remains unchanged; N>=3 uses v2.
    No initial-state reachability, Effect, or Provider proof is implied.
    """
    names=set(names)
    candidates=sorted(name for name in names if name in fields
                      and fields[name]['domain'].get('type')=='integer'
                      and set(fields[name]['domain']) <= {'type','min','max'}
                      and (name not in input_presence or input_presence[name]=='required'))
    if not 2 <= len(candidates) <= 5:return {}
    domain=fields[candidates[0]]['domain']
    if any(fields[name]['domain']!=domain for name in candidates[1:]):return {}
    low,high=domain.get('min'),domain.get('max')
    if low is not None and type(low) is not int:return {}
    if high is not None and type(high) is not int:return {}
    if low is not None and high is not None and low>high:return {}
    width=min(len(candidates),high-low+1) if low is not None and high is not None else len(candidates)
    if width<2:return {}  # Exact finite enumeration already handles a singleton.
    # When only an upper bound exists, choose the highest width values if
    # required. Re-ranking never leaves the declared integral Domain.
    lower=low if low is not None else (min(0,high-width+1) if high is not None else 0)
    if high is not None and lower+width-1>high:return {}
    group=set(candidates)
    def supported(node):
        if not isinstance(node,dict):return False
        if not group.intersection(used_refs(node,definitions)):
            return True
        op=node.get('op');args=node.get('args',[])
        if op in ('and','or','not') and isinstance(args,list):
            return all(supported(arg) for arg in args)
        if op in ('eq','ne','lt','le','gt','ge') and isinstance(args,list) and len(args)==2:
            return (all(isinstance(arg,dict) and set(arg)=={'ref'}
                        and arg['ref'] in group for arg in args)
                    and args[0]['ref']!=args[1]['ref'])
        return False
    if not all(supported(predicate) for predicate in predicates):return {}
    representatives=[lower+i for i in range(width)]
    return {name:representatives for name in candidates}


def _integer_reference_range_values(fields, names, predicates, input_presence, definitions):
    """Exact local order classes across 2..3 integer Domains and literal cuts.

    Every direct integer comparison is invariant under an order-preserving
    re-ranking that fixes all integer literal constants and all Domain
    endpoints. Splitting Z at these values makes every Domain constant
    throughout each open interval. Up to N ordered representatives per
    open interval cover every weak order of N reference values in that cell.
    This is not a state-reachability, Effect, or Provider proof.
    """
    names=set(names)
    refs=sorted(name for name in names if name in fields
                and fields[name]['domain'].get('type')=='integer'
                and set(fields[name]['domain']) <= {'type','min','max'}
                and (name not in input_presence or input_presence[name]=='required'))
    if not 2 <= len(refs) <= 3:return {}
    group=set(refs)
    cuts=set()
    for name in refs:
        domain=fields[name]['domain']
        low,high=domain.get('min'),domain.get('max')
        if low is not None and type(low) is not int:return {}
        if high is not None and type(high) is not int:return {}
        if low is not None and high is not None and low>high:return {}
        if low is not None:cuts.add(low)
        if high is not None:cuts.add(high)
    saw_reference_pair=False
    def supported(node):
        nonlocal saw_reference_pair
        if not isinstance(node,dict):return False
        if not (group & used_refs(node,definitions)):return True
        op=node.get('op');args=node.get('args',[])
        if op in ('and','or','not') and isinstance(args,list):
            return all(supported(arg) for arg in args)
        if op not in ('eq','ne','lt','le','gt','ge') or not isinstance(args,list) or len(args)!=2:
            return False
        left,right=args
        if (all(isinstance(a,dict) and set(a)=={'ref'} and a['ref'] in group for a in args)
                and left['ref']!=right['ref']):
            saw_reference_pair=True
            return True
        for ref,lit in ((left,right),(right,left)):
            if (isinstance(ref,dict) and set(ref)=={'ref'} and ref['ref'] in group
                    and isinstance(lit,dict) and set(lit)=={'literal'}
                    and type(lit['literal']) is int):
                cuts.add(lit['literal'])
                return True
        return False
    if not all(supported(predicate) for predicate in predicates) or not saw_reference_pair:return {}
    ordered_cuts=sorted(cuts)
    values=[]
    n=len(refs)
    if not ordered_cuts:
        values=list(range(n))
    else:
        for index,cut in enumerate(ordered_cuts):
            if index==0:
                values.extend(range(cut-n,cut))
            else:
                start=ordered_cuts[index-1]+1
                values.extend(range(start,min(cut,start+n)))
            values.append(cut)
        values.extend(range(ordered_cuts[-1]+1,ordered_cuts[-1]+n+1))
    result={}
    for name in refs:
        domain=fields[name]['domain']
        low,high=domain.get('min'),domain.get('max')
        admissible=[v for v in values
                    if (low is None or v>=low) and (high is None or v<=high)]
        if not admissible:return {}
        result[name]=admissible
    return result

def _real_reference_range_values(fields, names, predicates, input_presence, definitions):
    """Local real weak-order classes for 2..3 direct required references.

    Fix every literal and Domain endpoint, then cover all relative orderings
    within each open cell by N distinct representable values. Failure to
    construct such witnesses stays unproved; no arithmetic or typed equality.
    """
    from fractions import Fraction
    import math
    refs=sorted(name for name in names if name in fields
                and fields[name]['domain'].get('type')=='real'
                and (name not in input_presence or input_presence[name]=='required'))
    if not 2<=len(refs)<=3:return {}
    group=set(refs);cuts=set();coupled=False
    def number(x):return type(x) is int or type(x) is float and math.isfinite(x)
    domains={name:fields[name]['domain'] for name in refs}
    for domain in domains.values():
        for value in (domain.get('min'),domain.get('max')):
            if value is None:continue
            if not number(value):return {}
            cuts.add(Fraction(value))
    def supported(node):
        nonlocal coupled
        if not isinstance(node,dict) or node.get('op')=='call':return False
        if not group.intersection(used_refs(node,definitions)):return True
        op,args=node.get('op'),node.get('args',[])
        if op in ('and','or','not'):return all(supported(a) for a in args)
        if op not in ('lt','le','gt','ge') or len(args)!=2:return False
        if all(set(a)=={'ref'} and a['ref'] in group for a in args):
            coupled |= args[0]['ref']!=args[1]['ref']
            return True
        for a,b in (args,args[::-1]):
            if set(a)=={'ref'} and a['ref'] in group and set(b)=={'literal'} and number(b['literal']):
                cuts.add(Fraction(b['literal']));return True
        return False
    if not all(supported(p) for p in predicates) or not coupled:return {}
    n=len(refs);points=sorted(cuts);values=[]
    if not points:values=list(range(n))
    else:
        if any(d.get('min') is None for d in domains.values()):
            values.extend(range(math.floor(points[0])-n,math.floor(points[0])))
        for i,point in enumerate(points):
            values.append(int(point) if point.denominator==1 else float(point))
            if i+1==len(points):continue
            right=points[i+1]
            if not any((d.get('min') is None or Fraction(d['min'])<=point)
                       and (d.get('max') is None or Fraction(d['max'])>=right) for d in domains.values()):continue
            start=math.floor(point)+1
            if start+n-1<right:cell=list(range(start,start+n))
            else:
                try:cell=[float((point*(n+1-k)+right*k)/(n+1)) for k in range(1,n+1)]
                except OverflowError:return {}
                if not all(math.isfinite(x) for x in cell):return {}
                if not point<Fraction(cell[0]) or not Fraction(cell[-1])<right or any(a>=b for a,b in zip(cell,cell[1:])):return {}
            values.extend(cell)
        if any(d.get('max') is None for d in domains.values()):
            start=math.ceil(points[-1])+1;values.extend(range(start,start+n))
    result={name:[v for v in values if typed.contains(domain,v)] for name,domain in domains.items()}
    return result if all(result.values()) else {}


def _has_pair_order_comparison(node):
    """Ordering labels cannot be confused with equality-only receipts."""
    if not isinstance(node,dict):return False
    return (node.get('op') in ('lt','le','gt','ge')
            or any(_has_pair_order_comparison(x) for x in node.get('args',[])))


def _record_projection_values(fields,names,predicates,presence,definitions,member_exprs=(),*,guard_only=False):
    """Exact Cartesian cells of projected scalar members; reassemble wire record.

    Temporary analysis IDs never escape into the Model or vector payload.
    A whole-record read or unknown relation disables this proof fragment.
    """
    parents=set().union(*(_member_parents(p) for p in [*predicates,*member_exprs]))
    if not parents:return {}
    if not parents<=set(names):return {}
    flat={name:fields[name] for name in names if name not in parents}
    flat_presence={n:presence[n] for n in flat if n in presence}
    groups={};keys={}
    for parent in sorted(parents):
        if presence.get(parent)!='required':return {}
        shape=_record_shape(fields[parent]['domain'])
        if shape is None:return {}
        groups[parent]=[]
        for member in shape['fields']:
            mid=member['id'];key='@member:'+parent+':'+mid
            if key in flat or key in fields:return {}
            if member['presence'] in ('optional','absent'):
                continue
            if member['presence']!='required':return {}
            d=member['domain']
            while d.get('type')=='reference' and d.get('resolved'):d=d['of']
            if d.get('type') not in ('boolean','integer','real','string','enum') and not (guard_only and d.get('type') in ('json','instant')):return {}
            keys[parent,mid]=key;groups[parent].append((mid,key))
            flat[key]={'id':key,'domain':d,'role':'input','presence':'required'}
            flat_presence[key]='required'
    def rewrite(node):
        if node.get('op')=='member':
            parent,mid=node['args'][0]['ref'],node['args'][1]['literal']
            if (parent,mid) not in keys:raise Blocked('projection not in required member scope')
            return {'ref':keys[parent,mid]}
        if node.get('ref') in parents or node.get('op')=='call':raise Blocked('whole record or opaque call in projection partition')
        return ({**node,'args':[rewrite(a) for a in node['args']]} if 'args' in node else node)
    try:clauses=[rewrite(p) for p in predicates]
    except Blocked:return {}
    used=set().union(*(used_refs(p,definitions) for p in clauses)) if clauses else set()
    if not used<=set(flat):return {}
    integer_pair=_integer_reference_equality_values(flat,used,clauses,flat_presence,definitions)
    integer_range={} if integer_pair else _integer_reference_range_values(flat,used,clauses,flat_presence,definitions)
    strings={n for n in used if flat[n]['domain']=={'type':'string'} and flat_presence.get(n,'required')=='required'}
    string_values={}
    if 2<=len(strings)<=5:
        constants=set();pair=False
        def string_clause(n):
            nonlocal pair
            if not strings.intersection(used_refs(n,definitions)):return True
            args=n.get('args',[])
            if n.get('op') in ('and','or','not'):return all(string_clause(a) for a in args)
            if n.get('op') not in ('eq','ne') or len(args)!=2:return False
            if all(set(a)=={'ref'} and a['ref'] in strings for a in args):pair=True;return True
            for a,b in (args,args[::-1]):
                if set(a)=={'ref'} and a['ref'] in strings and set(b)=={'literal'} and type(b['literal']) is str:
                    constants.add(b['literal']);return True
            return False
        if all(string_clause(c) for c in clauses) and pair:
            fresh=[];candidate=''
            while len(fresh)<len(strings):
                if candidate not in constants:fresh.append(candidate)
                candidate+='\x00'
            string_values={n:[*sorted(constants),*fresh] for n in strings}
    values={}
    for name,field in flat.items():
        domain=field['domain'];pr=flat_presence.get(name,'required')
        candidates=integer_range.get(name) or integer_pair.get(name) or string_values.get(name)
        if candidates is None:
            candidates=_presence_cases(domain,pr) if name in flat_presence else typed.finite_values(domain)
        if candidates is None and name not in used and pr=='optional':candidates=[typed.MISSING]
        if guard_only and candidates is None and name not in used and pr=='required':
            # Whole-record reads/calls have already been rejected. These
            # representatives witness nonempty unread sibling Domains only.
            if domain.get('type')=='json':candidates=[{} if domain['root']=='object' else None]
            elif domain.get('type')=='instant':candidates=[json_time.decode_offset_datetime('1970-01-01T00:00:00Z')]
        if candidates is None and pr=='required':
            for solver in (semantic_interval_partition.integer_partition_values,semantic_string_partition.string_partition_values,semantic_interval_partition.real_partition_values):
                candidates=solver(domain,name,clauses,allow_unused=name not in used)
                if candidates is not None:break
        if candidates is None or not candidates:return {}
        # All unobserved variables are irrelevant to this Guard relation;
        # choose one valid witness, not a sampled truth cell.
        values[name]=candidates if name in used else candidates[:1]
    result={n:values[n] for n in names if n not in parents}
    for parent,members in groups.items():
        dims=[values[key] for _,key in members]
        if __import__('math').prod(map(len,dims))>65536:return {}
        result[parent]=[dict(zip((mid for mid,_ in members),cell)) for cell in itertools.product(*dims)]
        if not all(typed.contains(fields[parent]['domain'],value) for value in result[parent]):return {}
    return result


def _presence_cases(domain,presence):
    """Exact PI input-state enumeration, not a fabricated ordinary value."""
    require(presence in ('required','optional','absent','undefined'),'invalid input Presence')
    if presence=='absent':return [typed.MISSING]
    if presence=='undefined':return [typed.UNDEFINED]
    values=typed.finite_values(domain)
    if values is None:return None
    return ([typed.MISSING,*values] if presence=='optional' else values)


def _guard_invariant_exprs(proofs):
    """Only opt-in certificates may restrict the finite Guard universe."""
    return {p['rule_id']:parse_expr_text(p['scope'][len('initial-state-relation '):])
            for p in proofs if p.get('requirement')=='@cat:finite-state-guard-invariant/v1'
            and p.get('status')=='passed' and p.get('scope','').startswith('initial-state-relation ')}


def _proved_guard_invariants(documents, fields, process, rules, checks, confirmed):
    if not confirmed:return {}
    proved={}
    for doc in documents:
        if doc['process']!=process or doc['kind']!='domain-spec' or not doc['scope_verified']:continue
        for rule in doc['rules']:
            scope=rule.get('condition','')
            if (rule.get('requirement')!='@cat:finite-state-guard-invariant/v1'
                    or rule.get('verification_contract')!='cat:intrinsic-model/v1'
                    or not scope.startswith('initial-state-relation ')):continue
            try:
                expr=parse_expr_text(scope[len('initial-state-relation '):])
                refs=sorted(used_refs(expr,{}))
                if not refs or any(fields.get(r,{}).get('role')!='state' for r in refs):continue
                if inspect_expr(expr,fields,{})!='boolean':continue
                dims=[typed.finite_values(fields[r]['domain']) for r in refs]
                if any(not d for d in dims) or __import__('math').prod(map(len,dims))>4096:continue
                states=[dict(zip(refs,v)) for v in itertools.product(*dims)]
                valid=[env for env in states if eval_expr(expr,env,{}) is True]
                if not valid:continue
                preserves=True
                for row in rules:
                    for n,out in enumerate(row['allowed'],1):
                        writes=[(i,w) for i,w in enumerate(out['write'],1) if w['target'] in refs]
                        if any(used_refs(w['expr'],{})-set(refs) or checks.get(
                            f"{row['source_artifact']}#{row['id']}:{n}:{i}:{w['target']}",{}).get('result')!='proved'
                            for i,w in writes):preserves=False;break
                        for env in valid:
                            after={**env,**{w['target']:eval_expr(w['expr'],env,{}) for _,w in writes}}
                            if eval_expr(expr,after,{}) is not True:preserves=False;break
                        if not preserves:break
                    if not preserves:break
                if preserves:proved[rule['id']]=expr
            except (Blocked,KeyError,TypeError,ValueError,ArithmeticError):continue
    return proved


def _active_pi_constraints(model, trigger):
    """Constraints on a PI are obligations only at that PI's accepted operation.

    Legacy models without source scopes retain the original single-boundary
    behavior. The scope inventory is preserved separately from its expressions
    so no generated guard may borrow another PI's input state.
    """
    scopes = model.get('pi_constraint_scopes')
    if scopes is None:
        return model.get('pi_constraints', [])
    return [item['expr'] for item in scopes if trigger in item['triggers']]


def _presence_accepted_operation(operations,trigger):
    matches=[op for op in operations if op['direction']=='accept' and op.get('trigger')==trigger]
    if len(matches)>1:
        return None,'ambiguous accepted PI operations for Presence closure'
    return (matches[0] if matches else None),None


def _input_operation_bindings(operations, trigger):
    """Local trigger readability only; does not prove peer/caller correlation.

    A provided PI's receive field is a reply, not a new external Trigger.
    It may be read by the caller's TCE only when a provided Operation has
    explicitly named that caller Trigger. An unspecified provide Trigger does
    not grant blanket permission, and ambiguous providers grant none.
    """
    matches=[op for op in operations if op['direction']=='accept'
             and op.get('trigger')==trigger]
    if len(matches)>1:
        return {}  # Existing ambiguous-accept proof remains unproven.
    bindings={op['source_pi']:op for op in matches}
    provided={}
    for op in operations:
        if op['direction']=='provide' and op.get('trigger')==trigger:
            provided.setdefault(op['source_pi'],[]).append(op)
    for owner,items in provided.items():
        if owner not in bindings and len(items)==1:
            bindings[owner]=items[0]
    return bindings


def _trigger_input_presence(field, bindings, overrides):
    return _presence_for_field(field,bindings.get(field.get('source_pi')),overrides)


def _presence_for_field(field,operation,overrides):
    result=field.get('presence','required')
    if operation is not None and operation['source_pi']==field.get('source_pi'):
        entries=[x for x in overrides if x['operation']==operation['id'] and x['field']==field['id']]
        require(len(entries)<=1,'duplicate operation Presence override')
        if entries:result=entries[0]['presence']
    return result


def _nonrequired_output_ids(fields,overrides):
    return {f['id'] for f in fields.values()
            if f['role']=='output' and f.get('presence','required')!='required'} | {
        item['field'] for item in overrides
        if fields[item['field']]['role']=='output' and item['presence']!='required'}


def _provided_output_frames(fields,operations,overrides,trigger):
    """Resolve fresh result frames by PI, not by a global provider count.

    Multiple frames require explicit Trigger bindings and distinct owners.
    The legacy singular unscoped operation is retained; no ordering or
    transport protocol is inferred from the frame map.
    """
    special=_nonrequired_output_ids(fields,overrides)
    declared=any(fields[item['field']]['role']=='output' for item in overrides)
    if not special and not declared:
        return None
    candidates=[op for op in operations if op['direction']=='provide'
                and (op.get('trigger') is None or op['trigger']==trigger)]
    frames={op['source_pi']:op for op in candidates}
    if not candidates:
        # An explicitly Trigger-bound provider inventory can be inactive.
        # Do not infer an empty frame for legacy/undeclared output owners.
        owners={f['source_pi'] for f in fields.values() if f['role']=='output'}
        scoped={op['source_pi'] for op in operations if op['direction']=='provide'
                and op.get('trigger') is not None}
        return {} if owners and owners<=scoped else None
    if len(frames)!=len(candidates):
        return None
    if len(candidates)>1 and any(op.get('trigger')!=trigger for op in candidates):
        return None
    # Overrides of explicitly distinct response Triggers belong to those
    # fresh frames. Reject accept, unscoped, unknown or ambiguous operations.
    for item in overrides:
        field=fields[item['field']]
        operation=frames.get(field.get('source_pi'))
        if field['role']!='output' or operation is None or item['operation']==operation['id']:
            continue
        other=[op for op in operations if op['id']==item['operation']
               and op['source_pi']==operation['source_pi']]
        if (len(other)!=1 or other[0]['direction']!='provide'
                or other[0].get('trigger') in (None,trigger)):
            return None
    return frames


def _unproved_output_presence(fields,operations,overrides,rules,triggers,explicit_frames=()):
    """Audit required output emission independently of nonrequired fields.

    No provide operation is needed for the legacy direct TCE output frame,
    but a nonrequired field still needs its explicit operation Presence.
    """
    if explicit_frames:
        from catlib.output_frame_contract import active_frames, declared_owners
        owners=declared_owners(explicit_frames)
        # Reuse legacy audit on the remaining owners, with no foreign writes.
        remaining={k:f for k,f in fields.items() if f.get('source_pi') not in owners}
        legacy_rules=[{**rule,'allowed':[{**out,'write':[w for w in out['write'] if w['target'] in remaining]}
                                      for out in rule['allowed']]} for rule in rules]
        errors=_unproved_output_presence(remaining,[op for op in operations if op['source_pi'] not in owners],
            [ov for ov in overrides if ov['field'] in remaining],legacy_rules,triggers)
        owned=[f for f in fields.values() if f['role']=='output' and f.get('source_pi') in owners]
        for rule in rules:
            for n,outcome in enumerate(rule['allowed'],1):
                active=active_frames(explicit_frames,operations,rule['trigger'],rule['id'],n)
                emitted={w['target'] for w in outcome['write']}
                for field in owned:
                    op=active.get(field['source_pi'])
                    presence=_presence_for_field(field,op,overrides) if op is not None else 'absent'
                    if presence=='undefined' or (presence=='required' and field['id'] not in emitted) or (presence=='absent' and field['id'] in emitted):
                        errors.add(field['id'])
        return errors
    special=_nonrequired_output_ids(fields,overrides)
    outputs=[f for f in fields.values() if f['role']=='output']
    errors=set()
    covered_owners=set()
    for trigger in triggers:
        frames=_provided_output_frames(fields,operations,overrides,trigger)
        if frames is not None:
            covered_owners.update(frames)
        if frames is None:
            errors.update(special)
            scoped_outputs=outputs
        else:
            scoped_outputs=[f for f in outputs
                            if f['source_pi'] in frames]
        scoped_ids={f['id'] for f in scoped_outputs}
        for rule in (r for r in rules if r['trigger']==trigger):
            for outcome in rule['allowed']:
                emitted={w['target'] for w in outcome['write']}
                if frames is not None:
                    # An unrelated PI may not silently be declared emitted
                    # under a selected provider for this trigger.
                    errors.update(emitted & ({f['id'] for f in outputs}-scoped_ids))
                for field in scoped_outputs:
                    name=field['id']
                    presence=(_presence_for_field(field,frames[field['source_pi']],overrides)
                              if frames is not None else field.get('presence','required'))
                    if (presence=='undefined'
                            or (presence=='required' and name not in emitted)
                            or (presence=='absent' and name in emitted)):
                        errors.add(name)
    errors.update(f['id'] for f in outputs if f['id'] in special
                  and f['source_pi'] not in covered_owners)
    return errors


def _large_finite_predicate_cache(ordered, dimensions, predicates, definitions):
    """Bounded exact factorization; retain native ordered evaluation semantics.

    Keys are axis indices, not serialized values. Only dependencies identified
    by the full AST (including called definitions) enter each cache. Full
    Cartesian traversal is still exact; the expensive evaluator is memoized.
    """
    import math
    from operator import itemgetter
    product=math.prod(map(len,dimensions))
    if product>2_000_000 or product*len(predicates)>64_000_000:return None
    if any(any(v is _PRESENT_GUARD_VALUE for v in dim) for dim in dimensions):return None
    budget=0;lookups=0
    def plan(expr):
        nonlocal budget,lookups
        refs=used_refs(expr,definitions)
        if not refs<=set(ordered):raise ValueError('unknown predicate dependency')
        axes=tuple(i for i,n in enumerate(ordered) if n in refs)
        cells=math.prod(len(dimensions[i]) for i in axes)
        if cells>65536:
            # Split only a typed boolean connective. Retain source ordering
            # and short-circuit semantics; never evaluate an unreachable read.
            op=expr.get('op')
            if op not in ('and','or','not'):raise ValueError('large atomic predicate')
            children=[plan(child) for child in expr['args']]
            def evaluate(row):
                for child in children:
                    value=child(row)
                    require(type(value) is bool,op+' requires boolean')
                    if op=='not':return not value
                    if op=='and' and not value:return False
                    if op=='or' and value:return True
                return op=='and'
            return evaluate
        budget+=cells;lookups+=1
        if budget>1_000_000 or product*lookups>64_000_000:
            raise ValueError('predicate proof budget exceeded')
        cache={}
        get=itemgetter(*axes) if len(axes)>1 else (lambda row:(row[axes[0]],)) if axes else (lambda row:())
        def evaluate(row):
            key=get(row)
            if key not in cache:
                env={ordered[i]:dimensions[i][j] for i,j in zip(axes,key)}
                cache[key]=eval_expr(expr,env,definitions)
            return cache[key]
        return evaluate
    try:return [plan(expr) for expr in predicates]
    except ValueError:return None


def _debug_presence_env(env):
    def transport(value):
        if type(value) is json_time.InstantValue:return json_time.encode_instant_transport(value)
        if isinstance(value,dict):return {k:transport(v) for k,v in value.items()}
        if isinstance(value,list):return [transport(v) for v in value]
        return value
    return {key:({'$cat_presence':'missing'} if value is typed.MISSING else
                 {'$cat_presence':'undefined'} if value is typed.UNDEFINED else
                 {'$cat_presence':'present'} if value is _PRESENT_GUARD_VALUE else transport(value))
            for key,value in env.items()}


def load(process_path,pi_path,tce_path,domain_path=None,allow_draft=False,common_rules=(),domain_specs=(),allow_partial=False):
    pf,p=read_artifact(process_path,'process',allow_draft)
    rule_paths=[*common_rules,*domain_specs]
    try:rule_docs=semantic_rules.load_many(rule_paths,p['process'],allow_draft)
    except semantic_rules.RuleError as exc:raise Blocked(str(exc)) from exc
    rule_obligations=[x for d in rule_docs for x in d['rules']]
    try:
        type_registry=named_types.registry(rule_docs)
        resolved_type_definitions=named_types.resolved_definitions(type_registry)
    except (named_types.NamedTypeError,typed.DomainError) as exc:raise Blocked(str(exc)) from exc
    def resolve_domain_types(domain):
        try:return named_types.resolve(domain,type_registry)
        except (named_types.NamedTypeError,typed.DomainError) as exc:raise Blocked(str(exc)) from exc
    pi_paths=list(pi_path) if isinstance(pi_path,(list,tuple)) else [pi_path]
    require(bool(pi_paths),'at least one PI required')
    pi_docs=[]
    for path in pi_paths:
        pif,pi_item=read_artifact(path,'pi',allow_draft)
        pi_docs.append((path,pif,pi_item))
    pif,pi=pi_docs[0][1:]
    tce_paths=list(tce_path) if isinstance(tce_path,(list,tuple)) else [tce_path]
    require(tce_paths,'at least one TCE artifact required')
    tce_docs=[]
    for path in tce_paths:
        tf,tce=read_artifact(path,'tce',allow_draft)
        tce_docs.append((path,tf,tce))
    tf=tce_docs[0][1]
    dfile,domain=(read_artifact(domain_path,'domain-rule',allow_draft) if domain_path else (None,None))
    files=[(process_path,pf),*[(path,fm) for path,fm,_ in pi_docs],*[(path,fm) for path,fm,_ in tce_docs]]
    if dfile:files.append((domain_path,dfile))
    for path, doc in zip(rule_paths,rule_docs):
        files.append((path,{'id':doc['id'],'kind':doc['kind'],'status':doc['status'],
                            'semantic_contract':'markdown-v2'}))
    contracts={fm.get('semantic_contract') for _,fm in files}
    require(len(contracts)==1,'all compiled CAT artifacts must use the same semantic_contract')
    contract=next(iter(contracts))
    semantics=[p,*[a for _,_,a in pi_docs],*[tce for _,_,tce in tce_docs]]
    require(len({a['process'] for a in semantics})==1,'different Process IDs in artifacts')
    if domain and domain['process']!=p['process']:
        require(p['process'].startswith(domain['process']+'.'),
                'DomainRule scope is not an ancestor of the assembled Process')
        require(p['process'] in dfile.get('refs',[]),
                'shared DomainRule must explicitly reference the assembled Process')
    for _,item_fm,_ in pi_docs:
        require(pf['id'] in item_fm['refs'] or item_fm['id'] in p.get('interfaces',[]),
                'missing Process→PI reference: '+item_fm['id'])
    for _,tce_fm,_ in tce_docs:
        require(any(pi_fm['id'] in tce_fm['refs'] for _,pi_fm,_ in pi_docs),
                'missing assembled PI→TCE reference: '+tce_fm['id'])
    if domain:
        require(any(dfile['id'] in tce_fm['refs'] for _,tce_fm,_ in tce_docs),
                'DomainRule artifact not referenced by any TCE')

    process_optional=['interfaces','state_fields','observations','actions'] if contract=='markdown-v2' else []
    check_keys(p,['schema','kind','process','triggers','closed_world'],process_optional,where='Process')
    require(type(p['closed_world']) is bool,'Process closed_world must be boolean')
    require(isinstance(p['triggers'],list) and p['triggers'],'Process triggers required')
    for t in p['triggers']:
        check_keys(t,['id','origin'],where='Trigger');semantic_ident(t['id'],'Trigger');require(isinstance(t['origin'],str) and t['origin'],'Trigger origin required')
    unique([t['id'] for t in p['triggers']],'Triggers')

    fields={}
    pi_fields={}
    constraints=[]
    pi_constraint_sources=[]
    pi_operations=[]
    operation_presence=[]
    for _,pif,pi in pi_docs:
        if contract=='markdown-v2':
            require(pif['id'] in p.get('interfaces',[]),'Process Interfaces must reference loaded PI '+pif['id'])
            check_keys(pi,['schema','kind','process','boundary','fields','operations'],
                       ['constraints','operation_presence','output_frames'],where='PI')
            check_keys(pi['boundary'],['peer','direction'],['peers'],where='PI boundary')
            require(all(x==peer_binding.ORIGIN or peer_binding.concrete_process_id(x) for x in pi['boundary'].get('peers',[pi['boundary']['peer']])),
                    'PI peer process must use stable Process IDs')
            require(pi['boundary']['direction'] in ('receive','send','bidirectional'),'PI boundary direction invalid')
            peers=pi['boundary'].get('peers',[pi['boundary']['peer']])
            require(bool(peers) and len(peers)==len(set(peers)) and pi['boundary']['peer']==peers[0],
                    'PI boundary peers must be nonempty, unique and agree with primary peer')
            require(isinstance(pi['operations'],list),'PI operations must be array')
            for op in pi['operations']:
                check_keys(op,['id','direction','trigger'],['peer'],where='PI operation')
                semantic_ident(op['id'],'PI operation ID')
                require(op['direction'] in ('accept','provide'),'PI operation direction invalid')
                if 'peer' in op:
                    require(isinstance(op['peer'],str) and (op['peer']==peer_binding.ORIGIN or op['peer'] in peers),
                            'PI operation peer must match a declared boundary peer')
                else:
                    require(len(peers)==1,'PI operation peer required for multi-peer boundary')
                if op['direction']=='accept':
                    require(op['trigger'] in {t['id'] for t in p['triggers']},'accepted PI operation must reference Process trigger')
                elif op['trigger'] is not None:
                    require(op['trigger'] in {t['id'] for t in p['triggers']},'PI operation trigger undeclared')
            pi_operations.extend(dict(op, source_pi=pif['id']) for op in pi['operations'])
            known_ops={op['id'] for op in pi['operations']}
            known_fields={f['id'] for f in pi['fields']}
            for entry in pi.get('operation_presence',[]):
                check_keys(entry,['operation','field','presence'],where='Operation presence')
                require(entry['operation'] in known_ops,'presence references operation outside owning PI')
                require(entry['field'] in known_fields,'presence references field outside owning PI')
                require(entry['presence'] in ('required','optional','absent','undefined'),
                        'invalid operation presence')
                operation_presence.append(dict(entry,source_pi=pif['id']))
        else:
            check_keys(pi,['schema','kind','process','fields'],['constraints'],where='PI')
        require(isinstance(pi['fields'],list) and pi['fields'],'PI fields required')
        for field in pi['fields']:
            if contract=='markdown-v2':
                check_keys(field,['id','role','direction','presence','domain'],where='PI field')
                require(field['role'] in ('input','output'),'PI field role invalid')
                require(field['direction'] in ('receive','send'),'PI field direction invalid')
                require(field['presence'] in ('required','optional','absent','undefined'),'PI field presence invalid')
                semantic_ident(field['id'],'PI field')
            else:
                check_keys(field,['id','role','domain'],where='PI field')
                ident(field['id'],'PI field');require(field['role'] in ('input','state','output'),'PI field role invalid')
                require(field['id'].startswith(field['role']+'.'),'PI field ID must start with role')
            require(field['id'] not in fields,'duplicate PI field '+field['id'])
            field['domain']=resolve_domain_types(field['domain'])
            validate_domain(field['domain'])
            # Preserve PI ownership in the compiled TestModel, not just the
            # flat field name. Cross-Process bindings must not borrow a field
            # belonging to another PI of the same Process.
            owned={**field,'source_pi':pif['id']}
            fields[field['id']]=owned
            pi_fields[field['id']]=owned
        if contract=='markdown-v2':
            dirs={f['direction'] for f in pi['fields']}
            if pi['boundary']['direction']=='receive':
                require(dirs <= {'receive'},'receive-only PI boundary cannot contain send fields')
            elif pi['boundary']['direction']=='send':
                require(dirs <= {'send'},'send-only PI boundary cannot contain receive fields')
        cs=pi.get('constraints',[])
        require(isinstance(cs,list),'PI constraints must be array')
        constraints.extend(cs)
        pi_constraint_sources.extend((pif['id'], expr) for expr in cs)
    if contract=='markdown-v2':
        require(len(p.get('interfaces',[]))==len(set(p.get('interfaces',[]))),'duplicate Process Interface reference')
        require({fm['id'] for _,fm,_ in pi_docs} <= set(p.get('interfaces',[])),
                'compiled PI not declared in Process interfaces')
        unresolved_interfaces=sorted(set(p.get('interfaces',[]))-{fm['id'] for _,fm,_ in pi_docs})
        unique([op['id'] for op in pi_operations], 'assembled PI operations')
        unique([(x['operation'],x['field']) for x in operation_presence],
               'operation/field presence declarations')

    if contract=='markdown-v2':
        for name,items,role,extra in (
            ('State',p.get('state_fields',[]),'state',()),
            ('Observation',p.get('observations',[]),'observation',('source',)),
            ('Action',p.get('actions',[]),'action',('target',))):
            require(isinstance(items,list),f'Process {name} must be array')
            for field in items:
                check_keys(field,['id','role','domain',*extra],
                           ['available_on'] if role=='observation' else (),
                           where=f'Process {name}')
                require(field['role']==role,f'Process {name} role invalid')
                if role=='observation' and 'available_on' in field:
                    declared=[t['id'] for t in p['triggers']]
                    available=field['available_on']
                    require(isinstance(available,list) and bool(available)
                            and len(available)==len(set(available))
                            and all(t in declared for t in available),
                            'Observation available_on must contain unique declared Process triggers')
                semantic_ident(field['id'],f'Process {name} ID')
                require(field['id'] not in fields,f'duplicate specification field {field["id"]}')
                field['domain']=resolve_domain_types(field['domain'])
                validate_domain(field['domain']);fields[field['id']]=field

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
        for d in definitions.values():
            require(not _member_parents(d['body']),'record member projections must be bound directly in PI/TCE, not hidden in DomainRule')
            inspect_expr(d['body'],fields,definitions,d['params'])
    for predicate in constraints:
        if contract=='markdown-v2':_bind_member_refs(predicate,pi_fields)
        else:require(not _member_parents(predicate),'record projection requires markdown-v2 Source')
        require(inspect_expr(predicate,pi_fields,definitions)=='boolean','PI constraint must be boolean')

    # A flattened inventory is retained for old source/model readers, but
    # normative Guard-space evaluation is bound to the owning PI's accept
    # operations. A provide-only constraint describes a later result, not an
    # unobserved input at request start; it stays unproved until a result-time
    # relation verifier is supplied. No name-based or product-specific rules.
    pi_constraint_scopes=[]
    unbound_pi_constraints=[]
    for pi_id, predicate in pi_constraint_sources:
        refs=used_refs(predicate,definitions)
        require(all(ref in pi_fields and pi_fields[ref]['source_pi']==pi_id
                    for ref in refs),
                'PI constraint references a field outside its owning PI: '+pi_id)
        input_only=all(pi_fields[ref]['role']=='input' for ref in refs)
        accepted=sorted({op['trigger'] for op in pi_operations
                         if op['source_pi']==pi_id and op['direction']=='accept'})
        active=accepted if input_only else []
        for trigger in active:
            for parent in _member_parents(predicate):
                require(_trigger_input_presence(fields[parent],_input_operation_bindings(pi_operations,trigger),operation_presence)=='required',
                        'record projection parent is not required on accepted Operation')
        pi_constraint_scopes.append({'source_pi':pi_id,'expr':predicate,
                                     'triggers':active})
        if not active and contract=='markdown-v2':
            unbound_pi_constraints.append({'source_pi':pi_id,'expr':predicate,
                'reason':'non-input result relation' if not input_only
                         else 'no accepted Operation to bind PI constraint'})

    rules=[]
    local_coverage_requirements={}
    for _,tce_fm,tce in tce_docs:
        check_keys(tce,['schema','kind','process','coverage','rules'],where='TCE')
        require(tce['coverage'] in ('closed','partial'),'coverage requirement must be closed or partial')
        require(isinstance(tce['rules'],list) and tce['rules'],'TCE behaviors required')
        local_coverage_requirements[tce_fm['id']]=tce['coverage']
        for r in tce['rules']:
            check_keys(r,['id','trigger','when','allowed'],where='TCE behavior')
            (semantic_ident(r['id'],'TCE behavior id') if contract=='markdown-v2' else ident(r['id'],'TCE rule id'))
            require(r['trigger'] in {t['id'] for t in p['triggers']},'undeclared trigger '+str(r['trigger']))
            if contract=='markdown-v2':_bind_member_refs(r['when'],fields)
            else:require(not _member_parents(r['when']),'record projection requires markdown-v2 Source')
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
                    if contract=='markdown-v2':_bind_member_refs(e['expr'],fields)
                    else:require(not _member_parents(e['expr']),'record projection requires markdown-v2 Source')
                    produced=inspect_expr(e['expr'],fields,definitions)
                    expected=fields[e['target']]['domain']['type']
                    # Direct references preserve their full declared Domain, not only
                    # the top-level type. Python == would equate enum true with 1.
                    # A partial or unbounded subtype proof cannot license an Effect.
                    # Identical unresolved aliases retain Draft status (never Confirmed).
                    expression=e['expr'];target_domain=fields[e['target']]['domain']
                    if set(expression)=={'ref'} and expression['ref'] in fields:
                        source_domain=fields[expression['ref']]['domain']
                        inclusion=semantic_subtyping.subset(source_domain,target_domain)
                        if inclusion is not True:
                            inclusion=semantic_subtyping.subset(_guarded_source_domain(source_domain,r['when'],expression['ref']),target_domain)
                        if inclusion is None and _unresolved_domain(source_domain):
                            # Deferred name resolution is permitted only for an
                            # identical unresolved alias or an exact union arm.
                            inclusion=(typed.same(source_domain,target_domain)
                                or (expected=='union' and any(
                                    typed.same(source_domain,variant)
                                    for variant in target_domain['variants']))
                                or (expected=='nullable' and
                                    typed.same(source_domain,target_domain['of'])))
                        require(inclusion is True,
                                f'Effect {e["target"]}: type mismatch, {produced} -> {expected}')
                    elif expression.get('op') in collection_relation.OPERATORS:
                        require(semantic_subtyping.subset(collection_relation.operator_domain(expression,fields),target_domain) is True,
                                f'Effect {e["target"]}: collection Domain mismatch')
                    elif expression.get('op')=='member':
                        require(semantic_subtyping.subset(_member_domain(expression,fields),target_domain) is True,
                                f'Effect {e["target"]}: projected member Domain mismatch')
                    elif 'literal' in expression:
                        # A literal that has the right broad kind may still fall
                        # outside a range, format, collection, or enum Domain.
                        try:
                            literal_accepted=typed.contains(target_domain,expression['literal'])
                        except typed.DomainError as exc:
                            raise Blocked(f'Effect {e["target"]}: unresolved domain: {exc}') from exc
                        require(literal_accepted,
                                f'Effect {e["target"]}: type mismatch, {produced} -> {expected}')
                    else:
                        # Legacy operator expressions retain their independent
                        # expression type check; runtime range proof is separate.
                        require(produced==expected,
                                f'Effect {e["target"]}: type mismatch, {produced} -> {expected}')
                    if expected=='enum':
                        expr=e['expr']
                        if 'literal' in expr:
                            require(in_domain(fields[e['target']]['domain'],expr['literal']),'enum literal not in Effect target domain')
                        elif expr.get('op')=='member':
                            require(semantic_subtyping.subset(_member_domain(expr,fields),fields[e['target']]['domain']) is True,
                                    'member enum not subset of effect enum')
                        elif 'ref' in expr and expr['ref'] in fields and fields[expr['ref']]['domain']['type']=='enum':
                            require(all(in_domain(fields[e['target']]['domain'],x) for x in fields[expr['ref']]['domain']['values']),'source enum not subset of effect enum')
                        else:
                            raise Blocked('effect enum range not proven; explicit enum mapping required')
                    targets.append(e['target'])
                unique(targets,'Effect targets')
                frame=sorted(f for f in fields if fields[f]['role']=='state' and f not in targets)
                absent=sorted(f for f in fields if fields[f]['role'] in ('output','action') and f not in targets)
                outcomes.append({'write':outcome['write'],'unchanged':frame,'absent_outputs':absent})
            rules.append({'id':r['id'],'trigger':r['trigger'],'when':r['when'],'allowed':outcomes,
                          'source_artifact':tce_fm['id']})
    unique([r['id'] for r in rules],'TCE behaviors')

    if contract=='markdown-v2':
        # A PI input is an event-bound input, never Process state. Another
        # Operation's inputs cannot be borrowed by a TCE Condition/Effect,
        # even if finite Guard enumeration would make its truth table look
        # complete. Retaining the value needs an explicit Process State or
        # independently declared Observation with lawful provenance.
        for rule in rules:
            accepted=[op for op in pi_operations if op['direction']=='accept'
                      and op.get('trigger')==rule['trigger']]
            member_parents=_member_parents(rule['when'])
            for outcome in rule['allowed']:
                for write in outcome['write']:member_parents.update(_member_parents(write['expr']))
            if len(accepted)>1:
                require(not member_parents,'member projection requires unambiguous accepted Operation')
                continue  # The existing ambiguous-Operation audit fails closed.
            input_owners=_input_operation_bindings(pi_operations,rule['trigger'])
            for parent in member_parents:
                require(len(accepted)==1 and accepted[0]['source_pi']==fields[parent].get('source_pi') and
                        _trigger_input_presence(fields[parent],input_owners,operation_presence)=='required',
                        'member projection parent unavailable or nonrequired on this Operation')
            refs=used_refs(rule['when'],definitions)
            for outcome in rule['allowed']:
                for write in outcome['write']:
                    refs.update(used_refs(write['expr'],definitions))
            invalid=sorted(ref for ref in refs if ref in pi_fields
                           and pi_fields[ref]['role']=='input'
                           and pi_fields[ref]['source_pi'] not in input_owners)
            require(not invalid,
                    f'TCE {rule["id"]} reads PI input from inactive accepted Operation at {rule["trigger"]}: {invalid}')
            unavailable=sorted(ref for ref in refs if ref in fields
                               and fields[ref]['role']=='observation'
                               and 'available_on' in fields[ref]
                               and rule['trigger'] not in fields[ref]['available_on'])
            require(not unavailable,
                    f'TCE {rule["id"]} reads Observation unavailable at Trigger {rule["trigger"]}: {unavailable}')

    effect_checks=_effect_totality_checks(
        rules,fields,definitions,pi_operations=pi_operations,
        operation_presence=operation_presence)
    guard_invariants=_proved_guard_invariants(rule_docs,fields,p['process'],rules,effect_checks,
        all(fm['status']=='confirmed' for _,fm in files))
    from catlib import semantic_observation_relation
    observation_relations=semantic_observation_relation.prove(rule_docs,p['process'],fields,
        {t['id'] for t in p['triggers']},all(fm['status']=='confirmed' for _,fm in files))
    observation_proof_ids={rid for rels in observation_relations.values() for rid in rels}
    from catlib import semantic_transition_relation
    transition_proofs={r['id'] for doc in rule_docs for r in doc['rules']
        if all(fm['status']=='confirmed' for _,fm in files) and doc['process']==p['process']
        and doc['kind']=='domain-spec' and doc['scope_verified']
        and semantic_transition_relation.matches(r.get('requirement'),r.get('condition'))
        and r.get('verification_contract')=='cat:intrinsic-model/v1'
        and semantic_transition_relation.prove(r['condition'],fields,pi_docs,rules,effect_checks,guard_invariants.values(),observation_relations)}
    from catlib.output_frame_contract import declarations, validate_declarations
    explicit_frames=declarations(pi_docs)
    try:validate_declarations(explicit_frames,fields,pi_operations,operation_presence,rules,p['triggers'])
    except ValueError as exc:raise Blocked(str(exc)) from exc
    intrinsic_proofs=semantic_intrinsic_rules.evaluate(
        rule_docs,list(fields.values()),p['triggers'],rules,pi_operations,
        operation_presence,effect_checks,guard_invariants,transition_proofs,observation_proof_ids,explicit_frames)
    per_trigger={}; triggers=[t['id'] for t in p['triggers']]
    # A nonrequired output is provable only when a unique provided PI
    # operation owns its output and every TCE alternative respects the
    # presence-specific emission frame. Missing/undefined are never coerced.
    presence_unproven=_unproved_output_presence(
        fields,pi_operations,operation_presence,rules,triggers,explicit_frames)
    for trigger in triggers:
        rr=[r for r in rules if r['trigger']==trigger]
        operation,ambiguous=_presence_accepted_operation(pi_operations,trigger)
        if ambiguous:
            per_trigger[trigger]={'result':'unproven','reason':ambiguous}
            presence_unproven.update(
                f['id'] for f in pi_fields.values() if f['role']=='input')
            continue
        bindings=_input_operation_bindings(pi_operations,trigger)
        input_presence={
            field_id:_trigger_input_presence(field,bindings,operation_presence)
            for field_id,field in pi_fields.items() if field['role']=='input'
        }
        special={field_id for field_id,presence in input_presence.items() if presence!='required'}
        scoped_constraints = ([x['expr'] for x in pi_constraint_scopes
                               if trigger in x['triggers']]
                              if contract=='markdown-v2' else constraints)
        has_pi_constraints=bool(scoped_constraints)
        trigger_observations=observation_relations.get(trigger,{})
        scoped_constraints=[*scoped_constraints,*guard_invariants.values(),*trigger_observations.values()]
        relevant=set().union(
            *(used_refs(r['when'],definitions) for r in rr),
            *(used_refs(c,definitions) for c in scoped_constraints)) if rr or scoped_constraints else set()
        # Optional Presence is relevant to Guard closure only if the
        # normative Guard or PI constraint actually observes this field.
        # Otherwise all present/missing values share the same truth profile.
        # An Effect reading a missing/undefined input cannot be proved total
        # merely because the guards cover all states; keep such a contract open.
        effect_reads=set().union(
            *(used_refs(w['expr'],definitions) for r in rr for outcome in r['allowed']
              for w in outcome['write'])) if rr else set()
        unsafe_effect_reads={ref for r in rr for outcome in r['allowed']
                             for write in outcome['write']
                             for ref in used_refs(write['expr'],definitions) & special
                             if not _guard_guarantees_present(r['when'],ref)}
        if unsafe_effect_reads:
            per_trigger[trigger]={'result':'unproven','reason':'Effect reads a non-required PI input',
                                  'guard_refs':sorted(relevant)}
            presence_unproven.update(unsafe_effect_reads)
            continue
        ordered=sorted(relevant)
        domainvalues=[]
        partition_fields=[]
        partition_kinds=set()
        predicates=[*scoped_constraints,*(r['when'] for r in rr)]
        projected=_record_projection_values(fields,ordered,predicates,input_presence,definitions,guard_only=True)
        integer_pair=_integer_reference_equality_values(
            fields,ordered,predicates,input_presence,definitions)
        integer_range=({} if integer_pair else _integer_reference_range_values(
            fields,ordered,predicates,input_presence,definitions))
        raw_count=__import__('math').prod(len(v) if v is not None else 1 for v in
            (_presence_cases(fields[k]['domain'],input_presence[k]) if k in input_presence
             else typed.finite_values(fields[k]['domain']) for k in ordered)) if integer_pair else 0
        real_range=_real_reference_range_values(fields,ordered,predicates,input_presence,definitions)
        linear_range=_linear_order_values(fields,ordered,predicates,input_presence,definitions)
        string_pair=_string_reference_values(fields,ordered,predicates,input_presence)
        nullable_pair=semantic_string_partition.nullable_reference_cells({n:fields[n]['domain'] for n in ordered},predicates,input_presence)
        for field_id in ordered:
            if projected:
                domainvalues.append(projected[field_id]);partition_fields.append(field_id);partition_kinds.add('record_member');continue
            field=fields[field_id]
            values=(_presence_cases(field['domain'],input_presence[field_id])
                    if field_id in input_presence else typed.finite_values(field['domain']))
            if field_id in string_pair:
                values=string_pair[field_id]
                partition_fields.append(field_id)
                partition_kinds.add('string_ref')
            if field_id in nullable_pair:
                values=nullable_pair[field_id]
                if field_id not in partition_fields:partition_fields.append(field_id)
                partition_kinds.add('nullable_ref_equality')
            if field_id in linear_range:
                values=linear_range[field_id]
                partition_fields.append(field_id)
                partition_kinds.add('linear_order')
            if field_id in real_range:
                values=real_range[field_id]
                partition_fields.append(field_id)
                partition_kinds.add('real_ref_range')
            if field_id in integer_range:
                # Values for every coupled reference must come from the same
                # Domain-endpoint/literal cuts. A per-field interval sampler
                # would not preserve x<y when x and y occupy the same cell.
                values=integer_range[field_id]
                partition_fields.append(field_id)
                partition_kinds.add('integer_ref_range')
            if (values is None and field_id in input_presence
                    and input_presence[field_id]=='optional'
                    and all(_presence_only_guard_use(predicate,field_id) for predicate in predicates)):
                # Every predicate sees presence only, not the arbitrary value.
                # A marker represents the entire class of present values.
                values=[typed.MISSING,_PRESENT_GUARD_VALUE]
            if values is None and (field_id not in input_presence
                                   or input_presence[field_id]=='required'):
                values=semantic_interval_partition.integer_partition_values(
                    field['domain'],field_id,predicates)
                if values is not None:
                    partition_fields.append(field_id)
                    partition_kinds.add('integer')
            if values is None and (field_id not in input_presence
                                   or input_presence[field_id]=='required'):
                values=semantic_string_partition.string_partition_values(
                    field['domain'],field_id,predicates)
                if values is not None:
                    partition_fields.append(field_id)
                    partition_kinds.add('string')
            if values is None and (field_id not in input_presence
                                   or input_presence[field_id]=='required'):
                values=semantic_string_partition.nullable_string_null_partition(field['domain'],field_id,predicates)
                if values is not None:
                    partition_fields.append(field_id)
                    partition_kinds.add('nullable_string_null')
            if values is None and (field_id not in input_presence
                                   or input_presence[field_id]=='required'):
                values=semantic_interval_partition.real_partition_values(field['domain'],field_id,predicates)
                if values is not None:
                    partition_fields.append(field_id)
                    partition_kinds.add('real')
            if values is None and (field_id not in input_presence or input_presence[field_id]=='required'):
                values=semantic_interval_partition.sequence_length_values(field['domain'],field_id,predicates)
                if values is not None:
                    partition_fields.append(field_id)
                    partition_kinds.add('sequence_length')
            if values is None and input_presence.get(field_id)=='optional':
                present=semantic_interval_partition.integer_partition_values(
                    field['domain'],field_id,predicates,allow_presence=True)
                kind='optional_integer'
                if present is None:
                    present=semantic_string_partition.string_partition_values(
                        field['domain'],field_id,predicates,allow_presence=True)
                    kind='optional_string'
                if present is not None:
                    values=[typed.MISSING,*present]
                    partition_fields.append(field_id)
                    partition_kinds.add(kind)
            if field_id in integer_pair and (values is None or raw_count>65536):
                values=integer_pair[field_id]
                partition_fields.append(field_id)
                partition_kinds.add((
                    'integer_ref_multi_order' if any(
                        _has_pair_order_comparison(clause) for clause in predicates)
                    else 'integer_ref_multi_equality') if len(integer_pair)>=3 else (
                    'integer_ref_order' if any(
                        _has_pair_order_comparison(clause) for clause in predicates)
                    else 'integer_ref_pair'))
            domainvalues.append(values)
        if any(values is None for values in domainvalues):
            per_trigger[trigger]={'result':'unproven',
                                  'reason':'guard reads non-finite or too-large domain/Presence',
                                  'guard_refs':ordered}
            presence_unproven.update(special & relevant)
            continue
        combinations=__import__('math').prod(len(x) for x in domainvalues)
        cache=(_large_finite_predicate_cache(ordered,domainvalues,predicates,definitions)
               if combinations>65536 else None)
        masks=None
        if combinations>65536 and cache is None and not any(
                any(v is _PRESENT_GUARD_VALUE for v in dim) for dim in domainvalues):
            from catlib.finite_truth_masks import truth_masks
            masks=truth_masks(ordered,domainvalues,scoped_constraints,[r['when'] for r in rr],
                              definitions,eval_expr,used_refs,Blocked)
        if combinations>65536 and cache is None and masks is None:
            # Solver capacity is an absence of proof, not a domain mismatch.
            # Shadow/partial models retain the source-bound reason; normative
            # compilation still blocks unless an independent proof is supplied.
            per_trigger[trigger]={'result':'unproven',
                                  'reason':'finite closure exceeds configured 65536 combinations and factorized proof budget',
                                  'combination_count':combinations,
                                  'guard_refs':ordered}
            presence_unproven.update(special & relevant)
            continue
        gaps=[];overlaps=[];unreachable=set(r['id'] for r in rr);unknown=None
        admissible=0;gap_count=overlap_count=0
        if masks is not None:
            from catlib.finite_truth_masks import row_indices, first_indices
            accepted,hits=masks
            admissible=accepted.bit_count();seen=collision=0
            for rule,hit in zip(rr,hits):
                if hit:unreachable.discard(rule['id'])
                collision|=seen&hit;seen|=hit
            missing=accepted^seen
            gap_count=missing.bit_count();overlap_count=collision.bit_count()
            def env_at(i):return {k:d[j] for k,d,j in zip(ordered,domainvalues,row_indices(i,domainvalues))}
            gaps=[_debug_presence_env(env_at(i)) for i in first_indices(missing,64)]
            overlaps=[{'state':_debug_presence_env(env_at(i)),
                       'rules':[r['id'] for r,hit in zip(rr,hits) if (hit>>i)&1]}
                      for i in first_indices(collision,16)]
        rows=(() if masks is not None else
              itertools.product(*(range(len(d)) for d in domainvalues)) if cache is not None
              else itertools.product(*domainvalues))
        for values in rows:
            env=None if cache is not None else dict(zip(ordered,values))
            try:
                if cache is not None:
                    if not all(fn(values) for fn in cache[:len(scoped_constraints)]):continue
                    admissible+=1
                    hit=[r['id'] for r,fn in zip(rr,cache[len(scoped_constraints):]) if fn(values)]
                else:
                    if not all(eval_expr(c,env,definitions) for c in scoped_constraints):continue
                    admissible+=1
                    hit=[r['id'] for r in rr if eval_expr(r['when'],env,definitions)]
            except Blocked as exc:
                unknown=str(exc)
                break
            if not hit or len(hit)>1:
                if env is None:env={k:d[i] for k,d,i in zip(ordered,domainvalues,values)}
                if not hit:
                    gap_count+=1
                    if len(gaps)<64:gaps.append(_debug_presence_env(env))
                else:
                    overlap_count+=1
                    if len(overlaps)<16:overlaps.append({'state':_debug_presence_env(env),'rules':hit})
            unreachable-=set(hit)
        if unknown:
            per_trigger[trigger]={'result':'unproven','reason':unknown,
                                  'guard_refs':ordered}
            presence_unproven.update(special & relevant)
            continue
        if not admissible:
            # A closed truth table over zero accepted states is vacuous.
            # It does not establish an executable Trigger's Source closure.
            per_trigger[trigger]={'result':'unproven',
                                  'reason':'no admissible Source-constrained Guard state',
                                  'guard_refs':ordered,
                                  'unreachable_rules':sorted(unreachable),
                                  'excluded_by_pi_constraints':has_pi_constraints}
            presence_unproven.update(special & relevant)
            continue
        require(allow_draft or not overlaps,'overlapping TCE behaviors: '+json.dumps(overlaps[:4],ensure_ascii=False))
        check={'result':'conflict' if overlaps else 'proved' if not gaps else 'uncovered',
               'guard_refs':ordered,'overlap_count':overlap_count if not partition_fields else None,
               'overlaps':overlaps[:16],'uncovered':gaps[:64],
               'uncovered_count':gap_count if not partition_fields else None,
               'unreachable_rules':sorted(unreachable),
               'excluded_by_pi_constraints':has_pi_constraints}
        if guard_invariants:check['guard_invariant_rule_ids']=sorted(guard_invariants)
        if trigger_observations:check['observation_relation_rule_ids']=sorted(trigger_observations)
        if partition_fields:
            method=('integer-literal-partition/v1' if partition_kinds=={'integer'}
                    else 'string-literal-equality-partition/v1' if partition_kinds=={'string'}
                    else 'string-reference-equality-partition/v1' if partition_kinds=={'string_ref'}
                    else 'nullable-string-null-partition/v1' if partition_kinds=={'nullable_string_null'}
                    else 'nullable-reference-equality-partition/v1' if partition_kinds=={'nullable_ref_equality'}
                    else 'sequence-length-literal-partition/v1' if partition_kinds=={'sequence_length'}
                    else 'real-literal-order-partition/v1' if partition_kinds=={'real'}
                    else 'real-reference-order-partition/v1' if partition_kinds=={'real_ref_range'}
                    else 'two-reference-linear-order-partition/v1' if partition_kinds=={'linear_order'}
                    else 'required-record-member-partition/v1' if partition_kinds=={'record_member'}
                    else 'optional-string-literal-equality-partition/v1' if partition_kinds=={'optional_string'}
                    else 'optional-integer-literal-partition/v1' if partition_kinds=={'optional_integer'}
                    else 'integer-reference-equality-partition/v1' if partition_kinds=={'integer_ref_pair'}
                    else 'integer-reference-order-partition/v1' if partition_kinds=={'integer_ref_order'}
                    else 'integer-reference-equality-partition/v2' if partition_kinds=={'integer_ref_multi_equality'}
                    else 'integer-reference-order-partition/v2' if partition_kinds=={'integer_ref_multi_order'}
                    else 'integer-reference-range-order-partition/v1' if partition_kinds=={'integer_ref_range'}
                    else 'mixed-exact-predicate-partition/v1')
            check.update(proof_method=method,
                         partition_fields=partition_fields,
                         abstract_state_count=combinations,
                         proof_scope='local-guard-truth-partition-not-effect-or-implementation')
        per_trigger[trigger]=check
        require(allow_draft or not unreachable,'unreachable TCE behavior(s): '+str(sorted(unreachable)))
    presence_unproven=sorted(presence_unproven)
    coverage_proved = (p['closed_world'] and all(x['result']=='proved' for x in per_trigger.values())
                       and not presence_unproven and not unbound_pi_constraints
                       and not (unresolved_interfaces if contract=='markdown-v2' else [])
                       )
    if not coverage_proved:
        require(allow_draft or allow_partial,
                'assembled Process closed-world coverage requirement not proved: '+json.dumps({'closed_world':p['closed_world'],'tce':local_coverage_requirements,'presence':presence_unproven,'triggers':per_trigger},ensure_ascii=False)[:700])

    source_records=[]
    hashes={}
    for path,fm in files:
        digest=hashlib.sha256(Path(path).read_bytes()).hexdigest()
        source_records.append({'id':fm['id'],'kind':fm['kind'],'sha256':digest})
        key=fm['kind'] if fm['kind'] not in hashes else fm['kind']+':'+fm['id']
        hashes[key]=digest
    authority={'markdown-v2':'cat-markdown/v2','markdown-v1':'cat-markdown/v1','machine-only':'cat-machine/v2'}[contract]
    unresolved_domains=sorted(x['id'] for x in fields.values() if _unresolved_domain(x['domain']))
    # A rule can be proved here only when the *authorized source itself*
    # declares one of the exact, fully decidable model predicates.
    # Runtime fixtures and free-text Rule verification do not qualify.
    # Establish selected Effect value totality before certifying a fresh output.
    proven_rule_ids={proof['rule_id'] for proof in intrinsic_proofs}
    for rule in rule_obligations:
        if rule['id'] in proven_rule_ids:
            rule['verification_status']='intrinsic-proved'
    unverified_rule_ids=sorted({r['id'] for r in rule_obligations
                                if r['verification_status']!='not-applicable'}-proven_rule_ids)
    # Guard coverage does not prove all Effect expressions total and in Domain.
    unverified_effect_ids=sorted(key for key,proof in effect_checks.items()
                                 if proof['result']!='proved')
    normative_model = (all(fm['status']=='confirmed' for _,fm in files)
                       and coverage_proved and not unresolved_domains
                       and not unverified_rule_ids and not unverified_effect_ids)
    result={'schema':M,'process':p['process'],'status':('confirmed' if normative_model else 'draft'),
            'semantic_authority':authority,'language':tf.get('language','en') if contract=='markdown-v2' else 'en',
            'source_artifacts':[fm['id'] for _,fm in files],
            'source_records':source_records,
            'source_sha256':hashes,'triggers':p['triggers'],'fields':list(fields.values()),'pi_constraints':constraints,
            **({'pi_constraint_scopes':pi_constraint_scopes,
                'unbound_pi_constraints':unbound_pi_constraints} if contract=='markdown-v2' else {}),
            'definitions':list(definitions.values()),'coverage_requirement':'closed' if coverage_proved else 'partial',
            'local_coverage_requirements':local_coverage_requirements,
            'coverage_checks':per_trigger,'rules':rules,
            'model_type':'symbolic-relation','limits':['finite-guard-closure-only','no-general-reachability-proof','no-process-composition']}
    result['coverage_claim']='closed' if coverage_proved else 'partial'
    result['presence_unproven']=presence_unproven
    result['unresolved_domains']=unresolved_domains
    result['unresolved_interfaces']=unresolved_interfaces if contract=='markdown-v2' else []
    result['pi_artifacts']=[fm['id'] for _,fm,_ in pi_docs]
    result['rule_obligations']=rule_obligations
    result['normative_rule_inputs']=[{'id':d['id'],'kind':d['kind'],'process':d['process'],
                                      'sha256':d['sha256']} for d in rule_docs]
    result['named_type_definitions']=resolved_type_definitions
    result['unverified_rule_ids']=unverified_rule_ids
    result['effect_checks']=effect_checks
    result['unverified_effect_ids']=unverified_effect_ids
    result['intrinsic_rule_proofs']=intrinsic_proofs
    tce_map=[]
    for _,tce_fm,_ in tce_docs:
        owned=[x for x in rules if x.get('source_artifact')==tce_fm['id']]
        tce_map.append({'artifact':tce_fm['id'],'rules':[x['id'] for x in owned],
                        'outcome_count':sum(len(x['allowed']) for x in owned),
                        'local_coverage':local_coverage_requirements[tce_fm['id']]})
    result['source_semantic_map']={
        'process':{
            'artifact':pf['id'],
            'triggers':[x['id'] for x in p['triggers']],
            'interfaces':list(p.get('interfaces',[])),
            'state':[x['id'] for x in p.get('state_fields',[])],
            'observations':[x['id'] for x in p.get('observations',[])],
            'actions':[x['id'] for x in p.get('actions',[])]},
        'pi':{
            'artifact':pif['id'] if len(pi_docs)==1 else None,
            'artifacts':[fm['id'] for _,fm,_ in pi_docs],
            'fields':list(pi_fields),
            'operations':[x['id'] for x in pi_operations],
            'constraint_count':len(constraints)},
        'tce':tce_map,
        'common_rules':[d['id'] for d in rule_docs if d['kind']=='common-rule'],
        'domain_specs':[d['id'] for d in rule_docs if d['kind']=='domain-spec'],
        'type_definitions':[d['id'] for d in resolved_type_definitions],
        'domain_rule':{
            'artifact':dfile['id'] if dfile else None,
            'definitions':sorted(definitions)}}
    if contract=='markdown-v2':
        result['pi_boundary']=pi_docs[0][2]['boundary'] if len(pi_docs)==1 else None
        result['pi_boundaries']=[{'artifact':fm['id'],**spec['boundary']} for _,fm,spec in pi_docs]
        result['pi_operations']=pi_operations
        result['operation_presence']=operation_presence
        if explicit_frames:result['output_frames']=explicit_frames
        result['process_interfaces']=p.get('interfaces',[])
    if contract in ('markdown-v1','markdown-v2'):result['normalized_ir']='cat-machine/v2'
    return result

def match_rules(model, trigger, env):
    defs={d['id']:d for d in model['definitions']}
    matched=[r for r in model['rules'] if r['trigger']==trigger and eval_expr(r['when'],env,defs)]
    require(len(matched)==1,f'test vector has {len(matched)} matching TCE rules at {trigger}')
    return matched[0]

def _vector_operation(model,test):
    matches=[op for op in model.get('pi_operations',[])
             if op['direction']=='accept' and op.get('trigger')==test['trigger']]
    specified=test.get('operation')
    if specified is None:
        require(len(matches)<=1,
                'ambiguous accepted PI operations for trigger; vector.operation required')
        return matches[0] if matches else None
    matching=[op for op in matches if op['id']==specified]
    require(len(matching)==1,'vector.operation not accepted for trigger')
    return matching[0]


def _vector_field_presence(model,operation,field):
    presence=field.get('presence','required')
    if operation is None or field.get('source_pi')!=operation.get('source_pi'):
        return presence
    matched=[x for x in model.get('operation_presence',[])
             if x['operation']==operation['id'] and x['field']==field['id']]
    require(len(matched)<=1,'ambiguous per-operation field presence')
    return matched[0]['presence'] if matched else presence


def _exact_value_kind(domain):
    while domain.get('type')=='reference' and domain.get('resolved'):
        domain=domain['of']
    return domain.get('type') if domain.get('type') in ('json','instant') else None


def _encode_vector_value(domain,value):
    kind=_exact_value_kind(domain)
    if kind=='json':return json_time.encode_json_transport(value)
    if kind=='instant':return json_time.encode_instant_transport(value)
    return value


def _decode_vector_value(domain,value):
    kind=_exact_value_kind(domain)
    if kind=='json':return json_time.decode_json_transport(value)
    if kind=='instant':return json_time.decode_instant_transport(value)
    return value


def _vector_input_value(domain,presence,payload,name,exact_values=False):
    if name not in payload:
        require(presence in ('optional','absent'),
                'vector missing required/undefined input '+name)
        return typed.MISSING
    value=payload[name]
    if presence=='undefined' and value=={'$cat_presence':'undefined'}:
        return typed.UNDEFINED
    require(presence not in ('absent','undefined'),
            'value input incompatible with Presence '+name)
    if exact_values:value=_decode_vector_value(domain,value)
    require(in_domain(domain,value), 'input out of domain '+name)
    return value



def _explicit_vector_frames(model,fields,rule):
    from catlib.output_frame_contract import active_frames, declared_owners
    rows=model['output_frames']; owners=declared_owners(rows)
    operations=model.get('pi_operations',[])
    legacy_fields={k:f for k,f in fields.items() if f.get('source_pi') not in owners}
    legacy_ops=[op for op in operations if op['source_pi'] not in owners]
    legacy_overrides=[ov for ov in model.get('operation_presence',[]) if ov['field'] in legacy_fields]
    legacy=_provided_output_frames(legacy_fields,legacy_ops,legacy_overrides,rule['trigger'])
    require(legacy is not None or not any(f['role']=='output' for f in legacy_fields.values()),
            'explicit frames with unresolved legacy output transport')
    alternatives=[{**(legacy or {}),**active_frames(rows,operations,rule['trigger'],rule['id'],n)}
                  for n in range(1,len(rule['allowed'])+1)]
    require(bool(alternatives),'empty allowed result')
    return alternatives


def _vector_output_operations(model,test,fields,rule=None):
    overrides=model.get('operation_presence',[])
    declared=[x for x in overrides if fields[x['field']]['role']=='output']
    operations=model.get('pi_operations',[])
    frames=_provided_output_frames(fields,operations,overrides,test['trigger'])
    chosen=test.get('output_operation')
    if 'output_operations' in test:
        many=test['output_operations']
        require('output_operation' not in test,
                'vector.output_operation and output_operations are mutually exclusive')
        require(isinstance(many,list) and len(many)>1
                and all(isinstance(x,str) for x in many) and len(set(many))==len(many),
                'vector.output_operations requires distinct operation IDs')
        require(frames is not None and set(many)=={x['id'] for x in frames.values()},
                'vector.output_operations must match every source-bound provided operation for trigger')
        return frames
    require(frames is None or len(frames)<=1,
            'multiple source-bound providers require vector.output_operations')
    if frames == {}:
        require(chosen is None, 'inactive provided output frame cannot select an operation')
        return {}
    if declared or _nonrequired_output_ids(fields,overrides):
        require(chosen is not None,
                'nonrequired/operation-scoped output Presence requires vector.output_operation')
    if chosen is None:return {}
    ops=[x for x in operations if x['direction']=='provide'
         and (x.get('trigger') is None or x['trigger']==test['trigger'])]
    require(len(ops)==1 and ops[0]['id']==chosen,
            'vector.output_operation is not a unique provided operation for trigger')
    op=ops[0]
    require(all(x['source_pi']==op['source_pi'] for x in declared
                if x['operation']==op['id']),
            'output Presence override belongs to another PI')
    return {op['source_pi']:op}


def _vector_observation_context(model, trigger, fields):
    """Concrete test environment witnesses, not caller input or runtime evidence.

    Normative CLI independently checks the model against Source before selection.
    Retain the approved finite trigger-entry scope and proved restrictions here.
    """
    from catlib import semantic_transition_relation as relation
    from catlib import semantic_observation_relation as observation
    proofs=model.get('intrinsic_rule_proofs',[])
    if not any(f.get('role')=='observation' for f in fields.values()) and not any(
            p.get('requirement') in (relation.OBS_TOKEN,observation.TOKEN) for p in proofs):
        return [],[]
    defs={d['id']:d for d in model['definitions']}
    inventory=set();constraints=[];constraint_ids=[]
    def verified(proof):
        require(proof.get('status')=='passed' and proof.get('verification_contract')=='cat:intrinsic-model/v1'
                and proof.get('proof_method')=='cat:intrinsic-model/v1',
                'observation witness requires passed intrinsic proof')
        require(any(x.get('id')==proof.get('rule_id') and x.get('condition')==proof.get('scope')
                    and x.get('requirement')==proof.get('requirement')
                    and x.get('verification_contract')==proof.get('verification_contract')
                    and x.get('verification_status')=='intrinsic-proved'
                    and x.get('source_artifact')==proof.get('source_artifact')
                    and x.get('source_sha256')==proof.get('source_sha256')
                    and x.get('source_kind')=='domain-spec'
                    for x in model.get('rule_obligations',[]))
                and any(x.get('id')==proof.get('source_artifact') and x.get('kind')=='domain-spec'
                        and x.get('sha256')==proof.get('source_sha256')
                        and x.get('process')==model.get('process')
                        for x in model.get('normative_rule_inputs',[])),
                'observation proof is not bound to normative Source')
    for proof in proofs:
        token=proof.get('requirement');scope=proof.get('scope','')
        if token==relation.OBS_TOKEN:
            require(scope.startswith(relation.OBS_PREFIX),'invalid observed relation scope')
            try:spec=json.loads(scope[len(relation.OBS_PREFIX):],object_pairs_hook=relation._unique_object)
            except (ValueError,TypeError) as e:raise Blocked('invalid observed relation scope') from e
            require(isinstance(spec,dict),'invalid observed relation scope')
            if spec.get('trigger')!=trigger:continue
            verified(proof)
            required={'trigger','pi','operation','peer'}
            require(required<=spec.keys(),'incomplete observed relation scope')
            accept=[op for op in model.get('pi_operations',[]) if op.get('direction')=='accept' and op.get('trigger')==trigger]
            require(len(accept)==1 and accept[0].get('id')==spec['operation'] and accept[0].get('source_pi')==spec['pi'],
                    'observation witness accept scope mismatch')
            boundary=[b for b in model.get('pi_boundaries',[]) if b.get('artifact')==spec['pi']]
            require(len(boundary)==1 and peer_binding.match_operation(boundary[0].get('peers',[boundary[0].get('peer')]),accept[0].get('peer'),spec['peer'])=='static',
                    'observation witness peer scope mismatch')
            names=spec.get('observations')
            require(isinstance(names,list) and names and all(isinstance(n,str) for n in names) and len(set(names))==len(names),'invalid observation witness inventory')
            for name in names:
                field=fields.get(name,{})
                require(field.get('role')=='observation' and field.get('available_on')==[trigger] and field['domain']['type'] in ('boolean','enum'),
                        'unsupported observation witness domain or availability '+name)
                origin=field.get('source','');prefix='same-execution-observation '
                require(origin.startswith(prefix),'observation witness lacks explicit source '+name)
                try:binding=json.loads(origin[len(prefix):],object_pairs_hook=relation._unique_object)
                except (ValueError,TypeError) as e:raise Blocked('invalid observation source') from e
                require(isinstance(binding,dict) and set(binding)==required|{'cut','source'}
                        and all(binding[k]==spec[k] for k in required) and binding['cut']=='trigger-entry'
                        and isinstance(binding['source'],str) and binding['source'].strip(),
                        'observation witness source scope mismatch '+name)
                inventory.add(name)
        elif token==observation.TOKEN:
            require(scope.startswith(observation.PREFIX),'invalid observation constraint scope')
            cut,sep,expr=scope[len(observation.PREFIX):].partition(' ')
            require(sep and expr,'invalid observation constraint scope')
            if cut!=trigger:continue
            verified(proof);constraints.append(parse_expr_text(expr));constraint_ids.append(proof['rule_id'])
    check=model.get('coverage_checks',{}).get(trigger,{})
    require(set(constraint_ids)==set(check.get('observation_relation_rule_ids',[])),
            'observation constraint inventory differs from proved coverage')
    exprs=[*_active_pi_constraints(model,trigger),*_guard_invariant_exprs(proofs).values(),*constraints]
    for row in model['rules']:
        if row['trigger']==trigger:
            exprs.append(row['when'])
            exprs.extend(w['expr'] for out in row['allowed'] for w in out['write'])
    refs=set().union(*(used_refs(expr,defs) for expr in exprs)) if exprs else set()
    needed={n for n in refs if fields.get(n,{}).get('role')=='observation'}
    require(needed<=inventory and (not constraints or inventory),
            'observation relation requires explicit proved finite observation binding for vectors')
    if inventory:
        require(model.get('status')=='confirmed' and model.get('coverage_requirement')=='closed' and check.get('result')=='proved',
                'observation witness requires proved closed trigger')
    return sorted(inventory),constraints


def expand_cases(model, vectors):
    check_keys(vectors,['schema','process','cases'],optional=('selection_rule','semantic_value_transport'),where='vectors')
    require(vectors.get('semantic_value_transport') in (None,'cat-exact-values/v1'),'unsupported vector semantic value transport')
    exact_values=vectors.get('semantic_value_transport')=='cat-exact-values/v1'
    require(vectors['schema']==V and vectors['process']==model['process'],'vector version/Process mismatch')
    fields={f['id']:f for f in model['fields']}
    inputs={f for f in fields if fields[f]['role']=='input'}
    states={f for f in fields if fields[f]['role']=='state'}
    cases=[]
    for test in vectors['cases']:
        check_keys(test,['id','trigger','input','state'],optional=('operation','output_operation','output_operations','observations'),where='test vector')
        ident(test['id'],'test ID');require(test['trigger'] in {t['id'] for t in model['triggers']},'unknown vector trigger')
        require(isinstance(test['input'],dict) and isinstance(test['state'],dict),'vector input/state must be objects')
        operation=_vector_operation(model,test)
        require(set(test['input'])<=inputs and set(test['state'])==states,
                'vector input includes undeclared fields or omits state')
        observation_ids,observation_constraints=_vector_observation_context(model,test['trigger'],fields)
        payload=test.get('observations',{})
        require(isinstance(payload,dict) and set(payload)==set(observation_ids) and ('observations' not in test or observation_ids),
                'vector observations must match the proved trigger inventory')
        env={}
        for name,val in payload.items():
            require(in_domain(fields[name]['domain'],val),'observation out of domain '+name)
            env[name]=val
        # An explicit vector.operation resolves an otherwise ambiguous accept
        # operation without altering Source-level coverage/closure proofs.
        # The selected operation's Presence overrides must be used for this
        # witness, rather than discarding them because two accepts share a Trigger.
        bindings=_input_operation_bindings(model.get('pi_operations',[]),test['trigger'])
        if operation is not None:
            bindings[operation['source_pi']]=operation
        active_inputs=(set(inputs) if 'pi_constraint_scopes' not in model or operation is None
                       else {name for name in inputs if fields[name].get('source_pi') in bindings})
        require(set(test['input'])<=active_inputs,
                'vector contains input from an inactive PI Operation')
        for name in sorted(active_inputs):
            field=fields[name]
            presence=_trigger_input_presence(field,bindings,model.get('operation_presence',[]))
            val=_vector_input_value(field['domain'],presence,test['input'],name,exact_values)
            if val is not typed.MISSING:env[name]=val
        for name,val in test['state'].items():
            if exact_values:val=_decode_vector_value(fields[name]['domain'],val)
            require(in_domain(fields[name]['domain'],val),f'{test["id"]}: {name} out of declared domain')
            env[name]=val
        defs={d['id']:d for d in model['definitions']}
        # Presence-aware expressions may inspect missing/undefined inputs. An
        # ordinary read still fails inside eval_expr and cannot become an oracle.
        require(all(eval_expr(c,env,defs) for c in _active_pi_constraints(model,test['trigger'])),
                f'{test["id"]}: violates PI combination constraint')
        require(all(eval_expr(c,env,defs) for c in _guard_invariant_exprs(model.get('intrinsic_rule_proofs',[])).values()),
                f'{test["id"]}: violates proved state invariant')
        require(all(eval_expr(c,env,defs) is True for c in observation_constraints),
                f'{test["id"]}: violates proved observation relation')
        rule=match_rules(model,test['trigger'],env)
        explicit=bool(model.get('output_frames'))
        if explicit:
            alternative_frames=_explicit_vector_frames(model,fields,rule)
            inventory=sorted({op['id'] for frame in alternative_frames for op in frame.values()})
            require('output_operation' not in test and test.get('output_operations')==inventory,
                    'vector.output_operations must equal explicit source-bound provider inventory (including empty)')
        else:output_frames=_vector_output_operations(model,test,fields,rule)
        defs={d['id']:d for d in model['definitions']}
        allowed=[]
        for index,out in enumerate(rule['allowed']):
            if explicit:output_frames=alternative_frames[index]
            after={key:deepcopy(env[key]) for key in states}; emitted={}
            for write in out['write']:
                target=write['target'];val=eval_expr(write['expr'],env,defs)
                require(in_domain(fields[target]['domain'],val),f'{test["id"]}: output {target} out of declared domain')
                if fields[target]['role']=='state':after[target]=val
                else:emitted[target]=val
            if model.get('output_frames') or output_frames or _provided_output_frames(fields,model.get('pi_operations',[]),
                    model.get('operation_presence',[]),test['trigger']) == {}:
                require(all(fields[target].get('source_pi') in output_frames
                            for target in emitted if fields[target]['role']=='output'),
                        'output Effect belongs to another provided PI')
                for field in fields.values():
                    owner=field.get('source_pi')
                    if field['role']!='output' or owner not in output_frames:
                        continue
                    output_operation=output_frames[owner]
                    pres=_vector_field_presence(model,output_operation,field)
                    require(pres!='undefined',
                            'undefined output effect requires explicit technology transport')
                    require(pres!='required' or field['id'] in emitted,
                            'required output missing for operation '+output_operation['id']+': '+field['id'])
                    require(pres!='absent' or field['id'] not in emitted,
                            'absent output emitted by operation '+output_operation['id']+': '+field['id'])
            allowed.append({'state':{k:(_encode_vector_value(fields[k]['domain'],v) if exact_values else v) for k,v in after.items()},'output':{k:(_encode_vector_value(fields[k]['domain'],v) if exact_values else v) for k,v in emitted.items()},'unchanged':out['unchanged'],'absent_outputs':out['absent_outputs'],
                            **({'output_operations':sorted(op['id'] for op in output_frames.values())} if explicit else {})})
        case_data={'id':test['id'],'source_tce':rule['id'],'trigger':test['trigger'],
                   'input':test['input'],'initial_state':test['state'],'allowed':allowed}
        if observation_ids:case_data['observations']=payload
        if explicit:
            case_data['output_operations']=inventory
        elif len(output_frames)==1:
            case_data['output_operation']=next(iter(output_frames.values()))['id']
        elif output_frames:
            case_data['output_operations']=sorted(op['id'] for op in output_frames.values())
        cases.append(case_data)
    unique([t['id'] for t in cases],'vector IDs')
    return cases

def _ordered_effect_witness_values(model, trigger, fields, guard_names, observed, presence, definitions):
    """Concrete values for guard-independent required structured fields only.

    The rule coverage and all Effect totality checks must already be proved.
    Witness selection is not a new proof of totality or implementation correctness.
    """
    from catlib.semantic_structural_copy import _example, _supported
    if (model.get('coverage_requirement') != 'closed'
            or model.get('coverage_checks', {}).get(trigger, {}).get('result') != 'proved'):
        return {}
    checks = model.get('effect_checks', {})
    refs = set()
    for rule in model['rules']:
        if rule['trigger'] != trigger:
            continue
        for n, outcome in enumerate(rule['allowed'], 1):
            for i, write in enumerate(outcome['write'], 1):
                target, expr = write['target'], write['expr']
                check = checks.get(f"{rule['source_artifact']}#{rule['id']}:{n}:{i}:{target}", {})
                if check.get('result') != 'proved':
                    return {}
                if expr.get('op') in ('sequence-append', 'sequence-swap', 'sequence-replace-member', 'record-value'):
                    if (check.get('proof_method') != 'typed-domain-closure/v1'
                            or _symbolic_effect_containment(expr, fields[target]['domain'], fields) is not True):
                        return {}
                    refs.update(used_refs(expr, definitions))
    if not refs:
        return {}
    values = {}
    for name, field in fields.items():
        domain = field['domain']
        shape = domain
        while shape.get('type') == 'reference' and shape.get('resolved') is True:
            shape = shape['of']
        if (field['role'] not in ('input', 'state') or name in guard_names
                or presence.get(name, 'required') != 'required'
                or shape.get('type') not in ('record', 'sequence')
                or not _supported(domain) or (name in observed and name not in refs)):
            continue
        try:
            sample = _example(domain, empty=name not in refs)
            if typed.contains(domain, sample):
                values[name] = [sample]
        except (ValueError, TypeError, KeyError, IndexError, RecursionError):
            continue
    return values


def selection_vectors(model, strategy='rule-witness/v1'):
    require(strategy == 'rule-witness/v1','unsupported test-selection rule: '+str(strategy))
    require(model.get('status')=='confirmed','normative vector selection requires confirmed TestModel')
    fields={f['id']:f for f in model['fields']}
    presence_inputs=[f['id'] for f in fields.values() if f['role']=='input'
                     and f.get('presence','required')!='required']
    presence_inputs.extend(x['operation']+':'+x['field']
                           for x in model.get('operation_presence',[])
                           if fields[x['field']]['role']=='input' and x['presence']!='required')
    if presence_inputs:
        checks=model.get('coverage_checks',{})
        require(model.get('coverage_requirement')=='closed'
                and not model.get('presence_unproven',[*presence_inputs])
                and bool(checks) and all(c.get('result')=='proved' for c in checks.values()),
                'non-required operation Presence lacks a source-backed finite closure proof')
    output_special=_nonrequired_output_ids(fields,model.get('operation_presence',[]))
    if output_special:
        checks=model.get('coverage_checks',{})
        require(model.get('coverage_requirement')=='closed'
                and model.get('presence_unproven')==[]
                and bool(checks) and all(x.get('result')=='proved' for x in checks.values()),
                'nonrequired output Presence needs proved operation and Effect frame')
    all_variable_ids=sorted(f for f in fields if fields[f]['role'] in ('input','state'))
    defs={d['id']:d for d in model['definitions']}
    witnesses={}
    for trigger in sorted(t['id'] for t in model['triggers']):
        operation,ambiguous=_presence_accepted_operation(model.get('pi_operations',[]),trigger)
        require(ambiguous is None,ambiguous or 'ambiguous operation')
        bindings=_input_operation_bindings(model.get('pi_operations',[]),trigger)
        presence={
            fid:_trigger_input_presence(field,bindings,model.get('operation_presence',[]))
            for fid,field in fields.items() if field['role']=='input'
        }
        output_overrides=[x for x in model.get('operation_presence',[])
                          if fields[x['field']]['role']=='output']
        provide_frames=None
        if not model.get('output_frames') and (output_overrides or output_special):
            provide_frames=_provided_output_frames(
                fields,model.get('pi_operations',[]),
                model.get('operation_presence',[]),trigger)
            require(provide_frames is not None,
                    'ambiguous provided output operation for deterministic vectors')
        observation_ids,observation_constraints=_vector_observation_context(model,trigger,fields)
        variable_ids=([name for name in all_variable_ids
                       if fields[name]['role']=='state' or operation is None
                       or 'pi_constraint_scopes' not in model
                       or fields[name].get('source_pi') in bindings])+observation_ids
        domains=[]
        rules_here=[r for r in model['rules'] if r['trigger']==trigger]
        constraints=[*_active_pi_constraints(model,trigger),*_guard_invariant_exprs(model.get('intrinsic_rule_proofs',[])).values(),*observation_constraints]
        predicates=[*constraints,*(r['when'] for r in rules_here)]
        observed=set().union(*(used_refs(expr,defs) for expr in predicates)) if predicates else set()
        for rule in rules_here:
            for outcome in rule['allowed']:
                for write in outcome['write']:
                    observed.update(used_refs(write['expr'],defs))
        guard_names=set().union(*(used_refs(predicate,defs) for predicate in predicates)) if predicates else set()
        projected=_record_projection_values(fields,variable_ids,predicates,presence,defs,
            [w['expr'] for r in rules_here for outcome in r['allowed'] for w in outcome['write']])
        integer_pair=_integer_reference_equality_values(
            fields,guard_names,predicates,presence,defs)
        integer_range=({} if integer_pair else _integer_reference_range_values(
            fields,guard_names,predicates,presence,defs))
        raw_count=__import__('math').prod(len(v) if v is not None else 1 for v in
            (_presence_cases(fields[k]['domain'],presence[k]) if k in presence
             else typed.finite_values(fields[k]['domain']) for k in variable_ids)) if integer_pair else 0
        real_range=_real_reference_range_values(fields,guard_names,predicates,presence,defs)
        linear_range=_linear_order_values(fields,guard_names,predicates,presence,defs)
        string_pair=_string_reference_values(fields,guard_names,predicates,presence)
        nullable_pair=semantic_string_partition.nullable_reference_cells({n:fields[n]['domain'] for n in guard_names},predicates,presence)
        from catlib.semantic_structural_copy import witness_values
        copy_values=witness_values(model,trigger,fields,guard_names,observed,presence)
        ordered_values=_ordered_effect_witness_values(model,trigger,fields,guard_names,observed,presence,defs)
        for field_id in variable_ids:
            if projected:
                domains.append(projected[field_id]);continue
            field=fields[field_id]
            values=(_presence_cases(field['domain'],presence[field_id])
                    if field_id in presence else typed.finite_values(field['domain']))
            if field_id in string_pair:values=string_pair[field_id]
            if field_id in nullable_pair:values=nullable_pair[field_id]
            if field_id in integer_range:
                values=integer_range[field_id]
            if field_id in real_range:
                values=real_range[field_id]
            if field_id in linear_range:
                values=linear_range[field_id]
            if values is None and field_id in presence and presence[field_id]=='optional' and field_id not in observed:
                # The omission is a valid witness of an unobserved optional
                # value; it is not a sample used as a finite-domain proof.
                values=[typed.MISSING]
            if values is None and (field_id not in presence
                                   or presence[field_id]=='required'):
                values=semantic_interval_partition.integer_partition_values(
                    field['domain'],field_id,predicates,allow_unused=True)
            if values is None and (field_id not in presence
                                   or presence[field_id]=='required'):
                values=semantic_string_partition.string_partition_values(
                    field['domain'],field_id,predicates,allow_unused=True)
            if values is None and (field_id not in presence or presence[field_id]=='required'):
                values=semantic_string_partition.nullable_string_null_partition(field['domain'],field_id,predicates)
            if values is None and (field_id not in presence or presence[field_id]=='required'):
                values=semantic_interval_partition.real_partition_values(field['domain'],field_id,predicates,allow_unused=True)
            if values is None and (field_id not in presence or presence[field_id]=='required'):
                values=semantic_interval_partition.sequence_length_values(field['domain'],field_id,predicates)
            if values is None and presence.get(field_id)=='optional':
                present=semantic_interval_partition.integer_partition_values(
                    field['domain'],field_id,predicates,allow_unused=True,allow_presence=True)
                if present is None:
                    present=semantic_string_partition.string_partition_values(
                        field['domain'],field_id,predicates,allow_unused=True,allow_presence=True)
                if present is not None:values=[typed.MISSING,*present]
            if field_id in integer_pair and (values is None or raw_count>65536):
                values=integer_pair[field_id]
            if values is None and field_id in copy_values:
                values=copy_values[field_id]
            if values is None and field_id in ordered_values:
                values=ordered_values[field_id]
            require(values is not None,
                    'rule-witness/v1 cannot enumerate or soundly partition domain/Presence of '+field_id)
            require(values,'test-selection domain is empty: '+field_id)
            domains.append(values)
        combinations=__import__('math').prod(len(x) for x in domains)
        cache=None
        if combinations>65536:
            require(model.get('coverage_requirement')=='closed'
                    and model.get('coverage_checks',{}).get(trigger,{}).get('result')=='proved',
                    'large test-selection requires proved source-bound Guard coverage')
            cache=_large_finite_predicate_cache(variable_ids,domains,predicates,defs)
            if cache is None:
                from catlib.finite_truth_masks import truth_masks, row_indices, first_indices
                masks=truth_masks(variable_ids,domains,constraints,[r['when'] for r in rules_here],
                                  defs,eval_expr,used_refs,Blocked)
                require(masks is not None,'test-selection exceeds configured 65536 combinations and factorized proof budget')
                accepted,hits=masks;seen=0
                for hit in hits:
                    require(hit and not (seen&hit),'confirmed TestModel has empty or overlapping Guard region')
                    seen|=hit
                require(seen==accepted,'confirmed TestModel has uncovered Guard region')
                indices=sorted(next(first_indices(hit,1)) for hit in hits)
                selected=[tuple(d[j] for d,j in zip(domains,row_indices(i,domains))) for i in indices]
            else:selected=None
        else:selected=None
        rows=(selected if selected is not None else
              itertools.product(*(range(len(d)) for d in domains)) if cache is not None
              else itertools.product(*domains))
        for values in rows:
            if cache is not None:
                if not all(fn(values) for fn in cache[:len(constraints)]):continue
                hit=[r for r,fn in zip(rules_here,cache[len(constraints):]) if fn(values)]
                env=None
            else:
                env=dict(zip(variable_ids,values))
                if not all(eval_expr(c,env,defs) for c in constraints):continue
                hit=[r for r in rules_here if eval_expr(r['when'],env,defs)]
            require(len(hit)==1,f'confirmed TestModel selection found {len(hit)} rules at {trigger}')
            rule=hit[0]
            if rule['id'] in witnesses:continue
            if env is None:env={k:d[i] for k,d,i in zip(variable_ids,domains,values)}
            sample={
                'id':'case.'+rule['id'],'trigger':trigger,
                'input':{key:({'$cat_presence':'undefined'} if env[key] is typed.UNDEFINED else _encode_vector_value(fields[key]['domain'],env[key]))
                         for key in variable_ids if fields[key]['role']=='input'
                         and env[key] is not typed.MISSING},
                'state':{key:_encode_vector_value(fields[key]['domain'],env[key]) for key in variable_ids if fields[key]['role']=='state'}
            }
            if observation_ids:sample['observations']={key:env[key] for key in observation_ids}
            if operation is not None and any(value!='required' for value in presence.values()):
                sample['operation']=operation['id']
            if model.get('output_frames'):
                sample['output_operations']=sorted({op['id'] for frame in _explicit_vector_frames(model,fields,rule) for op in frame.values()})
            elif provide_frames:
                if len(provide_frames)==1:
                    sample['output_operation']=next(iter(provide_frames.values()))['id']
                else:
                    sample['output_operations']=sorted(op['id'] for op in provide_frames.values())
            witnesses[rule['id']]=sample
    missing=[r['id'] for r in model['rules'] if r['id'] not in witnesses]
    require(not missing,'test-selection produced no witness for TestModel rule(s): '+str(missing))
    return {'schema':V,'process':model['process'],'selection_rule':strategy,
            'cases':[witnesses[r['id']] for r in model['rules']],
            **({'semantic_value_transport':'cat-exact-values/v1'} if any(_exact_value_kind(f['domain']) for f in fields.values()) else {})}

def _vitest_renderer():
    import importlib.util
    path = ROOT / 'skills' / 'tech-vitest' / 'scripts' / 'cat_vitest_renderer.py'
    require(path.is_file(), 'Vitest generation requires installed tech-vitest Skill renderer')
    spec = importlib.util.spec_from_file_location('_cat_vitest_renderer', path)
    require(spec is not None and spec.loader is not None, 'cannot load tech-vitest renderer')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.render_vitest


def _check_observation_transport(model, binding, expected):
    """Admit only proved finite trigger-entry observations to a test adapter.

    The driver reports what it actually observed in its controlled execution;
    this is not independent runtime/provider evidence for implementation closure.
    """
    transport=binding.get('observation_transport')
    require(transport in (None,expected),'unsupported observation transport binding')
    if transport is None:return False
    fields={f['id']:f for f in model['fields']}
    observations={f['id'] for f in fields.values() if f['role']=='observation'}
    require(observations and not any(f['role']=='action' for f in fields.values()),
            'observation transport requires finite observations and no unsupported action capabilities')
    inventory=set()
    for trigger in model['triggers']:
        ids,_=_vector_observation_context(model,trigger['id'],fields)
        inventory.update(ids)
    require(inventory==observations,'observation transport requires proved source-bound inventory for every declared observation')
    require(binding.get('capability_scope') is None,
            'observation transport cannot be combined with PI-only-unverified scope')
    return True


def emit_vitest(model,vectors,binding_path):
    require(binding_path is not None,'Vitest renderer requires explicit JSON/instant binding and driver binding')
    binding=json.loads(Path(binding_path).read_text(encoding='utf-8'))
    check_keys(binding,['schema','process','driver'],
               optional=('undefined_transport','output_operation_transport','observation_transport','semantic_value_transport'),
               where='driver binding')
    require(binding['schema']==D and binding['process']==model['process'],'driver binding incompatible')
    semantic=[f for f in model.get('fields',[]) if typed.has_semantic_domain(f['domain'])]
    require(binding.get('semantic_value_transport') in (None,'cat-exact-values/v1'), 'unsupported semantic value transport')
    require(not semantic or (binding.get('semantic_value_transport')=='cat-exact-values/v1' and all(
            f['role'] in ('input','state','output') and _exact_value_kind(f['domain']) for f in semantic)),
            'Vitest renderer requires explicit JSON/instant binding for supported top-level fields')
    require(semantic or binding.get('semantic_value_transport') is None, 'semantic transport requires semantic fields')
    require(not semantic or vectors.get('semantic_value_transport')=='cat-exact-values/v1',
            'exact semantic driver requires explicitly tagged vectors; regenerate or convert vectors explicitly')
    require(isinstance(binding['driver'],str) and binding['driver'].startswith('./') and not '..' in Path(binding['driver']).parts,
            'driver must be an explicit local relative module')
    observed=_check_observation_transport(model,binding,'js-driver-observed/v1')
    require(observed or not any(f['role'] in ('observation','action') for f in model['fields']),
            'test-code generation for explicit observation/action capabilities requires a technology binding extension; TestModel remains valid')
    cases=expand_cases(model,vectors)
    uses_output_operation=any('output_operation' in x or 'output_operations' in x for x in cases)
    multiple=any('output_operations' in x for x in cases)
    transport=binding.get('output_operation_transport')
    if transport not in (None,'js-driver-provide/v1','js-driver-provides/v1'):
        raise Blocked('unsupported output-operation transport binding')
    if multiple and transport!='js-driver-provides/v1':
        raise Blocked('Vitest renderer requires multi-output-operation identity transport')
    if observed and any('observations' in c and ('output_operation' in c or 'output_operations' in c) for c in cases):
        require(transport=='js-driver-provides/v1','observed operation frames require js-driver-provides/v1')
    if uses_output_operation and transport not in ('js-driver-provide/v1','js-driver-provides/v1'):
        raise Blocked('Vitest renderer lacks output-operation identity transport; cannot assert provider operation')
    uses_undefined=any(any(v=={'$cat_presence':'undefined'} for v in c['input'].values()) for c in cases)
    if binding.get('undefined_transport') not in (None,'js-undefined/v1'):
        raise Blocked('unsupported undefined transport binding')
    if uses_undefined and binding.get('undefined_transport')!='js-undefined/v1':
        raise Blocked('Vitest renderer has no source-backed undefined transport binding; cannot generate a false oracle')
    # The bundled Vitest renderer emits ordinary JavaScript number literals.
    # Integers beyond Number.MAX_SAFE_INTEGER would silently lose precision;
    # require a separately specified BigInt/transport contract instead.
    stack=[cases]
    while stack:
        item=stack.pop()
        if type(item) is int and abs(item)>SAFE_INT:
            raise Blocked('Vitest renderer cannot safely encode integer outside JS safe range; explicit transport required')
        if isinstance(item,dict):stack.extend(item.values())
        elif isinstance(item,(list,tuple)):stack.extend(item)
    return _vitest_renderer()(model,cases,binding)




def emit_junit(model, vectors, binding_path):
    """Render current queued CAT cases using the explicitly selected JUnit adapter."""
    import importlib.util
    binding=json.loads(Path(binding_path).read_text(encoding='utf-8'))
    check_keys(binding,['schema','process','test_package','test_class','driver_class'],
               optional=('capability_scope','output_operation_transport','observation_transport'), where='JUnit driver binding')
    require(binding['schema']=='cat-junit-driver-binding/v1'
            and binding['process']==model['process'], 'JUnit driver binding incompatible')
    observations=[f['id'] for f in model['fields'] if f['role']=='observation']
    actions=[f['id'] for f in model['fields'] if f['role']=='action']
    capability_scope=binding.get('capability_scope')
    observed=_check_observation_transport(model,binding,'java-driver-observed/v1')
    transport=binding.get('output_operation_transport')
    require(transport in (None,'java-driver-provides/v1'),'unsupported JUnit output-operation transport binding')
    framed=transport=='java-driver-provides/v1'
    if not observed and (observations or actions):
        # The scalar driver tests only the declared PI inputs/outputs.
        # Process observation/action capabilities must be explicitly listed
        # as NOT TESTED, never silently dropped or claimed as verified.
        require(isinstance(capability_scope,dict),
                'JUnit renderer requires explicit capability scope for observation/action')
        check_keys(capability_scope,['kind','observations','actions'],
                   where='JUnit capability scope')
        require(capability_scope['kind']=='pi-only-unverified',
                'JUnit capability scope must be pi-only-unverified')
        for role,actual in [('observations',observations),('actions',actions)]:
            declared=capability_scope[role]
            require(isinstance(declared,list) and all(isinstance(x,str) for x in declared)
                    and len(declared)==len(set(declared))
                    and set(declared)==set(actual),
                    'JUnit PI-only scope must exactly enumerate unverified '+role)
    elif not observed:
        require(capability_scope is None,
                'JUnit capability exclusions require declared Process capabilities')
    # Eligibility is a property of the tested PI/state/output contract.
    # An explicitly excluded Process observation/action is NOT transported
    # by the scalar PI-only test; its Domain must not reject generation.
    tested_fields=[f for f in model['fields']
                   if f['role'] in ('input','state','output')]
    require(not any(typed.has_semantic_domain(f['domain']) for f in tested_fields),
            'JUnit renderer requires explicit structured/instant transport binding')
    require(all(f['domain']['type'] in ('boolean','enum','integer')
                and (f.get('presence','required')=='required' or
                     (framed and f['role']=='output' and f.get('presence') in ('optional','absent')))
                for f in tested_fields),
            'JUnit scalar renderer supports only required boolean/enum/integer fields')
    field_roles={f['id']:f['role'] for f in model['fields']}
    require(not model.get('operation_presence') or (framed and all(
            field_roles[item['field']]=='output' and item['presence'] in ('required','optional','absent')
            for item in model['operation_presence'])),
            'JUnit scalar renderer does not carry unsupported operation-scoped Presence')
    cases=expand_cases(model,vectors)
    require(observed or not any('observations' in c for c in cases),
            'JUnit renderer cannot transport observed test environment witnesses')
    require(framed or not any('output_operation' in c or 'output_operations' in c for c in cases),
            'JUnit scalar renderer cannot carry output-operation identity')
    path=ROOT / 'skills' / 'tech-junit' / 'scripts' / 'cat_junit_renderer.py'
    require(path.is_file(), 'JUnit generation requires installed tech-junit Skill renderer')
    spec=importlib.util.spec_from_file_location('_cat_junit_renderer',path)
    require(spec is not None and spec.loader is not None, 'cannot load tech-junit renderer')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        return module.render_junit(model,cases,binding)
    except ValueError as e:
        raise Blocked(str(e)) from e


def make_queue(model, vectors, model_bytes, vector_bytes):
    require(model.get('status') == 'confirmed', 'normative Queue requires confirmed TestModel')
    cases = expand_cases(model, vectors)
    require(cases, 'Queue requires at least one concrete vector')
    covered={case['source_tce'] for case in cases}
    missing=sorted({r['id'] for r in model['rules']}-covered)
    require(not missing, 'test-selection omitted TestModel rule(s): '+str(missing))
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
    # Re-derive source TCE identity from every concrete vector, including
    # pending/done items. The SHA of the vector file authenticates the vector
    # set, but must not be used to trust the Queue's mutable references.
    expected_cases = expand_cases(model, vectors)
    expected_by_id = {case['id']:case['source_tce'] for case in expected_cases}
    require(len(queue['items']) == len(expected_cases),
            'Queue vectors do not match complete test selection')
    seen_vectors = set()
    seen = set(); current = []
    last_order = 0
    for item in queue['items']:
        check_keys(item, ['id','model_ref','vector_ref','order','status','evidence_ref'], where='Queue item')
        ident(item['id'], 'Queue item ID')
        require(item['id'] not in seen, 'duplicate Queue item ID'); seen.add(item['id'])
        require(item['vector_ref'] in expected_by_id, 'Queue item references unknown vector')
        require(item['vector_ref'] not in seen_vectors,
                'Queue vectors do not match: duplicate vector_ref')
        seen_vectors.add(item['vector_ref'])
        require(item['model_ref'] == expected_by_id[item['vector_ref']],
                'Queue model_ref does not match vector-derived TestModel rule')
        require(item['id'] == item['vector_ref'],
                'Queue item ID must equal its vector_ref')
        require(type(item['order']) is int and item['order'] > last_order,
                'Queue order must be strictly increasing integers')
        last_order = item['order']
        require(item['status'] in ('pending','current','done','blocked'), 'Queue status invalid')
        require(item['evidence_ref'] is None or isinstance(item['evidence_ref'], str), 'Queue evidence_ref invalid')
        if item['status'] == 'current': current.append(item)
    require(seen_vectors == set(expected_by_id),
            'Queue vectors do not match complete test selection')
    require([item['vector_ref'] for item in queue['items']] ==
            [case['id'] for case in expected_cases] and
            [item['order'] for item in queue['items']] ==
            list(range(1, len(expected_cases)+1)),
            'Queue order or vector sequence differs from deterministic selection')
    require(len(current) <= 1, 'Queue may contain at most one current item')
    return current[0] if current else None


def current_vectors(model, vectors, queue, model_bytes, vector_bytes):
    current = validate_queue(queue, model, vectors, model_bytes, vector_bytes)
    require(current is not None, 'Queue has no current item')
    chosen = [x for x in vectors['cases'] if x['id'] == current['vector_ref']]
    require(len(chosen) == 1, 'current Queue vector must resolve exactly once')
    probe = expand_cases(model, {**vectors, 'cases': chosen})[0]
    require(probe['source_tce'] == current['model_ref'], 'Queue model_ref does not match vector-derived TestModel rule')
    return {**vectors, 'cases': chosen}

def format_domain(d, language='en'):
    t=d['type']
    if t=='reference':return ('型参照<' if language=='ja' else 'ref<')+d['name']+'>'
    if t=='null':return '明示null' if language=='ja' else 'null'
    if t=='json':return ('JSON値' if d['root']=='value' else 'JSONオブジェクト') if language=='ja' else ('json' if d['root']=='value' else 'json-object')
    if t=='instant':return '瞬間値' if language=='ja' else 'instant'
    names={'ja':{'boolean':'真偽','integer':'整数','string':'文字列','set':'集合','sequence':'列','enum':'列挙'},
           'en':{'boolean':'boolean','integer':'integer','string':'string','set':'set','sequence':'sequence','enum':'enum'}}[language]
    if t=='boolean':return names['boolean']
    if t=='integer':
        if d.get('min') is None and d.get('max') is None:return names['integer']
        return names['integer']+'['+(decimal_integer.format_int(d['min']) if 'min' in d else '')+'..'+(decimal_integer.format_int(d['max']) if 'max' in d else '')+']'
    if t=='string':
        if d.get('format','any')=='any':return names['string']
        fmt='安全符号付き整数' if language=='ja' and d['format']=='safe-signed-integer' else d['format']
        return names['string']+'<'+fmt+'>'
    if t in ('set','sequence'):
        element=d['element']
        return f"{names[t]}<{format_domain(element,language) if isinstance(element,dict) else names[element]}>"
    if t=='enum':return names['enum']+'{' + ', '.join(_format_literal(v,language) for v in d['values']) + '}'
    if t=='bytes':return 'バイト列' if language=='ja' else 'bytes'
    if t=='real':return ('実数' if language=='ja' else 'real')+('['+(decimal_integer.format_int(d['min']) if type(d.get('min')) is int else str(d.get('min','')))+'..'+(decimal_integer.format_int(d['max']) if type(d.get('max')) is int else str(d.get('max','')))+']' if 'min' in d or 'max' in d else '')
    if t=='nullable':return format_domain(d['of'],language)+('またはnull' if language=='ja' else '|null')
    if t=='union':return 'Union<'+', '.join(format_domain(x,language) for x in d['variants'])+'>'
    if t=='record':
        if 'name' in d:return ('レコード<' if language=='ja' else 'record<')+d['name']+'>'
        return ('レコード<' if language=='ja' else 'record<')+','.join(
            f['id']+('['+f['presence']+']' if f.get('presence','required')!='required' else '')+
            (':'+format_domain(f['domain'],language) if f['domain']['type']!='unknown' else '')
            for f in d['fields'])+'>'
    raise Blocked('unknown domain for rendering')


def _format_literal(v, language='en'):
    if v is True:return '真' if language=='ja' else 'true'
    if v is False:return '偽' if language=='ja' else 'false'
    if v is None:return 'なし' if language=='ja' else 'null'
    if isinstance(v,str):return json.dumps(v,ensure_ascii=False)
    if isinstance(v,list):return '['+', '.join(_format_literal(x,language) for x in v)+']'
    return decimal_integer.format_int(v) if type(v) is int else str(v)


def format_expr(expr, params=(), language='en'):
    if 'literal' in expr:return _format_literal(expr['literal'],language)
    if 'ref' in expr:
        ref=expr['ref']
        return ref[6:] if ref.startswith('param.') and ref[6:] in params else ref
    op=expr['op'];args=[format_expr(x,params,language) for x in expr['args']]
    if op=='member':
        require(set(expr)=={'op','args'} and len(args)==2 and set(expr['args'][0])=={'ref'}
                and set(expr['args'][1])=={'literal'} and isinstance(expr['args'][1]['literal'],str),'invalid projected Model expression')
        return 'member['+args[0]+', '+args[1]+']'
    symbols={'eq':'==','ne':'!=','lt':'<','le':'<=','gt':'>','ge':'>=','add':'+','sub':'-','mul':'*','div':'/'}
    if op in symbols:return '('+(' '+symbols[op]+' ').join(args)+')'
    if op=='record-value':return '{'+', '.join(k+': '+v for k,v in zip(args[::2],args[1::2]))+'}'
    if op in ('and','or'):
        word={'and':('かつ' if language=='ja' else 'and'),'or':('または' if language=='ja' else 'or')}[op]
        return '('+(' '+word+' ').join(args)+')'
    if op=='not':return ('否定('+args[0]+')') if language=='ja' else '(not '+args[0]+')'
    if op in ('is-missing','is-undefined','is-present'):
        return op.replace('-','_')+'('+args[0]+')'
    funcs_en={'floor':'floor','abs':'abs','length':'length','concat':'concat','to-int':'to_int','set-add':'set_add','set-remove':'set_remove','sequence-append':'sequence_append','sequence-swap':'sequence_swap','sequence-replace-member':'sequence_replace_member'}
    funcs_ja={'floor':'floor','abs':'abs','length':'長さ','concat':'連結','to-int':'整数化','set-add':'集合追加','set-remove':'集合削除','sequence-append':'列追加','sequence-swap':'列交換','sequence-replace-member':'列項目更新'}
    if op=='call':return expr['name']+'('+', '.join(args)+')'
    if op in collection_relation.OPERATORS:return op.replace('-','_')+'('+', '.join(args)+')'
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
    records=model.get('source_records')
    if records is None:
        records=[{'id':aid,'kind':kind,'sha256':digest} for aid,(kind,digest) in zip(model['source_artifacts'],model['source_sha256'].items())]
    for rec in records:lines.append(f"| {_md(rec['id'])} | {_md(rec['kind'])} | `{rec['sha256']}` |")
    # Source-bound CommonRule/DomainSpec inventory is normative data, not a
    # comment on TCE behavior. The Markdown Model must retain the same
    # ownership, meaning and unresolved proof status as the JSON Model.
    lines += ['',('## 規範Rule出典' if ja else '## Normative rule sources'),'',
              ('| 出典ID | 種別 | 宣言元Process | SHA-256 |' if ja else
               '| Source ID | Kind | Declaring Process | SHA-256 |'),
              '| --- | --- | --- | --- |']
    for source in model.get('normative_rule_inputs',[]):
        lines.append(f"| {_md(source['id'])} | {_md(source['kind'])} | "
                     f"{_md(source['process'])} | `{source['sha256']}` |")
    lines += ['',('## 規範Rule義務' if ja else '## Normative rule obligations'),'',
              ('| ID | 出典Artifact | 出典種別 | 適用条件 | 要求 | 検証契約 | 検証状態 | 出典SHA-256 | 適用範囲束縛 |' if ja else
               '| ID | Source artifact | Source kind | Condition | Requirement | Verification contract | Verification status | Source SHA-256 | Scope binding |'),
              '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for rule in model.get('rule_obligations',[]):
        scope=rule.get('scope_binding')
        scope_text=('—' if scope is None else
                    json.dumps(scope,sort_keys=True,ensure_ascii=False,separators=(',',':')))
        lines.append(f"| {_md(rule['id'])} | {_md(rule['source_artifact'])} | "
                     f"{_md(rule['source_kind'])} | {_md(rule['condition'])} | {_md(rule['requirement'])} | "
                     f"{_md(rule['verification_contract'])} | "
                     f"{_md(rule.get('verification_status','unverified'))} | "
                     f"{_md(rule.get('source_sha256') or '—')} | {_md(scope_text)} |")
    # Exact typed declarations are not equivalent to display-only Domain names.
    # Preserve full resolved definitions, including their Source and SHA.
    lines += ['',('## 解決済み名前付き型' if ja else '## Resolved named types'),'',
              '```json',json.dumps(model.get('named_type_definitions',[]),
                  ensure_ascii=False,sort_keys=True,indent=2),'```']
    # Operations can override the base PI Presence for a particular Trigger.
    lines += ['',('## 操作別Presence' if ja else '## Operation presence'),'',
              ('| 操作 | フィールド | Presence | 出典PI |' if ja else
               '| Operation | Field | Presence | Source PI |'),
              '| --- | --- | --- | --- |']
    for entry in model.get('operation_presence',[]):
        lines.append('| '+' | '.join(_md(entry[key]) for key in
            ('operation','field','presence','source_pi'))+' |')
    if model.get('output_frames'):
        lines += ['',('## 提供出力フレーム' if ja else '## Output frames'),'','```json',
                  json.dumps(model['output_frames'],ensure_ascii=False,sort_keys=True,indent=2),'```']
    lines += ['',('## 観測利用可能時点' if ja else '## Observation availability'),'',
              ('| 観測ID | 出典 | 利用可能な起点(JSON) |' if ja else
               '| Observation ID | Source | Available on (JSON) |'),
              '| --- | --- | --- |']
    for entry in model['fields']:
        if entry['role']!='observation':continue
        available=(entry['available_on'] if 'available_on' in entry else None)
        lines.append(f"| {_md(entry['id'])} | {_md(entry['source'])} | "+
                     '`'+json.dumps(available,ensure_ascii=False,separators=(',',':'))+'` |')
    # Only established Source-bound intrinsic structural predicates can have
    # proof certificates. Preserve the entire certificate in readable Models;
    # a Rule's `intrinsic-proved` label alone cannot prove its predicate.
    lines += ['',('## 内在Rule証明' if ja else '## Intrinsic rule proofs'),'',
              ('| Rule ID | 出典Artifact | 出典SHA-256 | 要求 | 検証契約 | 証明方法 | 適用範囲 | 証明状態 |' if ja else
               '| Rule ID | Source artifact | Source SHA-256 | Requirement | Verification contract | Proof method | Scope | Proof status |'),
              '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for proof in model.get('intrinsic_rule_proofs',[]):
        lines.append('| '+' | '.join(_md(proof[field]) for field in
            ('rule_id','source_artifact','source_sha256','requirement',
             'verification_contract','proof_method','scope','status'))+' |')
    if model.get('process_interfaces') is not None:
        lines += ['',('## Process境界' if ja else '## Process interfaces'),'', '| PI |','| --- |']
        for ref in model.get('process_interfaces',[]): lines.append(f"| {_md(ref)} |")
    if model.get('pi_boundary'):
        boundary=model['pi_boundary']
        lines += ['',('## PI境界' if ja else '## PI boundary'),'',('| 相手Process | 方向 |' if ja else '| Peer process | Direction |'),'| --- | --- |']
        direction={'receive':'受信','send':'送信','bidirectional':'双方向'}.get(boundary['direction'],boundary['direction']) if ja else boundary['direction']
        for peer in boundary.get('peers',[boundary['peer']]):
            lines.append(f"| {_md(peer)} | {_md(direction)} |")
    if model.get('pi_boundaries') is not None:
        # A Process may have several PIs, each with a distinct peer/direction.
        # The legacy singular PI boundary view is insufficient for this graph.
        lines += ['',('## PI境界一覧' if ja else '## PI boundaries'),'',
                  ('| 出典PI | 相手Process | 方向 | 相手Process一覧(JSON) |' if ja else
                   '| Source PI | Peer process | Direction | Peers (JSON) |'),
                  '| --- | --- | --- | --- |']
        direction_ja={'receive':'受信','send':'送信','bidirectional':'双方向'}
        for boundary in model['pi_boundaries']:
            direction=(direction_ja.get(boundary['direction'],boundary['direction'])
                       if ja else boundary['direction'])
            peers=json.dumps(boundary.get('peers'),ensure_ascii=False,separators=(',',':'))
            lines.append(f"| {_md(boundary['artifact'])} | {_md(boundary['peer'])} | "
                         f"{_md(direction)} | `{_md(peers)}` |")
    if model.get('pi_operations') is not None:
        has_peer=any('peer' in op for op in model['pi_operations'])
        heading=('| ID | 方向 | 起点 | 相手Process | 出典PI |' if ja else '| ID | Direction | Trigger | Peer process | Source PI |') if has_peer else ('| ID | 方向 | 起点 | 出典PI |' if ja else '| ID | Direction | Trigger | Source PI |')
        lines += ['',('## PI操作' if ja else '## PI operations'),'',heading,
                  '| --- | --- | --- | --- | --- |' if has_peer else '| --- | --- | --- | --- |']
        direction_ja={'accept':'受付','provide':'提供'}
        for op in model.get('pi_operations',[]):
            direction=direction_ja.get(op['direction'],op['direction']) if ja else op['direction']
            row=f"| {_md(op['id'])} | {_md(direction)} | {_md(op.get('trigger') or '—')} |"
            if has_peer:
                row+=f" {_md(op.get('peer') or '—')} |"
            row+=f" {_md(op.get('source_pi') or '—')} |"
            lines.append(row)
    lines += ['',('## 起点' if ja else '## Triggers'),'',('| ID | 由来 |' if ja else '| ID | Origin |'),'| --- | --- |']
    for t in model['triggers']:lines.append(f"| {_md(t['id'])} | {_md(t['origin'])} |")
    lines += ['',('## 仕様要素' if ja else '## Fields'),'',('| ID | 役割 | Domain | Presence | 出典PI |' if ja else '| ID | Role | Domain | Presence | Source PI |'),'| --- | --- | --- | --- | --- |']
    role_ja={'input':'受信','output':'送信','state':'状態','observation':'観測','action':'作用'}
    for f in model['fields']:
        is_pi_field=f['role'] in ('input','output')
        lines.append(f"| {_md(f['id'])} | {_md(role_ja.get(f['role'],f['role']) if ja else f['role'])} | `{_md(format_domain(f['domain'],lang))}` | {_md(f.get('presence','required') if is_pi_field else '—')} | {_md((f.get('source_pi') or '—') if is_pi_field else '—')} |")
    if model['pi_constraints']:
        lines += ['',('## PI制約' if ja else '## PI constraints'),'',('| 式 |' if ja else '| Expression |'),'| --- |']
        for c in model['pi_constraints']:lines.append(f'| `{_md(format_expr(c,language=lang))}` |')
    if model.get('pi_constraint_scopes'):
        # The human-readable TestModel must preserve the owning PI and the
        # exact Trigger/evaluation-time binding, not merely the formula text.
        # Missing binding is an unresolved Source relation, not a no-op.
        lines += ['',('## PI制約の束縛' if ja else '## PI constraint bindings'),'',
                  ('| 出典PI | 起点 | 式 | 未証明理由 |' if ja else
                   '| Source PI | Triggers | Expression | Unproved reason |'),
                  '| --- | --- | --- | --- |']
        unbound=model.get('unbound_pi_constraints',[])
        for binding in model['pi_constraint_scopes']:
            matches=[item['reason'] for item in unbound
                     if item['source_pi']==binding['source_pi']
                     and item['expr']==binding['expr']]
            reason=(matches[0] if not binding['triggers'] and matches else '—')
            lines.append('| '+_md(binding['source_pi'])+' | '
                         +_md(', '.join(binding['triggers']) or '—')+' | `'
                         +_md(format_expr(binding['expr'],language=lang))+'` | '
                         +_md(reason)+' |')
    if model['definitions']:
        lines += ['',('## DomainRule定義' if ja else '## DomainRule definitions'),'',('| ID | 引数 | 式 |' if ja else '| ID | Parameters | Expression |'),'| --- | --- | --- |']
        for d in model['definitions']:lines.append(f"| {_md(d['id'])} | {_md(', '.join(d['params']) or '—')} | `{_md(format_expr(d['body'],d['params'],lang))}` |")
    lines += ['',('## 網羅要求' if ja else '## Coverage requirement'),'','`'+model.get('coverage_requirement',model.get('coverage_claim','partial'))+'`']
    lines += ['',('## 規則' if ja else '## Rules'),'',('| ID | 出典TCE | 起点 | 条件 |' if ja else '| ID | Source TCE | Trigger | Condition |'),'| --- | --- | --- | --- |']
    for r in model['rules']:lines.append(f"| {_md(r['id'])} | {_md(r.get('source_artifact','—'))} | {_md(r['trigger'])} | `{_md(format_expr(r['when'],language=lang))}` |")
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
    return render_model_markdown(model) if Path(output_path).suffix.lower()=='.md' else decimal_integer.dumps(model,sort_keys=True,ensure_ascii=False,indent=2)+'\n'

def write(path,content,check):
    p=Path(path);require(not check or (p.exists() and p.read_bytes()==content.encode()),f'{p}: output differs or missing')
    if not check:p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content,encoding='utf-8',newline='\n')

def main(argv=None):
    cli=argparse.ArgumentParser(description=__doc__)
    sub=cli.add_subparsers(dest='command',required=True)
    m=sub.add_parser('model');m.add_argument('process');m.add_argument('pi');m.add_argument('--pi-extra',action='append',default=[]);m.add_argument('--common-rule',action='append',default=[]);m.add_argument('--domain-spec',action='append',default=[]);m.add_argument('--allow-partial',action='store_true');m.add_argument('tce',nargs='+');m.add_argument('--domain-rule');m.add_argument('--allow-draft',action='store_true');m.add_argument('--check',action='store_true');m.add_argument('-o','--output',required=True)
    v=sub.add_parser('vectors');v.add_argument('model');v.add_argument('--selection-rule',default='rule-witness/v1');v.add_argument('--process',required=True);v.add_argument('--pi',required=True);v.add_argument('--pi-extra',action='append',default=[]);v.add_argument('--common-rule',action='append',default=[]);v.add_argument('--domain-spec',action='append',default=[]);v.add_argument('--allow-partial',action='store_true');v.add_argument('--tce',action='append',required=True);v.add_argument('--domain-rule');v.add_argument('--allow-draft',action='store_true');v.add_argument('--check',action='store_true');v.add_argument('-o','--output',required=True)
    q=sub.add_parser('queue');q.add_argument('model');q.add_argument('vectors');q.add_argument('--process',required=True);q.add_argument('--pi',required=True);q.add_argument('--pi-extra',action='append',default=[]);q.add_argument('--common-rule',action='append',default=[]);q.add_argument('--domain-spec',action='append',default=[]);q.add_argument('--allow-partial',action='store_true');q.add_argument('--tce',action='append',required=True);q.add_argument('--domain-rule');q.add_argument('--allow-draft',action='store_true');q.add_argument('--check',action='store_true');q.add_argument('-o','--output',required=True)
    t=sub.add_parser('tests');t.add_argument('model');t.add_argument('vectors');t.add_argument('binding');t.add_argument('--queue');t.add_argument('--framework',choices=('vitest','junit'),default='vitest');t.add_argument('--process',required=True);t.add_argument('--pi',required=True);t.add_argument('--pi-extra',action='append',default=[]);t.add_argument('--common-rule',action='append',default=[]);t.add_argument('--domain-spec',action='append',default=[]);t.add_argument('--allow-partial',action='store_true');t.add_argument('--tce',action='append',required=True);t.add_argument('--domain-rule');t.add_argument('--allow-draft',action='store_true');t.add_argument('--check',action='store_true');t.add_argument('-o','--output',required=True)
    args=cli.parse_args(argv)
    try:
        if args.command=='model':
            result=load(args.process,[args.pi,*getattr(args,'pi_extra',[])],args.tce,args.domain_rule,args.allow_draft,args.common_rule,args.domain_spec,args.allow_partial)
            write(args.output,_model_content(result,args.output),args.check)
        else:
            fresh=load(args.process,[args.pi,*args.pi_extra],args.tce,
                       args.domain_rule,args.allow_draft,args.common_rule,
                       args.domain_spec,args.allow_partial)
            model_bytes=Path(args.model).read_bytes()
            if Path(args.model).suffix.lower()=='.md':
                require(model_bytes.decode('utf-8')==render_model_markdown(fresh),
                        'test model does not match current CAT source: regenerate')
                model=fresh
            else:
                model=decimal_integer.loads(model_bytes.decode('utf-8'))
                require(model.get('schema')==M,'wrong model schema')
                require(model.get('status')=='confirmed' or args.allow_draft,'draft model requires --allow-draft')
                require(model.get('semantic_authority') in (S,'cat-markdown/v1','cat-markdown/v2'),'missing CAT semantic authority')
                require(model==fresh,'test model does not match current CAT source: regenerate')
            if args.command=='vectors':
                result=selection_vectors(model,args.selection_rule)
                write(args.output,decimal_integer.dumps(result,sort_keys=True,ensure_ascii=False,indent=2)+'\n',args.check)
            else:
                vector_bytes=Path(args.vectors).read_bytes()
                vectors=decimal_integer.loads(vector_bytes.decode('utf-8'))
                if not args.allow_draft:
                    require(vectors==selection_vectors(model),
                            'test vectors differ from deterministic test-selection output: regenerate')
                if args.command=='queue':
                    result=make_queue(model,vectors,model_bytes,vector_bytes)
                    write(args.output,decimal_integer.dumps(result,sort_keys=True,ensure_ascii=False,indent=2)+'\n',args.check)
                else:
                    if args.queue:
                        queue=json.loads(Path(args.queue).read_text(encoding='utf-8'))
                        vectors=current_vectors(model,vectors,queue,model_bytes,vector_bytes)
                    else:
                        require(args.allow_draft, 'normative test generation requires --queue with exactly one current item')
                    write(args.output,(emit_junit(model,vectors,args.binding) if args.framework=='junit'
                                       else emit_vitest(model,vectors,args.binding)),args.check)
        return 0
    except (Blocked,TypeError,KeyError,ValueError,FileNotFoundError) as e:
        print('BLOCKED: '+str(e),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
