"""CAT33: independent PI providers must be scoped by trigger, not whole Process."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / '.cat-system' / 'scripts'), str(ROOT / 'tests')]
from cat_compile_v2 import load, selection_vectors, expand_cases, Blocked
from cat_model_conformance import validate
from test_intrinsic_rule_proofs import approve_fixture


def artifact(kind, ident, refs, body):
    return ("---\ncat_version: '0.3'\nkind: " + kind + "\nid: " + ident
            + "\nstatus: draft\nprocess: investigation.presence\n"
            + "source_refs:\n  - isolated-independent-providers\ndecision_ref: ''\nrefs: "
            + json.dumps(refs) + "\nsemantic_contract: markdown-v2\nlanguage: en\n---\n\n"
            + body + "\n")


def fixture(root):
    root.mkdir(parents=True, exist_ok=True)
    names = ('first', 'second')
    ids = [f'investigation.presence.{name}.pi' for name in names]
    p = root / 'process.md'
    p.write_text(artifact('process', 'investigation.presence', ids, '''# Process

## Contract
Closed world: true

## Interfaces
| PI |
| --- |
''' + '\n'.join('| ' + ident + ' |' for ident in ids) + '''

## State
| ID | Domain |
| --- | --- |

## Observations
| ID | Source | Domain |
| --- | --- | --- |

## Actions
| ID | Target | Domain |
| --- | --- | --- |

## Triggers
| ID | Source |
| --- | --- |
''' + '\n'.join(f'| {name} | investigation.presence.{name}.pi/{name} |' for name in names)), encoding='utf-8')
    pis = []
    for name in names:
        pi = root / (name + '.pi.md')
        pi.write_text(artifact('pi', f'investigation.presence.{name}.pi',
            ['investigation.presence', 'investigation.presence.tce'],
            f'''# PI

## Boundary
| Peer process | Direction |
| --- | --- |
| investigation.{name} | bidirectional |

## Fields
| ID | Direction | Domain | Presence |
| --- | --- | --- | --- |
| input.{name} | receive | boolean | required |
| output.{name} | send | boolean | optional |

## Operations
| ID | Direction | Trigger |
| --- | --- | --- |
| {name} | accept | {name} |
| {name}_result | provide | {name} |

## Operation presence
| Operation | Field | Presence |
| --- | --- | --- |
| {name}_result | output.{name} | optional |

## Constraints
| Expression |
| --- |'''), encoding='utf-8')
        pis.append(pi)
    tce = root / 'tce.md'
    tce.write_text(artifact('tce', 'investigation.presence.tce',
        ['investigation.presence', *ids], '''# TCE

Coverage requirement: closed

## Behaviors
| ID | Trigger | Condition | Outcome | Effects |
| --- | --- | --- | --- | --- |
''' + '\n'.join(f'| {name}.yes | {name} | `input.{name}` | 1 | `output.{name} = true` |\n'
                  f'| {name}.no | {name} | `not(input.{name})` | 1 | 変更なし |' for name in names)), encoding='utf-8')
    for path in (p, *pis, tce):
        approve_fixture(path)
    return p, pis, tce


class TriggerScopedOutputPresenceTests(unittest.TestCase):
    def test_two_independent_providers_with_distinct_triggers_are_fully_proved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p, pis, tce = fixture(root)
            model = load(p, pis, tce)
            self.assertEqual(model['status'], 'confirmed')
            self.assertEqual(model['presence_unproven'], [])
            self.assertTrue(all(x['result'] == 'proved' for x in model['coverage_checks'].values()))
            path = root / 'Model.json'
            path.write_text(json.dumps(model), encoding='utf-8')
            self.assertEqual(validate(p, pis, tce, path)['status'], 'passed')
            vectors = selection_vectors(model)
            cases = expand_cases(model, vectors)
            self.assertEqual({x['output_operation'] for x in cases}, {'first_result', 'second_result'})
            for case in cases:
                self.assertEqual(case['output_operation'], case['trigger'] + '_result')
                self.assertTrue(all(name.startswith('output.' + case['trigger'])
                                    for alt in case['allowed'] for name in alt['output']))

    def test_two_providers_for_same_trigger_remain_unproved(self):
        with tempfile.TemporaryDirectory() as td:
            p, pis, tce = fixture(Path(td))
            second = pis[1]
            second.write_text(second.read_text(encoding='utf-8').replace(
                '| second_result | provide | second |',
                '| second_result | provide | first |'), encoding='utf-8')
            model = load(p, pis, tce, allow_draft=True, allow_partial=True)
            self.assertEqual(model['status'], 'draft')
            self.assertIn('output.first', model['presence_unproven'])

    def test_cross_pi_output_effect_is_not_claimed_under_wrong_provider(self):
        with tempfile.TemporaryDirectory() as td:
            p, pis, tce = fixture(Path(td))
            tce.write_text(tce.read_text(encoding='utf-8').replace(
                '| first.yes | first | `input.first` | 1 | `output.first = true` |',
                '| first.yes | first | `input.first` | 1 | `output.second = true` |'), encoding='utf-8')
            model = load(p, pis, tce, allow_draft=True, allow_partial=True)
            self.assertEqual(model['status'], 'draft')
            self.assertIn('output.second', model['presence_unproven'])


if __name__ == '__main__':
    unittest.main()
