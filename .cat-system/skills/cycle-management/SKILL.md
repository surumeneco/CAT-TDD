---
name: cycle-management
description: "Turn development Issues into Process-scoped Tasks and human-readable Work Markdown; manage Git branches and repository-independent integration evidence, handoffs and resumption. Use for CAT lifecycle and Git coordination with any Git remote host."
---

# Cycle: intake → integration

1. プロジェクト入口から仕様正本・技術制約・Git運用規則を確認し、対象repoの`git status`、base commit、branch、remoteを実測する。
2. 人間から受け付けたIssueの要求、現象、観測可能な完了条件、対象外、未知事項をAIが整理する。人間にTask/Workへの分解を要求しない。
3. `cycle-scope-divider`がProcessごとにTask、独立検証可能な仕様差ごとにWorkを生成する。跨ぐrepoは一つの意味的Workにrepo別の変更・検証状態を付与する。
4. `Work.md`に変更対象、保持対象、規範URL、base revision、依存、担当を記録し、外部/意味ゲートは`Gates`表へ証拠参照付きで記録する。
5. 正本化と必要な再取得を確認した後に、プロジェクトのbranch規則に従って作業branchを作る。
6. git commit/push、レビュー、CI、merge、deployを個別の証拠として扱う。利用不能なら`not-run`と理由を残す。
7. 再開時はGit実状態と必要な外部証拠を再取得し、引継ぎメモだけを完了証拠にしない。
8. 不可逆なGit操作、仕様正本の意味変更、merge/deployはプロジェクトの承認・実行権限に従う。

## 定型処理のCLI委譲

AIがIssue→Task→Workを分解して`Work.md`を作成したら、`python scripts/cat_flow.py validate --work <Work.md>`、`route --stage <stage>`、`git --work <Work.md>`を使用する。Lifecycle状態の配置変更は、移動先をAI/人間が明示した上で`python .cat-system/skills/cycle-management/scripts/cat_lifecycle.py move --kind work --id <id> --to <state>`を使い、AIが都度`mv`コマンドを組み立てない。`cat_flow.py`はMarkdownを内部`cat-work/v1`へ正規化して処理し、旧`work.json`は互換入力としてのみ扱う。`status/handoff`で証拠の有効性・未完了ゲートを再取得する。`reported-complete/unverified-external-evidence`は外部証拠の再取得前の最終完了を意味しない。

詳細は`.cat-system/docs/Artifact記法.md`と`.cat-system/docs/AI実行契約.md`。
