# ChatモードにおけるCAT-TDD運用

更新: 2026-10-31。対象: **Chatモードで実施するソフトウェア開発作業のみ**。VS Code、Codex、Workその他の環境へ本Chat専用の手順を強制しない。CAT-TDDの意味論、4つの独立フロー、決定論的所有権、権限、Gateの正本は `.cat-system/config/routing.json` と関連するスクリプト・契約文書にある。

## 入口とArtifact先行

1. 新しい機能・修正要求ではIssueを整理し、原則としてAIがTask/Workへ分解する。Workの責務と依存関係を定め、`cat_scope_order.py` で順序を機械的に決める。
2. 要件と期待動作が定まったら、**本番ソースを変更する前に必要なCAT Artifact（Process/PI/TCE等）を作成する**。これは規範の確定と同義ではない。AIが作ったDraft/Candidateは、適切な決定根拠と正規の昇格工程なしにはConfirmedにしない。既にConfirmedが存在する場合は再利用する。
3. 確認済み規範仕様がある実装Workでは`spec-implementation`へ明示的にhandoffする。仕様復元`code-to-spec`、振る舞い維持`refactor`、Issue受付`issue-work`は独立したフローであり、すべてのWorkに強制的なTDDを適用しない。

## Chatでの決定論的スクリプト実行

**MCPは必須ではない。** Chat側で利用可能なPython/ターミナル実行機構を確認し、GitHubコネクタ等で取得したCAT-TDDソースと依存ファイル・入力Artifactを許可された作業領域に配置する。実行するスクリプト本体、routing、参照資料は特定のGitリビジョンとハッシュに照合する。GitHub APIでコードを読めることと、Pythonから実行できる配置が済んだことを混同しない。

正規スクリプトを実行するときは、`python .cat-system/scripts/cat_flow.py --help`、`cat_compile_v2.py --help` 等の**現行実体の引数**を確認し、`routing.json` のStageのexecutor、read/write、prohibited、handoff/guardを尊重する。Chat専用プラグインの`runtime/chat_direct.py`のような薄いアダプターで既存スクリプトを起動してもよいが、CATロジックのAIによる模倣・再実装を正規Gateとして扱わない。ローカルに常設開発環境がないことやMCPがないことを、実行不能の根拠として短絡的に扱わない。

## 実装前Gate・テスト生成

規範仕様の承認後、実装前に現行ルーティングに沿って`process-closure`、TestModel生成、`model-conformance`、vectors、Queue、**current項目のみの生成テスト**を機械的に実行する。TestModel、vectors、Queue、生成テストのoracleは対応するcompiler/selector/rendererが所有し、AIが直接加筆して不足を補ってはならない。生成順序は正規契約を優先し、ここでの説明は新しいStageを追加するものではない。

## GitHub・CI・実装

生成テストは許可されたリポジトリと対象ブランチへ配置できる。GitHub書込みの前後にはHEAD・blob SHA・差分・反映を確認する。**実装前に**実際のCIまたは正規のテスト実行器で、期待動作の未実装によるRedを確認する（単なるCI失敗はRedではない）。

GateとRedを通過したcurrent項目に限定して本番コードを変更し、CIによるGreenと要求された回帰テストの証拠を取得する。Queueの状態変更は、正規の状態管理器がテストID・Queueハッシュと新鮮な実行証拠を照合して行う。次のcurrent項目へ進む。最後に`implementation-conformance`と必要なintegrationを**別々に**検証する。Greenは仕様適合性の十分条件ではない。

## 証拠と障害復旧

少なくともWork ID、規範Artifactの参照・版/ハッシュ、使用スクリプト/routingのリビジョン、TestModel・vectors・Queue・生成テストのハッシュ、対象コミットSHA、CI run/checkのID・結果、Gateの生ログと状態を対応づける。入力変更後の証拠は`stale`とする。

スクリプトや実行手段が見つからない場合は、利用可能なChat Python実行機構、取得手順、依存、引数、パス、環境、権限と実エラーを調査・修正して再実行する。実行できないGateは`not-run`/`blocked`と明示し、推論を`passed`の代用にしない。独立して可能なWorkは進め、**最後に残る実ブロッカーだけ**を確認する。必要な権限やユーザーによる規範の決定は勝手に代行しない。

## 参照と責務の境界

- `.cat-system/docs/開発フロー.md`：4独立フロー・handoff
- `.cat-system/docs/AI実行契約.md`：役割・決定論的処理・Gate・guard
- `.cat-system/docs/機械的変換.md`：TestModel、vectors、Queue、テストの機械的導出
- `.cat-system/config/routing.json`：Stage単位の実行契約
- ChatGPT個人用Plugin `cat-tdd-chatgpt`：Chat内でのSkillルーティングと正規スクリプト実行手順

この資料はChat用アダプター契約であり、VS Code版のCAT-TDDを置き換えたり、テスト実行やGitHub Actionsの成功を宣言したりするものではない。
