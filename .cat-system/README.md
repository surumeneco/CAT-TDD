---
title: CAT実用エージェント体系
status: trial
version: '1.0'
---

# CAT実用エージェント体系

CAT理論をVS Code / GitHub Copilot上の開発作業へ接続するための定義原本。**Gitを前提とするが、GitHubでのホスティングを前提としない。** 理論正本は`forGPT/SystemDevelopment/00_理論・構想/設計理論.md`。自然言語Conditionの網羅性、一般的なProcess合成、テストの完全性を機械証明できるとは扱わない。

| 原本 | 開発ワークスペースへの配置 | 管轄 |
| --- | --- | --- |
| `agents/*.agent.md` | `.github/agents/` | 役割・責任・禁止・成果物境界 |
| `skills/{cat-*,cycle-*,tdd-*,refactor-*}/` | `.github/skills/<skill>/`と`.cat-system/skills/<skill>/` | CAT/Cycle/TDD/Refactorの技術非依存手順と、そのSkillだけが使う`references/`・`scripts/`等 |
| `skills/<technology-skill>/` | `config/routing.json`で対象技術に登録されたものだけ`.github/skills/<skill>/`と`.cat-system/skills/<skill>/`へ配置 | 言語・フレームワーク・DB・テスト基盤固有の手順と補助コード。自作は原則`tech-*`、外部Skillは上流名を保持できる |
| `extensions/<project>-adapter/` | 明示選択時だけ`.github/skills/`と`.cat-system/extensions/`へ配置 | プロジェクト固有Skillと参照マップ。共通coreから分離 |
| `optional-skills/*/` | 明示的に診断・補助機能を使う場合だけ個別導入 | 通常Workに必須でない補助Skill。`cat_install.py`の共通Skill自動配布対象外 |
| `docs/*.md` | `.cat-system/docs/` | 人間が読む工程、記法、正本・技術Skillの選択契約 |
| `config/*` | `.cat-system/config/` | routing等の機械設定。人間向け正本を置かない |
| `scripts/` | `.cat-system/scripts/` | 複数Skillから共有するランタイム、Lifecycle実行、コンパイル、非破壊導入。Skill固有コードは置かない |
| `tests/` | 導入先へは配布しない | 実運用パッケージ自身の回帰テストと汎用fixture |


## パッケージ内部の責務境界

`docs/`は人間が読み書きする契約、`config/`は機械が読む設定、トップレベル`scripts/`は複数Skillから共有する実行コード、各`skills/<name>/scripts/`はそのSkillだけが使う実行コード、`tests/`はパッケージ保守用の自己テストとする。JSONを使用すること自体ではなく、**人間向け正本と機械内部表現を同じ配置・同じ編集責務に置くこと**を避ける。

`tests/`と未選択`extensions/`は`.cat-system`へ配布しない。実運用環境へ必要なのは`README.md / docs / config / scripts / agents / 選択済みskills / optional-skills`であり、自己テストのfixtureを実プロジェクトの仕様・検証生成物へ依存させない。

## 目標: CAT×TDDを組み込んだAI開発環境

**対象は「開発を実行できる環境」であり、特定プロダクトのCAT変換プロジェクトではない。** CAT-TDDは単一の一本道ではなく、`spec-implementation / issue-work / code-to-spec / refactor`を独立flowとして扱う。通常の新規要求では人間がIssueを入力し、`cycle-scope-divider`がIssue→Task(Process)→Workへ意味的に分解し、依存graphのcycle/depth/ready算出はScriptへ委譲する。決定論的なmodel/Queue/test生成、Gate validation、Git inspection、evidence集約はPythonが担当し、AIは意味判断とproduction implementation等に限定する。

入口: [AI実行契約](docs/AI実行契約.md)、[開発フロー](docs/開発フロー.md)、[Issue / Task / Workを含むArtifact Markdown形式](docs/Artifact記法.md)。

| スクリプト | AIが呼ぶ機能 | 非対象 |
|---|---|---|
| `scripts/cat_flow.py` | flow-aware routing、permissions、Git read、write guard、command evidence、conformance、structured handoff | 規範意味の決定・外部provider結果の創作 |
| `scripts/cat_compile_v2.py` | confirmed CAT source→TestModel、TestModel+vectors→TDD Queue、current item→技術renderer | unsupported意味のAI補完 |
| `scripts/cat_queue.py` | Queueの`pending/current/done/blocked`遷移。currentは最大1件 | Scenario / Oracle等の意味記述 |
| `scripts/cat_scope_order.py` | Work parent/depends-onのcycle、depth、ready最深scope算出 | 依存関係そのものの意味決定 |
| `scripts/cat_install.py` | 採用済みSkillのディレクトリ一式と共通Agent/ツールを非破壊導入 | 技術採用の決定・無断上書き |
| `scripts/cat_package_lint.py` | Agent/Skill定義のfront matterを静的検証 | CAT Semantic Artifactの意味・構文検証 |
| `skills/cat-specification-gate/scripts/cat_artifact_lint.py` | CAT Artifactのfront matter、ID、明示参照を静的検証 | 自然言語Conditionの意味証明 |
| `skills/cat-artifacts/scripts/cat_artifact_scaffold.py` | Semantic Artifactの空構造と必須メタデータを決定論的に生成 | Process/PI/TCE等の意味内容の推測 |
| `skills/cycle-management/scripts/cat_lifecycle.py` | Issue/Task/Workの現在配置を一意確認し、明示されたLifecycle状態へディレクトリごと安全に移動 | 遷移の意味的妥当性・完了判定 |
| `skills/tech-vitest/scripts/cat_vitest_renderer.py` | 汎用ケースをVitestソースへ描画する内部renderer | CATモデル・具体値の決定 |

具体的手順・エラー/ゲートの扱いは[AI実行契約](docs/AI実行契約.md)。モデルの`Draft`は規範oracleではなく、生成コードの成功は実Red/Greenではない。

### 機械変換器は開発環境の一機能

[変換契約](docs/機械的変換.md)は、新規標準`semantic_contract: markdown-v2`の人間可読なSemantic Artifactを扱い、日本語/英語の表記差を同一の型付きIRへ正規化する。旧`markdown-v1`/`machine-only`は互換入力に限る。現行の変換器によって**CAT理論全体の決定論的変換ができるとは宣言しない**。production pathで機械対応範囲外の意味は`BLOCKED / unsupported`とし、AIがTestModelやtest oracleを補完しない。Compiler / schema / renderer改善Work、または仕様上定義された領域別検証へ分離する。

## 技術の採用とSkill選択

採用技術、対象component、版、制約、テストコマンドは**プロジェクトの現行文書**に記載する。全プロジェクトへ同名の文書を強制せず、入口から既存の技術構成正本を辿る。技術Skillはその技術での作業方法であり、技術を採用する権限を持たない。技術Skillかどうかの機械的な判定は名前のprefixではなく`config/routing.json`の`technology_skills`登録を正とする。

対象Workの技術と実行境界に合致するSkillだけを選ぶ。現行catalogueは次を保持する。

- 言語: `tech-typescript`、`tech-csharp`、`tech-java`、`tech-python`。
- UI / Web: `tech-vue`、`tech-react`、`tech-nextjs`、`tech-aspnet-core`、`tech-spring-boot`、`tech-fastapi`。
- DB: `tech-postgresql`、`tech-mysql`、`tech-sqlserver`、`tech-oracle-db`。
- Test: `tech-vitest`、`tech-playwright`、`tech-xunit`、`tech-junit`、`tech-pytest`。
- Container: Docker公式`docker-project-foundations`、`docker-build-strategies`、`docker-compose-patterns`、`docker-destructive-guardrails`。Dockerは1つの採用技術から複数Skillへrouteする。

採用しない技術のSkillは配布先へ入れない。未収録技術は技術構成文書に基づいて独立Skillを追加し、CAT共通Skillへ技術固有の方法を混入させない。Docker外部Skillの固定版・出典は[外部Skill](docs/外部Skill.md)に記録する。

詳細な選択規則、GitとGitHubの分離、Adapterの設置判断は[プロジェクト適用](docs/プロジェクト適用.md)を参照。CAT適合性の診断指数が必要な場合は `optional-skills/cat-conformance-review/SKILL.md` を明示的に使用する。

## 権威の分離

- 人間による最新の明示指示と指定された規範的仕様を、要求された振る舞いの基準とする。ソースコード・テスト・CI・ログは現実の証拠であって、コードだけを仕様に昇格させない。
- CAT正本とテストモデルからテストの期待結果を定める。実装結果をoracleにしない。レビュー者の分離だけで独立性が保証されるとも扱わない。
- `spec-confirmed`、`tests-green`、`ci-passed`、`merged`、`deployed`、`real-use-verified`は独立状態。
- 静的なプロジェクト情報は文書、プロジェクト固有の繰り返し手順のみ`<project>-adapter`に置く。XPlayServer固有情報は`extensions/xplayserver-adapter/`へ隔離し、`--adapter xplayserver-adapter`を明示したWorkだけへ導入する。

## 配置時の最小手順

1. 起点と目的から4 flowのいずれかを選ぶ。Issueなら`cycle-scope-divider`がTask/Workへ分解し、`cat_scope_order.py`がreadyな最深scopeを選ぶ。既存Workの再開では`flow / work_kind / parent / depends_on`を使用する。
2. 共通`agents/`と共通Skill、`routing.json`で採用技術に対応する技術Skillだけを配置し、プロジェクト手続きがある場合だけ`extensions/<project>-adapter`を明示選択して配置する。`optional-skills/`は通常導入に含めず、対象の診断・補助作業を明示した場合だけ個別に使用する。
3. 指示ファイルは入口と正本への参照に留め、同じルールを繰り返さない。GitHub以外のremoteでも、Copilotの`.github/agents`/`.github/skills`はワークスペースの設定パスとして使用できる。
4. `routing.json`のexecutorを直接使い、Script / Compiler / Validatorで確定できるstageではAgentを起動しない。Validatorが`inconclusive`の時だけconditional reviewerを使う。Agent書込みstageでは可能な限りpre/post guardを行い、Markdownの禁止文だけを強制権限制御とみなさない。

## 参照資料

- [CAT設計理論](https://drive.google.com/file/d/1yCwl46msHLvDSMObrHRBL7_RLV3H9ZJt/view)
- [XPlayServer作業入口](https://drive.google.com/file/d/1oyuQJfvjho_RsWIrlPI_XCmLlc4Df0dl/view)
- [VS Code Custom Agents](https://code.visualstudio.com/docs/agent-customization/custom-agents)
- [VS Code Agent Skills](https://code.visualstudio.com/docs/agent-customization/agent-skills)
