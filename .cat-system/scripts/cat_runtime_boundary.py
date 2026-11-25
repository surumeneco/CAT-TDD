"""Live, independently observed, finite stream-boundary conformance.

This optional transport adapter verifies an actual connected pair of processes
under a declared Work. It never ingests a product-generated verdict or trace
receipt. It is not a proof of a different production route or a sandbox.
"""
from __future__ import annotations

import fnmatch
import itertools
import json
import math
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import cat_process_composition as composition
from cat_compile_v2 import eval_expr, _active_pi_constraints
from catlib import semantic_types as typed
from catlib.common import Blocked, require, read_json, sha, json_bytes

SCHEMA = 'cat-runtime-boundary-binding/v1'
MAX_CASES = 64
MAX_FRAME = 65536


class Unsupported(ValueError):
    pass


def _path(root, relative):
    require(isinstance(relative, str) and relative and not Path(relative).is_absolute()
            and '..' not in Path(relative).parts, 'invalid boundary dependency path')
    candidate = root / relative
    path = candidate.resolve(strict=True)
    require(path.is_relative_to(root) and path.is_file() and not candidate.is_symlink(),
            'boundary dependency escapes root or is not a regular file')
    return path


def _dependency(root, entry):
    require(isinstance(entry, dict) and set(entry) == {'path', 'sha256'},
            'boundary dependency requires path and exact SHA256')
    path = _path(root, entry['path'])
    actual = sha(path.read_bytes())
    require(actual == entry['sha256'], 'boundary dependency hash mismatch: ' + entry['path'])
    return path, {'path': str(path), 'sha256': actual}


def _git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, timeout=15)
    require(result.returncode == 0, 'cannot verify boundary repository: ' + ' '.join(args[:1]))
    return result.stdout


def prepare(path, repositories):
    """Read only: independently reconstruct every versioned input dependency."""
    path = Path(path).resolve(strict=True)
    binding = read_json(path)
    require(isinstance(binding, dict) and set(binding) == {
        'schema', 'profile', 'models', 'source_assemblies', 'links', 'endpoints'},
        'invalid runtime boundary binding inventory (submitted receipts are not inputs)')
    require(binding['schema'] == SCHEMA and binding['profile'] == 'finite-required-stream/v1',
            'unsupported runtime boundary evidence profile')
    require(isinstance(binding['links'], list) and len(binding['links']) == 1,
            'stream profile requires exactly one explicit connection')
    link = binding['links'][0]
    require(isinstance(link, dict) and set(link) == {'source_process','source_pi','source_operation',
            'target_process','target_pi','target_operation','field_links'}, 'invalid boundary link')
    pids = {link['source_process'], link['target_process']}
    require(len(pids) == 2 and all(isinstance(p,str) and p for p in pids),
            'distinct source and target Processes required')
    require(isinstance(binding['models'],dict) and set(binding['models']) == pids
            and isinstance(binding['endpoints'],dict) and set(binding['endpoints']) == pids,
            'boundary model/endpoint inventory must match both Processes')
    files, models, hashes, endpoints = {}, {}, {}, {}
    interpreter=Path(sys.executable).resolve(strict=True)
    inputs={'binding':{'path':str(path),'sha256':sha(path.read_bytes())},
            'observer-python':{'path':str(interpreter),'sha256':sha(interpreter.read_bytes())}}
    assemblies, source_inputs = composition.composition_source_inputs(path)
    require(set(assemblies) == pids, 'boundary requires both Confirmed Source assemblies')
    for pid in sorted(pids):
        files[pid], info = _dependency(path.parent, binding['models'][pid])
        hashes[pid] = info['sha256']; inputs['model:'+pid] = info
        models[pid] = read_json(files[pid])
        require(models[pid].get('process') == pid, 'boundary model Process mismatch')
        for name, item in source_inputs[pid].items():
            inputs['source:'+pid+':'+name] = item
        endpoint = binding['endpoints'][pid]
        require(isinstance(endpoint,dict) and set(endpoint) == {'repository','head','script'},
                'endpoint requires declared repository, exact HEAD and tracked script')
        repo = repositories.get(endpoint['repository'])
        require(repo is not None, 'boundary endpoint repository is not declared in Work')
        root = Path(repo['root']).resolve(strict=True)
        head = _git(root, 'rev-parse', 'HEAD').decode('ascii').strip()
        require(head == endpoint['head'], 'boundary endpoint HEAD mismatch')
        require(not _git(root, 'status','--porcelain','--untracked-files=no').strip(),
                'boundary endpoint tracked implementation is dirty')
        script, info = _dependency(root, endpoint['script'])
        rel = script.relative_to(root).as_posix()
        require(any(fnmatch.fnmatchcase(rel,pat) for pat in repo['production_paths'])
                and not any(fnmatch.fnmatchcase(rel,pat) for pat in repo['test_paths']),
                'boundary endpoint must be a declared production path, not a test double')
        require(_git(root, 'rev-parse', 'HEAD:'+rel).strip()==_git(root,'hash-object','--path='+rel,str(script)).strip(),
                'boundary endpoint is not the tracked executable source')
        inputs['endpoint:'+pid] = info
        endpoints[pid] = {'root':root,'script':script,'head':head}
    require(endpoints[link['source_process']]['script'] != endpoints[link['target_process']]['script'],
            'the two independently launched endpoints must be distinct')
    return binding, files, models, hashes, assemblies, endpoints, inputs


def input_hashes(path, repositories):
    return prepare(path, repositories)[-1]


def _profile(model, pi_id, operation_id, direction, peer):
    # A boundary-level obligation cannot be discharged by one chosen operation
    # from a multi-operation/bidirectional PI. Other profiles remain unproved.
    bound = [b for b in model['pi_boundaries'] if b['artifact'] == pi_id]
    ops = [o for o in model['pi_operations'] if o['source_pi'] == pi_id]
    expected = 'send' if direction == 'provide' else 'receive'
    if (len(bound)!=1 or bound[0]['direction']!=expected
            or bound[0].get('peers',[bound[0].get('peer')]) != [peer]
            or len(ops)!=1 or ops[0]['id']!=operation_id or ops[0]['direction']!=direction):
        raise Unsupported('profile requires a single-operation, one-way bound PI')
    if (model.get('definitions') or model.get('output_frames') or
            any(f['role'] not in ('input','output') for f in model['fields'])):
        raise Unsupported('profile requires stateless input/output-only models without explicit alternative frames')
    accepts=[o for o in model['pi_operations'] if o['direction']=='accept']
    provides=[o for o in model['pi_operations'] if o['direction']=='provide']
    if len(accepts)!=1 or len(provides)!=1 or not accepts[0].get('trigger') or provides[0].get('trigger')!=accepts[0]['trigger']:
        raise Unsupported('profile requires one accepted and one provided operation in one evaluation cut')
    accept, provide=accepts[0], provides[0]
    trigger=accept['trigger']
    if {r['trigger'] for r in model['rules']}!={trigger}:
        raise Unsupported('profile requires all rules in the same Trigger')
    fields={f['id']:f for f in model['fields']}
    ins={k:f for k,f in fields.items() if f['role']=='input'}
    outs={k:f for k,f in fields.items() if f['role']=='output'}
    if not ins or not outs or any(f['source_pi']!=op['source_pi'] or
            composition._effective_presence(model,op['id'],f)!='required' or
            f['domain']['type'] not in ('boolean','enum','integer')
            for fs,op in ((ins,accept),(outs,provide)) for f in fs.values()):
        raise Unsupported('profile requires all input/output fields required and scalar')
    return accept,provide,ins,outs,trigger


def _allowed(model, profile, values):
    _,_,ins,outs,trigger=profile
    require(set(values)==set(ins) and all(typed.contains(f['domain'],values[k]) for k,f in ins.items()),
            'runtime input tuple does not match declared types')
    if not all(eval_expr(c, values, {}) is True for c in _active_pi_constraints(model,trigger)):
        return None
    rules=[r for r in model['rules'] if r['trigger']==trigger and eval_expr(r['when'],values,{}) is True]
    require(len(rules)==1, 'runtime boundary source Guard not uniquely covered')
    result=[]
    for outcome in rules[0]['allowed']:
        writes=outcome['write']
        require(len(writes)==len(outs) and {w['target'] for w in writes}==set(outs),
                'runtime boundary requires the complete output tuple')
        emitted={w['target']:eval_expr(w['expr'],values,{}) for w in writes}
        require(all(typed.contains(f['domain'],emitted[k]) for k,f in outs.items()),
                'runtime boundary output outside declared type')
        result.append(emitted)
    require(bool(result),'runtime boundary has no allowed output')
    return result


def _cases(model, profile):
    ins=profile[2]; keys=sorted(ins)
    dims=[typed.finite_values(ins[k]['domain'],MAX_CASES) for k in keys]
    if any(not d for d in dims) or math.prod(map(len,dims))>MAX_CASES:
        raise Unsupported('profile requires exact finite input enumeration within 64 cases')
    result=[]
    for values in itertools.product(*dims):
        inputs=dict(zip(keys,values)); allowed=_allowed(model,profile,inputs)
        if allowed is not None:result.append((inputs,allowed))
    if not result:raise Unsupported('no admissible boundary stimulus')
    return result


def _object(pairs):
    result={}
    for key,val in pairs:
        if key in result:raise ValueError('duplicate JSON key')
        result[key]=val
    return result


def _observe(endpoint, data, deadline):
    # Actual subprocess I/O, no shell and no product-provided observation file.
    # TemporaryFile avoids unbounded memory use on a malformed stdout stream.
    require(time.monotonic()<deadline,'boundary observation time budget exhausted')
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            run=subprocess.run([sys.executable,'-I',str(endpoint['script'])],
                cwd=endpoint['root'],input=data,stdout=stdout,stderr=stderr,
                timeout=min(5,max(0.01,deadline-time.monotonic())),check=False)
        except subprocess.TimeoutExpired as exc:
            raise Blocked('boundary endpoint timed out') from exc
        require(run.returncode==0,'boundary endpoint execution failed')
        stdout.seek(0); raw=stdout.read(MAX_FRAME+1)
    require(0<len(raw)<=MAX_FRAME,'missing or oversized live boundary frame')
    try:
        record=json.loads(raw,object_pairs_hook=_object)
    except (UnicodeError,ValueError) as exc:
        raise Blocked('invalid live boundary frame') from exc
    require(isinstance(record,dict),'boundary frame must be an object')
    return raw,record


def _frame(execution,process,operation,fields):
    return {'execution':execution,'process':process,'pi':operation['source_pi'],
            'operation':operation['id'],'fields':fields}


def _matches(record, execution, process, operation, allowed):
    # Structural JSON equality distinguishes boolean/integer and missing/null.
    return any(json_bytes(record)==json_bytes(_frame(execution,process,operation,values)) for values in allowed)


def evaluate(path, repositories, local_model_path, local_source_hashes):
    """Run a fresh finite trace; a verdict never comes from a submitted receipt."""
    binding,files,models,hashes,assemblies,endpoints,inputs=prepare(path,repositories)
    local=read_json(local_model_path); pid=local['process']
    require(pid in files and sha(Path(local_model_path).read_bytes())==hashes[pid],
            'runtime boundary does not bind the current Work Model')
    require({r['id']:r['sha256'] for r in local['source_records']}==local_source_hashes,
            'runtime boundary local Source inventory differs from current Work')
    composition._conform_sources(models,files,assemblies,hashes)
    link=binding['links'][0]; verified=composition._link(link,models)
    require(verified['status']=='structurally-matched','runtime boundary typed/peer connection not matched')
    source_id,target_id=link['source_process'],link['target_process']
    source,target=models[source_id],models[target_id]
    try:
        a=_profile(source,link['source_pi'],link['source_operation'],'provide',target_id)
        b=_profile(target,link['target_pi'],link['target_operation'],'accept',source_id)
        cases=_cases(source,a)
        # Every declared producer alternative must be accepted by the receiver.
        # Runtime exercises actual selected outcomes, not artificial forcing of
        # nondeterminism. v1 only accepts deterministic output tuples.
        pairs=[(f['source_field'],f['target_field']) for f in verified['field_links']]
        if {x for x,y in pairs}!=set(a[3]) or {y for x,y in pairs}!=set(b[2]):
            raise Unsupported('link must map the entire source and target tuple')
        for _, alternatives in cases:
            if len({json_bytes(x) for x in alternatives})!=1:
                raise Unsupported('profile cannot force or exhaust non-deterministic producer alternatives')
            for candidate in alternatives:
                permitted=_allowed(target,b,{y:candidate[x] for x,y in pairs})
                require(permitted is not None,'producer allowed tuple violates receiver constraints')
    except Unsupported as exc:
        return {'status':'inconclusive','reason':str(exc),'covered_obligation_ids':[], 'inputs':inputs}
    observations=[]
    deadline=time.monotonic()+60
    for stimulus, expected in cases:
        execution=secrets.token_hex(16)
        # The producer's actual output bytes are forwarded *unchanged* to the
        # independently started receiver. No reconstructed expected value is
        # injected in place of actual delivery.
        raw, sent=_observe(endpoints[source_id],json_bytes(_frame(execution,source_id,a[0],stimulus)),deadline)
        require(_matches(sent,execution,source_id,a[1],expected),'live producer frame violates source outcome or execution/Operation identity')
        received_values={y:sent['fields'][x] for x,y in pairs}
        allowed=_allowed(target,b,received_values)
        require(allowed is not None,'live boundary receiver input inadmissible')
        reply, observed=_observe(endpoints[target_id],raw,deadline)
        require(_matches(observed,execution,target_id,b[1],allowed),'live receiver output violates target outcome or execution/Operation identity')
        observations.append({'execution':execution,'stimulus':stimulus,'source_output':sent,
                             'delivered_bytes_sha256':sha(raw),'receiver_output':observed,
                             'receiver_output_bytes_sha256':sha(reply)})
    require(input_hashes(path,repositories)==inputs and sha(Path(local_model_path).read_bytes())==hashes[pid],
            'boundary input or endpoint changed during execution')
    local_pi=link['source_pi'] if pid==source_id else link['target_pi']
    peer=target_id if pid==source_id else source_id
    return {'status':'passed','profile':'finite-required-stream/v1','inputs':inputs,
            'model_sha256':hashes,'observations':observations,
            'covered_obligation_ids':['cross-process.boundary.'+local_pi+'.'+peer],
            'limitation':'actual independently launched production endpoints over the declared stream path; no claim about other deployment routes, external effects, unobserved operations, dependency/environment attestation or hostile endpoint authenticity'}
