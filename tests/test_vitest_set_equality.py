"""W06/W08: generated Vitest must compare CAT sets by deep value, not array order."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'skills'/'tech-vitest'/'scripts'))
from cat_vitest_renderer import render_vitest


class SetRendererTests(unittest.TestCase):
    def sample(self):
        model={'status':'confirmed','process':'demo.process','fields':[
            {'id':'state.tags','role':'state','domain':{
                'type':'set','element':{'type':'record','resolved':True,
                   'fields':[{'id':'id','presence':'required','domain':{'type':'string'}}]}}},
            {'id':'output.events','role':'output','domain':{
                'type':'set','element':{'type':'record','resolved':True,
                   'fields':[{'id':'id','presence':'required','domain':{'type':'string'}}]}}},
            {'id':'state.flag','role':'state','domain':{'type':'boolean'}},
        ]}
        cases=[{'id':'case.one','source_tce':'demo.one','trigger':'submit',
                 'input':{},'initial_state':{'state.tags':[{'id':'A'},{'id':'B'}],
                                           'state.flag':True},
                 'allowed':[{'state':{'state.tags':[{'id':'B'},{'id':'A'}],
                                      'state.flag':True},
                            'output':{'output.events':[{'id':'C'},{'id':'D'}]}}]}]
        return model,cases,{'driver':'./driver'}

    def test_nested_record_sets_are_compared_without_array_sort(self):
        model,cases,binding=self.sample()
        content=render_vitest(model,cases,binding)
        self.assertIn('function sameCATSet(',content)
        self.assertIn('function equalCATValue(',content)
        self.assertIn('isDeepStrictEqual(item, expected[i])',content)
        self.assertIn('equalCATValue(id,after[id],expected.state[id],stateSetFields)',content)
        self.assertIn('equalCATValue(id,output[id],expected.output[id],outputSetFields)',content)
        self.assertIn('"output.events"',content)
        self.assertNotIn('[...value].sort()',content)
        self.assertNotIn('isDeepStrictEqual(output,expected.output)',content)
        self.assertEqual(render_vitest(model,cases,binding),content)

    def test_duplicate_set_elements_are_rejected_not_accepted_as_matches(self):
        model,cases,binding=self.sample()
        content=render_vitest(model,cases,binding)
        self.assertIn('hasDuplicate(observed)',content)
        self.assertIn('hasDuplicate(expected)',content)
        self.assertIn('used.add(i)',content)

    def test_scalar_and_record_outputs_retain_strict_equality(self):
        model,cases,binding=self.sample()
        model['fields']=[{'id':'state.flag','role':'state',
                          'domain':{'type':'boolean'}},
                         {'id':'output.ok','role':'output',
                          'domain':{'type':'boolean'}}]
        cases[0]['initial_state']={'state.flag':True}
        cases[0]['allowed']=[{'state':{'state.flag':True},
                              'output':{'output.ok':True}}]
        content=render_vitest(model,cases,binding)
        self.assertIn('return isDeepStrictEqual(observed,expected)',content)
        self.assertIn('Object.keys(output).length === Object.keys(expected.output).length',content)


if __name__=='__main__':unittest.main()
