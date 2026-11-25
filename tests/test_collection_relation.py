"""Source-bound unbounded filter and stable-sort relation profiles."""
import json
import tempfile
import unittest
from pathlib import Path
from test_structural_copy_relation import fixture, flow, load, validate, render_model_markdown, expand_cases, selection_vectors
from catlib.semantic_collection_relation import evaluate


class CollectionRelationTests(unittest.TestCase):
    def test_source_and_independent_checks(self):
        for operation in ('filter_by(input.items, "enabled", true)', 'stable_sort_by(input.items, "id", "asc")'):
            for variant,expected in [({},'passed'),({'rhs':'input.items'},'inconclusive'),
                                     ({'rhs':operation.replace('input.items','input.other')},'inconclusive'),
                                     ({'second':'input.other'},'inconclusive'),({'peer':'othercaller'},'inconclusive')]:
                with self.subTest(operation=operation,variant=variant),tempfile.TemporaryDirectory() as td:
                    root=Path(td)
                    args={'rhs':operation,'relation':'after.output.items == '+operation,
                          'token':'@cat:collection-relation/v1','prefix':'collection-relation '}
                    args.update(variant)
                    p,pi,tce,spec=fixture(root,**args)
                    run,result=flow(root,'conformance','--kind','process-closure')
                    self.assertEqual(result['status'],expected,(run.stdout,run.stderr))
                    if expected!='passed':continue
                    m=load(p,pi,tce,domain_specs=[spec]);v=selection_vectors(m)
                    witness=v['cases'][0]['input']['input.items'];after=expand_cases(m,v)[0]['allowed'][0]['output']['output.items']
                    self.assertNotEqual(witness,after)
                    for name,body in [('Independent.json',json.dumps(m)),('Independent.md',render_model_markdown(m))]:
                        path=root/name;path.write_text(body,encoding='utf-8')
                        self.assertEqual(validate(p,pi,tce,path,domain_specs=[spec])['status'],'passed')
                    for kind in ('model','vectors','queue','tests'):
                        run,result=flow(root,'compile','--kind',kind)
                        self.assertEqual(result['status'],'passed',(run.stdout,run.stderr))

    def test_exact_order_and_multiplicity_semantics(self):
        a={'id':1,'enabled':True};b={'id':1,'enabled':False};c={'id':2,'enabled':True}
        self.assertEqual(evaluate('filter-by',[[c,b,a,c],'enabled',True]),[c,a,c])
        self.assertEqual(evaluate('filter-by',[[],'enabled',True]),[])
        self.assertEqual(evaluate('filter-by',[[a,c],'enabled',True]),[a,c])
        self.assertEqual(evaluate('filter-by',[[b],'enabled',True]),[])
        self.assertEqual(evaluate('stable-sort-by',[[c,b,a,c],'id','asc']),[b,a,c,c])
        self.assertEqual(evaluate('stable-sort-by',[[c,b,a,c],'id','desc']),[c,c,b,a])
        self.assertEqual(evaluate('stable-sort-by',[[],'id','asc']),[])
