#!/usr/bin/env python3
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.cat-system' / 'scripts'))
from cat_compile_v2 import load, render_model_markdown, Blocked


def fm(kind, identifier, refs, contract='markdown-v2', language=None):
    refs_text='\n'.join('  - '+x for x in refs) if refs else ''
    lang=f'language: {language}\n' if language else ''
    return f"""---
cat_version: '0.3'
kind: {kind}
id: {identifier}
status: draft
process: demo.process
source_refs:
  - https://example.org/spec
refs:{('' if refs else ' []')}
{refs_text}
decision_ref: ''
semantic_contract: {contract}
{lang}---
"""


def write_v2(root, ja):
    process=root/'Process.md'; pi=root/'PI.md'; tce=root/'TCE.md'
    if ja:
        process.write_text(fm('process','demo.process.contract',[],language='ja')+"""
# Process: デモ
## 契約
閉世界: 真
## 境界
| PI |
| --- |
| demo.process.pi |
## 仕様状態
| ID | Domain |
| --- | --- |
| state.ready | 真偽 |
## 観測能力
| ID | 由来 | Domain |
| --- | --- | --- |
## 作用能力
| ID | 対象 | Domain |
| --- | --- | --- |
## 起点
| ID | 由来 |
| --- | --- |
| submit | demo.process.pi |
""",encoding='utf-8')
        pi.write_text(fm('pi','demo.process.pi',['demo.process.contract'],language='ja')+"""
# PI: デモ
## 境界
| 相手Process | 方向 |
| --- | --- |
| demo.user | 双方向 |
## 項目
| ID | 方向 | Domain | 存在 |
| --- | --- | --- | --- |
| input.enabled | 受信 | 真偽 | 必須 |
| output.accepted | 送信 | 真偽 | 必須 |
## 操作
| ID | 方向 | 起点 |
| --- | --- | --- |
| submit_op | 受付 | submit |
## 制約
| 式 |
| --- |
""",encoding='utf-8')
        tce.write_text(fm('tce','demo.process.tce',['demo.process.pi'],language='ja')+"""
# TCE: デモ
網羅要求: closed
## 振る舞い
| ID | 起点 | 条件 | 結果 | 効果 |
| --- | --- | --- | ---: | --- |
| demo.accept | submit | `input.enabled` | 1 | `state.ready = 真; output.accepted = 真` |
| demo.reject | submit | `否定(input.enabled)` | 1 | `output.accepted = 偽` |
""",encoding='utf-8')
    else:
        process.write_text(fm('process','demo.process.contract',[],language='en')+"""
# Process: demo
## Contract
Closed world: true
## Interfaces
| PI |
| --- |
| demo.process.pi |
## State
| ID | Domain |
| --- | --- |
| state.ready | boolean |
## Observations
| ID | Source | Domain |
| --- | --- | --- |
## Actions
| ID | Target | Domain |
| --- | --- | --- |
## Triggers
| ID | Source |
| --- | --- |
| submit | demo.process.pi |
""",encoding='utf-8')
        pi.write_text(fm('pi','demo.process.pi',['demo.process.contract'],language='en')+"""
# PI: demo
## Boundary
| Peer process | Direction |
| --- | --- |
| demo.user | bidirectional |
## Fields
| ID | Direction | Domain | Presence |
| --- | --- | --- | --- |
| input.enabled | receive | boolean | required |
| output.accepted | send | boolean | required |
## Operations
| ID | Direction | Trigger |
| --- | --- | --- |
| submit_op | accept | submit |
## Constraints
| Expression |
| --- |
""",encoding='utf-8')
        tce.write_text(fm('tce','demo.process.tce',['demo.process.pi'],language='en')+"""
# TCE: demo
Coverage requirement: closed
## Behaviors
| ID | Trigger | Condition | Outcome | Effects |
| --- | --- | --- | ---: | --- |
| demo.accept | submit | `input.enabled` | 1 | `state.ready = true; output.accepted = true` |
| demo.reject | submit | `not input.enabled` | 1 | `output.accepted = false` |
""",encoding='utf-8')
    return process,pi,tce


class ReadableArtifactTests(unittest.TestCase):
    def test_japanese_v2_artifacts_compile_to_symbolic_model(self):
        fixture=Path(__file__).resolve().parent/'fixtures/minimal'
        m=load(fixture/'Process.md',fixture/'PI.md',fixture/'TCE.md',allow_draft=True)
        self.assertEqual(m['semantic_authority'],'cat-markdown/v2')
        self.assertEqual(m['language'],'ja')
        self.assertEqual(m['coverage_requirement'],'closed')
        self.assertEqual(m['coverage_checks']['送信']['result'],'proved')
        roles={f['id']:f['role'] for f in m['fields']}
        self.assertEqual(roles['状態.準備'],'state')
        self.assertEqual(roles['入力.有効'],'input')
        rendered=render_model_markdown(m)
        self.assertIn('## 網羅要求',rendered)
        self.assertIn('## 網羅検証',rendered)
        self.assertNotIn('## Coverage claim',rendered)

    def test_japanese_and_english_v2_normalize_to_same_meaning(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            ja=load(*write_v2(Path(a),True),allow_draft=True)
            en=load(*write_v2(Path(b),False),allow_draft=True)
            for key in ('triggers','fields','pi_constraints','rules','coverage_requirement','pi_boundary','pi_operations'):
                self.assertEqual(ja[key],en[key],key)

    def test_v2_expression_rejects_arbitrary_code(self):
        with tempfile.TemporaryDirectory() as d:
            process,pi,tce=write_v2(Path(d),True)
            tce.write_text(tce.read_text().replace('`input.enabled`','`__import__("os")`'),encoding='utf-8')
            with self.assertRaises(Blocked): load(process,pi,tce,allow_draft=True)

    def test_declared_observation_and_action_are_first_class_capabilities(self):
        with tempfile.TemporaryDirectory() as d:
            process,pi,tce=write_v2(Path(d),True)
            process.write_text(process.read_text()
                .replace('| ID | 由来 | Domain |\n| --- | --- | --- |\n',
                         '| ID | 由来 | Domain |\n| --- | --- | --- |\n| observation.allowed | 業務カレンダー | 真偽 |\n',1)
                .replace('| ID | 対象 | Domain |\n| --- | --- | --- |\n',
                         '| ID | 対象 | Domain |\n| --- | --- | --- |\n| action.audit | 監査通知 | 真偽 |\n',1), encoding='utf-8')
            tce.write_text(tce.read_text()
                .replace('`input.enabled`', '`input.enabled かつ observation.allowed`',1)
                .replace('`否定(input.enabled)`', '`否定(input.enabled) または 否定(observation.allowed)`')
                .replace('`state.ready = 真; output.accepted = 真`',
                         '`state.ready = 真; output.accepted = 真; action.audit = 真`'), encoding='utf-8')
            model=load(process,pi,tce,allow_draft=True)
            roles={f['id']:f['role'] for f in model['fields']}
            self.assertEqual(roles['observation.allowed'],'observation')
            self.assertEqual(roles['action.audit'],'action')
            accept=next(r for r in model['rules'] if r['id']=='demo.accept')
            self.assertIn('action.audit',[e['target'] for e in accept['allowed'][0]['write']])

    def test_optional_presence_is_preserved_but_not_silently_compiled_as_required(self):
        with tempfile.TemporaryDirectory() as d:
            process,pi,tce=write_v2(Path(d),False)
            pi.write_text(pi.read_text().replace('input.enabled | receive | boolean | required',
                                                 'input.enabled | receive | boolean | optional'),encoding='utf-8')
            with self.assertRaisesRegex(Blocked,'supports required PI presence only'):
                load(process,pi,tce,allow_draft=True)

    def test_undeclared_observation_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            process,pi,tce=write_v2(Path(d),True)
            tce.write_text(tce.read_text().replace('`input.enabled`','`観測.天気 == "晴"`',1),encoding='utf-8')
            with self.assertRaisesRegex(Blocked,'unknown or non-readable ref'):
                load(process,pi,tce,allow_draft=True)

    def test_undeclared_effect_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            process,pi,tce=write_v2(Path(d),True)
            tce.write_text(tce.read_text().replace('state.ready = 真','作用.外部 = 真'),encoding='utf-8')
            with self.assertRaisesRegex(Blocked,'not declared/actuable'):
                load(process,pi,tce,allow_draft=True)

    def test_closed_requirement_keeps_unproven_result_in_draft_but_blocks_normative_compile(self):
        with tempfile.TemporaryDirectory() as d:
            process,pi,tce=write_v2(Path(d),False)
            pi.write_text(pi.read_text().replace('input.enabled | receive | boolean','input.enabled | receive | integer'),encoding='utf-8')
            tce.write_text(tce.read_text().replace('`input.enabled`','`input.enabled > 0`',1)
                           .replace('`not input.enabled`','`input.enabled <= 0`'),encoding='utf-8')
            model=load(process,pi,tce,allow_draft=True)
            self.assertEqual(model['coverage_checks']['submit']['result'],'unproven')
            self.assertEqual(model['status'],'draft')
            for path in (process,pi,tce):
                text=path.read_text(encoding='utf-8').replace('status: draft','status: confirmed')
                text=text.replace("decision_ref: ''",'decision_ref: https://example.org/decision')
                path.write_text(text,encoding='utf-8')
            with self.assertRaisesRegex(Blocked,'coverage requirement not proved'):
                load(process,pi,tce,allow_draft=False)

    def test_closed_uncovered_boolean_coverage_can_be_inspected_only_as_draft(self):
        with tempfile.TemporaryDirectory() as d:
            process,pi,tce=write_v2(Path(d),False)
            lines=[line for line in tce.read_text(encoding='utf-8').splitlines() if 'demo.reject' not in line]
            tce.write_text('\n'.join(lines)+'\n',encoding='utf-8')
            model=load(process,pi,tce,allow_draft=True)
            self.assertEqual(model['coverage_checks']['submit']['result'],'uncovered')
            self.assertEqual(model['status'],'draft')

    def test_markdown_v1_remains_supported(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            def oldfm(kind,identifier,refs):
                refs_block='refs: []' if not refs else 'refs:\n'+'\n'.join('  - '+x for x in refs)
                return f"---\ncat_version: '0.2'\nkind: {kind}\nid: {identifier}\nstatus: draft\nprocess: demo.process\nsource_refs:\n  - https://example.org/spec\n{refs_block}\ndecision_ref: ''\nsemantic_contract: markdown-v1\n---\n"
            p=root/'Process.md'; p.write_text(oldfm('process','demo.process',[])+"\n## Contract\nClosed world: true\n## Triggers\n| ID | Origin |\n| --- | --- |\n| submit | user |\n")
            pi=root/'PI.md'; pi.write_text(oldfm('pi','demo.pi',['demo.process'])+"\n## Fields\n| ID | Role | Domain |\n| --- | --- | --- |\n| input.enabled | input | boolean |\n| output.accepted | output | boolean |\n")
            t=root/'TCE.md'; t.write_text(oldfm('tce','demo.tce',['demo.pi'])+"\nCoverage: closed\n## Rules\n| ID | Trigger | Condition |\n| --- | --- | --- |\n| yes | submit | `input.enabled` |\n| no | submit | `not input.enabled` |\n## Effects\n| Rule | Outcome | Target | Expression |\n| --- | ---: | --- | --- |\n| yes | 1 | output.accepted | `true` |\n| no | 1 | output.accepted | `false` |\n")
            model=load(p,pi,t,allow_draft=True)
            self.assertEqual(model['semantic_authority'],'cat-markdown/v1')

    def test_legacy_json_block_remains_supported(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            def write(name,kind,identifier,refs,obj):
                refs_line='['+', '.join(json.dumps(x) for x in refs)+']'
                text=(f"---\ncat_version: '0.1'\nkind: {kind}\nid: {identifier}\nstatus: draft\nprocess: demo.process\n"
                      f"source_refs: [\"https://example.org/spec\"]\ndecision_ref: ''\nrefs: {refs_line}\nsemantic_contract: machine-only\n---\n"
                      '```cat-machine\n'+json.dumps(obj)+'\n```\n')
                path=root/name;path.write_text(text,encoding='utf-8');return path
            process=write('Process.md','process','demo.process',[],{'schema':'cat-machine/v2','kind':'process','process':'demo.process','triggers':[{'id':'submit','origin':'user'}],'closed_world':True})
            pi=write('PI.md','pi','demo.pi',['demo.process'],{'schema':'cat-machine/v2','kind':'pi','process':'demo.process','fields':[{'id':'input.enabled','role':'input','domain':{'type':'boolean'}},{'id':'output.accepted','role':'output','domain':{'type':'boolean'}}],'constraints':[]})
            tce=write('TCE.md','tce','demo.tce',['demo.pi'],{'schema':'cat-machine/v2','kind':'tce','process':'demo.process','coverage':'closed','rules':[{'id':'yes','trigger':'submit','when':{'ref':'input.enabled'},'allowed':[{'write':[{'target':'output.accepted','expr':{'literal':True}}]}]},{'id':'no','trigger':'submit','when':{'op':'not','args':[{'ref':'input.enabled'}]},'allowed':[{'write':[{'target':'output.accepted','expr':{'literal':False}}]}]}]})
            model=load(process,pi,tce,allow_draft=True)
            self.assertEqual(model['semantic_authority'],'cat-machine/v2')
            self.assertNotIn('normalized_ir',model)


if __name__=='__main__': unittest.main()
