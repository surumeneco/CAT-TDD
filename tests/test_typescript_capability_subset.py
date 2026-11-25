from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.cat-system' / 'skills/tech-typescript/scripts'))
import cat_typescript_conformance as inspector

PROCESS = '''---
cat_version: '0.3'
kind: process
id: demo.pure
status: confirmed
process: demo.pure
source_refs:
  - https://example.org/spec
refs: []
decision_ref: https://example.org/decision
semantic_contract: markdown-v2
language: ja
---
# Process: pure

## 契約
閉世界: 真

## 境界
| PI |
| --- |
| demo.pure.pi |

## 仕様状態
| ID | Domain |
| --- | --- |

## 観測能力
| ID | 由来 | Domain |
| --- | --- | --- |

## 作用能力
| ID | 対象 | Domain |
| --- | --- | --- |

## 起点
| ID | 由来 |
| --- | --- |
| 判定 | demo.pure.pi |
'''
PI = '''---
cat_version: '0.3'
kind: pi
id: demo.pure.pi
status: confirmed
process: demo.pure
source_refs:
  - https://example.org/spec
refs: []
decision_ref: https://example.org/decision
semantic_contract: markdown-v2
language: ja
---
# PI: pure

## 境界
| 相手Process | 方向 |
| --- | --- |
| demo.caller | 双方向 |

## 項目
| ID | 方向 | Domain | 存在 |
| --- | --- | --- | --- |
| 入力.値 | 受信 | 真偽 | 必須 |
| 出力.結果 | 送信 | 真偽 | 必須 |

## 操作
| ID | 方向 | 起点 |
| --- | --- | --- |
| check | 受付 | 判定 |

## 制約
| 式 |
| --- |
'''

class PrimitiveCapabilityClosureTest(unittest.TestCase):
    def observe(self, code, *, proof=True, binding_updates=None, extra_files=None, process=PROCESS):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / 'app'
            repo.mkdir()
            (root / 'Process.md').write_text(process, encoding='utf-8')
            (root / 'PI.md').write_text(PI, encoding='utf-8')
            (repo / 'api.ts').write_text(code, encoding='utf-8')
            for name, content in (extra_files or {}).items():
                (repo / name).write_text(content, encoding='utf-8')
            binding = {'schema': 'cat-typescript-conformance-binding/v1', 'repository': 'app',
                       'source_globs': ['api.ts'], 'public_entrypoints': ['api.ts'],
                       'interface_symbols': {'check': 'check'}, 'capabilities': {}}
            if proof:
                binding['capability_analysis'] = 'primitive-pure-functions/v1'
            binding.update(binding_updates or {})
            (root / 'binding.json').write_text(json.dumps(binding), encoding='utf-8')
            return inspector.inspect(repo, root / 'binding.json', root / 'Process.md', root / 'PI.md')

    def test_primitive_return_module_has_closed_capability_set(self):
        for code in [
            'export function check(a: boolean, b: boolean): boolean { return a || b; }',
            "export function check(a:boolean, b:'root'|'child', c:'same'|'none'):boolean { return a && (b==='root' ? c==='none' : c==='same'); }",
            'export function check(a:boolean, b:boolean) { return { a:a, b:b, no:false, } as const; }',
        ]:
            with self.subTest(code=code):
                result = self.observe(code)
                self.assertEqual(result['status'], 'passed', result)
                self.assertIn('capability.closed-set', result['covered_obligation_ids'], result)
                self.assertEqual(result['capability_analysis']['status'], 'passed')
                self.assertIn('api.ts', result['capability_analysis']['source_sha256'])
                self.assertNotIn('implementation-constraint.typescript', result['covered_obligation_ids'])

    def test_unknown_capability_or_syntax_is_not_proved(self):
        for code in [
            'export function check(a:boolean) { return globalThis.someExternal; }',
            'import {helper} from "./other";\nexport function check(a:boolean) { return helper(a); }',
            'export function check(a:boolean) { return a; }\nconst hidden = globalThis.someExternal;',
            'export function check(a:{value:boolean}) { return a.value; }',
            'export function check(a:boolean = sideEffect()) { return a; }',
            'export function check(a:boolean) { return { get value(){ return globalThis.x; } }; }',
            'export function check(a:boolean) { return {...globalThis.x}; }',
            'export function check(a:boolean) { return a; } // comment\u2028globalThis.x = 1;',
            'export function check(a:boolean) { return `x${sideEffect()}`; }',
            'export function check(a:boolean) { return a || freeVariable; }',
            'export function check(a:boolean) { return { __proto__: a }; }',
            'export function check(a:boolean) { return a; } /* comment */ globalThis.x = 1;',
        ]:
            with self.subTest(code=code):
                result = self.observe(code)
                self.assertNotIn('capability.closed-set', result['covered_obligation_ids'], result)
                self.assertNotEqual(result.get('capability_analysis',{}).get('status'), 'passed', result)

    def test_unproved_scope_never_claims_closed_set(self):
        code = 'export function check(a:boolean) { return a; }'
        for updates, extras in [
            ({'source_globs':['*.ts']}, {}),
            ({'source_globs':['api.ts','hidden.ts']}, {'hidden.ts':'const v = 1;'}),
        ]:
            with self.subTest(updates=updates):
                result = self.observe(code, binding_updates=updates, extra_files=extras)
                self.assertNotIn('capability.closed-set', result['covered_obligation_ids'], result)
        open_world = self.observe(code, process=PROCESS.replace('閉世界: 真', '閉世界: 偽'))
        self.assertNotIn('capability.closed-set', open_world['covered_obligation_ids'], open_world)
        legacy = self.observe(code, proof=False)
        self.assertEqual(set(legacy['covered_obligation_ids']), {'interface.check'})

    def test_mapping_to_absent_export_never_passes_interface(self):
        result = self.observe('function check(a:boolean) { return a; }', proof=False)
        self.assertNotEqual(result['status'], 'passed', result)
        self.assertNotIn('interface.check', result['covered_obligation_ids'])

    def test_public_entrypoint_outside_source_scope_is_rejected(self):
        from cat_compile_v2 import Blocked
        with self.assertRaises(Blocked):
            self.observe('export function check(a:boolean) { return a; }',
                         proof=False, binding_updates={'source_globs': ['other.ts']},
                         extra_files={'other.ts': 'const x = 1;'})

    def test_known_external_capability_still_blocks(self):
        result = self.observe('export function check(a:boolean) { return fetch("https://example.invalid"); }')
        self.assertEqual(result['status'], 'blocked', result)
        self.assertNotIn('capability.closed-set', result['covered_obligation_ids'])

if __name__ == '__main__':
    unittest.main()
