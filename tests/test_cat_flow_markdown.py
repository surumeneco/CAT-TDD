#!/usr/bin/env python3
import sys
import tempfile
import unittest
import shutil
import shlex
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import cat_flow as flow
from cat_flow import read_work_markdown, render_work_markdown, validate


class WorkMarkdownTests(unittest.TestCase):
    def test_human_work_normalizes_to_existing_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'Work.md'
            p.write_text("""---
cat_version: '0.2'
kind: work
id: demo.work
status: candidate
process: demo.process
source_refs:
  - https://example.org/spec
decision_ref: ''
refs:
  - demo.tce
entry: issue
mode: implementation
issue_ref: issue-1
project_entry_ref: https://example.org/project
spec_status: confirmed
---
# Work: demo.work
## Evidence
| URI |
| --- |
| https://example.org/evidence |
## Scope
| Process IDs | Changed IDs | Preserved IDs |
| --- | --- | --- |
| demo.process | demo.tce | demo.pi |
## Technologies
| Technology |
| --- |
| TypeScript |
## Repositories
| Name | Path | Base ref | Branch pattern | Allowed paths |
| --- | --- | --- | --- | --- |
| app | ./app | origin/develop | feature/* | src/**; tests/** |
## Checks
| ID | Stage | Runner | CWD | Command | Test IDs | Inputs | Outputs | Timeout |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: |
| unit.green | green | junit | @repo:app | npm test -- --reporter=junit --outputFile {report} | demo test | src/a.ts | — | 120 |
""",encoding='utf-8')
            # confirmed requires decision_ref: make it explicit before validation
            w=read_work_markdown(p)
            self.assertEqual(w['checks'][0]['argv'][0:2],['npm','test'])
            self.assertEqual(w['repositories'][0]['allowed_paths'],['src/**','tests/**'])
            self.assertIn('confirmed specification requires decision_ref',validate(w))

    def test_scaffold_is_markdown_not_json(self):
        text=render_work_markdown('demo.work')
        self.assertIn('# Work: demo.work',text)
        self.assertIn('| Process IDs |',text)
        self.assertIn('## Gates',text)
        self.assertNotIn('"schema"',text)

    def test_markdown_standard_path_validate_route_compile_run_status(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); fixture=Path(__file__).resolve().parent/'fixtures/minimal'
            for name in ('Process.md','PI.md','TCE.md','Work.md'):
                shutil.copyfile(fixture/name,root/name)
            wp=root/'Work.md'; text=wp.read_text(encoding='utf-8')
            text=text.replace("mode: shadow","mode: implementation")
            text=text.replace("spec_status: candidate","spec_status: confirmed")
            text=text.replace("decision_ref: ''","decision_ref: https://example.org/decision",1)
            cmd=shlex.quote(sys.executable)+' -c '+shlex.quote('pass')
            text=text.replace('| --- | --- | --- | --- | --- | --- | --- | --- | ---: |\n\n## ゲート',
                '| --- | --- | --- | --- | --- | --- | --- | --- | ---: |\n'
                f'| lint | review | exit-zero | @work | {cmd} | — | Work.md | — | 30 |\n\n## ゲート')
            wp.write_text(text,encoding='utf-8')
            p,w=flow.work_file(wp)
            self.assertEqual(flow.validate(w),[])
            self.assertEqual(flow.route(w,'tests')['status'],'ready')
            self.assertEqual(flow.compile_work(p,w,'model',False)['status'],'passed')
            self.assertEqual(flow.command_work(p,w,'lint',True)['verdict'],'passed')
            self.assertEqual(flow.status_work(p,w)['checks']['lint']['status'],'passed')
            self.assertEqual(w['gates'][0]['id'],'semantic-review')

    def test_japanese_work_body_normalizes_to_same_manifest_shape(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'Work.md'
            p.write_text("""---
cat_version: '0.2'
kind: work
id: demo.work.ja
status: candidate
process: demo.process
source_refs:
  - https://example.org/spec
decision_ref: ''
refs:
  - demo.tce
entry: issue
mode: shadow
issue_ref: issue-ja
project_entry_ref: https://example.org/project
spec_status: candidate
---
# Work: demo.work.ja
## 証拠
| 参照 |
| --- |
| https://example.org/evidence |
## 範囲
| プロセスID | 変更ID | 保持ID |
| --- | --- | --- |
| demo.process | demo.tce | demo.pi |
## 技術
| 技術 |
| --- |
| TypeScript |
## リポジトリ
| 名前 | パス | 基準ref | ブランチ規則 | 許可パス |
| --- | --- | --- | --- | --- |
## 検査
| ID | 工程 | 実行形式 | 作業場所 | コマンド | テストID | 入力 | 出力 | タイムアウト |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: |
## ゲート
| ゲート | 状態 | 証拠 |
| --- | --- | --- |
| semantic-review | 未実行 | — |
| test-oracle-review | 未実行 | — |
| red-review | 未実行 | — |
| pr-review | 対象外 | local-only |
| ci | 未実行 | — |
| merge | 未実行 | — |
| deployment | 未実行 | — |
| real-use | 未実行 | — |
""",encoding='utf-8')
            w=read_work_markdown(p)
            self.assertEqual(w['scope']['process_ids'],['demo.process'])
            self.assertEqual(w['technologies'],['TypeScript'])
            gm={g['id']:g['status'] for g in w['gates']}
            self.assertEqual(gm['semantic-review'],'not-run')
            self.assertEqual(gm['pr-review'],'not-applicable')


if __name__=='__main__': unittest.main()
