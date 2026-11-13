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
                 'source_pi':name+'.pi','domain':{'type':'integer'}}]}

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

    def test_claimed_confirmed_without_closure_receipt_stays_inconclusive(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            paths=[]
            for name in ('p.one','p.two'):
                m=model(name,'outside','send')
                m['pi_boundaries']=[]
                # A status string alone is not local-closure evidence.
                p=root/(name+'.json');p.write_text(json.dumps(m));paths.append(p)
            result=composer.compose(paths)
            self.assertEqual(result['status'],'inconclusive')
            self.assertEqual(set(result['unproved_local_processes']),{'p.one','p.two'})

    def test_unproved_coverage_and_unresolved_interface_are_not_silently_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            paths=[]
            for name in ('p.one','p.two'):
                m=model(name,'outside','send')
                m['pi_boundaries']=[]
                m['coverage_claim']='closed'
                m['coverage_checks']={'trigger':{'result':'proved'}}
                m['unresolved_interfaces']=[]
                if name=='p.one':m['coverage_checks']['trigger']['result']='unproven'
                if name=='p.two':m['unresolved_interfaces']=['unbound.pi']
                p=root/(name+'.json');p.write_text(json.dumps(m));paths.append(p)
            result=composer.compose(paths)
            self.assertEqual(result['status'],'inconclusive')
            self.assertEqual(set(result['unproved_local_processes']),{'p.one','p.two'})

    def test_consistent_local_claims_without_boundaries_can_be_structurally_closed(self):
        # This test only checks the composition protocol's local-claim input
        # contract; independent Source->Model Conformance remains separate.
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            paths=[]
            for name in ('p.one','p.two'):
                m=model(name,'outside','send')
                m['pi_boundaries']=[]
                m['coverage_claim']='closed'
                m['coverage_checks']={'trigger':{'result':'proved'}}
                m['unresolved_interfaces']=[]
                p=root/(name+'.json');p.write_text(json.dumps(m));paths.append(p)
            result=composer.compose(paths)
            self.assertEqual(result['status'],'passed')
            self.assertEqual(result['unproved_local_processes'],[])

    def test_matching_pi_does_not_prove_external_effects(self):
        with tempfile.TemporaryDirectory() as td:
            a,b,links=self.write(Path(td))
            result=composer.compose([a,b],links)
            self.assertEqual(result['status'],'inconclusive')
            self.assertEqual(result['bindings'][0]['status'],'structurally-matched')
            self.assertEqual(len(result['unresolved_connections']),0)
            self.assertFalse(result['bindings'][0]['external_effects_verified'])

    def test_other_pi_field_cannot_be_borrowed_for_binding(self):
        with tempfile.TemporaryDirectory() as td:
            producer=model('p.one','p.two','send')
            producer['fields'][0]['source_pi']='p.one.another-pi'
            a,b,links=self.write(Path(td),first=producer)
            with self.assertRaisesRegex(composer.CompositionError,'owned by PI p.one.pi'):
                composer.compose([a,b],links)

    def test_type_mismatch_blocks_binding(self):
        with tempfile.TemporaryDirectory() as td:
            bad=model('p.two','p.one','receive')
            bad['fields'][0]['domain']={'type':'string'}
            a,b,links=self.write(Path(td),second=bad)
            with self.assertRaisesRegex(composer.CompositionError,'typed/presence mismatch'):
                composer.compose([a,b],links)

    def test_boolean_enum_cannot_bind_to_integer_enum(self):
        with tempfile.TemporaryDirectory() as td:
            producer=model('p.one','p.two','send')
            consumer=model('p.two','p.one','receive')
            producer['fields'][0]['domain']={'type':'enum','values':[True]}
            consumer['fields'][0]['domain']={'type':'enum','values':[1]}
            a,b,links=self.write(Path(td),first=producer,second=consumer)
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

    def test_bidirectional_pi_needs_reverse_direction_binding(self):
        with tempfile.TemporaryDirectory() as td:
            first=model('p.one','p.two','send')
            second=model('p.two','p.one','receive')
            first['pi_boundaries'][0]['direction']='bidirectional'
            second['pi_boundaries'][0]['direction']='bidirectional'
            a,b,links=self.write(Path(td),first=first,second=second)
            result=composer.compose([a,b],links)
            missing={(e['source_process'],e['direction']) for e in result['unresolved_connections']}
            self.assertEqual(missing,{('p.one','receive'),('p.two','send')})
            self.assertEqual(result['status'],'inconclusive')

    def test_multiple_operations_on_same_pi_can_be_independently_bound(self):
        with tempfile.TemporaryDirectory() as td:
            first=model('p.one','p.two','send')
            second=model('p.two','p.one','receive')
            first['pi_operations'].append(dict(first['pi_operations'][0],id='p.one.other'))
            second['pi_operations'].append(dict(second['pi_operations'][0],id='p.two.other'))
            links=binding()
            second_link=json.loads(json.dumps(links['links'][0]))
            second_link['source_operation']='p.one.other'
            second_link['target_operation']='p.two.other'
            links['links'].append(second_link)
            a,b,bindings=self.write(Path(td),first=first,second=second,links=links)
            result=composer.compose([a,b],bindings)
            self.assertEqual(len(result['bindings']),2)
            self.assertEqual(result['unresolved_connections'],[])
            self.assertEqual(result['status'],'inconclusive')

    def test_exact_duplicate_operation_link_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            links=binding()
            links['links'].append(dict(links['links'][0]))
            a,b,bindings=self.write(Path(td),links=links)
            with self.assertRaisesRegex(composer.CompositionError,'duplicate connection link'):
                composer.compose([a,b],bindings)

    def test_narrow_integer_domain_is_accepted_by_wider_consumer(self):
        with tempfile.TemporaryDirectory() as td:
            producer=model('p.one','p.two','send')
            consumer=model('p.two','p.one','receive')
            producer['fields'][0]['domain']={'type':'integer','min':1,'max':5}
            consumer['fields'][0]['domain']={'type':'integer','min':0,'max':10}
            a,b,links=self.write(Path(td),first=producer,second=consumer)
            result=composer.compose([a,b],links)
            self.assertEqual(result['bindings'][0]['status'],'structurally-matched')
            self.assertEqual(result['unresolved_connections'],[])

    def test_wider_integer_domain_is_not_a_valid_narrow_consumer(self):
        with tempfile.TemporaryDirectory() as td:
            producer=model('p.one','p.two','send')
            consumer=model('p.two','p.one','receive')
            producer['fields'][0]['domain']={'type':'integer','min':0,'max':10}
            consumer['fields'][0]['domain']={'type':'integer','min':1,'max':5}
            a,b,links=self.write(Path(td),first=producer,second=consumer)
            with self.assertRaisesRegex(composer.CompositionError,'typed/presence mismatch'):
                composer.compose([a,b],links)

    def test_unknown_record_shape_does_not_get_structural_proof(self):
        with tempfile.TemporaryDirectory() as td:
            producer=model('p.one','p.two','send')
            consumer=model('p.two','p.one','receive')
            nominal={'type':'record','name':'User','resolved':False}
            producer['fields'][0]['domain']=nominal
            consumer['fields'][0]['domain']=nominal
            a,b,links=self.write(Path(td),first=producer,second=consumer)
            result=composer.compose([a,b],links)
            self.assertEqual(result['status'],'inconclusive')
            self.assertEqual(result['bindings'][0]['status'],'inconclusive')
            self.assertEqual(result['bindings'][0]['field_links'][0]['status'],'inconclusive')
            self.assertTrue(result['unresolved_connections'])

    def test_nullable_source_does_not_satisfy_nonnullable_consumer(self):
        with tempfile.TemporaryDirectory() as td:
            producer=model('p.one','p.two','send')
            producer['fields'][0]['domain']={'type':'nullable','of':{'type':'integer'}}
            a,b,links=self.write(Path(td),first=producer)
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
