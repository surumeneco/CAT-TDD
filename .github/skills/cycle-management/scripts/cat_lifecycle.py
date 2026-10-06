#!/usr/bin/env python3
"""Safe mechanical Lifecycle locator/mover for Issue, Task and Work directories.

This tool never decides whether a lifecycle transition is semantically justified.
The caller must explicitly name the destination state.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

STATES = ("New", "InProgress", "Blocked", "Completed", "Cancelled")
KINDS = {"issue": "Issues", "task": "Tasks", "work": "Works"}
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class Blocked(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise Blocked(message)


def _base(root: Path, kind: str) -> Path:
    require(kind in KINDS, f"unsupported kind: {kind}")
    root = root.resolve()
    base = root / KINDS[kind]
    require(base.is_dir(), f"lifecycle kind directory missing: {base}")
    return base


def locate(root: Path, kind: str, identifier: str) -> dict:
    require(bool(ID.fullmatch(identifier)), f"invalid lifecycle id: {identifier!r}")
    base = _base(root, kind)
    matches = []
    for state in STATES:
        path = base / state / identifier
        if path.exists() or path.is_symlink():
            require(not path.is_symlink(), f"refusing symlink lifecycle entry: {path}")
            require(path.is_dir(), f"lifecycle entry is not a directory: {path}")
            matches.append((state, path))
    require(matches, f"lifecycle entry not found: {kind}:{identifier}")
    require(len(matches) == 1,
            f"lifecycle id exists in multiple states: {kind}:{identifier}: {[s for s, _ in matches]}")
    state, path = matches[0]
    return {"kind": kind, "id": identifier, "state": state, "path": str(path)}


def move(root: Path, kind: str, identifier: str, to_state: str, from_state: str | None = None) -> dict:
    require(to_state in STATES, f"unsupported destination state: {to_state}")
    current = locate(root, kind, identifier)
    if from_state is not None:
        require(from_state in STATES, f"unsupported source state: {from_state}")
        require(current["state"] == from_state,
                f"source state mismatch: expected {from_state}, actual {current['state']}")
    require(current["state"] != to_state, f"already in lifecycle state: {to_state}")

    source = Path(current["path"])
    dest_parent = _base(root, kind) / to_state
    require(dest_parent.is_dir(), f"destination state directory missing: {dest_parent}")
    dest = dest_parent / identifier
    require(not dest.exists() and not dest.is_symlink(), f"destination already exists: {dest}")
    os.replace(source, dest)
    return {
        "kind": kind,
        "id": identifier,
        "from": current["state"],
        "to": to_state,
        "path": str(dest),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("locate", "move"):
        q = sub.add_parser(name)
        q.add_argument("--lifecycle-root", type=Path, default=Path("Lifecycle"))
        q.add_argument("--kind", choices=sorted(KINDS), required=True)
        q.add_argument("--id", required=True)
        if name == "move":
            q.add_argument("--to", choices=STATES, required=True)
            q.add_argument("--from-state", choices=STATES)
    args = p.parse_args(argv)
    try:
        if args.command == "locate":
            result = locate(args.lifecycle_root, args.kind, args.id)
        else:
            result = move(args.lifecycle_root, args.kind, args.id, args.to, args.from_state)
        print(json.dumps({"status": "passed", **result}, ensure_ascii=False, indent=2))
        return 0
    except (Blocked, OSError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
