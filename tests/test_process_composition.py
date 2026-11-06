#!/usr/bin/env python3
"""Composition checks cannot turn interface similarity into effect proof."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
import cat_process_composition as composer

def model(name,peer,role):
    send=role=='send'
    return {'schema':'cat-test-model/v2','process':name,'status':'confirmed',
      'coverage_requirement':'closed','unverified_rule_ids':[],
      'unresolved_domains':[],'presence_unproven':[],
      'pi_boundaries':[{'artifact':name+'.pi','peer':peer,'direction':role}],
      'pi_operations':[{'source_pi':name+'.pi','id':name+'.op',
                        'direction':'provide' if send else 'accept','trigger':'run'}],
      'fields':[{'id':'output.value' if send else 'input.value',
                 'role':'output' if send else 'input','presence':'required',
                 'domain':{'type':'integer'}}]}

def binding():
    return {'schema':'cat-process-bindings/v1','links':[{
        'source_process':'p.one','target_process':'p.two',
        'source_pi':'p.one.pi','target_pi':'p.two.pi',
        'source_operation':'p.one.op','target_operation':'p.two.op',
        'field_links':[{'source_field':'output.value','target_field':'input.value'}]
    }]}

class CompositionTests(unittest.TestCase):
    def write(self,root,first=None,second=None,links=None):
        p=root/'a.json';q=root/'b.json';r=root/'bindings.json'
        p.write_text(json.dumps(first if first is not None else model('p.one','p.two','send')))
        q.write_text(json.dumps(second if second is not None else model('p.two','p.one','receive')))
        r.write_text(json.dumps(links if links is not None else binding()))
        return p,q,r

    def test_matching_pi_does_not_prove_external_effects(self):
        with tempfile.TemporaryDirectory() as td:
            a,b,links=self.write(Path(td))
            result=composer.compose([a,b],links)
            self.assertEqual(result['status'],'inconclusive')
            self.assertEqual(result['bindings'][0]['status'],'structurally-matched')
            self.assertEqual(len(result['unresolved_connections']),0)
            self.assertFalse(result['bindings'][0]['external_effects_verified'])

    def test_type_mismatch_blocks_binding(self):
        with tempfile.TemporaryDirectory() as td:
            bad=model('p.two','p.one','receive')
            bad['fields'][0]['domain']={'type':'string'}
            a,b,links=self.write(Path(td),second=bad)
            with self.assertRaisesRegex(composer.CompositionError,'typed/presence mismatch'):
                composer.compose([a,b],links)

    def test_optional_producer_cannot_satisfy_required_input(self):
        with tempfile.TemporaryDirectory() as td:
            outgoing=model('p.one','p.two','send')
            outgoing['fields'][0]['presence']='optional'
            a,b,links=self.write(Path(td),first=outgoing)
            with self.assertRaisesRegex(composer.CompositionError,'typed/presence mismatch'):
                composer.compose([a,b],links)

    def test_required_value_cannot_satisfy_absent_only_consumer(self):
        with tempfile.TemporaryDirectory() as td:
            receiving=model('p.two','p.one','receive')
            receiving['fields'][0]['presence']='absent'
            a,b,links=self.write(Path(td),second=receiving)
            with self.assertRaisesRegex(composer.CompositionError,'typed/presence mismatch'):
                composer.compose([a,b],links)

    def test_absent_producer_can_satisfy_optional_consumer(self):
        with tempfile.TemporaryDirectory() as td:
            outgoing=model('p.one','p.two','send')
            outgoing['fields'][0]['presence']='absent'
            receiving=model('p.two','p.one','receive')
            receiving['fields'][0]['presence']='optional'
            a,b,links=self.write(Path(td),first=outgoing,second=receiving)
            result=composer.compose([a,b],links)
            self.assertEqual(result['bindings'][0]['status'],'structurally-matched')
            self.assertEqual(result['unresolved_connections'],[])
            self.assertEqual(result['status'],'inconclusive')

    def test_undefined_state_is_not_optional_missing(self):
        with tempfile.TemporaryDirectory() as td:
            outgoing=model('p.one','p.two','send')
            outgoing['fields'][0]['presence']='undefined'
            receiving=model('p.two','p.one','receive')
            receiving['fields'][0]['presence']='optional'
            a,b,links=self.write(Path(td),first=outgoing,second=receiving)
            with self.assertRaisesRegex(composer.CompositionError,'typed/presence mismatch'):
                composer.compose([a,b],links)

    def test_unmapped_external_peer_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as td:
            incoming=model('p.two','p.external','receive')
            a,b,links=self.write(Path(td),second=incoming,links={'schema':'cat-process-bindings/v1','links':[]})
            result=composer.compose([a,b],links)
            self.assertEqual(result['status'],'inconclusive')
            self.assertTrue(any(e['target_process']=='p.external' for e in result['unresolved_connections']))

    def test_duplicate_process_or_hash_pin_mismatch_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            a,b,links=self.write(root)
            with self.assertRaisesRegex(composer.CompositionError,'duplicate'):
                composer.compose([a,a],links)
            payload=json.loads(links.read_text())
            payload['model_sha256']={'p.one':'fake','p.two':'fake'}
            links.write_text(json.dumps(payload))
            with self.assertRaisesRegex(composer.CompositionError,'model hash mismatch'):
                composer.compose([a,b],links)

if __name__=='__main__':unittest.main()
