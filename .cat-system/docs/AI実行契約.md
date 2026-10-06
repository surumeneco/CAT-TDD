---
title: CAT×TDD AI実行契約
status: trial
version: '0.7'
---

# CAT×TDD AI実行契約

## 目的と非目的

目標はCATの仕様境界とTDDのRed/Green/Refactorを、AIに開発を委譲できる**継続的な開発環境**へ組み込むこと。機械変換器の対応する題材数を増やすこと、既存WebAppをCATに全面再構築することは目的ではない。具体物（XPlayWebApp等）は、Issueから仕様・テスト・実装・回帰・Git・実動作確認まで**実際に環境を使えるか**の検証対象である。

## 責任分割

| 役割 | 行うこと | 行わないこと |
|---|---|---|
| 人間/規範正本 | Issueとして要求・問題・目的・完了条件を提示し、意味上の選択を確定・承認する | Task/Workへの分解を通常運用の必須作業にしない。コードから意味を自動昇格させない |
| AI（orchestrator/役割Agent） | Issueの整理、`cycle-scope-divider`によるIssue→Task→Work分解、正本取得、候補整理、設計/コード作業、失敗原因の解釈、未決定事項のエスカレーション | 未決定の意味を補完しない。試験未実行や根拠不明を成功として報告しない |
| `cat_flow.py` | Skillルート、ローカルGit差分・変更可能パス、宣言済みコマンド実行、JUnit成績、証拠の失効、引継ぎ情報を扱う。Work Markdownの解析・validationは内部`catlib/work.py`へ委譲する | 意味判断、仕様承認、CI/merge/deployの実行成功判定 |
| `cat-specification-gate/scripts/cat_artifact_lint.py` | CAT Semantic Artifactのfront matter、ID、明示参照の静的検証 | 自然言語Conditionの完全性判定 |
| `cat_package_lint.py` | Agent/Skill定義のfront matterを静的検証 | CAT Artifactの意味・構文検証 |
| `cycle-management/scripts/cat_lifecycle.py` | Issue/Task/Workの配置状態を一意確認し、明示された状態へ安全に移動 | 状態遷移の意味的妥当性・完了判定 |
| `cat_compile_v2.py` | 形式化済みCATサブセットから記号モデル/具体テスト入力を生成し、選択技術のrendererへ委譲 | 全CAT、一般Process合成、自由記述の自動解釈、技術固有rendererの責務 |
| `cat_install.py` | 対象Workの採用技術を使い、選択Skillの`SKILL.md`・`scripts/`・`references/`等を同一単位で非破壊導入 | 技術採用の決定、ユーザAgentの無断上書き |

**重要**: Issue→Task→Workの意味的分解はAI Agentの責務であり、`cat_flow.py`の責務ではない。人間可読な`Work.md`はAIと人間がレビューできる実行契約であって、人間による手作成を前提としない。スクリプトの`passed`は**実行したそのチェックの結果**のみ。`spec-confirmed`、`red-reviewed`、`CI-provider-passed`、`merged`、`deployed`、`real-use-verified`を転用しない。Work manifestに書かれた`confirmed`と`decision_ref`も、リンクの内容・人間の承認権限をスクリプトが検証したことにはならない。

## 最小運用

1. `Lifecycle`の状態フォルダを探索indexとして使う。新規受付は`Issues/New/`を入口とし、AIがIssueの要求・現象・完了条件・対象外・未知事項を整理した後、`cycle-scope-divider`でProcess単位のTaskと独立検証可能な仕様差分のWorkを生成する。人間は通常Task/Workを作成しない。既存の継続作業は`Works/InProgress/`、判断・依存待ちは`Blocked/`を優先し、必要がない限り`Completed/`全件を走査しない。Work生成時にプロジェクト入口と現行正本・Git実状態を取得し、人間可読な[Work Markdown契約](Artifact記法.md)へ整理する。既存コードからの復元はcandidateを原則とする。
2. `python scripts/cat_flow.py validate --work <Work.md>`を実行する。`route --stage <stage>`の結果にある共通Agent/Skillと、宣言技術に合う`tech-*`だけを選ぶ。GitHubホストは前提にしない。
3. 未決定の意味は人間へ差し戻す。`python .cat-system/skills/cat-specification-gate/scripts/cat_artifact_lint.py --files <Process.md> <PI.md> <TCE.md>`で形式を確認し、レビュー後にのみconfirmedへ移す。独立するWorkは続行可。 Processは境界・仕様状態・観測/作用能力、PIは相手Process・方向・Presence、TCEは振る舞い単位を正本に持つ。CommonRule / DomainSpecが必要な意味を自由記述へ逃がさない。
4. 機械可読な範囲では`cat_flow.py compile --kind model|tests --check`を使う。CATの新規意味正本は`semantic_contract: markdown-v2`の人間向け構造・表・限定式とし、JSON ASTはコンパイラ内部IRとしてのみ用いる。TestModelもMarkdownを標準出力とする。未対応の領域・形式はAIが規範からモデルを記述し、同じレビューゲートを受ける。**コンパイラ未対応=作業全体を終了**とはしない。逆に部分モデルの通過で未対応部分の仕様成立を主張しない。
5. テスト生成後は`route --stage test-review`で実装担当とは分離したテスト/oracle審査を行う。TDDでは仕様由来oracleを固定して`cat_flow.py run --id <declared-check> --execute`で実際の試験だけを実行する。RedはJUnitで対象テストの失敗が観測されても、**期待した理由かどうかの判断は別**。Green/回帰は宣言した対象だけの実行成功。既存失敗・関連テスト・実ブラウザ/DBは別境界で確認する。
6. Refactor前は`route --stage refactor-scope`で保存対象と変更可能範囲を固定し、その後に`refactor`を行う。`cat_flow.py git`と`cat_flow.py handoff`で変更可能パス、リポジトリ・証拠・未着手ゲートを取得する。PR/MR・CI提供元の結果・merge/deploy/実操作を個別に確認する。環境が無ければ`not-run`。

Issue / Task / WorkのLifecycle状態は`New / InProgress / Blocked / Completed / Cancelled`の配置フォルダを正本とする。`lifecycle_status`をfront matterへ複製しない。状態変更はIDディレクトリ全体の移動で行い、ID参照は維持する。Gateの`blocked`等は個別工程の判定であり、Lifecycleフォルダの`Blocked`とは別概念である。Workを`Completed`へ移すのは必要なcheck/Gateと受入条件の確認後とし、`reported-complete/unverified-external-evidence`だけでは完了へ移さない。

`run`が実行するのは**Workに明示したコマンド**だけ。`shell=True`を使わず、`--execute`を要求し、さらに`mode: implementation`でなければ実行を拒否する。`mode: shadow`では任意argvを実行しない。Workのコマンドはプロジェクトの承認済みテスト/検査コマンドから作ること。命令自体の安全性や秘密情報の取り扱いはCLIでは保証できない。JUnitレポート/証拠はWork横の`.cat-flow/`に保存するので、機密が含まれる場合はアクセス制御しGitから除外する。

## 必要な能力と失敗時の扱い

- 機械判定できないCATの意味・要件変更: `blocked/semantic-decision-required`、Agentが候補と区別を提示する。
- 機械可読形式に未対応: `unsupported`としてAI作成＋独立レビュー。スクリプトの対応拡張は、実作業中に繰り返す機械作業が判明したときだけ行う。
- ローカルGitワークツリーが無い: `not-run`。APIでのコード取得・ブランチ確認は別途行い、ローカルdiffの実測と混同しない。
- テストfixture/DB/ブラウザ等を用意できない: 実行結果は`not-run`。型チェック/モデルコンパイルをGreenへ昇格させない。
- JUnitで失敗は観測したが根因未審査: `inconclusive`。失敗した事実の機械認識と期待失敗理由の判断を分離する。
- 正本文書とコード/運用状態が相違: 認識差を候補・問題として記録し、どちらかで他方を書き換えない。

## 導入と版管理

GitによるWork隔離と正本文書の参照が前提。`cat_install.py`はデフォルトで差分計画だけ出す。`--apply`で`.github/agents`、採用した`.github/skills`、`.cat-system`に共通実行物を配置する。同名の既存ファイルが異なれば停止し、`--overwrite`は人間がレビュー済みで明示した時だけ使う。外部repoの`main`/`develop`やGitHubを固定しない。インストールはVS Code/Copilot上の起動・自動Skill選択成功を証明しないため別検証が必要。

## 現行実装の実行境界

パッケージ内部で強制できる境界は、現行実装で次のように扱う。

- `git_snapshot`は追加・変更・rename・type change・**削除**を差分対象にする。許可外の削除も`blocked`となる。
- `mode: shadow`では`run --execute`そのものを拒否し、任意argvの「読取専用らしさ」を推測しない。
- `run`後は宣言`input_paths/output_paths`に加えてcwd全体のcontext fingerprintを証拠へ保存する。Git worktreeではHEAD・diff・untracked内容、非Gitではキャッシュ類を除くファイル木をfingerprintし、未宣言ファイルの後続変更も`stale`にする。過大な非Git treeでは証拠化を拒否する。
- Workの`Gates`に意味レビュー、oracleレビュー、Red理由レビュー、PR/MR、CI、merge、deployment、real-useの報告証拠を保持できる。CLIは外部証拠の真正性を自動検証しないため、条件が揃った場合も`overall: reported-complete/unverified-external-evidence`とし、外部再取得を要求する。
- `cat_install.py`は採用Skillのディレクトリ一式をruntime/Copilotへ配置し、未選択の技術Skill・project extensionを入れない。Skill内`scripts/`等も同じ選択境界に従う。書込み前に導入後Markdown参照を検査する。

残る外部境界は、Copilot上のAgentツール制限・Skill自動選択、Drive/Gitホスト/CI等の認証済み外部証拠取得である。これはローカルMarkdownやPythonだけでは強制できないため、対象実行環境でのpilot検証を完了条件として扱う。スクリプトの形式上の成功を、本番操作や外部承認そのものへ昇格させない。

## Artifact表現と内部IR

人間が直接確認・レビューできるSemantic Artifact (Process / PI / TCE / CommonRule / DomainRule / DomainSpec / TestModel)とLifecycle Artifact (Issue / Task / Work等)はMarkdownを標準とする。通常の新規要求では人間がIssueを入力し、Task/WorkはAIが生成する。Semantic ArtifactとWorkの実行情報を同じ意味層へ混在させない。`cat_flow.py`と`cat_compile_v2.py`は実行時に必要な内部object/JSON IRへ正規化してよいが、それを規範正本として保存・手編集しない。旧`markdown-v1`、旧`work.json`、旧`cat-machine` JSONブロックは移行用の互換入力であり、新規Semantic Artifactの標準は`markdown-v2`とする。本文の日本語/英語表記は同じ内部IRへ正規化し、front matterの機械keyだけを安定化する。
