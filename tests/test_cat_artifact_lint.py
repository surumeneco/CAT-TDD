#!/usr/bin/env python3
"""Standard-library smoke tests for the narrowly scoped CAT linter."""
import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'skills' / 'cat-specification-gate' / 'scripts'))
from cat_artifact_lint import artifact_errors
from catlib.markdown import parse_frontmatter
from cat_package_lint import agent_errors, skill_errors


def doc(identifier='alpha.test', status='confirmed', ref=''):
    return ("---\ncat_version: '0.3'\nkind: tce\nid: "+identifier+"\n"
            "status: "+status+"\nprocess: alpha\nsource_refs: []\n"
            "refs: "+('['+repr(ref).replace("'",'"')+']' if ref else '[]')+"\n"
            "decision_ref: 'approved-decision'\nsemantic_contract: markdown-v2\nlanguage: ja\n---\n"
            "# Example\n\n網羅要求: partial\n\n## 振る舞い\n| ID | 起点 | 条件 | 結果 | 効果 |\n| --- | --- | --- | ---: | --- |\n"
            "| alpha.behavior | submit | `true` | 1 | `-` |\n")


class ContractLintTests(unittest.TestCase):
    def test_valid_and_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'a.md').write_text(doc(), encoding='utf-8')
            self.assertEqual(artifact_errors(root), [])
            (root/'b.md').write_text(doc(), encoding='utf-8')
            self.assertTrue(any('duplicate' in s for s in artifact_errors(root)))

    def test_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'a.md').write_text(doc(ref='alpha.missing'), encoding='utf-8')
            self.assertTrue(any('unresolved' in s for s in artifact_errors(root)))

    def test_confirmed_requires_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'a.md').write_text(doc().replace("decision_ref: 'approved-decision'", "decision_ref: ''"), encoding='utf-8')
            self.assertTrue(any('decision_ref' in s for s in artifact_errors(root)))

    def test_frontmatter_block_lists(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'a.md'
            path.write_text("---\ncat_version: '0.2'\nkind: tce\nid: alpha.test\nstatus: draft\nprocess: alpha\nsource_refs:\n  - https://example.org/spec\nrefs:\n  - alpha.other\ndecision_ref: ''\n---\n# Example\n", encoding='utf-8')
            f = parse_frontmatter(path)
            self.assertEqual(f['source_refs'], ['https://example.org/spec'])
            self.assertEqual(f['refs'], ['alpha.other'])

    def test_common_rule_and_domain_spec_are_first_class_kinds(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            common=("---\ncat_version: '0.3'\nkind: common-rule\nid: alpha.common\nstatus: draft\nprocess: alpha\n"
                    "source_refs:\n  - https://example.org/spec\nrefs: []\ndecision_ref: ''\nsemantic_contract: markdown-v2\nlanguage: ja\n---\n"
                    "# Common Rule\n\n## 規則\n| ID | 適用対象 | 要求 | 検証 |\n| --- | --- | --- | --- |\n| no-change | alpha | 未指定作用先は不変 | TestModel |\n")
            domain=("---\ncat_version: '0.3'\nkind: domain-spec\nid: alpha.visual\nstatus: draft\nprocess: alpha\n"
                    "source_refs:\n  - https://example.org/spec\nrefs: []\ndecision_ref: ''\nsemantic_contract: markdown-v2\nlanguage: ja\n---\n"
                    "# Domain Spec\n\n## 対象\n| Ref | Aspect |\n| --- | --- |\n| alpha | visual |\n\n## 規則\n| ID | 条件 | 要求 | 検証 |\n| --- | --- | --- | --- |\n| v1 | 常時 | 主要表示を維持 | screenshot |\n")
            (root/'common.md').write_text(common,encoding='utf-8')
            (root/'domain.md').write_text(domain,encoding='utf-8')
            self.assertEqual(artifact_errors(root),[])

    def test_markdown_v2_requires_semantic_sections(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'a.md').write_text(doc().replace('## 振る舞い','## Other'),encoding='utf-8')
            self.assertTrue(any('Behaviors/振る舞い' in x for x in artifact_errors(root)))

    def test_skill_and_agent_headers(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'skills'/'example').mkdir(parents=True)
            (root/'skills'/'example'/'SKILL.md').write_text('---\nname: example\ndescription: work\n---\n', encoding='utf-8')
            (root/'agents').mkdir()
            (root/'agents'/'a.agent.md').write_text('---\nname: a\ndescription: work\n---\n', encoding='utf-8')
            self.assertEqual(skill_errors(root/'skills'), [])
            self.assertEqual(agent_errors(root/'agents'), [])


    def test_v2_semantic_kinds_and_required_sections(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            common=root/'common.md'
            common.write_text("""---
cat_version: '0.3'
kind: common-rule
id: alpha.common
status: draft
process: alpha
source_refs:
  - https://example.org/spec
refs: []
decision_ref: ''
semantic_contract: markdown-v2
language: ja
---
# Common Rule
## 規則
| ID | 適用対象 | 要求 | 検証 |
| --- | --- | --- | --- |
| same | alpha | 同じ意味を保持する | review |
""",encoding='utf-8')
            domain=root/'domain.md'
            domain.write_text("""---
cat_version: '0.3'
kind: domain-spec
id: alpha.domain
status: draft
process: alpha
source_refs:
  - https://example.org/spec
refs: []
decision_ref: ''
semantic_contract: markdown-v2
language: ja
---
# Domain Spec
## 対象
| Ref | Aspect |
| --- | --- |
| alpha | visual |
## 規則
| ID | 条件 | 要求 | 検証 |
| --- | --- | --- | --- |
| stable | always | 表示差を許容範囲に保つ | visual-regression |
""",encoding='utf-8')
            self.assertEqual(artifact_errors(root), [])

    def test_v2_pi_rejects_legacy_role_state_shape(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'pi.md'
            path.write_text("""---
cat_version: '0.3'
kind: pi
id: alpha.pi
status: draft
process: alpha
source_refs:
  - https://example.org/spec
refs: []
decision_ref: ''
semantic_contract: markdown-v2
---
# PI
## Boundary
| Peer process | Direction |
| --- | --- |
| beta | receive |
## Fields
| ID | Role | Domain | Presence |
| --- | --- | --- | --- |
| state.ready | state | boolean | required |
## Operations
| ID | Direction | Trigger |
| --- | --- | --- |
## Constraints
| Expression |
| --- |
""",encoding='utf-8')
            errs=artifact_errors(files=[path])
            self.assertTrue(any('must not contain Role/state' in e for e in errs))

    def test_v2_tce_rejects_legacy_rules_effects(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'tce.md'
            path.write_text("""---
cat_version: '0.3'
kind: tce
id: alpha.tce
status: draft
process: alpha
source_refs:
  - https://example.org/spec
refs: []
decision_ref: ''
semantic_contract: markdown-v2
---
# TCE
Coverage requirement: closed
## Behaviors
| ID | Trigger | Condition | Outcome | Effects |
| --- | --- | --- | ---: | --- |
| yes | submit | `input.ok` | 1 | `output.ok = true` |
## Rules
| ID |
| --- |
""",encoding='utf-8')
            errs=artifact_errors(files=[path])
            self.assertTrue(any('legacy Rules/Effects' in e for e in errs))

    def test_common_rule_requires_traceable_requirement_and_verification_columns(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'common.md'
            path.write_text("""---
cat_version: '0.3'
kind: common-rule
id: alpha.common
status: draft
process: alpha
source_refs:
  - https://example.org/spec
refs: []
decision_ref: ''
semantic_contract: markdown-v2
language: ja
---
# Common Rule
## 規則
| ID | 適用対象 | 要求 |
| --- | --- | --- |
| c1 | alpha | 一貫する |
""",encoding='utf-8')
            errs=artifact_errors(files=[path])
            self.assertTrue(any('Verification' in e or '検証' in e for e in errs))

    def test_domain_spec_requires_targets_rules_and_nonempty_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'domain.md'
            path.write_text("""---
cat_version: '0.3'
kind: domain-spec
id: alpha.domain
status: draft
process: alpha
source_refs:
  - https://example.org/spec
refs: []
decision_ref: ''
semantic_contract: markdown-v2
language: ja
---
# Domain Spec
## 対象
| Ref | Aspect |
| --- | --- |
| alpha | visual |
## 規則
| ID | 条件 | 要求 | 検証 |
| --- | --- | --- | --- |
| d1 | 常時 | 表示を維持 |  |
""",encoding='utf-8')
            errs=artifact_errors(files=[path])
            self.assertTrue(any('domain-spec rows must not contain empty cells' in e for e in errs))


if __name__ == '__main__':
    unittest.main()
