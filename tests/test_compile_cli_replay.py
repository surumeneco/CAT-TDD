"""W08: vector/queue/test CLI must recompile exactly the same source inventory."""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
import cat_compile_v2 as compiler
from test_typed_spec_test_sync import prepare
from test_intrinsic_rule_proofs import build


class SourceReplayCLITest(unittest.TestCase):
    def test_type_only_domain_spec_replayed_across_vectors_queue_and_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            model,paths,tces=prepare(root)
            common=['--process',paths['process'],'--pi',paths['pi'],
                    '--tce',tces[0],'--domain-spec',paths['domain_specs'][0]]
            output=root/'generated-vectors.json'
            self.assertEqual(compiler.main(['vectors',paths['model'],*common,'-o',str(output)]),0)
            self.assertEqual(json.loads(output.read_text(encoding='utf-8')),
                             compiler.selection_vectors(model))
            queue=root/'Queue.json'
            self.assertEqual(compiler.main(['queue',paths['model'],str(output),*common,
                                            '-o',str(queue)]),0)
            q=json.loads(queue.read_text(encoding='utf-8'))
            self.assertEqual(q['items'][0]['status'],'current')
            generated=root/'current.test.ts'
            self.assertEqual(compiler.main(['tests',paths['model'],str(output),paths['binding'],
                                            '--queue',str(queue),*common,
                                            '-o',str(generated)]),0)
            self.assertIn(q['items'][0]['id'],generated.read_text(encoding='utf-8'))
            self.assertEqual(compiler.main(['vectors',paths['model'],
                                            '--process',paths['process'],'--pi',paths['pi'],
                                            '--tce',tces[0],'-o',str(root/'wrong.json')]),2)

    def test_intrinsic_common_rule_replayed_without_silent_omission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p,pi,t,rule=build(root)
            model=compiler.load(p,pi,t,common_rules=[rule])
            self.assertEqual(model['status'],'confirmed')
            mp=root/'model.json'
            mp.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            args=['vectors',str(mp),'--process',str(p),'--pi',str(pi),
                  '--tce',str(t),'--common-rule',str(rule),
                  '-o',str(root/'vectors.json')]
            self.assertEqual(compiler.main(args),0)
            self.assertEqual(json.loads((root/'vectors.json').read_text()),
                             compiler.selection_vectors(model))
            args=args[:]
            offset=args.index('--common-rule')
            del args[offset:offset+2]
            self.assertEqual(compiler.main(args),2)


if __name__=='__main__':unittest.main()
