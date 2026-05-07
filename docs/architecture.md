# AI News to Discord — アーキテクチャ

## 1. アーキテクチャ方針

### 1.1 設計原則
- **疎結合**: 各ジョブは GitHub Actions のアーティファクトでのみ通信。前段の実装言語や内部構造に依存しない。
- **責務単一**: 取得 / 要約 / 投稿を別ジョブに分離。それぞれ独立して再実行・差し替え可能。
- **要約はLLM任せ**: 要約フォーマットはプロンプトで定義し、Pythonコードに埋め込まない。出力形式の変更はワークフロー編集だけで完結する。
- **Secrets最小化**: 各ジョブは必要なSecretsだけを参照。`fetch-news` はSecretsを使わない。

### 1.2 ジョブ責務分担

| ジョブ | 主言語 | 主入力 | 主出力 | Secrets |
|---|---|---|---|---|
| `fetch-news` | Python | RSS URL一覧 (定数) | `news.json` (artifact) | なし |
| `summarize` | (Claude Code Action) | `news.json` | `summary.md` (artifact) | `ANTHROPIC_API_KEY` |
| `notify-discord` | Python | `summary.md` | Discord メッセージ | `DISCORD_WEBHOOK_URL` |

### 1.3 なぜ Claude Code Action か
- LangChain依存とPython側のLLM呼び出しコードを撤廃でき、要約ロジックがプロンプトに集約される
- 要約品質改善のためのイテレーションがワークフローYAML編集だけで可能
- ファイル操作ツール (`Read`/`Write`) を許可することで、Claudeが直接ファイル成果物を生成できる
- `--max-turns` で実行時間とコストの上限を明示できる

## 2. 全体構成図

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          GitHub Actions Runner                          │
│                                                                          │
│   ┌────────────────┐   artifact   ┌─────────────────┐  artifact         │
│   │ fetch-news     │ ───────────► │ summarize       │ ──────┐           │
│   │ Python         │  news.json   │ claude-code-    │       │           │
│   │ feedparser     │              │ action@v1       │       │           │
│   └────────────────┘              └─────────────────┘       ▼           │
│            ▲                                ▲       ┌─────────────────┐ │
│            │                                │       │ notify-discord  │ │
│            │                                │       │ Python          │ │
│            │                                │       │ requests        │ │
│            │                                │       └─────────────────┘ │
└────────────┼────────────────────────────────┼───────────────┼───────────┘
             │                                │               │
             ▼                                ▼               ▼
    ┌────────────────┐               ┌────────────────┐  ┌────────────┐
    │ 7 RSS feeds    │               │ Anthropic API  │  │ Discord    │
    │ (国内外)        │               │ (Claude Sonnet)│  │ Webhook    │
    └────────────────┘               └────────────────┘  └────────────┘
```

## 3. データ受け渡し

### アーティファクト方式
`actions/upload-artifact@v4` と `actions/download-artifact@v4` を使い、ジョブ間でファイルを受け渡す。

利点:
- ジョブが別ランナーで動作してもよい(並列化や分散の余地)
- 失敗時のデバッグ用に成果物を7日間保持
- ジョブ間の境界が明確化される

代替案として `outputs` を介した文字列受け渡しも検討したが、要約のような長文(数KB)には不向きなため不採用。

## 4. 非機能要件

| 項目 | 目標 | 実現手段 |
|---|---|---|
| 実行時間 | < 5分 | per-job軽量化、`--max-turns 10` 制限 |
| コスト | 1日あたり数〜十数円 | Sonnetモデル + 入力JSONを最小化 |
| 可用性 | 失敗時に手動再実行可能 | `workflow_dispatch` トリガー併設 |
| 観測性 | 失敗原因が即特定可能 | ジョブ別ログ + アーティファクト保持 |
| セキュリティ | Secrets漏洩防止 | GitHub Secrets / `allowed_mentions` 制御 |
| 冪等性 | 同日複数実行で問題なし | RSSは時系列、Discord投稿は新規メッセージとして処理 |

## 5. セキュリティ設計

### 5.1 認証情報
- `ANTHROPIC_API_KEY` / `DISCORD_WEBHOOK_URL` は **GitHub リポジトリ Secrets** で管理
- ローカル実行時は `.env` を使用し、`.gitignore` でコミット防止
- ログにSecretsが出力されないよう、Pythonコードでは値を直接 `print` しない

### 5.2 メンション誤爆防止
Discord投稿時に `allowed_mentions: {parse: []}` を指定し、要約本文中に `@everyone` 等が混入しても通知発火しないようにしている。

### 5.3 プロンプトインジェクション対策
RSS取得元にはWeb上の任意テキストが含まれる可能性がある。プロンプトでは「JSONに無い情報を創作しない」「タイトル・URLを改変しない」を明示。`--max-turns 10` で暴走時のコスト/時間を上限化。

## 6. 拡張シナリオ

| シナリオ | 必要な変更 |
|---|---|
| Slack にも投稿したい | `slack_notifier.py` を作成 → Job 3 を分岐(matrix or 並列ジョブ追加) |
| カテゴリごとに別チャンネルへ投稿 | summarize 段階でカテゴリ別 `summary_xxx.md` を出力 → Job 3 を matrix 化 |
| 取得期間を指定 | `news_fetcher.py` で `published` を解析し、フィルタを追加 |
| 過去要約とのdedupe | KVストア(GitHub Gist / Issue) に過去URLを記録し、`fetch-news` で除外 |
| AWS Bedrock で要約 | `claude-code-action` の Bedrock 認証モードに切り替え(API key ではなく OIDC) |
