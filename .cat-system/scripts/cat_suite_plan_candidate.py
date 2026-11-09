"""Pure deterministic test suite plan, reused by the spec-test-sync executor.

This module is a non-normative metadata decision function; it neither renders
an oracle nor writes tests/Manifest/TDD Queue or asserts CAT Gate results.
The caller must independently prove Confirmed source, renderer binding, fresh
Gate evidence, repo revision, ownership and current disk hashes.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ITEM_KEYS = frozenset({"test_id", "model_ref", "vector_ref", "path", "content_sha256"})
_MANIFEST_KEYS = frozenset({
    "test_id", "owner", "file_sha256", "source_sha256", "model_sha256",
    "vectors_sha256", "renderer_version", "binding_version",
})


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{label} must be non-empty, whitespace-trimmed text")
    return value


def _hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 hex digest")
    return value


def _contains_control(value: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in value)


def _path(value: Any, prefix: str) -> str:
    path = _string(value, "path")
    if (not path.startswith(prefix) or len(path) <= len(prefix) or
            "\\" in path or "\0" in path or "\n" in path or "\r" in path or
            _contains_control(path) or
            path.startswith("/") or "//" in path or
            any(part in ("", ".", "..") for part in path.split("/"))):
        raise ValueError(f"path is not a normalized generated target: {path!r}")
    return path


def plan_suite(*, source_sha256: str, model_sha256: str,
               vectors_sha256: str, selection_rule: str, renderer_version: str,
               binding_version: str, repo_revision: str, allowed_prefix: str,
               desired: Sequence[Mapping[str, str]],
               disk_hashes: Mapping[str, str],
               manifest: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    """Return a stable *proposal* with no filesystem writes or oracle content.

    A file is updatable only with a generated ownership record and a current
    on-disk hash matching that record. Missing, unowned, or edited files are
    blocked, and obsolete generated files are retained rather than deleted.
    """
    inputs = {
        "source_sha256": _hash(source_sha256, "source_sha256"),
        "model_sha256": _hash(model_sha256, "model_sha256"),
        "vectors_sha256": _hash(vectors_sha256, "vectors_sha256"),
        "selection_rule": _string(selection_rule, "selection_rule"),
        "renderer_version": _string(renderer_version, "renderer_version"),
        "binding_version": _string(binding_version, "binding_version"),
        "repo_revision": _string(repo_revision, "repo_revision"),
    }
    prefix = _string(allowed_prefix, "allowed_prefix")
    if (not prefix.endswith("/") or prefix.startswith("/") or
            _contains_control(prefix) or
            "\\" in prefix or any(x in ("", ".", "..") for x in prefix[:-1].split("/"))):
        raise ValueError("allowed_prefix must be a normalized relative directory")
    if not isinstance(desired, (list, tuple)) or not isinstance(disk_hashes, Mapping) or not isinstance(manifest, Mapping):
        raise ValueError("desired, disk_hashes and manifest must have the required collection types")

    records: dict[str, dict[str, str]] = {}
    ids: set[str] = set()
    for source in desired:
        if not isinstance(source, Mapping) or set(source) != _ITEM_KEYS:
            raise ValueError("desired entry must contain only generated identity metadata, no oracle")
        record = {key: _string(source[key], key) for key in _ITEM_KEYS if key != "content_sha256"}
        record["content_sha256"] = _hash(source["content_sha256"], "content_sha256")
        path = _path(record["path"], prefix)
        if path in records or record["test_id"] in ids:
            raise ValueError("duplicate generated path or test ID")
        records[path] = record
        ids.add(record["test_id"])

    disk: dict[str, str] = {}
    for key, value in disk_hashes.items():
        path = _path(key, prefix)
        disk[path] = _hash(value, "disk hash")

    existing: dict[str, dict[str, str]] = {}
    manifest_ids: dict[str, str] = {}
    for key, value in manifest.items():
        path = _path(key, prefix)
        if not isinstance(value, Mapping) or set(value) != _MANIFEST_KEYS:
            raise ValueError("manifest entry has unknown or missing provenance fields")
        entry = {name: _string(value[name], name) for name in _MANIFEST_KEYS
                 if name not in {"file_sha256", "source_sha256", "model_sha256", "vectors_sha256"}}
        for name in ("file_sha256", "source_sha256", "model_sha256", "vectors_sha256"):
            entry[name] = _hash(value[name], name)
        if entry["owner"] not in {"generated", "handwritten"}:
            raise ValueError("unknown manifest ownership")
        # Test identity is namespace-wide, even when a record is handwritten.
        # A generated test must never reuse a manual test's existing ID.
        if entry["test_id"] in manifest_ids and manifest_ids[entry["test_id"]] != path:
            raise ValueError("one manifest test ID has multiple locations")
        manifest_ids[entry["test_id"]] = path
        existing[path] = entry

    output: list[dict[str, str]] = []
    for path, record in records.items():
        row = dict(record)
        previous = existing.get(path)
        actual_hash = disk.get(path)
        if record["test_id"] in manifest_ids and manifest_ids[record["test_id"]] != path:
            row.update(action="blocked", reason="test-id-owned-at-another-path")
        elif previous is None and actual_hash is None:
            row["action"] = "create"
        elif previous is None:
            row.update(action="blocked", reason="unowned-file")
        elif (previous["owner"] != "generated" or previous["test_id"] != record["test_id"]):
            row.update(action="blocked", reason="ownership-conflict")
        elif actual_hash is None:
            row.update(action="blocked", reason="recorded-file-missing")
        elif actual_hash != previous["file_sha256"]:
            row.update(action="blocked", reason="recorded-file-modified")
        elif (previous["file_sha256"] == record["content_sha256"] and
              all(previous[k] == inputs[k] for k in (
                  "source_sha256", "model_sha256", "vectors_sha256",
                  "renderer_version", "binding_version"))):
            row["action"] = "unchanged"
        else:
            row["action"] = "update"
        output.append(row)

    for path, previous in existing.items():
        if path not in records:
            action = "retain" if disk.get(path) == previous["file_sha256"] else "blocked"
            output.append({"test_id": previous["test_id"], "path": path,
                           "action": action,
                           **({"reason": "unselected-record-not-intact"} if action == "blocked" else {})})

    output.sort(key=lambda row: (row["path"], row["test_id"]))
    return {"status": "candidate", "inputs": inputs, "entries": output}
