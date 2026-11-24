from __future__ import annotations
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system/scripts'))
import cat_node_service_technology as checker
import cat_flow as flow
from catlib.common import Blocked,json_bytes

class NodeServiceTechnologyTest(unittest.TestCase):
    def test_supported_engine_and_actual_node(self):
        import shutil
        self.assertTrue(checker.node_engine('v22.1.0','>=22'))
        self.assertFalse(checker.node_engine('v21.99.99','>=22'))
        self.assertFalse(checker.node_engine('v22.0.0','>=22.1'))
        with self.assertRaises(Blocked):checker.node_engine('v22.1.0','^22')
        if shutil.which('node'):
            actual=subprocess.check_output(['node','--version'],text=True).strip()
            self.assertTrue(checker.node_engine(actual,'>=1'))
    def test_disposable_environment_is_mandatory(self):
        env={'NODE_ENV':'test','HTTP_ACCEPTANCE_DISPOSABLE_DB':'1','DATABASE_URL':'postgres://test:password@127.0.0.1:5432/isolated_test','HTTP_API_URL':'http://127.0.0.1:3001','HTTP_BASE_URL':'http://127.0.0.1:3000'}
        with patch.dict(os.environ,env,clear=True):checker.disposable_env('isolated_test')
        for k,v in [('NODE_ENV','production'),('HTTP_ACCEPTANCE_DISPOSABLE_DB','0'),('DATABASE_URL','postgres://other.invalid/isolated_test'),('DATABASE_URL','postgres://127.0.0.1/other'),('HTTP_BASE_URL','https://external.invalid')]:
            with patch.dict(os.environ,{**env,k:v},clear=True), self.assertRaises(Blocked):checker.disposable_env('isolated_test')
    def test_missing_or_unscoped_runtime_binding_never_passes(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);p=r/'binding.json';p.write_bytes(json_bytes({'schema':checker.SCHEMA,'repository':'wrong','check':'runtime-check','package':'package.json','engine_package':'package.json','postgres':{}}))
            w={'technologies':['Node','NestJS','PostgreSQL'],'repositories':[{'name':'app','production_paths':[]}],'checks':[]}
            result=checker.inspect(r/'work.json',w,r,p)
            self.assertEqual(len(result),3)
            self.assertTrue(all(x['status']=='inconclusive' and not x['covered_obligation_ids'] for x in result))
    def test_lock_and_manifest_match_required(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);p=r/'node_modules/pg';p.mkdir(parents=True);(p/'package.json').write_bytes(json_bytes({'name':'pg','version':'1.0.0'}))
            lock={'packages':{'node_modules/pg':{'version':'1.0.0'}}};manifest={'dependencies':{'pg':'^1.0.0'}}
            self.assertEqual(checker.locked_package(r,lock,manifest,'pg')['version'],'1.0.0')
            with self.assertRaises(Blocked):checker.locked_package(r,{'packages':{}},manifest,'pg')
            with self.assertRaises(Blocked):checker.locked_package(r,lock,{},'pg')
if __name__=='__main__':unittest.main()
