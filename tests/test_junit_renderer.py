"""Technology-specific JUnit emitter tests; this is not a normative product Gate."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / '.cat-system'
sys.path.insert(0, str(ROOT / 'scripts'))
import cat_compile_v2 as compiler


PROCESS = 'example.select-image'
MODEL = {
    'process': PROCESS,
    'fields': [
        {'id': 'input.collision', 'role': 'input', 'presence': 'required', 'domain': {'type': 'boolean'}},
        {'id': 'output.choice', 'role': 'output', 'presence': 'required', 'domain': {'type': 'enum', 'values': ['default', 'custom', 'reject']}},
    ],
    'operation_presence': [],
}
CASES = [{
    'id': 'case.s0', 'source_tce': 's0', 'trigger': 'select-image',
    'input': {'input.collision': True}, 'initial_state': {},
    'allowed': [{'state': {}, 'output': {'output.choice': 'reject'}, 'unchanged': [], 'absent_outputs': []}],
}]
BINDING = {
    'schema': 'cat-junit-driver-binding/v1', 'process': PROCESS,
    'test_package': 'cat.generated', 'test_class': 'GeneratedSelectionContractTest',
    'driver_class': 'cat.generated.ImageDriver',
}


class JUnitRendererTests(unittest.TestCase):
    def test_deterministic_junit_test_uses_confirmed_case_oracle(self):
        from importlib.util import spec_from_file_location, module_from_spec
        path = ROOT / 'skills/tech-junit/scripts/cat_junit_renderer.py'
        spec = spec_from_file_location('cat_junit_renderer', path)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        source = module.render_junit(MODEL, CASES, BINDING)
        self.assertEqual(source, module.render_junit(MODEL, CASES, BINDING))
        self.assertIn('new cat.generated.ImageDriver()', source)
        self.assertIn('@DisplayName("case.s0")', source)
        self.assertIn('java.util.Map.entry("output.choice", "reject")', source)
        self.assertIn('driver.observeState()', source)
        self.assertIn('accepts(after, output, allowed)', source)
        self.assertNotIn('vitest', source)

    def test_invalid_binding_and_unsupported_transport_are_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'binding.json'
            p.write_text(json.dumps(BINDING), encoding='utf8')
            original = compiler.expand_cases
            try:
                compiler.expand_cases = lambda model, vectors: CASES
                first = compiler.emit_junit(MODEL, {'cases': []}, p)
                self.assertIn('GeneratedSelectionContractTest', first)
                for bad in [dict(MODEL, fields=[dict(MODEL['fields'][0], domain={'type':'set'})]),
                            dict(MODEL, fields=[dict(MODEL['fields'][0], role='action')]),
                            dict(MODEL, operation_presence=[{'field': 'output.choice'}])]:
                    with self.assertRaises(compiler.Blocked):
                        compiler.emit_junit(bad, {'cases': []}, p)
                changed = dict(BINDING, test_class='Not.Valid.Class')
                p.write_text(json.dumps(changed), encoding='utf8')
                with self.assertRaises(compiler.Blocked):
                    compiler.emit_junit(MODEL, {'cases': []}, p)
            finally:
                compiler.expand_cases = original

    @unittest.skipUnless(shutil.which('javac') and shutil.which('java'), 'JDK not installed')
    def test_generated_junit_java_executes_and_detects_wrong_actual_output(self):
        from importlib.util import spec_from_file_location, module_from_spec
        path = ROOT / 'skills/tech-junit/scripts/cat_junit_renderer.py'
        spec = spec_from_file_location('cat_junit_renderer', path)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        source = module.render_junit(MODEL, CASES, BINDING)
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            target = d / 'cat/generated'
            target.mkdir(parents=True)
            (target / 'GeneratedSelectionContractTest.java').write_text(source,encoding='utf8')
            (target / 'ImageDriver.java').write_text('''package cat.generated;
import java.util.Map;
public final class ImageDriver implements GeneratedSelectionContractTest.Driver {
    public void prepare(Map<String,Object> s,Map<String,Object> i) {}
    public Map<String,Object> observeState() { return Map.of(); }
    public Map<String,Object> trigger(String t,Map<String,Object> i) {
        return Map.of("output.choice", Boolean.getBoolean("wrong.output") ? "custom" : "reject");
    }
}
''',encoding='utf8')
            junit = d / 'org/junit/jupiter/api'
            junit.mkdir(parents=True)
            (junit / 'Test.java').write_text('package org.junit.jupiter.api; public @interface Test {}\n',encoding='utf8')
            (junit / 'DisplayName.java').write_text('package org.junit.jupiter.api; public @interface DisplayName { String value(); }\n',encoding='utf8')
            (junit / 'Assertions.java').write_text('''package org.junit.jupiter.api;
public final class Assertions {
 public static void assertEquals(Object e,Object a,String reason) { if(!e.equals(a)) throw new AssertionError(reason); }
 public static void assertTrue(boolean value,String reason) { if(!value) throw new AssertionError(reason); }
}
''',encoding='utf8')
            (target / 'Runner.java').write_text('''package cat.generated;
public final class Runner {
 public static void main(String[] args) throws Exception {
   new GeneratedSelectionContractTest().catCase0001();
 }
}
''',encoding='utf8')
            files = [str(x) for x in d.rglob('*.java')]
            subprocess.run(['javac','-d',str(d),*files],check=True,capture_output=True,text=True)
            passed=subprocess.run(['java','-cp',str(d),'cat.generated.Runner'],capture_output=True,text=True)
            self.assertEqual(passed.returncode,0,passed.stderr)
            rejected=subprocess.run(['java','-Dwrong.output=true','-cp',str(d),'cat.generated.Runner'],capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode,0)
            self.assertIn('Observed state/output not in CAT allowed outcome set',rejected.stderr)


if __name__=='__main__':
    unittest.main()
