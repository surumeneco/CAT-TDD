"""Assembly regression is read-only and must not upgrade candidate authority."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
import cat_assembly_regression as regression
from cat_compile_v2 import Blocked

class AssemblyRegressionTests(unittest.TestCase):
 def test_parent_traversal_and_symlink_are_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);outside=root.parent/'outside-file-for-regression-test'
   (root/'inner').mkdir()
   (root/'inner'/'test.json').write_text('{}')
   self.assertEqual(regression.safe(root,'inner/test.json'),root/'inner'/'test.json')
   for name in ('../secret','/etc/passwd','inner\\test.json'):
    with self.assertRaises(Blocked):regression.safe(root,name)
   (root/'link').symlink_to(root/'inner',target_is_directory=True)
   with self.assertRaises(Blocked):regression.safe(root,'link/test.json')
 def test_bad_assembly_does_not_report_pass(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/'Assembly.json').write_text(json.dumps({
      'schema':'cat-reviewed-source-assembly/v1','processes':[{'owner':'bad','process':'NotPresent.md',
      'pis':[],'tces':[],'domain_specs':[],'common_rules':[],'domain_rules':[]}]}))
   with self.assertRaises(FileNotFoundError):
    regression.review(root,'Assembly.json',allow_draft=True)
 def test_full_assembly_never_silently_skips_domain_rule(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)
   # Required sources must exist even for an advisory diagnostic subset.
   (root/'Assembly.json').write_text(json.dumps({'schema':'cat-reviewed-source-assembly/v1',
       'processes':[{'owner':'one','process':'Present.md','pis':['PI.md'],
       'tces':['TCE.md'],'domain_specs':[],'common_rules':[],
       'domain_rules':['MissingDomainRule.md']}]}))
   for n in ('Present.md','PI.md','TCE.md'):(root/n).write_text('placeholder')
   with self.assertRaises(FileNotFoundError):regression.review(root,'Assembly.json',True)

if __name__=='__main__':unittest.main()
