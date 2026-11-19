"""Fixed CAT37 original input: canonical CLI and independent Model check.

The embedded bytes reproduce the exact 2026-11-19 CAT37 input ZIP files.
These candidate documents prove only local typed Effect membership, not a
WebApp normative Gate, actual execution or an approved product Source.
"""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / ".cat-system" / "scripts"
SOURCE_B64 = {
    "process.md": "LS0tCmNhdF92ZXJzaW9uOiAnMC4zJwpraW5kOiBwcm9jZXNzCmlkOiBpbnZlc3RpZ2F0aW9uLnByb29mCnN0YXR1czogY2FuZGlkYXRlCnByb2Nlc3M6IGludmVzdGlnYXRpb24ucHJvb2YKc291cmNlX3JlZnM6CiAgLSBjdXJyZW50LW1haW4tcHJvb2YtY2FwYWNpdHktaW52ZXN0aWdhdGlvbi1vbmx5CmRlY2lzaW9uX3JlZjogJycKcmVmczogWyJpbnZlc3RpZ2F0aW9uLnByb29mLnBpIl0Kc2VtYW50aWNfY29udHJhY3Q6IG1hcmtkb3duLXYyCmxhbmd1YWdlOiBlbgotLS0KCiMgUHJvY2VzcyBpbnZlc3RpZ2F0aW9uLnByb29mCgojIyBDb250cmFjdApDbG9zZWQgd29ybGQ6IHRydWUKCiMjIEludGVyZmFjZXMKfCBQSSB8CnwgLS0tIHwKfCBpbnZlc3RpZ2F0aW9uLnByb29mLnBpIHwKCiMjIFN0YXRlCnwgSUQgfCBEb21haW4gfAp8IC0tLSB8IC0tLSB8Cnwgc3RhdGUudmFsdWVzIHwgc2V0PHN0cmluZz4gfAoKIyMgT2JzZXJ2YXRpb25zCnwgSUQgfCBTb3VyY2UgfCBEb21haW4gfAp8IC0tLSB8IC0tLSB8IC0tLSB8CgojIyBBY3Rpb25zCnwgSUQgfCBUYXJnZXQgfCBEb21haW4gfAp8IC0tLSB8IC0tLSB8IC0tLSB8CgojIyBUcmlnZ2Vycwp8IElEIHwgU291cmNlIHwKfCAtLS0gfCAtLS0gfAp8IHN1Ym1pdCB8IGludmVzdGlnYXRpb24ucHJvb2YucGkvc3VibWl0IHwKCg==",
    "pi.md": "LS0tCmNhdF92ZXJzaW9uOiAnMC4zJwpraW5kOiBwaQppZDogaW52ZXN0aWdhdGlvbi5wcm9vZi5waQpzdGF0dXM6IGNhbmRpZGF0ZQpwcm9jZXNzOiBpbnZlc3RpZ2F0aW9uLnByb29mCnNvdXJjZV9yZWZzOgogIC0gY3VycmVudC1tYWluLXByb29mLWNhcGFjaXR5LWludmVzdGlnYXRpb24tb25seQpkZWNpc2lvbl9yZWY6ICcnCnJlZnM6IFsiaW52ZXN0aWdhdGlvbi5wcm9vZiIsICJpbnZlc3RpZ2F0aW9uLnByb29mLnRjZSJdCnNlbWFudGljX2NvbnRyYWN0OiBtYXJrZG93bi12MgpsYW5ndWFnZTogZW4KLS0tCgojIFBJIGludmVzdGlnYXRpb24ucHJvb2YucGkKCiMjIEJvdW5kYXJ5CnwgUGVlciBwcm9jZXNzIHwgRGlyZWN0aW9uIHwKfCAtLS0gfCAtLS0gfAp8IGludmVzdGlnYXRpb24uYWN0b3IgfCBiaWRpcmVjdGlvbmFsIHwKCiMjIEZpZWxkcwp8IElEIHwgRGlyZWN0aW9uIHwgRG9tYWluIHwgUHJlc2VuY2UgfAp8IC0tLSB8IC0tLSB8IC0tLSB8IC0tLSB8CnwgaW5wdXQudmFsdWUgfCByZWNlaXZlIHwgc3RyaW5nIHwgcmVxdWlyZWQgfAoKIyMgT3BlcmF0aW9ucwp8IElEIHwgRGlyZWN0aW9uIHwgVHJpZ2dlciB8CnwgLS0tIHwgLS0tIHwgLS0tIHwKfCBzdWJtaXQgfCBhY2NlcHQgfCBzdWJtaXQgfAoKIyMgQ29uc3RyYWludHMKfCBFeHByZXNzaW9uIHwKfCAtLS0gfAoKCg==",
    "tce.md": "LS0tCmNhdF92ZXJzaW9uOiAnMC4zJwpraW5kOiB0Y2UKaWQ6IGludmVzdGlnYXRpb24ucHJvb2YudGNlCnN0YXR1czogY2FuZGlkYXRlCnByb2Nlc3M6IGludmVzdGlnYXRpb24ucHJvb2YKc291cmNlX3JlZnM6CiAgLSBjdXJyZW50LW1haW4tcHJvb2YtY2FwYWNpdHktaW52ZXN0aWdhdGlvbi1vbmx5CmRlY2lzaW9uX3JlZjogJycKcmVmczogWyJpbnZlc3RpZ2F0aW9uLnByb29mIiwgImludmVzdGlnYXRpb24ucHJvb2YucGkiXQpzZW1hbnRpY19jb250cmFjdDogbWFya2Rvd24tdjIKbGFuZ3VhZ2U6IGVuCi0tLQoKIyBUQ0UgaW52ZXN0aWdhdGlvbi5wcm9vZi50Y2UKCkNvdmVyYWdlIHJlcXVpcmVtZW50OiBjbG9zZWQKCiMjIEJlaGF2aW9ycwp8IElEIHwgVHJpZ2dlciB8IENvbmRpdGlvbiB8IE91dGNvbWUgfCBFZmZlY3RzIHwKfCAtLS0gfCAtLS0gfCAtLS0gfCAtLS0gfCAtLS0gfAp8IHJlbW92ZSB8IHN1Ym1pdCB8IGB0cnVlYCB8IDEgfCBgc3RhdGUudmFsdWVzID0gc2V0X3JlbW92ZShzdGF0ZS52YWx1ZXMsIGlucHV0LnZhbHVlKWAgfAoK"
}
SOURCE_SHA256 = {
    "process.md": "1be82ba74f1bd1bbc9756a07916a2152af41b35843661f297fed049b219c051c",
    "pi.md": "ecc805669445ab155fd70cebf0cc09cbfee3dfc35def39652556a12d37ffb225",
    "tce.md": "9242477d55fed08f0e4c8686d4d5832bc1a9ab1b55c552c169e83eb62e023411"
}
EFFECT_ID = "investigation.proof.tce#remove:1:1:state.values"

class CAT37OriginalInputTests(unittest.TestCase):
    def write_original(self, root, changes=None):
        paths = {}
        for name, encoded in SOURCE_B64.items():
            raw = base64.b64decode(encoded)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), SOURCE_SHA256[name])
            if changes and name in changes:
                old, new = changes[name]
                self.assertEqual(raw.count(old.encode()), 1)
                raw = raw.replace(old.encode(), new.encode())
            paths[name] = root / name
            paths[name].write_bytes(raw)
        return paths

    def run_model(self, paths, root):
        output = root / "fresh-model.json"
        command = [sys.executable, str(SCRIPTS / "cat_compile_v2.py"), "model",
                   str(paths["process.md"]), str(paths["pi.md"]),
                   str(paths["tce.md"]), "--allow-draft", "--allow-partial",
                   "-o", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, (command, result.stdout, result.stderr))
        return output, json.loads(output.read_text(encoding="utf-8"))

    def conformance(self, paths, output):
        command = [sys.executable, str(SCRIPTS / "cat_model_conformance.py"),
                   str(paths["process.md"]), str(paths["pi.md"]), str(output),
                   "--tce", str(paths["tce.md"]), "--allow-draft"]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        return result, json.loads(result.stdout) if result.stdout else {}

    def test_original_source_unchanged_roundtrip_proves_typed_effect(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = self.write_original(root)
            output, model = self.run_model(paths, root)
            self.assertEqual(model["source_sha256"]["process"], SOURCE_SHA256["process.md"])
            self.assertEqual(model["source_sha256"]["pi"], SOURCE_SHA256["pi.md"])
            self.assertEqual(model["source_sha256"]["tce"], SOURCE_SHA256["tce.md"])
            self.assertEqual(model["effect_checks"][EFFECT_ID],
                             {"result": "proved", "proof_method": "typed-domain-closure/v1"})
            self.assertEqual(model["unverified_effect_ids"], [])
            self.assertEqual(model["status"], "draft")  # candidate Source, not Confirmed
            result, evidence = self.conformance(paths, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(evidence["status"], "passed")

    def test_original_source_wrong_element_domain_remains_unproved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = self.write_original(root, {"pi.md": ("| input.value | receive | string | required |",
                                                             "| input.value | receive | integer | required |")})
            _, model = self.run_model(paths, root)
            self.assertEqual(model["effect_checks"][EFFECT_ID]["result"], "unproven")

    def test_original_source_optional_input_without_guard_remains_unproved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = self.write_original(root, {"pi.md": ("| input.value | receive | string | required |",
                                                             "| input.value | receive | string | optional |")})
            _, model = self.run_model(paths, root)
            self.assertEqual(model["effect_checks"][EFFECT_ID]["result"], "unproven")

    def test_forged_effect_proof_fails_independent_model_comparison(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = self.write_original(root)
            output, model = self.run_model(paths, root)
            model["effect_checks"][EFFECT_ID] = {"result": "unproven", "reason": "forged"}
            output.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
            result, evidence = self.conformance(paths, output)
            self.assertEqual(result.returncode, 2, (result.stdout, result.stderr))
            self.assertEqual(evidence["status"], "blocked")
            self.assertIn("effect_checks", evidence["mismatches"])

if __name__ == "__main__":
    unittest.main()
