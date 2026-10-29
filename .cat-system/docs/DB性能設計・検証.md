---
title: DB性能設計・検証の実践知
role: reusable-database-engineering-guidance
scope: cat-tdd-technology-skills-and-chatgpt-review
status: adopted-guidance-not-normative-project-spec
updated: 2026-10-29
format: markdown
source:
  - https://zenn.dev/koduki/articles/d3e8984f420b370681f9
  - https://www.postgresql.org/docs/current/sql-truncate.html
  - https://www.postgresql.org/docs/18/indexes-multicolumn.html
  - https://www.postgresql.org/docs/current/using-explain.html
cat_tdd_issue: https://github.com/surumeneco/CAT-TDD/issues/2
---

# DB性能設計・検証の実践知

## 目的・位置付け

2026-10-29の利用者の依頼により、記事「データベースを遅くするための８つの方法」から、DBを用いるアプリケーション開発時に再利用すべき判断基準を抽出した。記事の経験則は**検討すべきリスクの発見**に利用し、DB製品・バージョン・設定・クエリ・データ分布・負荷・整合性要件を確認せずに普遍的ルールへ昇格させない。

本書は**ChatGPT向けの技術レビュー知見**であり、個別プロジェクトの規範仕様、CATのTestModel/Queue、実測ログの代替ではない。CAT-TDDに反映する実装作業はIssue #2で管理し、CAT-TDD本体のStage権限・guardに従う。本書だけでPlugin自動適用やテスト成功を主張しない。

## 開発・レビュー時の8観点

### 1. 大量の逐次コミット

- 大量のDMLに対する「1行につき1トランザクション/COMMIT」は、WAL/redo flush、ネットワーク往復、トランザクション管理の負荷を増やし得る。まとめたINSERT、COPY/LOAD、適切なバッチ化を候補にする。
- **バッチ件数を固定しない**。トランザクション長、ロック保持、WAL量、メモリ、エラー復旧、部分失敗、再実行、冪等性を含め、対象ワークロードで計測する。「1000件」「1万件」は規範ではない。
- COMMIT頻度と「インデックスの再構築」は別問題。通常のINSERTで既存インデックス全体を毎回作り直すとは限らず、索引更新・ページ分割・キャッシュ・ログコストなどを区別する。

### 2. 書込み並列化

- ワーカー数の単純な増加がINSERT/UPDATEスループットを向上させるとは限らない。行/索引ページ/ホットキー/トランザクションログ/接続数/ストレージI/Oを競合点として検証する。
- 上限つき並列度、負荷制御、バルクロード/DB側並列DML、キー分散、パーティショニングを比較する。シャーディングはコストの大きい設計変更であり、負荷測定なしに採用しない。

### 3. インデックスの過剰設置

- 索引は検索・ソート・結合に利益をもたらす一方、INSERT/UPDATE/DELETE、ストレージ容量、VACUUM/保守にコストを生む。列ごとに無差別に作らない。
- 実際のWHERE/JOIN/ORDER BY、複合索引の列順、カバリング・部分索引、既存索引との重複、更新頻度を比較する。測定可能なら実行計画、buffers、行数推定と実数を記録する。

### 4. 連番PKとUUID

- 連番IDには索引の局所性や小さいFKといった利点があり、UUIDには分散生成などの利点がある。どちらも万能ではない。B-tree最右端の競合、sequence cache/多重writer、UUID種別・生成方式、索引サイズ、書込順仮定、運用要件を評価する。
- 「連番PKは常に遅い」「UUIDは常に高速」「PK大小が書込順を保証する」を採用しない。イベントの順序が要件なら順序キーと同着時ルールを明示する。

### 5. 低カーディナリティ列と索引

- distinct値の数だけでは有効性を判定できない。条件を満たす行の**選択率**、値の偏り、複合条件、部分索引、テーブル/索引の大きさ、統計、optimizerの判断が重要。
- 「低カーディナリティだから禁止」は誤りになり得る。また通常のSQLの`WHERE a=... AND b=...`で述語の記載順を変えても、optimizerが評価・アクセス順を独立に決めることが多い。**SQL句の記載順**と**複合索引の列順**を混同しない。

### 6. ホットスポット更新と集計

- 多数の書込みが同じ集計行にUPDATEを集中させると、直列化やロック競合が起き得る。イベント/明細を追記して集計する設計、物化ビュー、非同期集計、時間窓ごとの部分集計などを候補にする。
- ただしUPDATE自体を禁止しない。業務上の即時整合性、遅延許容値、二重書込み、再計算/復旧手段、読み取り負荷とのトレードオフで選ぶ。Materialized Viewも自動で常時非同期とは限らず製品やrefresh方式を確認する。

### 7. 巨大・多列のテーブル

- 無秩序な非正規化/肥大化した行は、I/O、キャッシュ効率、更新衝突、schema変更、NULL/大きな可変長データの管理に影響する。
- ただし行指向ストレージが常に全列を物理読み込みするとの単純化は避け、ページ・TOAST等の格納方式、インデックスonly scan、SELECT列、アクセスパターンで評価する。正規化による結合コストも比較し、設計上の根拠を残す。

### 8. クライアント側JOIN/フィルタ

- RDBから大量の行を転送してアプリ側でJOIN/フィルタ/集計すると、ネットワーク帯域・シリアライズ・メモリ・往復回数を浪費し得る。原則として条件・結合・集計・必要列選択・ページングをDB側で検討する。
- ORMのN+1、過大フェッチ、取得後のページング・ソートによる仕様不整合にも注意。小さく不変に近い参照マスタのキャッシュなど、転送と更新負荷の実測で優位な例外は認める。

## データ削除・マイグレーションの注意

`TRUNCATE`を`DELETE`の汎用的な高速代替とはしない。DB製品・バージョン、トランザクション、ロック、外部キー、トリガ、レプリケーション、監査、復旧の要求を確認する。**PostgreSQLのTRUNCATEはトランザクション中ならロールバック可能**だがMVCC上の注意点がある。既存データを使う変更は事前のbackfill/互換性/ロールバック経路を定義し、本番データに破壊的検証を行わない。

## CAT-TDDへの適用契約

1. **対象判定**: WorkでDBに関するSQL、Schema、Migration、データアクセス、性能、同時実行、障害復旧を扱うとき、技術構成で確認したDB専用Skill（PostgreSQL/MySQL/SQL Server/Oracle）を選ぶ。採用製品が不明なまま推測で決めない。
2. **規範と証拠の区別**: 性能SLO、同時実行要件、整合性・分離性、最大データ量、復旧許容、DB制約は承認済みCAT/プロジェクト仕様で定義する。記事の例示値を自動で規範にしない。
3. **Work分解**: インデックスやトランザクションの調査・ベンチマークは独立の`analysis`/`verification` Work、実際の設計/実装変更は別の`implementation` Workとして扱う。仕様変更を要する場合は正規の仕様・承認フローへ戻す。
4. **観測方法**: 対象DBと版、schema、index、統計、接続プール、transaction isolation、実データと同質の分布、データ量、warm/cold cache、並列度を明記する。実行計画（PostgreSQL例: `EXPLAIN (ANALYZE, BUFFERS)`）、実行時間、p95/p99、throughput、ロック待ち、WAL/redo、CPU、I/O、転送量を必要十分な粒度で採取する。`EXPLAIN ANALYZE`はSQLを実行するため、変更系はロールバック可能性やテストDBを確認する。
5. **比較実験**: baseline対candidateを同じ負荷条件で比較し、測定回数・ばらつき・回帰・ロック競合を記録。改善があっても正しさ・整合性・再実行・復旧を損なってはならない。
6. **CAT固有Gate**: 性能測定の成功は`process-closure`、`model-conformance`、Red/Green、`implementation-conformance`、CI/実機の成功とは独立。測定結果から未承認のTestModel・Queue・テストoracleを直接書き換えない。guardを実行できない環境では`not-run`と記録する。

## 最小レビュー質問

- データはどこで絞り込み・結合・集計し、何行/何バイトを転送しているか？
- 読取りと書込みの実際の比率、テーブルの行数とデータ分布、成長速度は？
- COMMITと接続、バッチ/並列度はどの単位か？失敗時の再開・冪等性は？
- どの行・キー・索引ページが競合し得るか？
- この索引はどのクエリを支え、書込みコストとの実測上の差は？
- schema/migrationの安全性、既存データ、復旧手順は？
- ベンチマーク環境と本番条件はどこまで同質で、何が未測定か？

## 更新・追跡

- 原文: https://zenn.dev/koduki/articles/d3e8984f420b370681f9 （2020-11-15公開、2022-12-22更新）
- CAT-TDDへの統合Issue: https://github.com/surumeneco/CAT-TDD/issues/2
- PostgreSQL参考: https://www.postgresql.org/docs/current/sql-truncate.html 、https://www.postgresql.org/docs/18/indexes-multicolumn.html 、https://www.postgresql.org/docs/current/using-explain.html
- 今後の改善では、DB各社の公式ドキュメント、対象製品・版・実測値を優先し、本書の記述を無条件にコピーしない。
