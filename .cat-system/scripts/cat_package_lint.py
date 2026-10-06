#!/usr/bin/env python3
"""Deterministic contract lint for CAT package Agent and Skill definitions."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from catlib.markdown import parse_frontmatter

SKILL = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

def skill_errors(root):
    errors = []
    if not root.exists():
        return [f"{root}: path missing"]
    for path in sorted(root.glob("*/SKILL.md")):
        try:
            f = parse_frontmatter(path)
            name = f.get("name", "")
            if name != path.parent.name or not SKILL.fullmatch(name) or len(name) > 64:
                errors.append(f"{path}: skill name mismatch or invalid: '{name}'")
            if not f.get("description") or len(f["description"]) > 1024:
                errors.append(f"{path}: missing/overlong description")
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"{path}: {exc}")
    return errors


def agent_errors(root):
    errors = []
    if not root.exists():
        return [f"{root}: path missing"]
    for path in sorted(root.glob("*.agent.md")):
        try:
            f = parse_frontmatter(path)
            if f.get("name") != path.name.removesuffix(".agent.md"):
                errors.append(f"{path}: agent name mismatch")
            if not f.get("description"):
                errors.append(f"{path}: description missing")
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"{path}: {exc}")
    return errors



def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills", type=Path)
    parser.add_argument("--agents", type=Path)
    args = parser.parse_args(argv)
    if not any([args.skills, args.agents]):
        parser.error("specify at least one of --skills/--agents")
    errors=[]
    if args.skills: errors.extend(skill_errors(args.skills))
    if args.agents: errors.extend(agent_errors(args.agents))
    if errors:
        print("FAIL: package contract lint", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("PASS: Agent/Skill package contract lint")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
