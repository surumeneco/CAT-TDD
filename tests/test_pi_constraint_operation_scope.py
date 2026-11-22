"""CAT41: a PI constraint must not leak into unrelated Process operations.

All sources here are isolated synthetic CAT fixtures. `confirmed` labels are
fixtures only, not product decisions or a promotion mechanism.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / '.cat-system' / 'scripts'), str(ROOT / 'tests')]
from cat_compile_v2 import Blocked, expand_cases, load, render_model_markdown, selection_vectors
from cat_model_conformance import validate
from test_intrinsic_rule_proofs import approve_fixture
from test_cat_compile_readable import write_v2


def artifact(kind, ident, refs, body):
    return ("---\ncat_version: '0.3'\nkind: " + kind + "\nid: " + ident
            + "\nstatus: draft\nprocess: demo.scope\nsource_refs:\n"
            + "  - isolated-cat41-operation-scope\ndecision_ref: ''\nrefs: "
            + json.dumps(refs) + "\nsemantic_contract: markdown-v2\nlanguage: en\n---\n\n"
            + body + "\n")


def fixture(root, *, cross_pi=False):
    root.mkdir(parents=True, exist_ok=True)
    a = 'demo.scope.a.pi'
    b = 'demo.scope.b.pi'
    p = root / 'Process.md'
    p.write_text(artifact('process', 'demo.scope', [a, b], f'''## Contract
Closed world: true

## Interfaces
| PI |
| --- |
| {a} |
| {b} |

## State
| ID | Domain |
| --- | --- |
| state.done | boolean |

## Triggers
| ID | Origin |
| --- | --- |
| A | {a}/A |
| B | {b}/B |'''), encoding='utf-8')
    pi_a = root / 'A.pi.md'
    pi_b = root / 'B.pi.md'
    pi_a.write_text(artifact('pi', a, ['demo.scope'], '''## Boundary
| Peer process | Direction |
| --- | --- |
| demo.caller | receive |

## Fields
| ID | Direction | Domain | Presence |
| --- | --- | --- | --- |
| input.a | receive | boolean | required |
| input.b | receive | boolean | required |

## Operations
| ID | Direction | Trigger |
| --- | --- | --- |
| A | accept | A |

## Constraints
| Expression |
| --- |
| `input.a == input.b` |''' if not cross_pi else '''## Boundary
| Peer process | Direction |
| --- | --- |
| demo.caller | receive |

## Fields
| ID | Direction | Domain | Presence |
| --- | --- | --- | --- |
| input.a | receive | boolean | required |
| input.b | receive | boolean | required |

## Operations
| ID | Direction | Trigger |
| --- | --- | --- |
| A | accept | A |

## Constraints
| Expression |
| --- |
| `input.a == input.other` |'''), encoding='utf-8')
    pi_b.write_text(artifact('pi', b, ['demo.scope'], '''## Boundary
| Peer process | Direction |
| --- | --- |
| demo.caller | receive |

## Fields
| ID | Direction | Domain | Presence |
| --- | --- | --- | --- |
| input.other | receive | boolean | required |

## Operations
| ID | Direction | Trigger |
| --- | --- | --- |
| B | accept | B |

## Constraints
| Expression |
| --- |'''), encoding='utf-8')
    tce = root / 'TCE.md'
    tce.write_text(artifact('tce', 'demo.scope.tce', [a, b], '''Coverage requirement: closed

## Behaviors
| ID | Trigger | Condition | Outcome | Effects |
| --- | --- | --- | --- | --- |
| A.done | A | `true` | 1 | `state.done = true` |
| B.done | B | `true` | 1 | `state.done = true` |'''), encoding='utf-8')
    for path in (p, pi_a, pi_b, tce):
        approve_fixture(path)
    return p, [pi_a, pi_b], tce


class OperationScopedPIConstraintsTests(unittest.TestCase):
    def test_a_only_b_only_and_combined_have_independent_guard_spaces(self):
        with tempfile.TemporaryDirectory() as td:
            p, pis, tce = fixture(Path(td))
            model = load(p, pis, tce)
            self.assertEqual(model['status'], 'confirmed')
            self.assertEqual(model['coverage_checks']['A']['guard_refs'], ['input.a', 'input.b'])
            self.assertEqual(model['coverage_checks']['B']['guard_refs'], [])
            self.assertTrue(model['coverage_checks']['A']['excluded_by_pi_constraints'])
            self.assertFalse(model['coverage_checks']['B']['excluded_by_pi_constraints'])
            model_path = Path(td) / 'Model.json'
            model_path.write_text(json.dumps(model, ensure_ascii=False), encoding='utf-8')
            self.assertEqual(validate(p, pis, tce, model_path)['status'], 'passed')
            self.assertEqual({x['trigger'] for x in selection_vectors(model)['cases']}, {'A', 'B'})
            # The A-only invalid input is rejected, B does not need A's input.
            with self.assertRaises(Blocked):
                expand_cases(model, {'schema':'cat-test-vectors/v2','process':'demo.scope',
                                     'cases':[{'id':'bad_a','trigger':'A',
                                               'input':{'input.a':True,'input.b':False},
                                               'state':{'state.done':False}}]})
            cases = expand_cases(model, {'schema':'cat-test-vectors/v2','process':'demo.scope',
                                         'cases':[{'id':'good_b','trigger':'B',
                                                   'input':{'input.other':True},
                                                   'state':{'state.done':False}}]})
            self.assertEqual(cases[0]['source_tce'],'B.done')

    def test_empty_admissible_guard_space_cannot_vacuously_prove_trigger(self):
        # Contradictory accept-time constraints make A impossible, but an
        # empty truth table must not be promoted to Process Closure. The
        # independent checker must derive that limit from the original PIs.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p, pis, tce = fixture(root)
            pi = pis[0]
            source = pi.read_text(encoding='utf-8')
            self.assertIn('| `input.a == input.b` |', source)
            pi.write_text(source.replace(
                '| `input.a == input.b` |',
                '| `input.a == true` |\\n| `input.a == false` |'.replace('\\n', '\n')),
                encoding='utf-8')
            approve_fixture(pi)
            original = tce.read_text(encoding='utf-8')
            self.assertIn('| A.done | A | `true` | 1 | `state.done = true` |', original)
            tce.write_text(original.replace(
                '| A.done | A | `true` | 1 | `state.done = true` |\\n'.replace('\\n','\n'),
                ''), encoding='utf-8')
            approve_fixture(tce)
            model = load(p, pis, tce, allow_draft=True, allow_partial=True)
            self.assertEqual(model['coverage_checks']['A']['result'], 'unproven')
            self.assertIn('no admissible', model['coverage_checks']['A']['reason'])
            self.assertEqual(model['coverage_claim'], 'partial')
            self.assertEqual(model['status'], 'draft')
            output = root / 'Model.json'
            output.write_text(json.dumps(model, ensure_ascii=False), encoding='utf-8')
            self.assertEqual(validate(p, pis, tce, output, allow_draft=True)['status'], 'passed')
            forged = json.loads(output.read_text(encoding='utf-8'))
            forged['coverage_checks']['A']['result'] = 'proved'
            forged.update(status='confirmed', coverage_requirement='closed',
                          coverage_claim='closed')
            output.write_text(json.dumps(forged, ensure_ascii=False), encoding='utf-8')
            self.assertEqual(validate(p, pis, tce, output, allow_draft=True)['status'],
                             'blocked')
            with self.assertRaisesRegex(Blocked, 'closed-world coverage'):
                load(p, pis, tce)

    def test_other_pi_input_cannot_drive_a_trigger_guard(self):
        with tempfile.TemporaryDirectory() as td:
            p, pis, tce = fixture(Path(td))
            original=tce.read_text(encoding='utf-8')
            tce.write_text(original.replace(
                '| B.done | B | `true` | 1 | `state.done = true` |',
                '| B.true | B | `input.a` | 1 | `state.done = true` |\n'
                '| B.false | B | `not input.a` | 1 | `state.done = false` |'),
                encoding='utf-8')
            with self.assertRaises(Blocked):
                load(p, pis, tce)

    def test_other_pi_input_cannot_drive_a_trigger_effect(self):
        with tempfile.TemporaryDirectory() as td:
            p, pis, tce = fixture(Path(td))
            original=tce.read_text(encoding='utf-8')
            tce.write_text(original.replace(
                '| B.done | B | `true` | 1 | `state.done = true` |',
                '| B.done | B | `true` | 1 | `state.done = input.a` |'),
                encoding='utf-8')
            with self.assertRaises(Blocked):
                load(p, pis, tce)

    def test_scope_forgery_is_detected_by_independent_model_conformance(self):
        with tempfile.TemporaryDirectory() as td:
            p, pis, tce = fixture(Path(td))
            model = load(p, pis, tce)
            self.assertTrue(model['pi_constraint_scopes'])
            model['pi_constraint_scopes'][0]['triggers']=['B']
            target = Path(td) / 'Model.json'
            target.write_text(json.dumps(model, ensure_ascii=False), encoding='utf-8')
            result = validate(p, pis, tce, target)
            self.assertEqual(result['status'], 'blocked')
            self.assertIn('constraint_scopes',result['mismatches'])

    def test_result_only_pi_constraint_is_not_an_acceptance_guard(self):
        # A constraint on a provided result is not an observable input at
        # request acceptance. The compiler leaves the normative relation
        # unproved, but the independent Model audit must agree on its local
        # Guard domain instead of importing the future response.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p, pis, tce = fixture(root)
            pi = pis[0]
            text = pi.read_text(encoding='utf-8')
            text = text.replace('demo.caller | receive |',
                                'demo.caller | bidirectional |')
            text = text.replace('| input.b | receive | boolean | required |',
                '| input.b | receive | boolean | required |\n'
                '| output.complete | send | boolean | required |')
            text = text.replace('| `input.a == input.b` |',
                                '| `output.complete == true` |')
            pi.write_text(text, encoding='utf-8')
            approve_fixture(pi)
            source = tce.read_text(encoding='utf-8').replace(
                '| A.done | A | `true` | 1 | `state.done = true` |',
                '| A.done | A | `true` | 1 | `state.done = true; output.complete = true` |')
            tce.write_text(source, encoding='utf-8')
            approve_fixture(tce)
            model = load(p, pis, tce, allow_draft=True)
            self.assertEqual(model['status'], 'draft')
            self.assertEqual(model['coverage_checks']['A']['result'], 'proved')
            self.assertEqual(model['coverage_checks']['A']['guard_refs'], [])
            self.assertFalse(model['coverage_checks']['A']['excluded_by_pi_constraints'])
            self.assertEqual(model['pi_constraint_scopes'][0]['triggers'], [])
            model_path = root / 'Model.json'
            model_path.write_text(json.dumps(model, ensure_ascii=False), encoding='utf-8')
            self.assertEqual(validate(p, pis, tce, model_path, allow_draft=True)['status'], 'passed')

    def test_input_and_result_constraints_have_distinct_evaluation_times(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p, pis, tce = fixture(root)
            pi = pis[0]
            text = pi.read_text(encoding='utf-8').replace(
                'demo.caller | receive |', 'demo.caller | bidirectional |')
            text = text.replace('| input.b | receive | boolean | required |',
                '| input.b | receive | boolean | required |\n'
                '| output.complete | send | boolean | required |')
            text = text.replace('| `input.a == input.b` |',
                '| `input.a == input.b` |\n| `output.complete == true` |')
            pi.write_text(text, encoding='utf-8')
            approve_fixture(pi)
            source = tce.read_text(encoding='utf-8').replace(
                '| A.done | A | `true` | 1 | `state.done = true` |',
                '| A.done | A | `true` | 1 | `state.done = true; output.complete = true` |')
            tce.write_text(source, encoding='utf-8')
            approve_fixture(tce)
            model = load(p, pis, tce, allow_draft=True)
            self.assertEqual(model['status'], 'draft')
            self.assertEqual(model['coverage_checks']['A']['guard_refs'], ['input.a', 'input.b'])
            self.assertTrue(model['coverage_checks']['A']['excluded_by_pi_constraints'])
            self.assertEqual(len(model['pi_constraint_scopes']), 2)
            self.assertEqual([x['triggers'] for x in model['pi_constraint_scopes']], [['A'], []])
            model_path = root / 'Model.json'
            model_path.write_text(json.dumps(model, ensure_ascii=False), encoding='utf-8')
            self.assertEqual(validate(p, pis, tce, model_path, allow_draft=True)['status'], 'passed')

    def test_result_only_constraint_cannot_forge_closed_confirmed_model(self):
        # A future result relation cannot be discharged by acceptance-Guard
        # coverage. The compiler knows the constraint is unbound, so the
        # independent Source->Model validator must reject a forged closure.
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p,pi,tce=write_v2(root,False)
            for source in (p,pi,tce):approve_fixture(source)
            pi.write_text(pi.read_text(encoding='utf-8') +
                          '\n| `output.accepted == true` |\n',encoding='utf-8')
            model=load(p,pi,tce,allow_draft=True)
            self.assertEqual(model['status'],'draft')
            self.assertEqual(model['coverage_requirement'],'partial')
            self.assertEqual(len(model['unbound_pi_constraints']),1)
            self.assertEqual(model['coverage_checks']['submit']['result'],'proved')
            target=root/'Model.json'
            target.write_text(json.dumps(model),encoding='utf-8')
            self.assertEqual(validate(p,pi,tce,target,allow_draft=True)['status'],'passed')
            model.update(status='confirmed',coverage_requirement='closed',
                         coverage_claim='closed')
            target.write_text(json.dumps(model),encoding='utf-8')
            result=validate(p,pi,tce,target,allow_draft=True)
            self.assertEqual(result['status'],'blocked',result)
            self.assertIn('source_guard_coverage',result['mismatches'])
            self.assertIn('normative_status_unjustified',result['mismatches'])

    def test_input_constraint_without_accept_operation_cannot_claim_closure(self):
        # A PI can declare an input constraint without a matching accepted
        # Operation. No new external Trigger or observational time is inferred.
        with tempfile.TemporaryDirectory() as td:
            p,pis,tce=fixture(Path(td))
            owner=pis[0]
            original=owner.read_text(encoding='utf-8')
            self.assertIn('| A | accept | A |',original)
            owner.write_text(original.replace('| A | accept | A |',''),encoding='utf-8')
            model=load(p,pis,tce,allow_draft=True)
            self.assertEqual(model['status'],'draft')
            self.assertEqual(model['unbound_pi_constraints'][0]['reason'],
                             'no accepted Operation to bind PI constraint')
            target=Path(td)/'Model.json'
            target.write_text(json.dumps(model),encoding='utf-8')
            self.assertEqual(validate(p,pis,tce,target,allow_draft=True)['status'],'passed')
            model.update(status='confirmed',coverage_requirement='closed',
                         coverage_claim='closed')
            target.write_text(json.dumps(model),encoding='utf-8')
            result=validate(p,pis,tce,target,allow_draft=True)
            self.assertEqual(result['status'],'blocked',result)
            self.assertIn('source_guard_coverage',result['mismatches'])
            self.assertIn('normative_status_unjustified',result['mismatches'])

    def test_markdown_model_retains_exact_pi_operation_constraint_bindings(self):
        # Human-readable models may not silently lose the explicit Trigger
        # scope that JSON models preserve for a Process with two PI owners.
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p,pis,tce=fixture(root)
            model=load(p,pis,tce)
            target=root/'TestModel.md'
            rendered=render_model_markdown(model)
            self.assertIn('## PI constraint bindings',rendered)
            self.assertIn('| demo.scope.a.pi | A |',rendered)
            target.write_text(rendered,encoding='utf-8')
            self.assertEqual(validate(p,pis,tce,target)['status'],'passed')
            tampered=rendered.replace('| demo.scope.a.pi | A |',
                                     '| demo.scope.a.pi | B |',1)
            self.assertNotEqual(tampered,rendered)
            target.write_text(tampered,encoding='utf-8')
            outcome=validate(p,pis,tce,target)
            self.assertEqual(outcome['status'],'blocked',outcome)
            self.assertIn('constraint_bindings',outcome['mismatches'])
            target.write_text(rendered.replace('## PI constraint bindings',
                                               '## hidden bindings',1),encoding='utf-8')
            self.assertIn('constraint_bindings',
                          validate(p,pis,tce,target)['mismatches'])

    def test_markdown_model_retains_result_time_constraint_as_unproved(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p,pi,tce=write_v2(root,False)
            for source in (p,pi,tce):approve_fixture(source)
            pi.write_text(pi.read_text(encoding='utf-8') +
                          '\n| `output.accepted == true` |\n',encoding='utf-8')
            model=load(p,pi,tce,allow_draft=True)
            self.assertEqual(model['status'],'draft')
            target=root/'TestModel.md'
            rendered=render_model_markdown(model)
            self.assertIn('## PI constraint bindings',rendered)
            self.assertIn('non-input result relation',rendered)
            target.write_text(rendered,encoding='utf-8')
            self.assertEqual(validate(p,pi,tce,target,allow_draft=True)['status'],'passed')
            target.write_text(rendered.replace('non-input result relation','—',1),
                              encoding='utf-8')
            outcome=validate(p,pi,tce,target,allow_draft=True)
            self.assertEqual(outcome['status'],'blocked',outcome)
            self.assertIn('constraint_bindings',outcome['mismatches'])

    def test_japanese_markdown_retains_unbound_result_constraint(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p,pi,tce=write_v2(root,True)
            for source in (p,pi,tce):approve_fixture(source)
            pi.write_text(pi.read_text(encoding='utf-8') +
                          '\n| `output.accepted == 真` |\n',encoding='utf-8')
            model=load(p,pi,tce,allow_draft=True)
            target=root/'TestModel.md'
            document=render_model_markdown(model)
            self.assertIn('## PI制約の束縛',document)
            self.assertIn('(output.accepted == 真)',document)
            self.assertIn('non-input result relation',document)
            target.write_text(document,encoding='utf-8')
            self.assertEqual(validate(p,pi,tce,target,allow_draft=True)['status'],'passed')

    def test_unbound_constraint_receipt_is_source_bound_and_not_erasable(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p,pi,tce=write_v2(root,False)
            for source in (p,pi,tce):approve_fixture(source)
            pi.write_text(pi.read_text(encoding='utf-8') +
                          '\n| `output.accepted == true` |\n',encoding='utf-8')
            model=load(p,pi,tce,allow_draft=True)
            self.assertEqual(len(model['unbound_pi_constraints']),1)
            target=root/'Model.json'
            for replacement in ([],None,[{'source_pi':'forged',
                                          'expr':model['unbound_pi_constraints'][0]['expr'],
                                          'reason':'non-input result relation'}]):
                with self.subTest(receipt=replacement):
                    forged=json.loads(json.dumps(model))
                    if replacement is None:
                        del forged['unbound_pi_constraints']
                    else:
                        forged['unbound_pi_constraints']=replacement
                    target.write_text(json.dumps(forged),encoding='utf-8')
                    result=validate(p,pi,tce,target,allow_draft=True)
                    self.assertEqual(result['status'],'blocked',result)
                    self.assertIn('unbound_pi_constraints',result['mismatches'])

    def test_constraint_cannot_silently_refer_to_another_pi_field(self):
        with tempfile.TemporaryDirectory() as td:
            p, pis, tce = fixture(Path(td), cross_pi=True)
            with self.assertRaises(Blocked):
                load(p, pis, tce, allow_draft=True)


if __name__ == '__main__':
    unittest.main()
