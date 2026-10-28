---
name: cat-tdd-entry
description: >
  Use for software development in this CAT-TDD workspace: feature implementation,
  bug fixes, Issue maintenance, code-to-spec reverse engineering, tests,
  and behavior-preserving refactors. Also applies to 開発・実装・機能追加・修正・バグ対応・
  テスト・既存コードからの仕様化・リファクタリング. Select one of four independent flows
  and use the shared CAT-TDD runtime; do not invent test or validation evidence.
---

# CAT-TDD development entry

CAT-TDD is configured once for GitHub Copilot, OpenAI Codex and Claude Code in VS Code. This Skill is only a routing entry, **not a second procedural authority**.

1. Read the root `AGENTS.md`, and `CLAUDE.md` if running Claude Code. Then read `.cat-system/docs/AI実行契約.md` and the appropriate part of `.cat-system/docs/開発フロー.md`. Load task-specific Skills only as required.
2. Use the task's source evidence to choose **one** flow: confirmed Process/PI/TCE → `spec-implementation`; new feature/bug/maintenance request → `issue-work`; observed code/tests → `code-to-spec`; behavior-preserving structural edit → `refactor`. Never force all four into a single flow.
3. Work metadata, dependencies, allowed paths and current state are read from actual artifacts; let `.cat-system/scripts/cat_scope_order.py` select the deepest-ready scope.
4. Use `.cat-system/config/routing.json` as the stage-specific routing, executor, read/write and authority source. Prefer scripts/compilers/validators and actual external providers to AI for deterministic tasks. Only invoke a reviewer on a validator result of `inconclusive`.
5. For AI-writable stages, require the prescribed `cat_flow.py handoff` and finishing guard. Do not modify compiler-owned TestModel, Queue, test/oracle or execution evidence. Do not infer normative meaning from existing code or tests.
6. If a runtime gate cannot run or a source cannot be accessed, report `not-run` or `blocked`; never claim `passed`. Keep repo/worktree Git boundaries and stage write scopes explicit.

The three VS Code harnesses share the same CAT procedure and do not become independent process authorities merely because each has its own Skill discovery directory. For placement and bootstrap, see `.cat-system/docs/VSCodeマルチエージェント.md`.
