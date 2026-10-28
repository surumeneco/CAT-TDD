# CAT-TDD for Claude Code

Read `AGENTS.md` first; it is the shared CAT-TDD workspace contract. Then use `.cat-system/docs/AI実行契約.md`, `.cat-system/docs/開発フロー.md`, `.cat-system/config/routing.json`, and only the relevant Skill in `.cat-system/skills/`.

Use `.claude/skills/` and `.claude/agents/` when installed. These are discovery adapters for Claude Code; the CAT procedures and write permissions remain in the common runtime, not in Claude-specific files. Do not assume subagents enforce filesystem isolation. When files have not been installed or execution cannot be verified, report that condition rather than treating missing tests/guards as passed.
