---
title: XPlayServer導入接続マップ
status: reference-only
version: '0.2'
---

# XPlayServer導入接続マップ

この文書は共通CAT体系をXPlayServerへ接続する**参照マップ**であり、XPlayServerの新しい仕様正本ではない。技術の採否・バージョン・環境・ブランチ運用に関して本文に値を複製しない。必ず下記の現行文書・実際のrepoを取得する。

| 目的 | 正本・証拠の所在 | 扱い |
| --- | --- | --- |
| 作業入口、最新の文書マップ、Git運用 | [XPlayServer `00_必読.md`](https://drive.google.com/file/d/1oyuQJfvjho_RsWIrlPI_XCmLlc4Df0dl/view) | 最初に読む正本。指示に沿って対象文書を選ぶ |
| WebApp技術構成 | `forGPT/XPlayServer/WebApp/技術構成.md` | 採用技術、構成、テスト系を決める現行文書 |
| WebApp開発・運用 | `forGPT/XPlayServer/WebApp/開発・運用.md` | 起動・Docker等の環境制約を確認 |
| DiscordBot技術・環境 | `forGPT/XPlayServer/DiscordBot/実装制約.md` および同領域の入口 | 現行制約を確認 |
| Minecraft技術・運用 | `forGPT/XPlayServer/Minecraft/` の入口で指定された文書 | 対象変更に応じて確認 |
| WebApp×Botの契約 | `forGPT/XPlayServer/連携/` の対象文書 | 相互PIや非同期処理の規範 |
| ソース・テストの現状 | `00_必読.md`で指定される現行repoの実際のGit branch/commit、`TESTING.md`など | 実装証拠。現行仕様と混同しない |

採用する`tech-*` Skillは、上記の技術構成正本・対象Work・現行repoから決定する。たとえばVueを使用するUIのWorkなら`tech-vue`、Vitestで実行するテストなら`tech-vitest`を検討するが、このマップを根拠に全Skillを常時起動しない。過去の検証生成物や実例は、技術採用・仕様決定の根拠として参照しない。

Google Driveの文書を変更した場合の確認方法や複数repo間の作業接続は同じextension内の`SKILL.md`が担当する。GitHubの利用、branch名、テストコマンド等の静的ルールを同Skill内に再掲しない。
