"""PI bindings must not mask unbound receiver inputs or ambiguous mappings."""
import sys, json, tempfile, unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'),str(Path(__file__).resolve().parent)]
from test_process_composition import model,binding
import cat_process_composition as composer

class BindingIntegrityTests(unittest.TestCase):
    def write(self,root,source,target,bind):
        files=[root/'source.json',root/'target.json',root/'binding.json']
        for path,value in zip(files,(source,target,bind)):
            path.write_text(json.dumps(value),encoding='utf-8')
        return files

    def test_missing_required_target_input_is_unresolved_not_structurally_matched(self):
        with tempfile.TemporaryDirectory() as td:
            s=model('p.one','p.two','send');t=model('p.two','p.one','receive')
            t['fields'].append({'id':'input.required-extra','role':'input','source_pi':'p.two.pi',
                                'presence':'required','domain':{'type':'integer'}})
            a,b,c=self.write(Path(td),s,t,binding())
            r=composer.compose([a,b],c)
            self.assertEqual(r['status'],'inconclusive')
            self.assertEqual(r['bindings'][0]['status'],'inconclusive')
            self.assertIn('input.required-extra',r['bindings'][0]['unmapped_target_fields'])
            self.assertEqual(len(r['unresolved_connections']),2)

    def test_two_source_fields_cannot_ambiguously_bind_one_target_field(self):
        with tempfile.TemporaryDirectory() as td:
            s=model('p.one','p.two','send');t=model('p.two','p.one','receive')
            s['fields'].append({'id':'output.secondary','role':'output','source_pi':'p.one.pi',
                                'presence':'required','domain':{'type':'integer'}})
            links=binding()
            links['links'][0]['field_links'].append({'source_field':'output.secondary','target_field':'input.value'})
            a,b,c=self.write(Path(td),s,t,links)
            with self.assertRaisesRegex(composer.CompositionError,'ambiguous target field binding'):
                composer.compose([a,b],c)

    def test_complete_required_target_link_remains_structurally_matched(self):
        with tempfile.TemporaryDirectory() as td:
            a,b,c=self.write(Path(td),model('p.one','p.two','send'),model('p.two','p.one','receive'),binding())
            r=composer.compose([a,b],c)
            self.assertEqual(r['bindings'][0]['status'],'structurally-matched')
            self.assertEqual(r['bindings'][0]['unmapped_target_fields'],[])

if __name__=='__main__':unittest.main()
