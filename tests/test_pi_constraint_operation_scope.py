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
from cat_compile_v2 import Blocked, expand_cases, load, selection_vectors
from cat_model_conformance import validate
from test_intrinsic_rule_proofs import approve_fixture


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

    def test_constraint_cannot_silently_refer_to_another_pi_field(self):
        with tempfile.TemporaryDirectory() as td:
            p, pis, tce = fixture(Path(td), cross_pi=True)
            with self.assertRaises(Blocked):
                load(p, pis, tce, allow_draft=True)


if __name__ == '__main__':
    unittest.main()
