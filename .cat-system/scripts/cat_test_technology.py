#!/usr/bin/env python3
"""Bounded technology execution checks for real Vitest and Playwright runs.

These checks cover adopted test-tool execution only. They are not static
proofs of UI/capability closure, provider authenticity, or all PI behavior.
"""
from __future__ import annotations

import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import cat_compile_v2 as compiler
from catlib.common import Blocked, read_json, require, sha

VITEST = ['node', 'node_modules/vitest/vitest.mjs', 'run']
NODE_TEST = ['node', '--test', '--test-reporter=junit']


def file_hash(path):
    require(path.is_file(), 'missing test technology input: '+str(path))
    return sha(path.read_bytes())


def package(cwd, name, entry, root=None):
    # Test tooling may be installed into an isolated dependency directory and
    # linked into the project; read the actual entry used by Node.
    root = root or cwd/'node_modules'/name
    meta = root/'package.json'
    doc = read_json(meta)
    require(doc.get('name') == name and isinstance(doc.get('version'), str), 'unexpected test runner package')
    if (cwd/'package-lock.json').is_file():
        lock = read_json(cwd/'package-lock.json')
        version = lock.get('packages',{}).get('node_modules/'+name,{}).get('version')
        require(version is None or version == doc['version'], 'test runner differs from adopted lockfile')
    return {'name': name, 'version': doc['version'], 'metadata_sha256': file_hash(meta),
            'entry_sha256': file_hash(root/entry)}


def command_kind(argv):
    # No shell wrapper, custom executable, config override, exclude or name
    # filtering is admitted in this bounded checker.
    if argv[:3] == VITEST and len(argv) >= 6:
        flags = argv[4:]
        if (flags.count('--reporter=junit') == 1 and
            sum(x.startswith('--outputFile=') for x in flags) == 1 and
            all(re.fullmatch(r'--(?:maxWorkers|testTimeout)=\d+', x) or
                x == '--reporter=junit' or x.startswith('--outputFile=') for x in flags)):
            return 'vitest', argv[3]
    if (argv[:3] == NODE_TEST and len(argv) == 7 and
            argv[3].startswith('--test-reporter-destination=') and
            argv[4:6] == ['--test-reporter=spec','--test-reporter-destination=stdout']):
        return 'node-test', argv[6]
    return None, None


def identity(cwd, argv, technologies):
    kind, test = command_kind(argv)
    if kind is None:
        return None
    if not (('Vitest' in technologies and kind == 'vitest') or 'Playwright' in technologies or (kind=='node-test' and any(t in technologies for t in ('Node','NestJS','PostgreSQL')))):
        return None
    try:
        node = subprocess.run(['node','--version'],cwd=cwd,capture_output=True,text=True,timeout=10,check=True).stdout.strip()
        require(re.fullmatch(r'v\d+\.\d+\.\d+',node), 'unknown Node runtime')
        head = subprocess.run(['git','rev-parse','HEAD'],cwd=cwd,capture_output=True,text=True,timeout=10,check=True).stdout.strip()
        require(re.fullmatch(r'[a-f0-9]{40,64}',head),'test technology requires fixed repository HEAD')
        info = {'kind':kind,'test':test,'node':node,'head':head}
        if kind == 'vitest':
            info['vitest'] = package(cwd,'vitest','vitest.mjs')
        if 'Playwright' in technologies:
            info['playwright'] = package(cwd,'playwright','index.mjs')
            info['playwright_core'] = package(cwd,'playwright-core','lib/server/browserType.js',
                (cwd/'node_modules'/'playwright').resolve().parent/'playwright-core')
        return info
    except (Blocked,OSError,subprocess.SubprocessError,ValueError,KeyError):
        return None


def browser_events(stdout, stderr, report):
    # Official Playwright pw:browser diagnostics emitted by the invoked test
    # process. Keep only PID pairing, not the command line or browser output.
    logs = stdout+'\n'+stderr
    if report.is_file():
        for tag in ET.parse(report).getroot().iter():
            if tag.tag in ('system-out','system-err') and tag.text:
                logs+='\n'+tag.text
    launched = re.findall(r'pw:browser\s+<launched> pid=(\d+)',logs)
    exited = re.findall(r'pw:browser\s+\[pid=(\d+)\]\s+<process did exit: exitCode=0, signal=null>',logs)
    return {'launched': sorted(set(launched)), 'clean_exit': sorted(set(exited))}


def observation(before, after, stdout, stderr, report):
    if before is None or before != after:
        return None
    result = dict(before)
    if 'playwright' in before:
        result['browser'] = browser_events(stdout, stderr, report)
    return result


def verify_report(path, expected, receipt):
    require(file_hash(path)==receipt.get('junit_sha256'), 'test technology report changed')
    nodes=ET.parse(path).getroot().findall('.//testcase')
    require(nodes and len({n.get('name') for n in nodes})==len(nodes), 'test technology report missing or ambiguous')
    require({n.get('name') for n in nodes}==set(expected), 'test technology report has unexpected test inventory')
    require(all(not any(n.find(t) is not None for t in ('error','failure','skipped')) for n in nodes), 'test technology report contains failed or skipped cases')
    require(receipt.get('observed_targets')=={x:'passed' for x in expected}, 'test technology target receipt mismatch')


def checked_receipt(wpath, work, cwd, check, receipt_path, generated=None):
    receipt = read_json(receipt_path)
    require(receipt.get('schema')=='cat-flow-evidence/v1' and receipt.get('work_id')==work['id'] and
            receipt.get('manifest_sha256')==file_hash(wpath) and receipt.get('check_id')==check['id'] and
            receipt.get('stage')==check['stage'] and receipt.get('runner')=='junit' and
            receipt.get('verdict')=='passed' and receipt.get('exit_code')==0 and
            receipt.get('cwd')==str(cwd), 'test technology receipt context mismatch')
    report=wpath.parent/'.cat-flow'/'reports'/(check['id']+'.xml')
    argv=[arg.replace('{report}',str(report)) for arg in check['argv']]
    require(receipt.get('argv')==argv,'test technology command changed')
    observed=receipt.get('test_technology') or {}
    live=identity(cwd,argv,work['technologies'])
    require(live is not None and {k:v for k,v in observed.items() if k!='browser'}==live,'test technology execution identity missing or stale')
    recorded=receipt.get('input_sha256') or {}
    require(set(recorded)==set(check.get('input_paths',[])), 'test technology inputs differ')
    require(live['test'] in recorded,'executed test not in input inventory')
    for raw, digest in recorded.items():
        path=(cwd/raw).resolve()
        require(path.is_relative_to(cwd), 'test technology input outside repository')
        actual = generated[1] if generated is not None and path==generated[0] else file_hash(path)
        require(digest==actual,'test technology input changed: '+raw)
    verify_report(report,check['test_ids'],receipt)
    browser=observed.get('browser') or {}
    return {'kind':live['kind'],'browser':bool(browser.get('launched')) and browser.get('launched')==browser.get('clean_exit'),
            'check_id':check['id'],'receipt_sha256':file_hash(receipt_path)}


def inspect(wpath, work, cwd, model, vectors, queue, binding, test_path):
    """Caller must first verify current Queue receipts with cat_queue_evidence."""
    results=[]
    observations=[]
    error=None
    checks={c['id']:c for c in work['checks']}
    try:
        require(queue and queue.get('items') and all(x['status']=='done' for x in queue['items']), 'test technology requires all Queue items complete')
        require(len({x['evidence_ref'] for x in queue['items']})==len(queue['items']), 'test technology receipt reused')
        for item in queue['items']:
            path=Path(item['evidence_ref'])
            check=checks.get(read_json(path).get('check_id'))
            require(check and check['stage']=='green','missing Green check declaration')
            chosen=[x for x in vectors['cases'] if x['id']==item['vector_ref']]
            require(len(chosen)==1,'test technology vector missing')
            subset={**vectors,'cases':chosen}
            text=compiler.emit_vitest(model,subset,binding)
            expected=model['process']+' CAT symbolic contract > '+item['vector_ref']
            require(check['test_ids']==[expected],'generated test technology target differs')
            kind,raw=command_kind(check['argv'])
            require(kind=='vitest' and (cwd/raw).resolve()==test_path,'Green command does not execute current generated test')
            inputs={(cwd/p).resolve() for p in check.get('input_paths',[])}
            driver=read_json(binding)['driver']
            driver_base=(test_path.parent/driver).resolve()
            matches=[p for p in inputs if p==driver_base or p.with_suffix('')==driver_base]
            require(binding in inputs and len(matches)==1,'generated test driver/binding not pinned')
            observations.append(checked_receipt(wpath,work,cwd,check,path,(test_path,sha(text.encode('utf-8')))))
    except (Blocked,OSError,ValueError,KeyError,TypeError,ET.ParseError) as exc:
        error=str(exc)
    for tech in ('Vitest','Playwright'):
        if tech not in work['technologies']: continue
        observed=[] if error else observations
        passed=bool(observed) and (tech=='Vitest' or all(x['browser'] for x in observed))
        reason=error or 'browser execution not observed for every current vector'
        # An independently declared browser test may cover adopted browser
        # execution when the generated vectors use a pure policy driver.
        # It is deliberately NOT promoted to a CAT vector/behavior receipt.
        if tech=='Playwright' and not passed:
            for check in work['checks']:
                if check['stage']!='implementation-conformance' or not check['id'].startswith('browser-'):continue
                try:
                    kind,raw=command_kind(check['argv'])
                    require(kind=='node-test' and raw in work['repositories'][0].get('test_paths',[]), 'independent browser test not scoped to Work')
                    receipt=wpath.parent/'.cat-flow'/'evidence'/(check['id']+'.json')
                    actual=checked_receipt(wpath,work,cwd,check,receipt)
                    require(actual['browser'],'real browser launch/clean exit not observed')
                    observed=[actual];passed=True;break
                except (Blocked,OSError,ValueError,KeyError,TypeError,ET.ParseError) as exc:
                    reason=str(exc)
        results.append({'technology':tech,'status':'passed' if passed else 'inconclusive',
                        'covered_obligation_ids':['implementation-constraint.'+tech.lower()] if passed else [],
                        'reason': 'bounded execution of adopted test technology verified' if passed else reason,
                        'observations': observed if passed else []})
    return results
