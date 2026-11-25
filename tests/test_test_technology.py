from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system/scripts'))
import cat_test_technology as tech
import cat_flow as flow
import cat_queue
import cat_queue_evidence
import cat_compile_v2 as compiler
from catlib.common import Blocked,json_bytes,sha
from test_queue_evidence import spec


class TestTechnologyTests(unittest.TestCase):
    def test_only_standard_unfiltered_runner(self):
        cmd=['node','node_modules/vitest/vitest.mjs','run','one.test.ts','--maxWorkers=1','--reporter=junit','--outputFile={report}']
        self.assertEqual(tech.command_kind(cmd),('vitest','one.test.ts'))
        for args in (cmd+['--testNamePattern=one'],cmd+['--config=custom.mjs'],['node','fake.mjs',*cmd[2:]],cmd[:-1]):
            self.assertEqual(tech.command_kind(args),(None,None))

    def test_browser_launch_requires_corresponding_clean_exit(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td)/'report.xml'
            r.write_text('<testsuites><testsuite><system-err>pw:browser &lt;launched&gt; pid=12\npw:browser [pid=12] &lt;process did exit: exitCode=0, signal=null&gt;</system-err></testsuite></testsuites>')
            self.assertEqual(tech.browser_events('','',r),{'launched':['12'],'clean_exit':['12']})
            r.unlink()
            self.assertEqual(tech.browser_events('','pw:browser <launched> pid=12\npw:browser [pid=13] <process did exit: exitCode=0, signal=null>',r),{'launched':['12'],'clean_exit':['13']})
            self.assertEqual(tech.browser_events('','pw:browser [pid=12] <process did exit: exitCode=1, signal=null>',r)['clean_exit'],[])

    def test_junit_wrong_inventory_or_skip_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'report.xml'
            for xml in ('<testsuite><testcase name="other"/></testsuite>', '<testsuite><testcase name="case"><skipped/></testcase></testsuite>', '<testsuite><testcase name="case"/><testcase name="case"/></testsuite>'):
                p.write_text(xml)
                with self.assertRaises(Blocked):tech.verify_report(p,['case'],{'junit_sha256':sha(p.read_bytes()),'observed_targets':{'case':'passed'}})

    def test_real_generated_vitest_current_item_and_stale_source(self):
        modules=os.environ.get('CAT_TEST_VITEST_MODULES')
        if not modules or not shutil.which('node') or not shutil.which('git'):
            self.skipTest('set CAT_TEST_VITEST_MODULES to verified installed toolchain')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();wpath=root/'work.json';binding=root/'binding.json';test=root/'current.test.ts'
            subprocess.run(['git','init','-q',str(root)],check=True)
            (root/'.gitignore').write_text('node_modules/\n.cat-flow/\n')
            (root/'node_modules').symlink_to(Path(modules).resolve(),target_is_directory=True)
            (root/'driver.ts').write_text('export function createDriver(){let ready=false;return {async prepare(pre){ready=pre["state.ready"]},async trigger(){return {"output.ok":true}},async observeState(){return {"state.ready":ready}}}}\n')
            binding.write_bytes(json_bytes({'schema':compiler.D,'process':'demo.process','driver':'./driver'}))
            model,vectors=spec();m=root/'model.json';v=root/'vectors.json';q=root/'queue.json'
            m.write_bytes(json_bytes(model));v.write_bytes(json_bytes(vectors));q.write_bytes(json_bytes(compiler.make_queue(model,vectors,m.read_bytes(),v.read_bytes())))
            test.write_text(compiler.emit_vitest(model,vectors,binding),encoding='utf-8')
            check={'id':'green','stage':'green','runner':'junit','cwd':'@repo:demo','argv':['node','node_modules/vitest/vitest.mjs','run','current.test.ts','--maxWorkers=1','--reporter=junit','--outputFile={report}'],'input_paths':['current.test.ts','binding.json','driver.ts'],'test_ids':['demo.process CAT symbolic contract > case.demo.rule'],'timeout_seconds':60}
            w={'id':'demo.work','mode':'implementation','specification':{'status':'confirmed'},'technologies':['Vitest'],'checks':[check],'repositories':[{'name':'demo','path':str(root)}],'compilation':{'queue':'queue.json'}}
            wpath.write_bytes(json_bytes(w));subprocess.run(['git','-C',str(root),'add','.'],check=True);subprocess.run(['git','-C',str(root),'-c','user.name=CAT test','-c','user.email=cat@example.invalid','commit','-qm','fixture'],check=True)
            # This is actual runner execution of the canonical generated test.
            with patch.object(flow,'compilation_path',return_value=str(q)):
                ev=flow.command_work(wpath,w,'green',execute=True)
            self.assertEqual(ev['verdict'],'passed',ev)
            ep=Path(ev['evidence'])
            cat_queue.done_from_green(q,ep,expected_work_id=w['id'],allowed_evidence_root=ep.parent)
            cat_queue_evidence.verify(w['id'],q,m,v,ep.parent)
            def inspect():return tech.inspect(wpath,w,root,model,vectors,json.loads(q.read_text()),binding,test)[0]
            self.assertEqual(inspect()['covered_obligation_ids'],['implementation-constraint.vitest'],inspect())
            (root/'driver.ts').write_text('// changed source\n')
            self.assertEqual(inspect()['status'],'inconclusive')

if __name__=='__main__':unittest.main()
