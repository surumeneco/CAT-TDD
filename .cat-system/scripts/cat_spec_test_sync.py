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


def run_tests(root, argv, timeout):
    if not isinstance(argv, list) or not argv or any(
            not isinstance(x, str) or not x for x in argv):
        raise Blocked("runner must be a nonempty argv list")
    try:
        result = subprocess.run(argv, cwd=root, text=True, capture_output=True,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "test-execution-not-run", "reason": str(exc)}
    return {"status": "test-execution-passed" if result.returncode == 0
            else "test-execution-failed", "exit_code": result.returncode,
            "stdout_tail": result.stdout[-2000:],
            "stderr_tail": result.stderr[-2000:]}



def run_declared_check(work_path, work, root, selected_ids, check_id):
    """Run a Work-declared JUnit check, not an arbitrary caller-supplied command."""
    check = next((item for item in work["checks"] if item["id"] == check_id), None)
    if not check or check["stage"] != "suite-run" or check["runner"] != "junit":
        raise Blocked("suite-run requires a declared JUnit check in Work")
    ids = check.get("test_ids", [])
    if len(ids) != len(set(ids)) or set(ids) != set(selected_ids):
        raise Blocked("declared JUnit test IDs differ from the generated suite")
    if not check["cwd"].startswith("@repo:"):
        raise Blocked("suite runner must execute in a declared target repository")
    declared_root = cat_flow.resolve_dir(work_path, work, check["cwd"])
    if declared_root != root:
        raise Blocked("declared suite-run repository does not match pinned target")
    if cat_flow.route(work, "suite-run")["status"] != "ready":
        raise Blocked("suite-run stage is not ready")
    executed = cat_flow.command_work(work_path, work, check_id, True)
    verdict = executed["verdict"]
    state = ("test-execution-passed" if verdict == "passed" else
             "test-execution-failed" if verdict == "blocked" else
             "test-execution-not-run")
    return {"status": state, "check_id": check_id,
            "work_evidence_sha256": digest(Path(executed["evidence"]).read_bytes()),
            "observed_targets": executed["observed_targets"],
            "reason": executed["reason"], "exit_code": executed["exit_code"]}


def execute(args):
    root = Path(args.repo).resolve(strict=True)
    if not root.is_dir() or not 1 <= args.timeout <= 3600:
        raise Blocked("invalid repo or timeout")
    repo_sha(root, args.repo_revision)
    work_path, work = cat_flow.work_file(args.work)
    desired, rendered, inputs = render_suite(work_path, work, args.prefix)
    plan, prior = create_plan(root, args.manifest, args.prefix,
                              desired, rendered, inputs, args.repo_revision)
    if args.phase == "plan":
        return {"status": "blocked" if any(
            x["action"] == "blocked" for x in plan["entries"]) else "planned",
            "plan": plan}
    if args.phase == "sync":
        return synchronize(root, args.manifest, plan, prior, rendered)
    verified = verify_plan(plan, prior)
    if args.phase == "verify":
        return verified

    if not args.report_path.startswith(".cat-flow/evidence/"):
        raise Blocked("execution report must live under .cat-flow/evidence/")
    evidence_path = checked_path(root, args.report_path)
    if args.phase == "run":
        if not args.runner_argv_json:
            raise Blocked("explicit test-runner argv required")
        outcome = {**verified, "repo_revision": args.repo_revision,
                   "test_execution": run_tests(
                       root, json.loads(args.runner_argv_json), args.timeout)}
        atomic_write(evidence_path, encoded(outcome))
        return outcome
    record = json.loads(evidence_path.read_text(encoding="utf-8"))
    if (record.get("manifest_sha256") != verified["manifest_sha256"] or
            record.get("repo_revision") != args.repo_revision):
        raise Blocked("stale test execution evidence")
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("plan", "sync", "verify", "run", "report"))
    parser.add_argument("--work", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--repo-revision", required=True)
    parser.add_argument("--prefix", default="tests/generated/")
    parser.add_argument("--manifest", default=".cat-flow/test-suite-manifest.json")
    parser.add_argument("--runner-argv-json")
    parser.add_argument("--report-path",
                        default=".cat-flow/evidence/test-suite-execution.json")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        result = execute(args)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2 if result.get("status") == "blocked" or result.get("test_execution", {}).get("status") in ("test-execution-failed", "test-execution-not-run") else 0
    except (Blocked, compiler.Blocked, ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)},
                         ensure_ascii=False), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
