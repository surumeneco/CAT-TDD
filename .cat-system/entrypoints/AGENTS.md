# CAT-TDD workspace entry (Codex / compatible agents)

This repository is the CAT-TDD **control workspace**, not the product repository. Product repositories are under `Room0/<repo>/`; numbered `Room1/`, `Room2/`, ... contain separate worktrees. Do not modify or commit product content through the CAT-TDD parent Git repository.

Before a software development task, read `.cat-system/docs/AI実行契約.md` and `.cat-system/docs/開発フロー.md`; use the relevant `.cat-system/skills/<skill>/SKILL.md` only when needed. All agents and harnesses use the same `.cat-system/config/routing.json` and `.cat-system/scripts/` runtime.

- Select **exactly one** independent flow from `spec-implementation`, `issue-work`, `code-to-spec`, `refactor` according to input and goal. Switching flows requires an explicit handoff. Do not append refactoring automatically to Green.
- Human feature and bug requests enter as Issues. The scope-divider responsibility decomposes Issue -> Task -> Work; use `cat_scope_order.py` for cycles, dependency ordering, and deepest-ready scope. Do not demand human-authored Task/Work.
- Approved specifications define semantics; existing code and tests are evidence, not automatically approved specifications. Never infer missing normative meaning from a passing test.
- `routing.json` stage permissions, executor, guards and conditional reviewer conditions are authoritative. Run deterministic scripts/providers directly rather than having an LLM emulate them. A reviewer may be invoked on `inconclusive` only, never to override `failed`/`blocked`.
- Do not hand-edit compiler-owned TestModel, test vectors, Queue, executable tests, or execution evidence. Production changes belong only to the explicitly permitted implementation/refactor stage and scope.
- For writable AI stages, use `cat_flow.py handoff` and the corresponding `guard --phase finish` before accepting results or entering the next stage. If the runtime or required evidence is absent, report `not-run`/`blocked`, not `passed`.
- Respect `Lifecycle/`, `Docs/`, `TestModels/`, `Room*/` and `.cat-flow/` Git boundaries. Always scope Git commands to the intended repository/worktree.
- Agent definitions are **role guidance**, not operating-system permission isolation. Use runtime guards and the actual harness approval controls; do not assume that a named agent's tool allowlist is enforced across harnesses.

Do not duplicate the CAT procedure in harness-specific instructions. For provider-specific discovery and installation paths, read `.cat-system/docs/VSCodeマルチエージェント.md`.
