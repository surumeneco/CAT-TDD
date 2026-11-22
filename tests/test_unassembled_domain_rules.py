"""Manifest-declared unassembled library Rules must not be accidentally compiled."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
import cat_assembly_regression as regression
from cat_compile_v2 import Blocked

class UnassembledDomainRulesTests(unittest.TestCase):
 def test_explicitly_unassembled_library_domain_rule_is_not_compiled(self):
  # An assembly-scoped omitted Source is retained for SHA audit, not
  # silently promoted to the compiled Process's normative Source graph.
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)
   for name in ('Present.md','PI.md'):(root/name).write_text('placeholder')
   (root/'TCE.md').write_text('---\nrefs: []\n---\nplaceholder')
   domain='---\nid: sample.library\nkind: domain-rule\nrefs: []\n---\nplaceholder'
   (root/'Domain.md').write_text(domain)
   entry={'id':'sample.library','kind':'domain-rule','path':'Domain.md',
          'sha256':hashlib.sha256((root/'Domain.md').read_bytes()).hexdigest()}
   (root/'Assembly.json').write_text(json.dumps({
       'schema':'cat-reviewed-source-assembly/v1','unassembled_sources':[entry],
       'processes':[{'owner':'one','process':'Present.md','pis':['PI.md'],
       'tces':['TCE.md'],'domain_specs':[],'common_rules':[],
       'domain_rules':['Domain.md']}]}))
   fake_model={'status':'draft','coverage_claim':'not-proved',
               'source_records':[{'id':'stub','sha256':'a'*64}],
               'unverified_rule_ids':[]}
   fake_validation={'status':'passed','mismatches':[]}
   with mock.patch.object(regression,'load',return_value=fake_model) as load,\
        mock.patch.object(regression.cat_model_conformance,'validate',return_value=fake_validation):
    result=regression.review(root,'Assembly.json',allow_draft=True)
   self.assertEqual(result['status'],'passed')
   self.assertIsNone(load.call_args.args[3])
   self.assertEqual(result['results'][0].get('unassembled_domain_rules'),['Domain.md'])

 def test_unassembled_domain_rule_must_match_declared_sha(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)
   for name in ('Present.md','PI.md','TCE.md','Domain.md'):
    (root/name).write_text('placeholder')
   (root/'Assembly.json').write_text(json.dumps({
       'schema':'cat-reviewed-source-assembly/v1',
       'unassembled_sources':[{'id':'sample.library','kind':'domain-rule',
                               'path':'Domain.md','sha256':'0'*64}],
       'processes':[{'owner':'one','process':'Present.md','pis':['PI.md'],
        'tces':['TCE.md'],'domain_specs':[],'common_rules':[],
        'domain_rules':['Domain.md']}]}))
   with self.assertRaises(Blocked):regression.review(root,'Assembly.json',True)


 def test_unassembled_domain_rule_referenced_by_tce_fails_closed(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)
   for name in ('Present.md','PI.md'):(root/name).write_text('placeholder')
   (root/'TCE.md').write_text('---\nrefs: ["sample.library"]\n---\nplaceholder')
   (root/'Domain.md').write_text('---\nid: sample.library\nkind: domain-rule\nrefs: []\n---\n')
   sha=hashlib.sha256((root/'Domain.md').read_bytes()).hexdigest()
   (root/'Assembly.json').write_text(json.dumps({
       'schema':'cat-reviewed-source-assembly/v1',
       'unassembled_sources':[{'id':'sample.library','kind':'domain-rule',
                               'path':'Domain.md','sha256':sha}],
       'processes':[{'owner':'one','process':'Present.md','pis':['PI.md'],
        'tces':['TCE.md'],'domain_specs':[],'common_rules':[],
        'domain_rules':['Domain.md']}]}))
   with self.assertRaisesRegex(Blocked,'referenced'):
    regression.review(root,'Assembly.json',True)

 def test_unassembled_domain_rule_source_identity_mismatch_fails_closed(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)
   for name in ('Present.md','PI.md','TCE.md'):(root/name).write_text('placeholder')
   (root/'Domain.md').write_text('---\nid: actual.library\nkind: domain-rule\nrefs: []\n---\n')
   sha=hashlib.sha256((root/'Domain.md').read_bytes()).hexdigest()
   (root/'Assembly.json').write_text(json.dumps({
       'schema':'cat-reviewed-source-assembly/v1',
       'unassembled_sources':[{'id':'wrong.library','kind':'domain-rule',
                               'path':'Domain.md','sha256':sha}],
       'processes':[{'owner':'one','process':'Present.md','pis':['PI.md'],
        'tces':['TCE.md'],'domain_specs':[],'common_rules':[],
        'domain_rules':['Domain.md']}]}))
   with self.assertRaisesRegex(Blocked,'identity mismatch'):
    regression.review(root,'Assembly.json',True)

if __name__=='__main__':unittest.main()
