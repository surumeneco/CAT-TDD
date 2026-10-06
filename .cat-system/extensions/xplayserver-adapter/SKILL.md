---
name: xplayserver-adapter
description: "Run XPlayServer-specific CAT handoff and Drive readback procedures across its code repositories and authoritative documentation. Use only for work explicitly scoped to XPlayServer; read its mandatory entrypoint before the connection map."
---

# XPlayServer project adapter

共通Skillに追加する、XPlayServer固有の作業手順のみを定める。最初に[XPlayServer `00_必読.md`](https://drive.google.com/file/d/1oyuQJfvjho_RsWIrlPI_XCmLlc4Df0dl/view)を取得する。その後、[導入接続マップ](https://drive.google.com/file/d/1RaVvgmufMYsZvDhZfJase-P_j6bzL1Ng/view)を参照し、対象正本・実装証拠への参照を解決する。実際のGit運用、技術採用、テスト方法はその現行文書とrepoから確認し、このSkillの記述で置き換えない。

1. 作業入口に従って今回の対象Process/Workと必要な領域文書を抽出し、規範と現行コードの証拠を別々に記録する。
2. WebApp・Bot・Minecraft等を跨ぐWorkは、対象repoごとの実装・連携境界・検証・統合状態を一つのWorkへ対応付ける。相手側の仕様や障害時の振る舞いを推測しない。
3. 仕様変更が必要な場合は現行の規範文書を先に改訂し、**Google Driveから再取得**して内容と配置を確認してから実装を進める。旧snapshotを再取得の代わりにしない。
4. 対象技術に応じた`tech-*`を[技術Skill選択契約](https://drive.google.com/file/d/1cBLt5I7KYSqUxme_JNMfx-TawKvwMX5x/view)に従って選ぶ。過去のXPlayServerのテスト・PR事例を仕様決定根拠へ自動昇格しない。
5. repoごとのGit状態、レビュー、CI、統合、本番反映、実動作確認をそれぞれ記録し、全対象repoの証拠が揃う前にWork全体の完了を宣言しない。

このSkillは技術スタックやGitHub APIを固定しない。XPlayServerの静的事実は接続先文書、再利用可能な技術手順は各`tech-*`を正とする。

## CAT×TDD環境pilot

このAdapterはWebApp全機能のCAT化を要求しない。Workは`.cat-system/docs/AI実行契約.md`に従い、プロジェクト入口・対象WebApp正本・Bot連携正本・実装証拠を別項目で固定して`cat_flow.py`を呼ぶ。既存文書の構築予定記載と現実の稼働を機械が同一視せず、実環境は別途確認する。XPlayServerの意味変更をする場合は`00_必読.md`の設計確定→Drive更新→再取得→実装を省略しない。
