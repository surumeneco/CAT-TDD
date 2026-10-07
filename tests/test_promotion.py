from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
import cat_promote


class PromotionTest(unittest.TestCase):
    def test_explicit_decision_promotes_and_moves_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'Lifecycle'/'CAT'/'Draft'/'Demo.md'
            source.parent.mkdir(parents=True)
            source.write_text("""---
cat_version: '0.3'
kind: tce
id: demo.tce
status: draft
process: demo
source_refs:
  - issue
refs: []
decision_ref: ''
semantic_contract: markdown-v2
language: ja
---
# Demo
""",encoding='utf-8')
            output=root/'Lifecycle'/'Docs'/'Processes'/'Demo.md'
            result=cat_promote.promote(source,output,'decision:approved')
            self.assertEqual(result['status'],'passed')
            self.assertFalse(source.exists())
            text=output.read_text(encoding='utf-8')
            self.assertIn('status: confirmed',text)
            self.assertIn('decision_ref: decision:approved',text)

    def test_promotion_requires_explicit_decision(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'Demo.md'
            source.write_text("---\nkind: tce\nid: demo.tce\nstatus: draft\ndecision_ref: ''\n---\n# Demo\n",encoding='utf-8')
            with self.assertRaises(cat_promote.Blocked):
                cat_promote.promote(source,root/'Confirmed.md','')


if __name__=='__main__':
    unittest.main()
