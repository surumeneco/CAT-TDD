---
title: CAT実用エージェント体系
status: trial
version: '0.9'
---

# CAT実用エージェント体系

CAT理論をVS Code / GitHub Copilot上の開発作業へ接続するための定義原本。**Gitを前提とするが、GitHubでのホスティングを前提としない。** 理論正本は`forGPT/SystemDevelopment/00_理論・構想/設計理論.md`。自然言語Conditionの網羅性、一般的なProcess合成、テストの完全性を機械証明できるとは扱わない。

| 原本 | 開発ワークスペースへの配置 | 管轄 |
| --- | --- | --- |
| `agents/*.agent.md` | `.github/agents/` | 役割・責任・禁止・成果物境界 |
| `skills/{cat-*,cycle-*,tdd-*,refactor-*}/SKILL.md` | `.github/skills/` | CAT/Cycle/TDD/Refactorの技術非依存の手順 |
| `skills/<technology-skill>/SKILL.md` | `config/routing.json`で対象技術に登録されたものだけ配置 | 言語・フレームワーク・DB・テスト基盤固有の処理。自作は原則`tech-*`、外部Skillは上流名を保持できる |
| `extensions/<project>-adapter/` | 明示選択時だけ`.github/skills/`と`.cat-system/extensions/`へ配置 | プロジェクト固有Skillと参照マップ。共通coreから分離 |
| `optional-skills/*/SKILL.md` | 明示的に診断・補助機能を使う場合だけ個別導入 | 通常Workに必須でない補助Skill。`cat_install.py`の共通Skill自動配布対象外 |
| `docs/*.md` | `.cat-system/docs/` | 人間が読む工程、記法、正本・技術Skillの選択契約 |
| `config/*` | `.cat-system/config/` | routing等の機械設定。人間向け正本を置かない |
| `scripts/*.py` | `.cat-system/scripts/` | Work実行/証拠管理、静的lint、条件付きコンパイル、非破壊導入 |
| `tests/` | 導入先へは配布しない | 実運用パッケージ自身の回帰テストと汎用fixture |


## パッケージ内部の責務境界

`docs/`は人間が読み書きする契約、`config/`は機械が読む設定、`scripts/`は実行コード、`tests/`はパッケージ保守用の自己テストとする。JSONを使用すること自体ではなく、**人間向け正本と機械内部表現を同じ配置・同じ編集責務に置くこと**を避ける。

`tests/`と未選択`extensions/`は`.cat-system`へ配布しない。実運用環境へ必要なのは`README.md / docs / config / scripts / agents / 選択済みskills / optional-skills`であり、自己テストのfixtureを実プロジェクトの仕様・検証生成物へ依存させない。

## 目標: CAT×TDDを組み込んだAI開発環境

**対象は「開発を実行できる環境」であり、特定プロダクトのCAT変換プロジェクトではない。** 通常の新規要求では人間がIssueを入力し、Orchestratorが`cycle-scope-divider`へ委譲してIssue→Task(Process)→Work(独立検証可能な仕様差)へ分解する。Task/Workの手作成を人間の必須作業としない。その後、CATの仕様根拠・テストモデル・TDD Red/Green/Refactor・Git・CI・実動作確認を段階別に扱う。機械で実行できる部分をPythonスクリプトへ移し、AIは判断を要する工程と実装を担当する。Work単位で再開でき、別のプロジェクト・Gitホストでも使えることを目指す。

入口: [AI実行契約](docs/AI実行契約.md)、[開発フロー](docs/開発フロー.md)、[Issue / Task / Workを含むArtifact Markdown形式](docs/Artifact記法.md)。

| スクリプト | AIが呼ぶ機能 | 非対象 |
|---|---|---|
| `scripts/cat_flow.py` | Work validation、Agent/Skill route、Git差分と変更許可、コマンド実行/証拠、古い証拠の検出、handoff | 意味の承認・本番結果の創作 |
| `scripts/cat_artifact_lint.py` | 指定ファイルのfront matter、IDと参照検証 | 自然言語の意味証明 |
| `scripts/cat_compile_v2.py` | 機械変換可能なCAT Artifactから記号的TestModel・Vitest生成 | CAT全体の意味保存・実環境接続 |
| `scripts/cat_install.py` | 採用済み技術のみのSkillと共通Agent/ツールを非破壊導入 | 技術採用の決定・無断上書き |

具体的手順・エラー/ゲートの扱いは[AI実行契約](docs/AI実行契約.md)。モデルの`Draft`は規範oracleではなく、生成コードの成功は実Red/Greenではない。

### 機械変換器は開発環境の一機能

[変換契約](docs/機械的変換.md)は、新規標準`semantic_contract: markdown-v2`の人間可読なSemantic Artifactを扱い、日本語/英語の表記差を同一の型付きIRへ正規化する。旧`markdown-v1`/`machine-only`は互換入力に限る。現行の変換器によって**CAT理論全体の決定論的変換ができるとは宣言しない**。機械対応範囲外のWorkは、承認済み仕様を根拠にAIがモデル・テストを起草し、独立ゲートを通す。変換器の対応数は環境全体の完成度ではない。

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

1. 新規要求では人間のIssueを入口とし、AIが`cycle-scope-divider`でTask/Workへ分解する。既存Workの再開ではそのWorkを入口とする。その後、入口文書から現行の技術構成・仕様正本・Git運用の正本を確認し、実際のGit remote/branchを照合する。XPlayServerの場合は現行の`00_必読.md`を先に読む。
2. 共通`agents/`と共通Skill、`routing.json`で採用技術に対応する技術Skillだけを配置し、プロジェクト手続きがある場合だけ`extensions/<project>-adapter`を明示選択して配置する。`optional-skills/`は通常導入に含めず、対象の診断・補助作業を明示した場合だけ個別に使用する。
3. 指示ファイルは入口と正本への参照に留め、同じルールを繰り返さない。GitHub以外のremoteでも、Copilotの`.github/agents`/`.github/skills`はワークスペースの設定パスとして使用できる。
4. `cat_flow.py`を用いてWork Markdown→内部manifest正規化→静的検査→CATの意味確認→モデル→TDD→Git/CI/merge/deployを個別に管理する。Skill自動選択・外部agent委譲・権限制御は実際のCopilot環境で検証する。Markdownの禁止文だけをOS/ホストの強制権限制御とみなさない。

## 参照資料

- [CAT設計理論](https://drive.google.com/file/d/1yCwl46msHLvDSMObrHRBL7_RLV3H9ZJt/view)
- [XPlayServer作業入口](https://drive.google.com/file/d/1oyuQJfvjho_RsWIrlPI_XCmLlc4Df0dl/view)
- [VS Code Custom Agents](https://code.visualstudio.com/docs/agent-customization/custom-agents)
- [VS Code Agent Skills](https://code.visualstudio.com/docs/agent-customization/agent-skills)
