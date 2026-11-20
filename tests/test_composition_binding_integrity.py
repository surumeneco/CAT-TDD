"""PI bindings must not mask unbound receiver inputs or ambiguous mappings."""
import sys, json, tempfile, unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'),str(Path(__file__).resolve().parent)]
from test_process_composition import model,binding
import cat_process_composition as composer
import cat_flow as flow

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


    def test_provider_operation_absent_overrides_pi_required_and_rejects_receiver(self):
        # A required PI-wide output is not guaranteed for an Operation whose
        # source-bound Presence declares it absent. Type-only composition used
        # to accept this link as structurally matched.
        with tempfile.TemporaryDirectory() as td:
            sender=model('p.one','p.two','send')
            receiver=model('p.two','p.one','receive')
            sender['operation_presence']=[{'operation':'p.one.op','source_pi':'p.one.pi',
                                          'field':'output.value','presence':'absent'}]
            a,b,c=self.write(Path(td),sender,receiver,binding())
            with self.assertRaisesRegex(composer.CompositionError,'typed/presence mismatch'):
                composer.compose([a,b],c)

    def test_receiver_operation_optional_can_accept_optional_sender(self):
        # A per-Operation *receiver* override must also affect comparison;
        # a base PI-required field cannot mask a legitimate optional input.
        with tempfile.TemporaryDirectory() as td:
            sender=model('p.one','p.two','send')
            receiver=model('p.two','p.one','receive')
            sender['fields'][0]['presence']='optional'
            receiver['operation_presence']=[{'operation':'p.two.op','source_pi':'p.two.pi',
                                            'field':'input.value','presence':'optional'}]
            a,b,c=self.write(Path(td),sender,receiver,binding())
            r=composer.compose([a,b],c)
            self.assertEqual(r['bindings'][0]['status'],'structurally-matched')
            self.assertEqual(r['bindings'][0]['field_links'][0]['presence'],('optional','optional'))

    def test_operation_absent_receiver_extra_does_not_require_missing_field_link(self):
        with tempfile.TemporaryDirectory() as td:
            sender=model('p.one','p.two','send')
            receiver=model('p.two','p.one','receive')
            receiver['fields'].append({'id':'input.extra','role':'input','source_pi':'p.two.pi',
                                       'presence':'required','domain':{'type':'boolean'}})
            receiver['operation_presence']=[{'operation':'p.two.op','source_pi':'p.two.pi',
                                            'field':'input.extra','presence':'absent'}]
            a,b,c=self.write(Path(td),sender,receiver,binding())
            r=composer.compose([a,b],c)
            self.assertEqual(r['bindings'][0]['unmapped_target_fields'],[])
            self.assertEqual(r['bindings'][0]['status'],'structurally-matched')

    def test_operation_required_receiver_extra_cannot_hide_behind_pi_absent(self):
        with tempfile.TemporaryDirectory() as td:
            sender=model('p.one','p.two','send')
            receiver=model('p.two','p.one','receive')
            receiver['fields'].append({'id':'input.extra','role':'input','source_pi':'p.two.pi',
                                       'presence':'absent','domain':{'type':'boolean'}})
            receiver['operation_presence']=[{'operation':'p.two.op','source_pi':'p.two.pi',
                                            'field':'input.extra','presence':'required'}]
            a,b,c=self.write(Path(td),sender,receiver,binding())
            r=composer.compose([a,b],c)
            self.assertEqual(r['bindings'][0]['unmapped_target_fields'],['input.extra'])
            self.assertEqual(r['bindings'][0]['status'],'inconclusive')

    def test_process_closure_gate_blocks_operation_presence_mismatch(self):
        # The official multi-Process closure entry must reject the same invalid
        # boundary, even when the synthetic Models claim local closure.
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            sender=model('p.one','p.two','send')
            receiver=model('p.two','p.one','receive')
            sender['operation_presence']=[{'operation':'p.one.op','source_pi':'p.one.pi',
                                          'field':'output.value','presence':'absent'}]
            a,b,c=self.write(root,sender,receiver,binding())
            work={'scope':{'process_ids':['p.one','p.two']},
                  'compilation':{'composition_models':[a.name,b.name],
                                 'composition_binding':c.name}}
            wp=root/'Work.json'
            wp.write_text(json.dumps(work),encoding='utf-8')
            verdict=flow.conformance_work(wp,work,'process-closure')
            self.assertEqual(verdict['status'],'blocked')
            self.assertIn('typed/presence mismatch',verdict['reason'])

    def test_unrelated_operation_override_does_not_change_linked_presence(self):
        with tempfile.TemporaryDirectory() as td:
            sender=model('p.one','p.two','send')
            receiver=model('p.two','p.one','receive')
            sender['pi_operations'].append({**sender['pi_operations'][0],
                                            'id':'p.one.other'})
            sender['operation_presence']=[{'operation':'p.one.other','source_pi':'p.one.pi',
                                          'field':'output.value','presence':'absent'}]
            a,b,c=self.write(Path(td),sender,receiver,binding())
            result=composer.compose([a,b],c)
            self.assertEqual(result['bindings'][0]['status'],'structurally-matched')
            self.assertEqual(result['bindings'][0]['field_links'][0]['presence'],('required','required'))
            self.assertTrue(any(e.get('operation')=='p.one.other'
                                for e in result['unresolved_connections']))

    def test_duplicate_operation_presence_claim_cannot_be_silently_selected(self):
        with tempfile.TemporaryDirectory() as td:
            sender=model('p.one','p.two','send')
            receiver=model('p.two','p.one','receive')
            sender['operation_presence']=[{'operation':'p.one.op','source_pi':'p.one.pi',
                                          'field':'output.value','presence':'required'},
                                         {'operation':'p.one.op','source_pi':'p.one.pi',
                                          'field':'output.value','presence':'absent'}]
            a,b,c=self.write(Path(td),sender,receiver,binding())
            with self.assertRaisesRegex(composer.CompositionError,'ambiguous operation Presence'):
                composer.compose([a,b],c)

if __name__=='__main__':unittest.main()
