"""Deterministic Test Suite Manifest and provenance checks for spec-test-sync."""
from __future__ import annotations
import hashlib
import json
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
