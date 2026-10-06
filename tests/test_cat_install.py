from __future__ import annotations
import sys
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'scripts'))
import cat_install as installer
import cat_flow as flow


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        fixture = Path(__file__).resolve().parent/'fixtures/minimal/Work.md'
        _, self.work = flow.work_file(fixture)
        self.workpath = self.project/'Work.md'
        self.workpath.write_text(fixture.read_text(encoding='utf-8'), encoding='utf-8')

    def selected(self, adapter=None):
        return installer.sources(self.work, adapter)

    def test_plan_does_not_write(self):
        a,s,e=self.selected()
        rows=installer.plan(self.project,a,s,False,e)
        self.assertTrue(rows)
        self.assertFalse((self.project/'.cat-system').exists())
        self.assertEqual(len([p for p in s if p.parent.name.startswith('tech-')]),3)

    def test_plan_excludes_unadopted_tech_everywhere(self):
        a,s,e=self.selected()
        rows=installer.plan(self.project,a,s,False,e)
        rel=[str(dst.relative_to(self.project)) for _,dst,_ in rows]
        self.assertFalse(any('tech-playwright' in x for x in rel))
        self.assertFalse(any('tech-vue' in x for x in rel))
        self.assertTrue(any('tech-vitest' in x for x in rel))
        self.assertIn('.cat-system/skills/cat-artifacts/scripts/cat_artifact_scaffold.py', rel)
        self.assertIn('.github/skills/tech-vitest/scripts/cat_vitest_renderer.py', rel)

    def test_project_extension_is_explicit_only(self):
        a,s,e=self.selected()
        rel=[str(dst.relative_to(self.project)) for _,dst,_ in installer.plan(self.project,a,s,False,e)]
        self.assertFalse(any('xplayserver-adapter' in x or 'XPlayServer.md' in x for x in rel))
        a,s,e=self.selected('xplayserver-adapter')
        self.assertEqual(e.name,'xplayserver-adapter')
        rel=[str(dst.relative_to(self.project)) for _,dst,_ in installer.plan(self.project,a,s,False,e)]
        self.assertIn('.github/skills/xplayserver-adapter/SKILL.md',rel)
        self.assertIn('.cat-system/extensions/xplayserver-adapter/XPlayServer.md',rel)
        rows=installer.plan(self.project,a,s,False,e)
        self.assertEqual(installer.planned_reference_errors(self.project,rows),[])

    def test_multi_skill_technology_is_selected_only_when_adopted(self):
        self.work['technologies']=['Docker']
        _, skills, _ = self.selected()
        names={p.parent.name for p in skills}
        expected={'docker-project-foundations','docker-build-strategies',
                  'docker-compose-patterns','docker-destructive-guardrails'}
        self.assertTrue(expected.issubset(names))
        self.work['technologies']=['TypeScript']
        _, skills, _ = self.selected()
        names={p.parent.name for p in skills}
        self.assertTrue(expected.isdisjoint(names))

    def test_unknown_technology_blocks(self):
        self.work['technologies']=['MadeUpFramework']
        with self.assertRaises(flow.Blocked): installer.sources(self.work,None)

    def test_conflicts_are_not_silently_overwritten(self):
        agents,skills,ext=self.selected()
        target=self.project/'.github/agents/orchestrator.agent.md'
        target.parent.mkdir(parents=True); target.write_text('USER_CUSTOM_AGENT',encoding='utf-8')
        result=installer.plan(self.project,agents,skills,False,ext)
        self.assertIn(str(target),[str(dst) for _,dst,kind in result if kind=='conflict'])
        self.assertEqual(target.read_text(),'USER_CUSTOM_AGENT')

    def test_runtime_plan_separates_docs_config_tests(self):
        agents,skills,ext=self.selected()
        rows=installer.plan(self.project,agents,skills,False,ext)
        rel=[str(dst.relative_to(self.project)) for _,dst,_ in rows]
        self.assertIn('.cat-system/docs/Artifact記法.md', rel)
        self.assertIn('.cat-system/config/routing.json', rel)
        self.assertIn('.cat-system/optional-skills/cat-conformance-review/SKILL.md', rel)
        self.assertFalse(any(x.startswith('.cat-system/tests/') for x in rel))
        self.assertEqual(installer.planned_reference_errors(self.project,rows),[])

    def test_broken_post_install_reference_blocks_before_write(self):
        agents,skills,ext=self.selected()
        skill=next(x for x in skills if x.parent.name=='cycle-management')
        original=skill.read_text(encoding='utf-8')
        try:
            skill.write_text(original+'\nBroken: `.cat-system/docs/DOES_NOT_EXIST.md`\n',encoding='utf-8')
            rows=installer.plan(self.project,agents,skills,False,ext)
            errs=installer.planned_reference_errors(self.project,rows)
            self.assertTrue(any('DOES_NOT_EXIST' in x for x in errs))
        finally:
            skill.write_text(original,encoding='utf-8')

    def test_apply_then_route_and_references_from_installed_runtime(self):
        result = subprocess.run([sys.executable, str(installer.ROOT/'scripts/cat_install.py'),
            '--work',str(self.workpath),'--project-root',str(self.project),'--apply'],
            text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        payload=json.loads(result.stdout); self.assertEqual(payload['reference_errors'],[])
        runner=self.project/'.cat-system/scripts/cat_flow.py'; self.assertTrue(runner.is_file())
        result=subprocess.run([sys.executable,str(runner),'route','--work',str(self.workpath),'--stage','tests'],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        selected=json.loads(result.stdout); self.assertEqual(selected['status'],'ready')
        self.assertTrue((self.project/'.github/skills/tech-vitest/SKILL.md').is_file())
        self.assertFalse((self.project/'.github/skills/tech-playwright').exists())
        self.assertFalse((self.project/'.cat-system/skills/tech-playwright').exists())
        self.assertFalse((self.project/'.cat-system/extensions/xplayserver-adapter').exists())
        again=subprocess.run([sys.executable,str(installer.ROOT/'scripts/cat_install.py'),
            '--work',str(self.workpath),'--project-root',str(self.project)],text=True,capture_output=True)
        self.assertEqual(again.returncode,0,again.stderr)
        self.assertEqual(json.loads(again.stdout)['conflicts'],[])

    def test_installed_runtime_rejects_work_escape(self):
        result=subprocess.run([sys.executable,str(installer.ROOT/'scripts/cat_install.py'),
            '--work',str(self.workpath),'--project-root',str(self.project),'--apply'],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        workdir=self.project/'Lifecycle'/'Works'/'w'; workdir.mkdir(parents=True)
        outside=self.project/'Lifecycle'/'Works'/'outside'; outside.mkdir()
        fixture=Path(__file__).resolve().parent/'fixtures/minimal'
        for name in ('PI.md','TCE.md'):
            shutil.copyfile(fixture/name, workdir/name)
        shutil.copyfile(fixture/'Process.md',outside/'Process.md')
        text=(fixture/'Work.md').read_text(encoding='utf-8').replace('Process.md | PI.md', '@work/../outside/Process.md | PI.md')
        wp=workdir/'Work.md'; wp.write_text(text,encoding='utf-8')
        runner=self.project/'.cat-system/scripts/cat_flow.py'
        out=subprocess.run([sys.executable,str(runner),'compile','--work',str(wp),'--kind','model'],text=True,capture_output=True)
        self.assertEqual(out.returncode,2)
        self.assertIn('escapes allowed compilation boundary',out.stderr)

    def test_symlink_is_refused(self):
        agents,skills,ext=self.selected()
        target=self.project/'.github/agents/orchestrator.agent.md'; target.parent.mkdir(parents=True)
        target.symlink_to(self.workpath)
        with self.assertRaises(flow.Blocked): installer.plan(self.project,agents,skills,False,ext)


if __name__=='__main__': unittest.main()
