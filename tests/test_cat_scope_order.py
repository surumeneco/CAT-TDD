from __future__ import annotations
import json, sys, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'scripts'
if not SCRIPTS.exists(): SCRIPTS=ROOT/'.cat-system'/'scripts'
sys.path.insert(0,str(SCRIPTS))
import cat_scope_order

def work(identifier,parent=None,depends=None):
    return {'schema':'cat-work/v1','id':identifier,'entry':'issue','mode':'shadow',
            'flow':'issue-work','work_kind':'analysis','parent':parent,'depends_on':depends or [],
            'issue_ref':'issue','project_entry_ref':'entry','normative':[{'uri':'spec'}],
            'evidence':[{'uri':'code'}],'specification':{'status':'candidate','decision_ref':None,'artifact_refs':[]},
            'scope':{'process_ids':['demo'],'changed_ids':[],'preserved_ids':[]},
            'technologies':[],'repositories':[],'checks':[],'gates':[]}

class ScopeOrderTest(unittest.TestCase):
    def write(self,root,w):
        p=root/(w['id']+'.json');p.write_text(json.dumps(w),encoding='utf-8');return p

    def test_deepest_ready_child_is_selected_before_parent(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            parent=self.write(root,work('parent'))
            child=self.write(root,work('child','parent'))
            r=cat_scope_order.build([str(parent),str(child)],set())
            self.assertEqual([x['id'] for x in r['ready']],['child'])
            r=cat_scope_order.build([str(parent),str(child)],{'child'})
            self.assertEqual([x['id'] for x in r['ready']],['parent'])

    def test_dependency_cycle_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            a=self.write(root,work('a',None,['b']))
            b=self.write(root,work('b',None,['a']))
            with self.assertRaisesRegex(ValueError,'cycle'):
                cat_scope_order.build([str(a),str(b)],set())

if __name__=='__main__': unittest.main()
