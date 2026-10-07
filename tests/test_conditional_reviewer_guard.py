from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
import cat_flow as flow


def work():
    return {
        'schema':'cat-work/v1','id':'demo.reviewer.guard','entry':'confirmed-spec',
        'mode':'implementation','flow':'spec-implementation','work_kind':'implementation',
        'parent':'','depends_on':[],'issue_ref':'spec','project_entry_ref':'project',
        'normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],
        'specification':{'status':'confirmed','decision_ref':'decision','artifact_refs':['demo.tce']},
        'scope':{'process_ids':['demo'],'changed_ids':[],'preserved_ids':[]},
        'technologies':[],'repositories':[],'checks':[],'gates':[]
    }


class ConditionalReviewerGuardTest(unittest.TestCase):
    def test_conditional_reviewer_is_guarded_and_cannot_edit_draft(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);w=work();wp=root/'work.json';wp.write_bytes(flow.json_bytes(w))
            draft=root/'Lifecycle'/'CAT'/'Draft';draft.mkdir(parents=True)
            reviews=root/'Lifecycle'/'CAT'/'Reviews';reviews.mkdir(parents=True)

            handoff=flow.handoff_work(wp,w,'model-conformance','inconclusive')
            self.assertEqual(handoff['executor']['id'],'cat-model-reviewer')
            self.assertEqual(handoff['guard']['status'],'passed')

            (reviews/'review.md').write_text('review',encoding='utf-8')
            (draft/'spec.md').write_text('unauthorized edit',encoding='utf-8')
            result=flow.guard_work(wp,w,'model-conformance','finish','inconclusive')
            self.assertEqual(result['status'],'blocked')
            self.assertTrue(any('Lifecycle/CAT/Draft/spec.md' in x.get('paths',[])
                                for x in result['violations']))

    def test_conditional_reviewer_may_write_only_review_area(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);w=work();wp=root/'work.json';wp.write_bytes(flow.json_bytes(w))
            reviews=root/'Lifecycle'/'CAT'/'Reviews';reviews.mkdir(parents=True)
            flow.handoff_work(wp,w,'model-conformance','inconclusive')
            (reviews/'review.md').write_text('review',encoding='utf-8')
            self.assertEqual(
                flow.guard_work(wp,w,'model-conformance','finish','inconclusive')['status'],
                'passed')


if __name__=='__main__':
    unittest.main()
