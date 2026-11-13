"""A composition report cannot silently discard declared TCE Effect gaps."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
import cat_process_composition as composer
from test_process_composition import model


def write_models(root,receipts):
    paths=[]
    for name in ('p.one','p.two'):
        m=model(name,'outside','send')
        m['pi_boundaries']=[]
        m['coverage_claim']='closed'
        m['coverage_checks']={'trigger':{'result':'proved'}}
        m['unresolved_interfaces']=[]
        m['rules']=[{'id':'effect.rule','source_artifact':name+'.tce',
                     'allowed':[{'write':[{'target':'output.value','expr':{
                         'op':'+','args':[{'literal':1},{'literal':2}]}}]}]}]
        key=name+'.tce#effect.rule:1:1:output.value'
        if receipts=='complete':
            m['effect_checks']={key:{'result':'proved'}}
            m['unverified_effect_ids']=[]
        elif receipts=='missing-proof':
            m['effect_checks']={}
            m['unverified_effect_ids']=[]
        elif receipts=='wrong-key':
            m['effect_checks']={'other.tce#effect.rule:1:1:output.value':{'result':'proved'}}
            m['unverified_effect_ids']=[]
        elif receipts=='unproved':
            m['effect_checks']={key:{'result':'unproven','reason':'out-of-domain'}}
            m['unverified_effect_ids']=[key]
        elif receipts=='missing-unverified-list':
            m['effect_checks']={key:{'result':'proved'}}
        elif receipts=='extraneous':
            m['effect_checks']={key:{'result':'proved'},'phantom':{'result':'proved'}}
            m['unverified_effect_ids']=[]
        elif receipts=='omitted':
            pass
        else:raise ValueError(receipts)
        p=root/(name+'.json');p.write_text(json.dumps(m),encoding='utf-8');paths.append(p)
    return paths

class CompositionEffectReceiptTests(unittest.TestCase):
    def test_missing_or_unauthorized_receipts_cannot_prove_local_processes(self):
        for case in ('omitted','missing-proof','wrong-key','unproved',
                     'missing-unverified-list','extraneous'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as td:
                result=composer.compose(write_models(Path(td),case))
                self.assertEqual(result['status'],'inconclusive')
                self.assertEqual(set(result['unproved_local_processes']),{'p.one','p.two'})

    def test_complete_claims_are_only_structural_not_source_conformance(self):
        with tempfile.TemporaryDirectory() as td:
            result=composer.compose(write_models(Path(td),'complete'))
            self.assertEqual(result['status'],'passed')
            self.assertEqual(result['unproved_local_processes'],[])
            self.assertNotIn('source_conformance',result)

if __name__=='__main__':unittest.main()
