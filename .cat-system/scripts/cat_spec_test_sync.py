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
