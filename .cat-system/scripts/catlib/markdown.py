#!/usr/bin/env python3
"""Shared parser for the intentionally small CAT Markdown front-matter subset."""
from __future__ import annotations

import json
import re
from pathlib import Path

def _scalar(value):
    value = value.strip()
    if value.startswith("["):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"inline lists must use JSON-compatible scalar syntax: {exc}") from exc
    if len(value) >= 2 and value.startswith(("\"", "'")) and value.endswith(value[0]):
        return value[1:-1]
    return value


def parse_frontmatter(path):
    raw = path.read_text(encoding="utf-8-sig")
    if not raw.startswith("---\n"):
        raise ValueError("missing YAML front matter at first line")
    end = raw.find("\n---\n", 4)
    if end < 0:
        raise ValueError("front matter closing delimiter missing")
    lines = raw[4:end].splitlines()
    fields = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*?)\s*$", line)
        if not match:
            raise ValueError(f"unsupported front matter line: {line[:80]}")
        key, value = match.groups()
        if key in fields:
            raise ValueError(f"duplicate field: {key}")
        if value:
            fields[key] = _scalar(value)
            i += 1
            continue
        items = []
        i += 1
        while i < len(lines):
            child = lines[i]
            if not child.strip() or child.lstrip().startswith("#"):
                i += 1
                continue
            item = re.match(r"^\s{2,}-\s+(.+?)\s*$", child)
            if not item:
                break
            parsed = _scalar(item.group(1))
            if isinstance(parsed, list):
                raise ValueError(f"{key}: nested lists are unsupported")
            items.append(parsed)
            i += 1
        fields[key] = items
    return fields

