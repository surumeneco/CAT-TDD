#!/usr/bin/env python3
"""Confirmed CAT test-suite sync, separate from TDD Red and Queue."""

from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
import cat_compile_v2 as compiler
import cat_flow
from cat_suite_manifest import (
    checked_path, create_plan, digest, encoded, atomic_write,
    synchronize, verify_plan,
)

class Blocked(ValueError):
    pass

def source_paths(work_path, work):
    route = cat_flow.route(work, "suite-plan")
    if cat_flow.infer_flow(work) != "spec-test-sync" or route["status"] != "ready":
        raise Blocked("confirmed spec-test-sync Work is not ready")
    config = work.get("compilation")
    if (not config or config.get("allow_draft") or config.get("common_rules")
            or config.get("domain_specs")):
        raise Blocked("unsupported or unconfirmed compilation inputs")
    for kind in ("process-closure", "model-conformance"):
        gate = cat_flow.conformance_evidence_status(work_path, work, kind)
        if gate["status"] != "passed":
            raise Blocked("prerequisite Gate " + kind + ": " + gate["status"])
    paths = {name: cat_flow.compilation_path(work_path, work, config, name, True)
             for name in ("process", "pi", "model", "vectors", "binding")}
    tces = cat_flow.compilation_tce_paths(work_path, work, config, True)
    domain = (cat_flow.compilation_path(work_path, work, config, "domain_rule", True)
              if config.get("domain_rule") else None)
    return paths, tces, domain


def render_suite(work_path, work, prefix):
    paths, tces, domain = source_paths(work_path, work)
    model = compiler.load(paths["process"], paths["pi"], tces, domain, False)
    if model.get("status") != "confirmed":
        raise Blocked("confirmed TestModel required")
    model_bytes = Path(paths["model"]).read_bytes()
    if Path(paths["model"]).suffix.lower() == ".md":
        if model_bytes.decode("utf-8") != compiler.render_model_markdown(model):
            raise Blocked("stale TestModel Markdown")
    elif json.loads(model_bytes) != model:
        raise Blocked("stale TestModel")
    vector_bytes = Path(paths["vectors"]).read_bytes()
    vectors = json.loads(vector_bytes)
    if vectors != compiler.selection_vectors(model, "rule-witness/v1"):
        raise Blocked("vectors differ from canonical deterministic selection")
    if not vectors["cases"]:
        raise Blocked("no selected test vectors")
    rendered, desired = {}, []

    for vector in vectors["cases"]:
        identity = vector["id"]
        safe = re.sub(r"[^a-z0-9]+", "_", identity.lower()).strip("_")[:40] or "vector"
        name = prefix + "cat_" + safe + "_" + hashlib.sha256(identity.encode()).hexdigest()[:12] + ".test.ts"
        subset = {"schema": vectors["schema"], "process": vectors["process"],
                  "cases": [vector]}
        case = compiler.expand_cases(model, subset)[0]
        data = compiler.emit_vitest(model, subset, paths["binding"]).encode("utf-8")
        if name in rendered:
            raise Blocked("generated test filename collision")
        rendered[name] = data
        desired.append({"test_id": identity, "model_ref": case["source_tce"],
                        "vector_ref": identity, "path": name,
                        "content_sha256": digest(data)})
    sources = [paths["process"], paths["pi"], *tces, *([domain] if domain else [])]
    hashes = [digest(Path(name).read_bytes()) for name in sources]
    scripts = [Path(compiler.__file__),
               compiler.ROOT / "skills/tech-vitest/scripts/cat_vitest_renderer.py"]
    inputs = {"source_sha256": digest(encoded(hashes)),
              "model_sha256": digest(model_bytes),
              "vectors_sha256": digest(vector_bytes),
              "selection_rule": vectors["selection_rule"],
              "renderer_version": "cat-v2:" + digest(b"".join(p.read_bytes() for p in scripts)),
              "binding_version": digest(Path(paths["binding"]).read_bytes())}
    return desired, rendered, inputs


def repo_sha(root, expected):
    p = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=15)
    if p.returncode or p.stdout.strip() != expected:
        raise Blocked('repository HEAD differs from pinned revision')

