"""Presence-only PI links do not compare impossible value Domains."""
import json,sys,tempfile,unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'),str(Path(__file__).resolve().parent)]
from test_process_composition import model,binding
import cat_process_composition as composition

class NonvaluePresenceTests(unittest.TestCase):
    def test_absent_and_undefined_only_links_do_not_require_domain_overlap(self):
        for presence in ('absent','undefined'):
            with self.subTest(presence=presence),tempfile.TemporaryDirectory() as td:
                s=model('p.one','p.two','send');t=model('p.two','p.one','receive')
                s['fields'][0].update(presence=presence,domain={'type':'string'})
                t['fields'][0].update(presence=presence,domain={'type':'integer'})
                root=Path(td);paths=[root/'a.json',root/'b.json',root/'binding.json']
                for path,obj in zip(paths,(s,t,binding())):
                    path.write_text(json.dumps(obj),encoding='utf-8')
                result=composition.compose(paths[:2],paths[2])
                self.assertEqual(result['bindings'][0]['status'],'structurally-matched')
                self.assertEqual(result['bindings'][0]['field_links'][0]['value_domain_proof'],'not-applicable')
                self.assertFalse(result['bindings'][0]['external_effects_verified'])

    def test_value_presence_still_requires_domain_inclusion(self):
        with tempfile.TemporaryDirectory() as td:
            s=model('p.one','p.two','send');t=model('p.two','p.one','receive')
            s['fields'][0]['domain']={'type':'string'}
            t['fields'][0]['domain']={'type':'integer'}
            paths=[Path(td)/'a.json',Path(td)/'b.json',Path(td)/'binding.json']
            for path,obj in zip(paths,(s,t,binding())):
                path.write_text(json.dumps(obj),encoding='utf-8')
            with self.assertRaisesRegex(composition.CompositionError,'typed/presence mismatch'):
                composition.compose(paths[:2],paths[2])

if __name__=='__main__':unittest.main()
