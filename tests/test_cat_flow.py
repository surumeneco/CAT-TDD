"""Contract, adversarial and read-only pilot tests for cat_flow.py."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.cat-system' / 'scripts'))
import cat_flow as flow


class CatFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workpath = Path(self.tmp.name) / 'work.json'
        self.work = {'schema': 'cat-work/v1', 'id': 'demo.test.work',
            'entry': 'issue', 'mode': 'shadow',
            'issue_ref': 'user-message-ref', 'project_entry_ref': 'https://example.org/entry',
            'normative': [{'uri': 'https://example.org/spec'}],
            'evidence': [{'uri': 'https://example.org/code'}],
            'specification': {'status': 'candidate', 'decision_ref': None, 'artifact_refs': []},
            'scope': {'process_ids': ['demo.test'], 'changed_ids': [], 'preserved_ids': []},
            'technologies': ['TypeScript', 'Vitest'], 'repositories': [], 'checks': [], 'gates': []}
        self.save()

    def save(self):
        self.workpath.write_bytes(flow.json_bytes(self.work))

    def test_valid_contract(self):
        self.assertEqual(flow.validate(self.work), [])

    def test_missing_reference(self):
        self.work['normative'] = []
        self.assertTrue(any('normative:' in x for x in flow.validate(self.work)))

    def test_confirmed_cannot_omit_decision_ref(self):
        self.work['specification']['status'] = 'confirmed'
        self.assertTrue(any('decision_ref' in x for x in flow.validate(self.work)))

    def test_code_cannot_promote_candidate_to_spec(self):
        self.assertEqual(flow.status_work(self.workpath, self.work)['specification'], 'candidate')
        self.assertEqual(flow.status_work(self.workpath, self.work)['overall'], 'not-complete')

    def test_routing_uses_declared_technologies(self):
        self.work['flow'] = 'spec-implementation'
        r = flow.route(self.work, 'tests')
        self.assertEqual(r['executor'], {'type': 'compiler', 'id': 'cat_compile_v2:tests-current'})
        self.assertIn('tech-vitest', r['skills'])
        self.assertNotIn('tech-postgresql', r['skills'])
        self.assertNotIn('tech-playwright', r['skills'])
        review = flow.route(self.work, 'test-review')
        self.assertEqual(review['executor']['type'], 'validator')
        self.assertEqual(review['conditional']['inconclusive']['id'], 'tdd-reviewer')
        self.work['flow'] = 'refactor'
        self.assertEqual(flow.route(self.work, 'refactor-scope')['executor']['id'], 'ref-scoper')

    def test_routing_flattens_multi_skill_technology(self):
        self.work['flow']='spec-implementation'
        self.work['technologies']=['Docker']
        r=flow.route(self.work,'tests')
        self.assertEqual(r['status'],'ready')
        for name in ('docker-project-foundations','docker-build-strategies',
                     'docker-compose-patterns','docker-destructive-guardrails'):
            self.assertIn(name,r['skills'])

    def test_routing_schema_uses_boolean_technology_selection(self):
        catalogue=flow.read_json(flow.CATALOG)
        self.assertEqual(catalogue['schema'],'cat-routing/v2')
        self.assertTrue(catalogue['stages']['tests']['include_technology_skills'])
        self.assertFalse(catalogue['stages']['model']['include_technology_skills'])
        self.assertEqual(catalogue['stages']['model']['executor']['type'],'compiler')
        self.assertEqual(catalogue['stages']['green']['executor']['type'],'script')

    def test_unknown_technology_blocks_instead_of_guessing(self):
        self.work['flow']='spec-implementation'
        self.work['technologies'] = ['Rust']
        r = flow.route(self.work, 'tests')
        self.assertEqual(r['status'], 'blocked')
        self.assertEqual(r['unknown_technologies'], ['Rust'])

    def test_no_git_checkout_is_not_run(self):
        self.work['repositories'] = [{'name': 'webapp', 'path': './missing-repo',
                                      'allowed_paths': ['apps/backend/test/*']}]
        self.assertEqual(flow.git_snapshot(self.workpath, self.work)[0]['status'], 'not-run')

    def test_git_diff_scope_and_branch_are_inspected(self):
        repo = Path(self.tmp.name) / 'git'
        repo.mkdir()
        def git(*args):
            subprocess.run(['git', '-C', str(repo), *args], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        git('init');git('config', 'user.email', 'test@example.org');git('config', 'user.name', 'Test')
        (repo/'src').mkdir(); (repo/'src'/'a.py').write_text('x=0\n')
        git('add','.');git('commit','-m','initial');git('checkout','-b','feature/test')
        (repo/'src'/'a.py').write_text('x=1\n')
        (repo/'secret.txt').write_text('x\n')
        self.work['repositories'] = [{'name': 'webapp', 'path': str(repo),
            'base_ref': 'HEAD', 'branch_pattern': 'feature/*',
            'allowed_paths': ['src/*']}]
        r = flow.git_snapshot(self.workpath, self.work)[0]
        self.assertEqual(r['status'], 'blocked')
        self.assertEqual(r['disallowed_changes'], ['secret.txt'])
        (repo/'secret.txt').unlink()
        self.assertEqual(flow.git_snapshot(self.workpath, self.work)[0]['status'], 'passed')

    def test_red_cannot_use_exit_only(self):
        self.work['checks'] = [{'id':'red', 'stage':'red','runner':'exit-zero',
                                'cwd':'@work','argv':['python','-V']}]
        self.assertTrue(any('requires JUnit' in e for e in flow.validate(self.work)))

    def test_no_execution_without_switch(self):
        self.work['checks'] = [{'id':'lint','stage':'review','runner':'exit-zero',
                                'cwd':'@work','argv':[sys.executable,'-c','print(42)']}]
        with self.assertRaisesRegex(flow.Blocked, '--execute'):
            flow.command_work(self.workpath, self.work, 'lint')

    def test_shadow_cannot_claim_red(self):
        self.work['checks'] = [self.junit_check('red', '<failure />', 1)]
        with self.assertRaisesRegex(flow.Blocked, 'shadow Work'):
            flow.command_work(self.workpath, self.work, 'red', True)

    def junit_check(self, stage, outcome_tag, exit_code):
        data = '<testsuites><testsuite tests="1"><testcase classname="suite" name="target">'+outcome_tag+'</testcase></testsuite></testsuites>'
        code = 'from pathlib import Path;import sys;Path(sys.argv[1]).write_text('+repr(data)+');sys.exit('+str(exit_code)+')'
        return {'id':stage, 'stage':stage, 'runner':'junit', 'cwd':'@work',
                'argv':[sys.executable,'-c',code,'{report}'], 'test_ids':['target']}

    def implementation(self):
        self.work['mode'] = 'implementation'
        self.save()

    def confirmed(self):
        self.work['mode'] = 'implementation'
        self.work['specification']['status'] = 'confirmed'
        self.work['specification']['decision_ref'] = 'https://example.org/human-decision'
        self.save()

    def test_red_does_not_self_approve_semantic_cause(self):
        self.confirmed()
        self.work['checks'] = [self.junit_check('red', '<failure message="actual failure" />', 1)]
        self.save()
        r = flow.command_work(self.workpath, self.work, 'red', True)
        self.assertEqual(r['verdict'], 'inconclusive')
        self.assertFalse(r['semantics_approved'])
        self.assertEqual(r['observed_targets'], {'target': 'failed'})

    def test_green_pass_with_junit(self):
        self.confirmed()
        self.work['checks'] = [self.junit_check('green', '', 0)]
        self.save()
        r = flow.command_work(self.workpath, self.work, 'green', True)
        self.assertEqual(r['verdict'], 'passed')
        self.assertEqual(r['observed_targets'], {'target': 'passed'})

    def test_skipped_is_not_green(self):
        self.confirmed()
        self.work['checks'] = [self.junit_check('green', '<skipped />', 0)]
        self.save()
        self.assertEqual(flow.command_work(self.workpath, self.work, 'green', True)['verdict'], 'blocked')

    def test_missing_junit_does_not_pass(self):
        self.confirmed()
        c = self.junit_check('green', '', 0)
        c['argv'] = [sys.executable,'-c','pass','{report}']
        self.work['checks'] = [c]
        self.save()
        self.assertEqual(flow.command_work(self.workpath, self.work, 'green', True)['verdict'], 'inconclusive')

    def test_stale_junit_cannot_be_reused(self):
        self.confirmed()
        self.work['checks'] = [self.junit_check('green', '', 0)]
        self.save()
        self.assertEqual(flow.command_work(self.workpath, self.work, 'green', True)['verdict'], 'passed')
        self.work['checks'][0]['argv'] = [sys.executable,'-c','pass','{report}']
        self.save()
        self.assertEqual(flow.command_work(self.workpath, self.work, 'green', True)['verdict'], 'inconclusive')

    def test_foreign_junit_failure_blocks_red(self):
        self.confirmed()
        c = self.junit_check('red', '<failure />', 1)
        c['argv'][2] = c['argv'][2].replace('</testsuite>',
            '<testcase name="other"><failure /></testcase></testsuite>')
        self.work['checks'] = [c];self.save()
        self.assertEqual(flow.command_work(self.workpath, self.work, 'red', True)['verdict'], 'blocked')

    def test_manifest_edit_invalidates_prior_evidence(self):
        self.implementation()
        self.work['checks'] = [{'id':'lint','stage':'review','runner':'exit-zero',
                                'cwd':'@work','argv':[sys.executable,'-c','pass']}]
        self.save()
        flow.command_work(self.workpath, self.work, 'lint', True)
        self.assertEqual(flow.status_work(self.workpath, self.work)['checks']['lint']['status'],'passed')
        self.work['scope']['preserved_ids'].append('new-contract')
        self.save()
        self.assertEqual(flow.status_work(self.workpath, self.work)['checks']['lint']['status'],'stale')

    def test_output_edit_invalidates_prior_evidence(self):
        self.implementation()
        (self.workpath.parent/'generated.txt').write_text('initial')
        self.work['checks'] = [{'id':'gen','stage':'tests','runner':'exit-zero',
            'cwd':'@work','argv':[sys.executable,'-c','pass'], 'output_paths':['generated.txt']}]
        self.save()
        flow.command_work(self.workpath, self.work, 'gen', True)
        (self.workpath.parent/'generated.txt').write_text('tampered')
        self.assertEqual(flow.status_work(self.workpath, self.work)['checks']['gen']['status'],'stale')

    def test_missing_declared_output_blocks(self):
        self.implementation()
        self.work['checks'] = [{'id':'gen','stage':'tests','runner':'exit-zero',
            'cwd':'@work','argv':[sys.executable,'-c','pass'], 'output_paths':['missing.txt']}]
        self.save()
        self.assertEqual(flow.command_work(self.workpath,self.work,'gen',True)['verdict'],'blocked')

    def test_source_edit_invalidates_prior_evidence(self):
        self.implementation()
        (self.workpath.parent/'source.txt').write_text('before')
        self.work['checks'] = [{'id':'lint','stage':'review','runner':'exit-zero',
            'cwd':'@work','argv':[sys.executable,'-c','pass'], 'input_paths':['source.txt']}]
        self.save()
        flow.command_work(self.workpath, self.work, 'lint', True)
        (self.workpath.parent/'source.txt').write_text('after')
        self.assertEqual(flow.status_work(self.workpath, self.work)['checks']['lint']['status'],'stale')

    def test_untrusted_absolute_source_path_rejected(self):
        self.work['checks'] = [{'id':'lint','stage':'review','runner':'exit-zero',
            'cwd':'@work','argv':['python','-V'], 'input_paths':['/etc/passwd']}]
        self.assertTrue(any('input_paths' in e for e in flow.validate(self.work)))

    def test_no_local_command_can_prove_ci_deployment(self):
        self.work['checks'] = [{'id':'ci','stage':'ci','runner':'exit-zero',
                                'cwd':'@work','argv':['python','-V']}]
        self.assertTrue(any('cannot prove ci' in e for e in flow.validate(self.work)))

    def test_compile_wrapper_replays_draft_but_not_normative(self):
        import shutil
        fixture = Path(__file__).resolve().parent/'fixtures/minimal'
        target = Path(self.tmp.name)/'compile'
        shutil.copytree(fixture,target)
        sample = target/'Work.md'
        _, w = flow.work_file(sample)
        r = flow.compile_work(sample, w, 'model', False)
        self.assertEqual(r['status'],'passed')
        self.assertFalse(r['normative'])
        self.assertTrue((target/'Model.md').is_file())

    def test_compile_path_cannot_escape_work_boundary_in_source_mode(self):
        w = copy.deepcopy(self.work)
        w['compilation']={'schema':'cat-compile/v2','process':'../Process.md','pi':'PI.md','tce':'TCE.md','model':'Model.md','allow_draft':True}
        with self.assertRaisesRegex(flow.Blocked, 'escapes allowed compilation boundary'):
            flow.compile_work(self.workpath,w,'model',False)

    def test_git_deletion_outside_scope_is_detected(self):
        repo = Path(self.tmp.name) / 'git-delete'; repo.mkdir()
        def git(*args):
            subprocess.run(['git','-C',str(repo),*args],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        git('init'); git('config','user.email','test@example.org'); git('config','user.name','Test')
        (repo/'src').mkdir(); (repo/'src'/'a.py').write_text('x=0\n')
        (repo/'secret.txt').write_text('keep\n')
        git('add','.'); git('commit','-m','initial'); git('checkout','-b','feature/test')
        (repo/'secret.txt').unlink()
        self.work['repositories']=[{'name':'app','path':str(repo),'base_ref':'HEAD','branch_pattern':'feature/*','allowed_paths':['src/*']}]
        r=flow.git_snapshot(self.workpath,self.work)[0]
        self.assertEqual(r['status'],'blocked')
        self.assertIn('secret.txt',r['disallowed_changes'])

    def test_shadow_refuses_even_exit_zero_execution(self):
        self.work['checks']=[{'id':'lint','stage':'review','runner':'exit-zero','cwd':'@work','argv':[sys.executable,'-c','pass']}]
        with self.assertRaisesRegex(flow.Blocked,'shadow Work cannot execute'):
            flow.command_work(self.workpath,self.work,'lint',True)

    def test_unregistered_context_change_invalidates_evidence(self):
        self.implementation()
        (self.workpath.parent/'declared.txt').write_text('stable')
        (self.workpath.parent/'undeclared.txt').write_text('before')
        self.work['checks']=[{'id':'lint','stage':'review','runner':'exit-zero','cwd':'@work',
                             'argv':[sys.executable,'-c','pass'],'input_paths':['declared.txt']}]
        self.save(); flow.command_work(self.workpath,self.work,'lint',True)
        self.assertEqual(flow.status_work(self.workpath,self.work)['checks']['lint']['status'],'passed')
        (self.workpath.parent/'undeclared.txt').write_text('after')
        st=flow.status_work(self.workpath,self.work)['checks']['lint']
        self.assertEqual(st['status'],'stale')
        self.assertIn('context changed',st['reason'])

    def test_work_prefixed_compile_path_cannot_escape_work_directory(self):
        outside=Path(self.tmp.name)/'outside'; outside.mkdir(); (outside/'Process.md').write_text('x')
        workdir=Path(self.tmp.name)/'nested'; workdir.mkdir(); wp=workdir/'work.json'; wp.write_bytes(flow.json_bytes(self.work))
        conf={'schema':'cat-compile/v2','process':'@work/../outside/Process.md','pi':'PI.md','tce':'TCE.md','model':'Model.md','allow_draft':True}
        with self.assertRaisesRegex(flow.Blocked,'escapes allowed compilation boundary'):
            flow.compilation_path(wp,self.work,conf,'process',False)

    def test_external_gates_can_close_reported_work_without_claiming_verification(self):
        self.confirmed()
        self.work['checks']=[{'id':'lint','stage':'review','runner':'exit-zero','cwd':'@work','argv':[sys.executable,'-c','pass']}]
        self.work['gates']=[{'id':g,'status':'passed','evidence':'evidence:'+g} for g in flow.EXTERNAL_GATES]
        self.save(); flow.command_work(self.workpath,self.work,'lint',True)
        st=flow.status_work(self.workpath,self.work)
        self.assertEqual(st['overall'],'reported-complete/unverified-external-evidence')
        self.assertEqual(st['external_evidence_verification'],'required')

    def test_explicit_lint_files_exclude_notes(self):
        script = flow.ROOT/'skills/cat-specification-gate/scripts/cat_artifact_lint.py'
        fixture = Path(__file__).resolve().parent/'fixtures/minimal'
        proc = subprocess.run([sys.executable,str(script),'--files',
            *(str(fixture/n) for n in ('Process.md','PI.md','TCE.md'))],
            text=True,capture_output=True)
        self.assertEqual(proc.returncode,0,proc.stderr)

    def test_status_never_says_all_done_in_shadow(self):
        st = flow.status_work(self.workpath,self.work)
        self.assertEqual(st['overall'],'not-complete')
        self.assertIn('real-use',st['independent_unverified_gates'])


if __name__=='__main__':
    unittest.main()
