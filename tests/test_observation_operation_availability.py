"""CAT41 U02: declaratively scoped observations are only readable at their declared Process triggers.

Source fixtures are synthetic and do not approve external observation providers.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
from cat_compile_v2 import Blocked,load
import cat_model_conformance as independent
from test_pi_constraint_operation_scope import fixture


def sample(root, available='B'):
    process, pis, tce=fixture(root)
    s=process.read_text(encoding='utf-8')
    s=s.replace('## Triggers\n',
                '## Observations\n| ID | Source | Domain | Available on |\n'
                '| --- | --- | --- | --- |\n'
                f'| observation.completed | correlated completion observation | boolean | {available} |\n\n'
                '## Triggers\n')
    process.write_text(s,encoding='utf-8')
    t=tce.read_text(encoding='utf-8').replace(
        '| B.done | B | `true` | 1 | `state.done = true` |',
        '| B.true | B | `observation.completed` | 1 | `state.done = true` |\n'
        '| B.false | B | `not observation.completed` | 1 | `state.done = false` |')
    tce.write_text(t,encoding='utf-8')
    return process,pis,tce


class ObservationAvailabilityTests(unittest.TestCase):
    def test_only_declared_trigger_reads_observation(self):
        with tempfile.TemporaryDirectory() as temp:
            p,pis,t=sample(Path(temp),'B')
            model=load(p,pis,t)
            obs=next(f for f in model['fields'] if f['id']=='observation.completed')
            self.assertEqual(obs['available_on'],['B'])
            self.assertEqual(model['coverage_checks']['B']['result'],'proved')
            path=Path(temp)/'model.json';path.write_text(json.dumps(model),encoding='utf-8')
            self.assertEqual(independent.validate(p,pis,[t],path)['status'],'passed')

    def test_future_observation_at_other_trigger_is_not_a_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            p,pis,t=sample(Path(temp),'A')
            with self.assertRaises(Blocked):
                load(p,pis,t)

    def test_unknown_trigger_cannot_be_used_as_observation_availability(self):
        with tempfile.TemporaryDirectory() as temp:
            p,pis,t=sample(Path(temp),'undefined_trigger')
            with self.assertRaises(Blocked):
                load(p,pis,t)

    def test_model_cannot_forge_observation_availability(self):
        with tempfile.TemporaryDirectory() as temp:
            p,pis,t=sample(Path(temp),'B')
            model=load(p,pis,t)
            obs=next(f for f in model['fields'] if f['id']=='observation.completed')
            obs['available_on']=['A']
            path=Path(temp)/'model.json';path.write_text(json.dumps(model),encoding='utf-8')
            verdict=independent.validate(p,pis,[t],path)
            self.assertEqual(verdict['status'],'blocked')
            self.assertIn('observation_availability',verdict['mismatches'])


if __name__=='__main__':unittest.main()
