"""Deterministic Test Suite Manifest and provenance checks for spec-test-sync."""
from __future__ import annotations
import hashlib
import json
import os
import tempfile
from pathlib import Path
from cat_suite_plan_candidate import plan_suite

SCHEMA = "cat-test-suite-manifest/v1"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def checked_path(root, relative):
    if (not isinstance(relative, str) or not relative or relative.startswith("/") or
        "\\" in relative or any(x in ("", ".", "..") for x in relative.split("/")) or
        any(ord(ch) < 32 or ord(ch) == 127 for ch in relative)):
        raise ValueError("unsafe test-suite path")
    base = Path(root).resolve(strict=True)
    path = base / relative
    if not path.resolve().is_relative_to(base) or any(
        item.is_symlink() for item in [path, *path.parents] if item == base or base in item.parents
    ):
        raise ValueError("test-suite path escapes repository or is a symlink")
    return path


def load_manifest(root, relative):
    path = checked_path(root, relative)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("entries"), dict):
        raise ValueError("invalid existing Test Suite Manifest")
    return data


def create_plan(root, manifest_path, prefix, desired, rendered, inputs, revision):
    if (not prefix.endswith("/") or prefix.startswith("/") or
            any(x in ("", ".", "..") for x in prefix[:-1].split("/"))):
        raise ValueError("invalid generated test prefix")
    if not manifest_path.startswith(".cat-flow/") or manifest_path.startswith(prefix):
        raise ValueError("Manifest path must be under .cat-flow")
    old = load_manifest(root, manifest_path)
    entries = old.get("entries", {})
    if set(rendered) != {x["path"] for x in desired}:
        raise ValueError("rendered files do not match selected vectors")
    disk = {}
    for name in set(rendered) | set(entries):
        if not name.startswith(prefix):
            raise ValueError("Manifest owns file outside generated prefix")
        path = checked_path(root, name)
        if path.exists():
            if not path.is_file():
                raise ValueError("generated test target is not a file")
            disk[name] = digest(path.read_bytes())
    proposal = plan_suite(
        **inputs, repo_revision=revision, allowed_prefix=prefix,
        desired=desired, disk_hashes=disk, manifest=entries)
    return proposal, old


def verify_plan(plan, recorded):
    if not recorded or any(r['action'] not in ('unchanged','retain') for r in plan['entries']):
        raise ValueError('suite out of sync')
    return {'status':'test-suite-verified','manifest_sha256':digest(encoded(recorded))}

def atomic_write(target, data):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError("output became a symlink")
    fd, temp = tempfile.mkstemp(prefix=".cat-sync-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def synchronize(root, manifest_path, proposal, previous, rendered):
    """Verify ownership and all on-disk hashes before any generated test write."""
    rows = proposal["entries"]
    if any(row["action"] == "blocked" for row in rows):
        raise ValueError("suite conflicts: no files changed")
    if load_manifest(root, manifest_path) != previous:
        raise ValueError("Manifest was modified after planning")
    owners = dict(previous.get("entries", {}))
    for row in rows:
        name, action = row["path"], row["action"]
        target = checked_path(root, name)
        previous_owner = owners.get(name)
        if action == "create" and target.exists():
            raise ValueError("new test target appeared after planning")
        if action in ("update", "unchanged", "retain"):
            if (not previous_owner or not target.is_file()
                    or digest(target.read_bytes()) != previous_owner["file_sha256"]):
                raise ValueError("owned test changed after planning")
        if action in ("create", "update", "unchanged"):
            if name not in rendered or digest(rendered[name]) != row["content_sha256"]:
                raise ValueError("renderer bytes changed after planning")
            owners[name] = {
                "test_id": row["test_id"], "owner": "generated",
                "file_sha256": row["content_sha256"],
                **{key: proposal["inputs"][key] for key in (
                    "source_sha256", "model_sha256", "vectors_sha256",
                    "renderer_version", "binding_version")},
            }
        elif action != "retain":
            raise ValueError("unknown suite action")
    result = {"schema": SCHEMA, "inputs": proposal["inputs"], "entries": owners}
    for row in rows:
        if row["action"] in ("create", "update"):
            atomic_write(checked_path(root, row["path"]), rendered[row["path"]])
    atomic_write(checked_path(root, manifest_path), encoded(result))
    return {"status": "test-suite-synced", "manifest_sha256": digest(encoded(result)),
            "actions": {key: sum(row["action"] == key for row in rows)
                        for key in ("create", "update", "unchanged", "retain")}}
