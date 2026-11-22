"""Independent Source->Model checking of claim provenance and proof-scope metadata.

Generated model maps are diagnostic claims, not an alternate normative Source.
A changed source_semantic_map or removed proof limitation must not receive an
independent 'passed' verdict merely because the normalized TCE rules match.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from test_model_conformance import ModelConformanceTest
import cat_compile_v2 as compiler
import cat_model_conformance as validator


class SourceSemanticMapIntegrityTests(unittest.TestCase):
    def test_source_claims_and_proof_limits_are_derived_from_original_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p,pi,t=ModelConformanceTest().confirmed_fixture(root)
            original=compiler.load(p,pi,t)
            model_path=root/'Model.json'
            def check(m):
                model_path.write_text(json.dumps(m,ensure_ascii=False),encoding='utf-8')
                return validator.validate(p,pi,t,model_path)
            self.assertEqual(check(original)['status'],'passed')
            # These changes are not edits to the normative Source. They are
            # changes to secondary, Compiler-owned model provenance claims.
            cases={
                'source-map-deleted': lambda m:m.pop('source_semantic_map'),
                'source-map-foreign-process':lambda m:m['source_semantic_map']['process'].__setitem__('artifact','foreign.process'),
                'source-map-silent-state-loss':lambda m:m['source_semantic_map']['process'].__setitem__('state',[]),
                'source-map-hidden-trigger':lambda m:m['source_semantic_map']['process'].__setitem__('triggers',[]),
                'source-map-forged-interface':lambda m:m['source_semantic_map']['process'].__setitem__('interfaces',['foreign.pi']),
                'source-map-false-pi':lambda m:m['source_semantic_map']['pi'].__setitem__('artifacts',['foreign.pi']),
                'source-map-false-pi-fields':lambda m:m['source_semantic_map']['pi'].__setitem__('fields',['入力.有効']),
                'source-map-false-operations':lambda m:m['source_semantic_map']['pi'].__setitem__('operations',[]),
                'source-map-false-constraint-count':lambda m:m['source_semantic_map']['pi'].__setitem__('constraint_count',5),
                'source-map-unrelated-tce':lambda m:m['source_semantic_map']['tce'][0].__setitem__('artifact','foreign.tce'),
                'source-map-removed-tce-rule':lambda m:m['source_semantic_map']['tce'][0].__setitem__('rules',[]),
                'source-map-false-allowed-count':lambda m:m['source_semantic_map']['tce'][0].__setitem__('outcome_count',1),
                'source-map-false-coverage':lambda m:m['source_semantic_map']['tce'][0].__setitem__('local_coverage','partial'),
                'source-map-forged-normative-input':lambda m:m['source_semantic_map'].__setitem__('common_rules',['foreign.rule']),
                'source-map-forged-domain-spec':lambda m:m['source_semantic_map'].__setitem__('domain_specs',['foreign.spec']),
                'source-map-forged-domain-rule':lambda m:m['source_semantic_map']['domain_rule'].__setitem__('artifact','foreign.domain'),
                'source-map-forged-type-source':lambda m:m['source_semantic_map'].__setitem__('type_definitions',['foreign.type']),
                'source-map-forged-extra-key':lambda m:m['source_semantic_map'].__setitem__('not_from_source','forged'),
                'local-coverage-forgery':lambda m:m['local_coverage_requirements'].__setitem__('demo.process.tce','partial'),
                'local-coverage-deleted':lambda m:m.pop('local_coverage_requirements'),
                'pi-artifact-inventory':lambda m:m.__setitem__('pi_artifacts',[]),
                'proof-limits-deleted':lambda m:m.pop('limits'),
                'proof-limits-erased':lambda m:m.__setitem__('limits',[]),
                'proof-limits-augmented':lambda m:m['limits'].append('proof-of-global-reachability'),
                'model-type-forged':lambda m:m.__setitem__('model_type','fully-proved-composition'),
                'normalized-ir-forged':lambda m:m.__setitem__('normalized_ir','unapproved-semantic-contract/v9'),
            }
            for label,mutation in cases.items():
                with self.subTest(case=label):
                    forged=copy.deepcopy(original)
                    mutation(forged)
                    result=check(forged)
                    self.assertEqual(result['status'],'blocked',result)
                    self.assertTrue(set(result['mismatches'])&{
                        'source_semantic_map','local_coverage_requirements',
                        'pi_artifacts','limits','model_type','normalized_ir'
                    },result)


    def test_official_process_closure_rejects_forged_source_map_and_proof_scope(self):
        from test_process_closure_source_conformance import ProcessClosureSourceConformanceTests
        gate=ProcessClosureSourceConformanceTests()
        valid=gate._gate()
        self.assertEqual(valid['status'],'passed',valid)
        for label,mutation in (
            ('drop-source-map',lambda m:m.pop('source_semantic_map')),
            ('invent-rule-source',lambda m:m['source_semantic_map'].__setitem__(
                'common_rules',['invented.source'])),
            ('hide-proof-limit',lambda m:m['limits'].remove('no-general-reachability-proof')),
            ('forge-global-reachability',lambda m:m.__setitem__('model_type','complete-reachability-proof')),
        ):
            with self.subTest(case=label):
                result=gate._gate(mutation)
                self.assertEqual(result['status'],'blocked',result)
                self.assertIn('source',result['reason'].lower())


if __name__=='__main__':unittest.main()
