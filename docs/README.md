# ドキュメント一覧

AI News to Discord プロジェクトのドキュメント索引です。

## ドキュメント構成

| ドキュメント | 内容 | 対象読者 |
|---|---|---|
| [design.md](./design.md) | システム設計書 — モジュール設計、データフロー、プロンプト仕様、エラー処理 | 開発者 |
| [architecture.md](./architecture.md) | アーキテクチャ — 構成方針、ジョブ分割、責務分担、非機能要件 | アーキテクト |
| [deployment.md](./deployment.md) | デプロイメントガイド — Secrets設定、初回セットアップ、ローカル実行 | DevOps |

## 読み順ガイド

### 初めてこのプロジェクトに触れる方
1. プロジェクトルートの [../README.md](../README.md) で全体像を把握
2. [deployment.md](./deployment.md) でセットアップ手順を確認
3. 必要に応じて [design.md](./design.md) でモジュール詳細を読む

### 改修を担当する開発者
1. [architecture.md](./architecture.md) で設計思想・ジョブ責務を理解
2. [design.md](./design.md) で各モジュールの詳細仕様とプロンプト設計を確認
3. 該当モジュールを編集 → ローカル実行で動作確認 → PRを作成

### 運用・障害対応
- [deployment.md](./deployment.md) の「トラブルシューティング」を参照
- 失敗ジョブはGitHub Actions UIで再実行(Re-run jobs)可能

## 関連リンク

- [anthropics/claude-code-action 公式ドキュメント](https://github.com/anthropics/claude-code-action)
- [Discord Webhook API リファレンス](https://discord.com/developers/docs/resources/webhook)
- [GitHub Actions ドキュメント](https://docs.github.com/actions)
