---
title: VS Code 三種のCoding AgentへのCAT-TDD適用
status: trial
version: '1.0'
---

# VS CodeのCopilot・Codex・Claude CodeでCAT-TDDを使う

## 正本の分離

CAT-TDDの意味・工程・責任・許可・実行証拠の正本は、利用するモデルやVS Code拡張ではなく、共通の`.cat-system/docs/`、`.cat-system/config/routing.json`、`.cat-system/scripts/`、`.cat-system/skills/`に置く。Harnessごとの設定は**入口と探索パスのadapter**であり、新しいCAT理論・独立したQueue・別種のテストoracleを作らない。

| Harness | 常時入口 | Skill探索パス | 役割定義の入口 |
| --- | --- | --- | --- |
| GitHub Copilot for VS Code | `.github/copilot-instructions.md` / `AGENTS.md` | `.github/skills/<name>/SKILL.md` | `.github/agents/<name>.agent.md` |
| Codex for VS Code | `AGENTS.md` | `.agents/skills/<name>/SKILL.md` (VS Code統合では`.github/skills`も対応) | VS Code統合の`.github/agents/<name>.agent.md`は利用可能だがtools定義を権限境界とみなさない |
| Claude Code for VS Code | `CLAUDE.md` | `.claude/skills/<name>/SKILL.md` | `.claude/agents/<name>.md` |

`AGENTS.md`は共通契約への入口であり、`CLAUDE.md`とCopilot用instructionsはこの共通契約を参照する。Claude Codeは専用の`CLAUDE.md`を入口とするため、`AGENTS.md`が自動読込されると仮定せず、明示参照する。

## 導入

CAT-TDDのパッケージインストーラは、最初のWorkが存在しない段階では`--bootstrap`で共通入口・共通Skill・Agentを配置する。Work確定後はその`technologies`に対応する技術Skillだけを追加する。未採用技術、未選択Adapterは配布しない。共通Skillsは3種類の探索パスへ複製**配置**するが、編集元は`.cat-system/skills/`の一つだけとする。配置コピーを独立正本として修正しない。

```bash
# 初回: 共通入口を計画し、問題なければ適用する
python .cat-system/scripts/cat_install.py --project-root . --bootstrap
python .cat-system/scripts/cat_install.py --project-root . --bootstrap --apply

# Work確定後: そのWorkで採用した技術Skillを追加する
python .cat-system/scripts/cat_install.py --work Lifecycle/Works/InProgress/<work-id>/Work.md --project-root .
python .cat-system/scripts/cat_install.py --work Lifecycle/Works/InProgress/<work-id>/Work.md --project-root . --apply
```

初回`--bootstrap`では技術Skillを勝手に選択しない。`--bootstrap`と`--work`は排他である。テンプレートをcloneしただけではCodex/Claudeの入口が全て作られたことを意味しないため、最初にbootstrapを実行する。

既定`--harness all`で3種を用意する。特定環境に絞る場合は`--harness copilot`、`--harness codex`、`--harness claude`を使用する。作業時の認証・権限は各Harnessと実行環境に依存する。

- Copilot: `.github/copilot-instructions.md`、共通Agents、選択Skillsを配置。
- Codex: `AGENTS.md`、`.agents/skills/`を配置。VS CodeのCodex向けAgent参照用に`.github/agents/`も配置。
- Claude: `CLAUDE.md`から`AGENTS.md`へ参照し、`.claude/skills/`と`.claude/agents/`へ配置する。
- すべて: `.cat-system/`にScripts/Config/Docs/選択Skillを配置する。実行コマンドと出力契約は共通。

インストーラはplan-onlyが既定で、`--apply`なしで書き込まない。既存ファイルと内容が違う場合は`conflict`で停止する。`--overwrite`は利用者による明示的な変更権限がある場合だけ使う。配置済みAgentやSkillで権限を表現しても、ファイルシステムの書込み制限を強制するわけではない。

## CAT-TDDの共通実行境界

1. 起点から`spec-implementation` / `issue-work` / `code-to-spec` / `refactor`の独立Flowを一つ選ぶ。自動的に全Flowを直列化しない。
2. Issue起点はAIがIssue→Task→Workへ分解し、Scope依存関係の閉路と最深ready判定は`cat_scope_order.py`を使う。
3. 各stageは`routing.json`のexecutor/permissionsに従う。決定論的Scriptで結果が得られる箇所にAI agentを追加起動しない。
4. AIが書き込むstageは`cat_flow.py handoff`および`guard --phase finish`で前後の範囲検証を行う。Reviewはvalidatorが`inconclusive`の場合に限る。
5. TDDのTestModel・Queue・現在のテスト・証拠は指定のcompiler/state manager/providerが所有する。AIが手で埋めたり、別Harnessのテスト結果を実測として再利用したりしない。
6. Flow/stageを跨ぐ際はWork ID、source revision、Work scope、current Queue、evidence refs、guard結果を引き継ぐ。Harnessが替わっても同一Workを無断で同時実行しない。

## 静的検証と実機検証の区別

インストーラの静的検査では、適合する各ディレクトリに参照を含む完全なSkillツリーが存在すること、未選択技術が配布されないこと、既存設定が上書きされないことを確認する。Python unit testsの範囲は`tests/test_cat_install.py`を参照。

次は**各Harnessで別に実機確認する必要がある**: instructionの自動発見、Skillの関連タスクでの選択、Agent役割の発見、Pythonコマンドの実行許可、guardとtest/CIの実測結果。Skillが存在することと自動採用されることは別。CopilotやCodexのcustom agent metadataは実ファイルへの書込禁止を保証しない。Claude Codeのsubagentでも実際のpermission mode・tool restrictionsを確認する。

VS CodeではAgent Customizationsで各Harnessを選択し、設定が検出されるか確認する。CopilotのAgent Debug Logsも有用。ただしClaude Code/Codexについては各拡張の実際のログと実行履歴を検証する。実施前の実機結果は`not-run`とする。

参照: [VS Code instructions](https://code.visualstudio.com/docs/agent-customization/custom-instructions)、[VS Code Skills](https://code.visualstudio.com/docs/agent-customization/agent-skills)、[VS Code agent customization guide](https://code.visualstudio.com/docs/agents/guides/customize-copilot-guide)、[Claude Code Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)。
