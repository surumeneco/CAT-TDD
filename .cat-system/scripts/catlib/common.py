#!/usr/bin/env python3
"""Shared deterministic helpers for CAT runtime scripts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


class Blocked(Exception):
    pass


def require(ok, msg):
    if not ok:
        raise Blocked(msg)


def json_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise Blocked(f"{path}: invalid JSON: {exc}") from exc
