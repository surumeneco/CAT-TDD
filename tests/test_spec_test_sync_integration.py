"""End-to-end confirmed CAT source -> independent suite sync, no TDD Queue."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".cat-system" / "scripts"))
import cat_compile_v2 as compiler
import cat_flow
from cat_spec_test_sync import main as sync_main
from test_cat_compile_readable import write_v2

class ConfirmedSyncIntegration(unittest.TestCase):
    def test_confirmed_process_generates_all_rule_tests_without_red_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process, pi, tce = write_v2(root, False)
            for source in (process, pi, tce):
                txt = source.read_text(encoding="utf-8")
                txt = txt.replace("status: draft", "status: confirmed")
                txt = txt.replace("decision_ref: ''", "decision_ref: https://example.org/approved")
                source.write_text(txt, encoding="utf-8")
            model = compiler.load(process, pi, [tce], None, False)
            (root / "Model.json").write_text(
                json.dumps(model, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            vectors = compiler.selection_vectors(model)
            (root / "Vectors.json").write_text(
                json.dumps(vectors, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            (root / "binding.json").write_text(json.dumps({
                "schema": compiler.D, "process": "demo.process", "driver": "./driver"
            }), encoding="utf-8")
            work = {
                "schema": "cat-work/v1", "id": "demo.sync", "entry": "confirmed-spec",
                "mode": "implementation", "flow": "spec-test-sync",
                "work_kind": "test-maintenance",
                "issue_ref": "issue:demo", "project_entry_ref": "https://example.org/project",
                "normative": [{"uri": "https://example.org/confirmed"}],
                "evidence": [{"uri": "https://example.org/current-source"}],
                "specification": {"status": "confirmed", "decision_ref": "https://example.org/approved",
                                  "artifact_refs": []},
                "scope": {"process_ids": ["demo.process"], "changed_ids": [], "preserved_ids": []},
                "technologies": ["Vitest"], "repositories": [], "checks": [], "gates": [],
                "compilation": {"schema": "cat-compile/v2", "process": "Process.md",
                                "pi": "PI.md", "tce": "TCE.md", "model": "Model.json",
                                "vectors": "Vectors.json", "binding": "binding.json",
                                "allow_draft": False},
            }

            suite_xml = "<testsuite>" + "".join(
                '<testcase name="' + case["id"] + '"/>'
                for case in vectors["cases"]) + "</testsuite>"
            command = ("from pathlib import Path;import sys;"
                       "Path(sys.argv[1]).write_text(" + repr(suite_xml) + ")")
            work["repositories"] = [{"name": "app", "path": str(root),
                                      "allowed_paths": ["tests/generated/*", ".cat-flow/*"]}]
            work["checks"] = [{
                "id": "suite", "stage": "suite-run", "runner": "junit",
                "cwd": "@repo:app",
                "argv": [sys.executable, "-c", command, "{report}"],
                "test_ids": [case["id"] for case in vectors["cases"]]}]
            workpath = root / "Work.json"
            workpath.write_text(json.dumps(work), encoding="utf-8")
            self.assertEqual(cat_flow.validate(work), [])
            for gate in ("process-closure", "model-conformance"):
                outcome = cat_flow.conformance_work(workpath, work, gate)
                self.assertEqual(outcome["status"], "passed", outcome)
                cat_flow.record_conformance_evidence(workpath, work, gate, outcome)
            def git(*argv):
                return subprocess.check_output(["git", "-C", str(root), *argv], text=True).strip()
            git("init", "-q")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.org")
            git("add", ".")
            git("commit", "-qm", "fixture")
            args = ["--work", str(workpath), "--repo", str(root),
                    "--repo-revision", git("rev-parse", "HEAD")]
            for phase in ("plan", "sync", "verify"):
                self.assertEqual(sync_main([phase, *args]), 0, phase)
            generated = list((root / "tests/generated").glob("*.test.ts"))
            self.assertEqual(len(generated), 2)
            self.assertFalse((root / "TDD/Queue").exists())
            self.assertTrue(all("isDeepStrictEqual" in p.read_text()
                                for p in generated))
            self.assertEqual(sync_main(["run", *args, "--check-id", "suite"]), 0)
            self.assertEqual(sync_main(["report", *args]), 0)
            execution = json.loads((root / ".cat-flow/evidence/test-suite-execution.json").read_text())
            self.assertEqual(execution["test_execution"]["status"], "test-execution-passed")
            self.assertEqual(cat_flow.status_work(workpath, work)["checks"]["suite"]["status"], "passed")
            self.assertEqual(
                set(execution["test_execution"]["observed_targets"]),
                {case["id"] for case in vectors["cases"]})
            # For the CI-only real Vitest smoke, export the already verified test
            # sources into a disposable project after the canonical gates pass.
            if os.environ.get("CAT_SYNC_VITEST_SMOKE_DIR"):
                target = Path(os.environ["CAT_SYNC_VITEST_SMOKE_DIR"])
                target.mkdir(parents=True, exist_ok=True)
                for source in generated:
                    shutil.copyfile(source, target / source.name)
                (target / "driver.ts").write_text(
                    "export function createDriver() {\n"
                    "  let state: Record<string, unknown> = {};\n"
                    "  return {\n"
                    "    async prepare(before: Record<string, unknown>) { state = { ...before }; },\n"
                    "    async observeState() { return { ...state }; },\n"
                    "    async trigger(_trigger: string, input: Record<string, unknown>) {\n"
                    "      const enabled = input['input.enabled'] === true;\n"
                    "      if (enabled) state['state.ready'] = true;\n"
                    "      return { 'output.accepted': enabled };\n"
                    "    },\n"
                    "  };\n"
                    "}\n", encoding="utf-8")
            # Mutating the source makes the earlier canonical Gate evidence stale.
            process.write_text(process.read_text() + "\n# changed\n")
            self.assertEqual(sync_main(["verify", *args]), 2)

if __name__ == "__main__":
    unittest.main()
