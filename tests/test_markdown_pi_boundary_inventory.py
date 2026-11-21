"""Multi-PI boundaries and multi-peer provenance must survive Markdown Model conversion."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
from cat_compile_v2 import Blocked,load,render_model_markdown
from cat_model_conformance import validate
from test_cat_compile_readable import write_v2
from test_operation_presence import OperationPresenceTests
from test_multi_peer_operation_binding import peer_pi


class MarkdownPIBoundaryInventoryTests(unittest.TestCase):
    def check(self,p,pis,t,root,**kwargs):
        model=load(p,pis,t,allow_draft=True,**kwargs)
        text=render_model_markdown(model)
        dest=root/'Model.md';dest.write_text(text,encoding='utf-8')
        self.assertEqual(validate(p,pis,[t],dest,allow_draft=True)['status'],'passed')
        return text,dest

    def test_one_pi_boundary_in_both_languages(self):
        for ja in (False,True):
            with self.subTest(ja=ja),tempfile.TemporaryDirectory() as td:
                root=Path(td);p,pi,t=write_v2(root,ja)
                text,dest=self.check(p,pi,t,root)
                self.assertIn('## PI境界一覧' if ja else '## PI boundaries',text)
                direction='双方向' if ja else 'bidirectional'
                row=f'| demo.process.pi | demo.user | {direction} | `null` |'
                self.assertIn(row,text)
                variants=(row.replace('demo.user','demo.other'),
                          row.replace(direction,'受信' if ja else 'receive'),
                          row.replace('`null`','`["demo.user","demo.other"]`'),
                          row.replace('demo.process.pi','unknown.pi'))
                for replacement in variants:
                    dest.write_text(text.replace(row,replacement,1),encoding='utf-8')
                    result=validate(p,pi,[t],dest,allow_draft=True)
                    self.assertEqual(result['status'],'blocked',result)
                    self.assertIn('pi_boundaries',result['mismatches'])
                dest.write_text(text.replace('## PI境界一覧' if ja else '## PI boundaries',
                                                 '## discarded'),encoding='utf-8')
                with self.assertRaisesRegex(Blocked,'missing Markdown PI boundaries'):
                    validate(p,pi,[t],dest,allow_draft=True)

    def test_multi_pi_boundaries_remain_distinguishable(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p,a,b,t,_,_=OperationPresenceTests().create(root)
            text,dest=self.check(p,[a,b],t,root)
            first='| demo.process.first | peer.first | bidirectional | `null` |'
            second='| demo.process.second | peer.second | bidirectional | `null` |'
            self.assertIn(first,text);self.assertIn(second,text)
            # Both PIs share one Process; swapping their peers must not be hidden
            # just because each peer remains present somewhere in the Model.
            modified=text.replace(first,'| demo.process.first | peer.second | bidirectional | `null` |',1)
            dest.write_text(modified,encoding='utf-8')
            self.assertIn('pi_boundaries',validate(p,[a,b],[t],dest,allow_draft=True)['mismatches'])

    def test_multi_peer_list_is_exact_source_bound(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p,pi,t=peer_pi(root)
            text,dest=self.check(p,pi,t,root,allow_partial=True)
            row='| demo.process.pi | demo.user | bidirectional | `["demo.user","demo.other"]` |'
            self.assertIn(row,text)
            changed=text.replace(row,row.replace('demo.other','demo.unrelated'),1)
            dest.write_text(changed,encoding='utf-8')
            self.assertIn('pi_boundaries',validate(p,pi,[t],dest,allow_draft=True)['mismatches'])


if __name__=='__main__':unittest.main()
