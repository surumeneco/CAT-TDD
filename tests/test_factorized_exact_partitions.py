"""Large exact Guard quotients may reuse bounded predicate evaluation."""
import json
import tempfile
import unittest
from pathlib import Path
from test_projection_unused_typed_sibling import fixture, closure, load, validate


class FactorizedExactPartitionTests(unittest.TestCase):
    def test_exact_record_and_null_quotients(self):
        for domain, guard, method in [
            ('record<version:boolean,metadata:json-object>', 'input.request.version == true and input.a >= 0 and input.b >= 0', 'required-record-member-partition/v1'),
            ('nullable<string>', 'input.request == null and input.a >= 0 and input.b >= 0', 'nullable-string-null-partition/v1'),
        ]:
            for gap in (False, True):
                with self.subTest(domain=domain, gap=gap), tempfile.TemporaryDirectory() as td:
                    root=Path(td); p, pi, tce=fixture(root, 'string', guard=guard, gap=gap)
                    content=pi.read_text(encoding='utf8').replace('record<version:integer,metadata:string>',domain)
                    content=content.replace('| output.answer |','| input.a | receive | integer[0..255] | required |\n| input.b | receive | integer[0..255] | required |\n| output.answer |')
                    content=content.replace('## Constraints\n| Expression |\n| --- |','## Constraints\n| Expression |\n| --- |\n| `input.a >= 0` |\n| `input.b >= 0` |')
                    pi.write_text(content,encoding='utf8')
                    model=load(p,pi,tce,allow_partial=True)
                    check=model['coverage_checks']['compare']
                    self.assertEqual(check['result'],'uncovered' if gap else 'proved',check)
                    self.assertEqual(check['proof_method'],method)
                    self.assertEqual(check['abstract_state_count'],131072)
                    # Quotient cells are not counts of all concrete values.
                    self.assertIsNone(check['uncovered_count'])
                    out=root/'Model.json';out.write_text(json.dumps(model),encoding='utf8')
                    self.assertEqual(validate(p,pi,tce,out)['status'],'passed')
                    self.assertEqual(closure(root)=='passed',not gap)
                    if gap:
                        check.update(result='proved',uncovered=[])
                        out.write_text(json.dumps(model),encoding='utf8')
                        self.assertNotEqual(validate(p,pi,tce,out)['status'],'passed')


    def test_split_short_circuit_never_reads_missing_value(self):
        for safe in (True, False):
            with self.subTest(safe=safe), tempfile.TemporaryDirectory() as td:
                root=Path(td)
                present='input.request == true and input.a >= 0 and input.b >= 0'
                guard=f'is_missing(input.request) or ({present})' if safe else f'({present}) or is_missing(input.request)'
                p,pi,tce=fixture(root,'string',guard=guard)
                content=pi.read_text(encoding='utf8').replace('record<version:integer,metadata:string> | required','boolean | optional')
                content=content.replace('| output.answer |','| input.a | receive | integer[0..255] | required |\n| input.b | receive | integer[0..255] | required |\n| output.answer |')
                pi.write_text(content,encoding='utf8')
                model=load(p,pi,tce,allow_partial=True)
                check=model['coverage_checks']['compare']
                self.assertEqual(check['result'],'proved' if safe else 'unproven',check)
                self.assertEqual(closure(root)=='passed',safe)

if __name__=='__main__':unittest.main()
