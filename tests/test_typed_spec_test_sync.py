"""W08: source-bound type-only DomainSpec in confirmed test-suite sync."""
from __future__ import annotations
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
import cat_compile_v2 as compiler
import cat_spec_test_sync as sync
from test_cat_compile_readable import write_v2, fm


def approve_fixture(path):
    # A synthetic isolated *test* fixture, NOT authorization for product sources.
    s=path.read_text(encoding='utf-8')
    path.write_text(s.replace('status: draft','status: confirmed')
                     .replace("decision_ref: ''",'decision_ref: test-only-decision'),
                    encoding='utf-8')


def prepare(root, with_rule=False):
    p,pi,t=write_v2(root,False)
    anchor='| input.enabled | receive | boolean | required |'
    pi.write_text(pi.read_text(encoding='utf-8').replace(
        anchor,anchor+'\n| input.data | receive | record<Change> | required |'),encoding='utf-8')
    ds=root/'DomainSpec.md'
    ds.write_text(fm('domain-spec','demo.types',[],language='en')+
        '\n## Types\n| ID | Domain |\n| --- | --- |\n'
        '| Change | record<flag:boolean> |\n'
        + ('\n## Rules\n| ID | Condition | Requirement | Verification |\n'
           '| --- | --- | --- | --- |\n'
           '| demo.rule | input.data | Audit required | static contract |\n'
           if with_rule else ''),encoding='utf-8')
    for source in (p,pi,t,ds):approve_fixture(source)
    m=compiler.load(p,pi,t,allow_draft=bool(with_rule),domain_specs=[ds])
    (root/'Model.json').write_text(json.dumps(m,ensure_ascii=False,sort_keys=True),encoding='utf-8')
    if m['status']=='confirmed':
        vectors=compiler.selection_vectors(m)
        (root/'Vectors.json').write_text(json.dumps(vectors,ensure_ascii=False,sort_keys=True),encoding='utf-8')
    (root/'binding.json').write_text(json.dumps({
        'schema':compiler.D,'process':'demo.process','driver':'./driver'
    }),encoding='utf-8')
    return m,{'process':str(p),'pi':str(pi),'model':str(root/'Model.json'),
              'vectors':str(root/'Vectors.json'),'binding':str(root/'binding.json'),
              'domain_specs':[str(ds)]},[str(t)]


class TypedSyncTests(unittest.TestCase):
    def test_type_only_domain_spec_generates_deterministic_suite_with_hash_bound_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            model,paths,tces=prepare(root)
            self.assertEqual(model['status'],'confirmed')
            self.assertEqual(model['rule_obligations'],[])
            with patch.object(sync,'source_paths',return_value=(paths,tces,None)):
                desired,rendered,inputs=sync.render_suite(root/'Work.json',{},'tests/generated/')
                again=sync.render_suite(root/'Work.json',{},'tests/generated/')
            self.assertEqual((desired,rendered,inputs),again)
            self.assertEqual(len(desired),2)
            self.assertEqual(len(rendered),2)
            self.assertTrue(all('isDeepStrictEqual' in data.decode() for data in rendered.values()))
            self.assertEqual(len(inputs['source_sha256']),64)
            original_hash=inputs['source_sha256']
            # DomainSpec is an actual source input, not an untracked parser hint.
            ds=Path(paths['domain_specs'][0])
            ds.write_text(ds.read_text(encoding='utf-8')+'\n',encoding='utf-8')
            with patch.object(sync,'source_paths',return_value=(paths,tces,None)):
                with self.assertRaises((sync.Blocked,compiler.Blocked)):
                    sync.render_suite(root/'Work.json',{},'tests/generated/')
            self.assertEqual(len(original_hash),64)

    def test_rule_bearing_domain_spec_never_bypasses_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            model,paths,tces=prepare(root,with_rule=True)
            self.assertTrue(model['rule_obligations'])
            self.assertEqual(model['status'],'draft')
            with patch.object(sync,'source_paths',return_value=(paths,tces,None)):
                with self.assertRaises((sync.Blocked,compiler.Blocked)):
                    sync.render_suite(root/'Work.json',{},'tests/generated/')


if __name__=='__main__':unittest.main()
