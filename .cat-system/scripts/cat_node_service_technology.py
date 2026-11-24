#!/usr/bin/env python3
"""Bounded, live Node/Nest/PostgreSQL implementation-technology checks.

This verifies adopted runtime/toolchain constraints and scoped executed tests;
not semantic PI closure, arbitrary SQL, or remote provider authenticity.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit, unquote

from catlib.common import Blocked, require, read_json, sha
import cat_test_technology as test_technology

SCHEMA='cat-node-service-technology/v1'
TECHNOLOGIES=('Node','NestJS','PostgreSQL')


def file(repo, rel):
    require(isinstance(rel,str) and rel,'runtime constraint path required')
    p=(repo/rel).resolve()
    require(p.is_relative_to(repo) and p.is_file(),'runtime constraint file missing or outside repository: '+rel)
    return p


def node_engine(version, requirement):
    # Bounded project-engine contract, not a generic semver parser.
    match=re.fullmatch(r'>=(\d+)(?:\.(\d+)(?:\.(\d+))?)?', requirement or '')
    actual=re.fullmatch(r'v(\d+)\.(\d+)\.(\d+)',version or '')
    require(match and actual,'unsupported Node engine constraint')
    return tuple(map(int,actual.groups()))>=tuple(int(x or 0) for x in match.groups())


def disposable_env(database):
    require(os.environ.get('HTTP_ACCEPTANCE_DISPOSABLE_DB')=='1' and os.environ.get('NODE_ENV')=='test',
            'live service probe requires explicitly disposable test environment')
    url=urlsplit(os.environ.get('DATABASE_URL',''))
    require(url.scheme in ('postgres','postgresql') and url.hostname in ('127.0.0.1','localhost','::1')
            and unquote(url.path.lstrip('/'))==database and not url.query and not url.fragment,
            'live service probe requires the explicitly bound loopback test database')
    for key in ('HTTP_API_URL','HTTP_BASE_URL'):
        address=urlsplit(os.environ.get(key,''))
        require(address.scheme=='http' and address.hostname=='127.0.0.1' and address.port is not None
                and address.path in ('','/') and not address.username and not address.password,
                'service test endpoints must be disposable loopback HTTP')


def locked_package(repo, lock, manifest, name):
    p=file(repo,'node_modules/'+name+'/package.json');installed=read_json(p)
    expected=lock.get('packages',{}).get('node_modules/'+name,{}).get('version')
    require(name in manifest.get('dependencies',{}) and installed.get('name')==name and isinstance(expected,str)
            and installed.get('version')==expected,'adopted runtime dependency mismatch: '+name)
    return {'package':name,'version':expected,'metadata_sha256':sha(p.read_bytes())}


# Probe is authored by the verifier, not supplied by a project binding or an
# arbitrary test receipt. Only a real installed Nest module / pg driver are
# used. No credentials or response body values are emitted into the receipt.
PROBE=r'''
const {createRequire}=require('node:module');
const path=require('node:path');
const spec=JSON.parse(process.argv[1]);
const req=createRequire(path.resolve(spec.package));
(async()=>{
  const out={node:process.version};
  if(spec.postgres){
    const {Client}=req('pg');
    const client=new Client({connectionString:process.env.DATABASE_URL});
    await client.connect();
    try{
      await client.query('BEGIN READ ONLY');
      const r=await client.query("SELECT current_database() AS name, current_setting('server_version_num')::int AS version");
      const inventory=await client.query('SELECT '+spec.postgres.column+' AS migration FROM '+spec.postgres.table+' ORDER BY 1');
      out.postgres={name:r.rows[0].name,version:r.rows[0].version,migrations:inventory.rows.map(x=>x.migration)};
      await client.query('COMMIT');
    }finally{await client.end()}
  }
  if(spec.nest){
    req('reflect-metadata');
    const {NestFactory}=req('@nestjs/core');
    const module=req(path.resolve(spec.nest.module))[spec.nest.export];
    if(typeof module!=='function')throw Error('Nest module export missing');
    const app=await NestFactory.create(module,{logger:false,abortOnError:false});
    try{
      await app.listen(0,'127.0.0.1');
      const address=app.getHttpServer().address();
      const response=await fetch('http://127.0.0.1:'+address.port+spec.nest.health_path,{redirect:'manual'});
      const body=await response.json();
      if(response.status!==200||Object.entries(spec.nest.health_fields).some(([k,v])=>body[k]!==v))throw Error('Nest route observation differs');
      out.nest={status:response.status,module:spec.nest.export,loopback:true};
    }finally{await app.close()}
  }
  process.stdout.write(JSON.stringify(out));
})().catch(e=>{console.error(e.name);process.exitCode=1});
'''


def inspect(wpath, work, repo, binding_path):
    selected=[x for x in TECHNOLOGIES if x in work.get('technologies',[])]
    if not selected:return []
    try:
        b=read_json(binding_path)
        require(b.get('schema')==SCHEMA and set(b)<= {'schema','repository','check','package','engine_package','postgres','nest'}
                and all(k in b for k in ('repository','check','package','engine_package','postgres')),'invalid service technology binding')
        declared=work['repositories'][0]
        require(len(work['repositories'])==1 and b['repository']==declared['name'],'service technology repository mismatch')
        check=next((x for x in work['checks'] if x['id']==b['check']),None)
        require(check and check['stage']=='implementation-conformance' and check['id'].startswith('runtime-'), 'runtime check missing')
        kind,test=test_technology.command_kind(check['argv'])
        require(kind=='node-test' and test in declared.get('test_paths',[]),'runtime check must execute scoped Node test')
        paths={(repo/p).resolve() for p in check.get('input_paths',[])}
        required={binding_path.resolve(),file(repo,b['package']),file(repo,b['engine_package']),file(repo,'package-lock.json')}
        for raw in declared.get('production_paths',[]):
            required.add(file(repo,raw))
        pg=b['postgres'];require(isinstance(pg,dict) and set(pg)=={'database','migrations','table','column'}, 'invalid PostgreSQL probe binding')
        require(isinstance(pg['database'],str) and re.fullmatch(r'[A-Za-z0-9_]+',pg['database']),'invalid test database name')
        for key in ('table','column'):
            require(isinstance(pg[key],str) and re.fullmatch(r'[a-z_][a-z0-9_]*',pg[key]), 'invalid migration inventory identifier')
        directory=(repo/pg['migrations']).resolve();require(directory.is_relative_to(repo) and directory.is_dir(),'migration directory missing')
        migrations=sorted(p for p in directory.glob('*.sql') if p.is_file())
        require(migrations,'migration inventory missing')
        required.update(migrations)
        if 'NestJS' in selected:
            n=b.get('nest');require(isinstance(n,dict) and set(n)=={'module','export','health_path','health_fields'},'invalid Nest runtime binding')
            require(re.fullmatch(r'[A-Za-z_$][\w$]*',n['export']) and re.fullmatch(r'/[A-Za-z0-9_/-]+',n['health_path'])
                    and isinstance(n['health_fields'],dict) and n['health_fields'] and all(isinstance(x,str) for x in n['health_fields'].values()),'invalid Nest route probe')
            required.add(file(repo,n['module']))
        else:require('nest' not in b,'Nest probe not declared in Work')
        require(required<=paths,'runtime check does not bind all production/configuration/migration inputs')
        disposable_env(pg['database'])
        receipt=wpath.parent/'.cat-flow'/'evidence'/(check['id']+'.json')
        observed=test_technology.checked_receipt(wpath,work,repo,check,receipt)
        manifest=read_json(file(repo,b['package']));lock=read_json(file(repo,'package-lock.json'))
        packages=[locked_package(repo,lock,manifest,'pg')]
        if 'NestJS' in selected:
            packages.extend(locked_package(repo,lock,manifest,name) for name in ('@nestjs/core','@nestjs/common','@nestjs/platform-express'))
        run=subprocess.run(['node','-e',PROBE,json.dumps(b,ensure_ascii=True)],cwd=repo,capture_output=True,text=True,timeout=60,check=False)
        require(run.returncode==0,'live Node/Nest/PostgreSQL probe failed')
        value=json.loads(run.stdout)
        engine=read_json(file(repo,b['engine_package'])).get('engines',{}).get('node')
        require(node_engine(value.get('node'),engine),'runtime does not satisfy adopted Node engine')
        actual=value.get('postgres',{})
        require(actual.get('name')==pg['database'] and type(actual.get('version')) is int and actual['version']>0
                and actual.get('migrations')==[p.name for p in migrations], 'live PostgreSQL migration inventory differs')
        if 'NestJS' in selected:
            require(value.get('nest')=={'status':200,'module':b['nest']['export'],'loopback':True},'live Nest route not observed')
        return [{'technology':t,'status':'passed','covered_obligation_ids':['implementation-constraint.'+t.lower()],
                 'reason':'adopted live runtime and scoped named service test observed',
                 'runtime':value,'packages':packages,'test':observed,'binding_sha256':sha(binding_path.read_bytes())} for t in selected]
    except (Blocked,ValueError,TypeError,KeyError,AttributeError,OSError,ET.ParseError,subprocess.SubprocessError) as exc:
        return [{'technology':t,'status':'inconclusive','reason':str(exc),'covered_obligation_ids':[]} for t in selected]
