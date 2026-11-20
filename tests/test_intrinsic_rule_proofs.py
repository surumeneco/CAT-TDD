"""W03: no free-text Verifier is allowed to self-confirm normative rules."""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
from cat_compile_v2 import load, render_model_markdown
import cat_model_conformance as independent
import cat_flow
from test_cat_compile_readable import write_v2,fm

PROOF='@cat:effect-targets-declared/v1'
CONTRACT='cat:intrinsic-model/v1'


def approve_fixture(path):
    # Synthetic authorized-looking test data is isolated; not a product decision.
    value=path.read_text(encoding='utf-8').replace('status: draft','status: confirmed')
    value=value.replace("decision_ref: ''",'decision_ref: test-only-synthetic-decision')
    path.write_text(value,encoding='utf-8')


def build(root,requirement=PROOF,verification=CONTRACT,condition='assembled-process',confirmed=True):
    p,pi,t=write_v2(root,False)
    r=root/'CommonRule.md'
    r.write_text(fm('common-rule','demo.rule.document',['demo.process.contract'],language='en')+
        '\n## Rules\n| ID | Condition | Requirement | Verification |\n'
        '| --- | --- | --- | --- |\n'
        f'| demo.rule.check | {condition} | {requirement} | {verification} |\n',
        encoding='utf-8')
    if confirmed:
        for path in (p,pi,t,r):approve_fixture(path)
    return p,pi,t,r


class IntrinsicRuleProofTests(unittest.TestCase):
    def test_confirmed_intrinsic_model_rule_passes_source_comparison_and_closure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p,pi,t,r=build(root)
            model=load(p,pi,t,common_rules=[r])
            self.assertEqual(model['coverage_requirement'],'closed')
            self.assertEqual(model['status'],'confirmed')
            self.assertEqual(model['unverified_rule_ids'],[])
            self.assertEqual([x['rule_id'] for x in model['intrinsic_rule_proofs']],['demo.rule.check'])
            self.assertEqual(model['rule_obligations'][0]['verification_status'],'intrinsic-proved')
            self.assertEqual(model['intrinsic_rule_proofs'][0]['source_sha256'],
                             model['normative_rule_inputs'][0]['sha256'])
            mp=root/'Model.json';mp.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            self.assertEqual(independent.validate(p,pi,[t],mp,common_rules=[r])['status'],'passed')
            w={'id':'test.work','scope':{'process_ids':['demo.process']},
               'compilation':{'process':'Process.md','pi':'PI.md','tce':'TCE.md',
                              'common_rules':['CommonRule.md'],'allow_partial':True,
                              'allow_draft':False}}
            workpath=root/'Work.json';workpath.write_text(json.dumps(w),encoding='utf-8')
            closure=cat_flow.conformance_work(workpath,w,'process-closure')
            self.assertEqual(closure['status'],'passed',closure)

    def test_markdown_intrinsic_source_proofs_are_independently_verified_in_both_languages(self):
        # The Markdown model is a first-class, Source-bound representation,
        # not just a human-readable summary of confirmed JSON.
        for ja in (False, True):
            with self.subTest(japanese=ja), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                if ja:
                    p,pi,t=write_v2(root,True)
                    r=root/'CommonRule.md'
                    r.write_text(fm('common-rule','demo.rule.document',
                                    ['demo.process.contract'],language='ja')+
                        '\n## 規則\n| ID | 条件 | 要求 | 検証 |\n'
                        '| --- | --- | --- | --- |\n'
                        f'| demo.rule.check | assembled-process | {PROOF} | {CONTRACT} |\n',encoding='utf-8')
                    for path in (p,pi,t,r):approve_fixture(path)
                else:
                    p,pi,t,r=build(root)
                model=load(p,pi,t,common_rules=[r])
                self.assertEqual(model['status'],'confirmed')
                target=root/'Model.md'
                target.write_text(render_model_markdown(model),encoding='utf-8')
                rendered=target.read_text(encoding='utf-8')
                self.assertIn(('## 内在Rule証明' if ja else '## Intrinsic rule proofs'),rendered)
                result=independent.validate(p,pi,[t],target,common_rules=[r])
                self.assertEqual(result['status'],'passed',result)

    def test_markdown_intrinsic_proof_tamper_missing_duplicate_and_stale_are_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p,pi,t,r=build(root)
            model=load(p,pi,t,common_rules=[r])
            original=render_model_markdown(model)
            target=root/'Model.md'
            target.write_text(original,encoding='utf-8')
            self.assertEqual(independent.validate(p,pi,[t],target,common_rules=[r])['status'],'passed')
            section='## Intrinsic rule proofs'
            idx=original.index(section)
            next_heading=original.find('\n## ',idx+len(section))
            proof_text=original[idx:next_heading if next_heading>0 else len(original)]
            proof_line=next(x for x in proof_text.splitlines() if x.startswith('| demo.rule.check |'))
            changes={
                'removed_section':original.replace(proof_text,''),
                'missing_proof':original.replace(proof_line+'\n',''),
                'wrong_requirement':original.replace(proof_line,proof_line.replace(PROOF,'@cat:invented/v1')),
                'unjustified_status':original.replace(proof_line,proof_line.replace(' | passed |',' | failed |')),
                'forged_source_sha':original.replace(proof_line,proof_line.replace(model['intrinsic_rule_proofs'][0]['source_sha256'],'0'*64)),
                'duplicate':original.replace(proof_line,proof_line+'\n'+proof_line),
            }
            for name,modified in changes.items():
                with self.subTest(case=name):
                    target.write_text(modified,encoding='utf-8')
                    if name=='duplicate':
                        with self.assertRaisesRegex(independent.Blocked,'duplicate Markdown intrinsic Rule proof'):
                            independent.validate(p,pi,[t],target,common_rules=[r])
                        continue
                    result=independent.validate(p,pi,[t],target,common_rules=[r])
                    self.assertEqual(result['status'],'blocked',result)
                    self.assertIn('intrinsic_rule_proofs',result['mismatches'])
            target.write_text(original,encoding='utf-8')
            r.write_text(r.read_text(encoding='utf-8')+'\n',encoding='utf-8')
            result=independent.validate(p,pi,[t],target,common_rules=[r])
            self.assertEqual(result['status'],'blocked')
            self.assertIn('intrinsic_rule_proofs',result['mismatches'])

    def test_markdown_free_text_rule_remains_unverified_and_forged_intrinsic_proof_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p,pi,t,r=build(root,requirement='Deliver a Discord message',verification='discord')
            model=load(p,pi,t,common_rules=[r],allow_draft=True)
            self.assertEqual(model['intrinsic_rule_proofs'],[])
            self.assertEqual(model['unverified_rule_ids'],['demo.rule.check'])
            target=root/'Model.md'
            original=render_model_markdown(model)
            target.write_text(original,encoding='utf-8')
            self.assertEqual(independent.validate(p,pi,[t],target,common_rules=[r],allow_draft=True)['status'],'passed')
            # A fabricated certificate with a matching Source SHA is still not
            # a proof of arbitrary text, even when the table parses correctly.
            proof='| demo.rule.check | demo.rule.document | '+model['normative_rule_inputs'][0]['sha256']+' | '+PROOF+' | '+CONTRACT+' | '+CONTRACT+' | assembled-process | passed |'
            section_start=original.index('## Intrinsic rule proofs')
            separator='| --- | --- | --- | --- | --- | --- | --- | --- |'
            insert_at=original.index(separator,section_start)+len(separator)
            target.write_text(original[:insert_at]+'\n'+proof+original[insert_at:],encoding='utf-8')
            check=independent.validate(p,pi,[t],target,common_rules=[r],allow_draft=True)
            self.assertEqual(check['status'],'blocked')
            self.assertIn('intrinsic_rule_proofs',check['mismatches'])

    def test_unstructured_requirements_cannot_be_elevated_by_any_named_verifier(self):
        for requirement,verification,condition in (
            ('Audit must be sent to Discord','discord','assembled-process'),
            (PROOF,'static contract','assembled-process'),
            (PROOF,CONTRACT,'when online'),
            ('@cat:pretend-external-effect/v1',CONTRACT,'assembled-process'),
        ):
            with self.subTest(requirement=requirement,verification=verification,condition=condition):
                with tempfile.TemporaryDirectory() as tmp:
                    p,pi,t,r=build(Path(tmp),requirement,verification,condition)
                    model=load(p,pi,t,common_rules=[r],allow_draft=True)
                    self.assertEqual(model['status'],'draft')
                    self.assertEqual(model['intrinsic_rule_proofs'],[])
                    self.assertEqual(model['unverified_rule_ids'],['demo.rule.check'])

    def test_draft_intrinsic_rule_does_not_approve_itself(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,pi,t,r=build(Path(tmp),confirmed=False)
            model=load(p,pi,t,common_rules=[r],allow_draft=True)
            self.assertEqual(model['status'],'draft')
            self.assertEqual(model['intrinsic_rule_proofs'],[])

    def test_proof_tamper_rejected_by_independent_source_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p,pi,t,r=build(root)
            model=load(p,pi,t,common_rules=[r])
            target=root/'Model.json'
            model['intrinsic_rule_proofs'][0]['requirement']='@cat:pretend-external-effect/v1'
            target.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            result=independent.validate(p,pi,[t],target,common_rules=[r])
            self.assertEqual(result['status'],'blocked')
            self.assertIn('intrinsic_rule_proofs',result['mismatches'])

    def test_proof_stale_when_source_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p,pi,t,r=build(root)
            model=load(p,pi,t,common_rules=[r])
            target=root/'Model.json';target.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            self.assertEqual(independent.validate(p,pi,[t],target,common_rules=[r])['status'],'passed')
            r.write_text(r.read_text(encoding='utf-8')+'\n',encoding='utf-8')
            result=independent.validate(p,pi,[t],target,common_rules=[r])
            self.assertEqual(result['status'],'blocked')
            self.assertIn('intrinsic_rule_proofs',result['mismatches'])


    def test_unverified_source_cannot_forge_confirmed_status_or_proof_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p,pi,t,r=build(root,
                requirement='Notify Discord users',
                verification='discord')
            model=load(p,pi,t,common_rules=[r],allow_draft=True)
            self.assertEqual(model['status'],'draft')
            target=root/'Model.json'
            model['status']='confirmed'
            target.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            result=independent.validate(p,pi,[t],target,common_rules=[r],allow_draft=True)
            self.assertEqual(result['status'],'blocked')
            self.assertIn('normative_status_unjustified',result['mismatches'])
            model['status']='draft'
            model['unverified_rule_ids']=[]
            target.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            result=independent.validate(p,pi,[t],target,common_rules=[r],allow_draft=True)
            self.assertEqual(result['status'],'blocked')
            self.assertIn('unverified_rule_ids',result['mismatches'])

    def test_draft_sources_cannot_forge_confirmed_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p,pi,t,r=build(root,confirmed=False)
            model=load(p,pi,t,common_rules=[r],allow_draft=True)
            self.assertEqual(model['status'],'draft')
            target=root/'Model.json'
            model['status']='confirmed'
            target.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            result=independent.validate(p,pi,[t],target,common_rules=[r],allow_draft=True)
            self.assertEqual(result['status'],'blocked')
            self.assertIn('normative_status_unjustified',result['mismatches'])


if __name__=='__main__':unittest.main()
