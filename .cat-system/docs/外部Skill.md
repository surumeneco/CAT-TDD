---
title: 外部Skill固定版
status: active
version: '0.2'
---

# 外部Skill

外部提供SkillをCAT-TDDの技術Skill poolへ取り込む場合、上流の識別子を可能な限り保持し、出典・固定版・commit・ライセンスを本書へ記録する。技術Skillとしての選択権限は`config/routing.json`にあり、外部Skill自身が技術採用を決定しない。

## Docker Skills

- upstream: `docker/skills`
- pinned release: `v0.3.1`
- commit: `8afc2c6ef4e0ec2ea8e4ba024d0b884ea930b926`
- license: Apache-2.0
- imported entrypoints: `docker-project-foundations`、`docker-build-strategies`、`docker-compose-patterns`、`docker-destructive-guardrails`
- excluded product-specific skills: Docker Agent系、Docker Sandboxes系

CAT-TDDの現行Skill配布契約は**選択したSkillディレクトリ全体**を`.github/skills/<skill>/`と`.cat-system/skills/<skill>/`へ配置する。上記4 Skillは現時点では`v0.3.1`の`SKILL.md`のみを取り込んでいるが、同一releaseから`references/`・`scripts/`・`checks/`等を追加した場合もInstallerはそのまま配布する。上流補助物を追加する際は、固定release/commitを変えず出典とライセンスを維持し、必要なものだけを取り込む。
