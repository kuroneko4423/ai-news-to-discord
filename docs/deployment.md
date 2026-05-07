# AI News to Discord — デプロイメントガイド

## 1. 前提条件

- GitHub アカウント（リポジトリを作成できること）
- Discord サーバーの管理者権限（Webhook を作成できること）
- Anthropic API のアカウント（API キーを発行できること）
- (ローカル動作確認時のみ) Python 3.11 以上

## 2. 初回セットアップ

### 2.1 リポジトリの準備

```bash
git clone <your-repository-url>
cd <repo-name>
```

新規プロジェクトとして始める場合:

```bash
git init
git add .
git commit -m "Initial commit: AI News to Discord"
git remote add origin git@github.com:<owner>/<repo>.git
git branch -M main
git push -u origin main
```

### 2.2 Discord Webhook URL の取得

1. Discord で投稿先のチャンネルを開く
2. チャンネル名横の歯車アイコン（チャンネル編集）→「連携サービス」
3. 「ウェブフック」→「新しいウェブフック」
4. 名前・アイコン・投稿先チャンネルを設定
5. 「ウェブフックURLをコピー」してメモする

### 2.3 Claude Code OAuth トークンの取得

本プロジェクトは Claude Pro / Max プランの**サブスクリプション利用枠**で動作します。APIキーではなく OAuth トークンを使うため、ローカルマシンで以下を実行してトークンを発行してください。

```bash
# 1. Claude Code を最新版にインストール / 更新
npm install -g @anthropic-ai/claude-code

# 2. Pro / Max プランのアカウントでログイン (まだの場合)
claude /login
# → ブラウザで Claude.ai にログイン → 認可

# 3. 1年間有効な OAuth トークンを発行
claude setup-token
# → ターミナルにトークンが表示される (sk-ant-oat01-... で始まる文字列)
```

**重要**:
- 表示されたトークンは1度しか出力されないので、すぐにコピーしてください
- このコマンド自体はトークンをローカルに保存しません
- 環境変数 `ANTHROPIC_API_KEY` がOSに設定されていると優先されてしまうため、サブスク認証を使う場合は `unset ANTHROPIC_API_KEY` で外しておくこと

> **個人利用前提**: Anthropicの利用規約上、Pro / Max プランの OAuth 認証は「個人による通常利用」が想定されています。本プロジェクトの想定利用ケース(自分専用のDiscordチャンネルへの投稿)はこの範囲内です。複数人が利用するチャンネルへ拡張する場合は、APIキー方式 (`ANTHROPIC_API_KEY`) または Team / Enterprise プランへの移行を検討してください。

### 2.4 GitHub Secrets の設定

リポジトリの **Settings → Secrets and variables → Actions → New repository secret** から以下2件を登録します。

| Secret 名 | 値 |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | `sk-ant-oat01-...` (2.3 で取得したトークン) |
| `DISCORD_WEBHOOK_URL` | `https://discord.com/api/webhooks/...` (2.2 で取得したURL) |

### 2.5 動作確認（手動実行）

1. GitHubリポジトリの **Actions** タブを開く
2. 左側で「Post AI News to Discord」を選択
3. 右上の「Run workflow」→ ブランチを選んで「Run workflow」
4. ワークフローが起動 → 3ジョブが順次実行される
5. 完了後、Discord チャンネルに要約が投稿されていることを確認

## 3. ローカル実行（任意）

開発・調整時にローカルで全フローを試したい場合の手順です。

```bash
# Python仮想環境
python -m venv venv
source venv/bin/activate     # Windows: venv\Scripts\activate

# 依存パッケージ
pip install -r requirements.txt

# 環境変数
cp .env.example .env
# .env を編集
#   DISCORD_WEBHOOK_URL=...
#   ANTHROPIC_API_KEY=...   ← ローカル実行時のみ必要(Anthropic SDK 直接呼び出しのため)

# 全フロー実行
python main.py
```

> **ローカルでの認証について**: `claude-code-action` は GitHub Actions ランナー専用のため、ローカル実行時は Anthropic Python SDK で代替します。SDK は OAuth トークンではなく APIキー (`sk-ant-api03-...`) を要求するため、ローカル動作確認時のみ Anthropic Console で APIキーを発行してください。本番(GitHub Actions)では引き続き OAuth トークンが使われます。

個別モジュールの単体テスト:

```bash
# 取得のみ
python news_fetcher.py     # → news.json が生成される

# 要約は本番では Claude Code Action が担うため、ローカルでは main.py 経由で確認

# 投稿のみ(事前に summary.md を用意)
echo "テスト投稿" > summary.md
python discord_notifier.py
```

## 4. スケジュール変更

`.github/workflows/post-news.yml` の `schedule.cron` を編集します。cron は **UTC** で記述する点に注意。

| 用途 | cron 式 |
|---|---|
| 毎日 09:00 JST (現状) | `0 0 * * *` |
| 平日のみ 09:00 JST | `0 0 * * 1-5` |
| 6時間ごと | `0 */6 * * *` |
| 毎週月曜 09:00 JST | `0 0 * * 1` |

> GitHub Actions の `schedule` は混雑状況により遅延することがあります（数分〜数十分）。厳密な時刻保証が必要なら外部スケジューラ + `repository_dispatch` を検討してください。

## 5. トラブルシューティング

### 5.1 ワークフロー全体が起動しない
- Actions が無効化されていないか: **Settings → Actions → General → Allow all actions**
- スケジュール実行は最終コミットから60日経過すると停止する → 何らかのコミットを行うか、手動実行する

### 5.2 `fetch-news` ジョブが失敗
- ログでフィード別取得数を確認
- 特定フィードがダウンしている場合、`news_fetcher.py` の `RSS_FEEDS` から一時的に除外
- `feedparser` のパースエラーは標準エラーに警告として出力される（ジョブは継続）

### 5.3 `summarize` ジョブが失敗
| 症状 | 原因 / 対処 |
|---|---|
| `claude_code_oauth_token is required` | Secret `CLAUDE_CODE_OAUTH_TOKEN` 未登録 |
| `401 Unauthorized` | OAuthトークンが期限切れ(1年)または失効 → ローカルで `claude setup-token` を再実行してSecret更新 |
| `Subscription required` | Pro / Max プランが解約されている、または支払い問題 |
| `usage limit exceeded` | サブスクの利用枠を使い切り → 翌月のリセット待ちか、APIキー方式に一時切替 |
| `summary.md was not generated or is empty` | プロンプトの調整(Write指示が伝わっていない可能性)、または `claude_args` の `--allowedTools` から `Write` が抜けていないか確認 |

### 5.4 `notify-discord` ジョブが失敗
| HTTPステータス | 原因 / 対処 |
|---|---|
| 401 / 403 | Webhook URL が無効/権限なし |
| 404 | Webhook が削除済み → 再作成して Secret を更新 |
| 429 | レート制限 → 自動リトライされるが、頻発する場合は分割数を見直す |
| 5xx | Discord 側の一時障害 → 手動再実行 |

### 5.5 Discord に投稿されるが文字化け
- 本実装では `requests.post(json=payload)` を使い UTF-8 を自動指定しているため、通常は発生しない
- もし発生したら `discord_notifier.py` の `_post` メソッドのリクエストヘッダを確認

## 6. コスト試算（参考）

毎日1回・1記事15件・平均要約2,500文字想定の場合:

| 項目 | 概算 |
|---|---|
| GitHub Actions 利用時間 | 約3〜4分/日（無料枠2,000分/月で十分カバー） |
| Claude 利用枠 | **既存の Pro / Max サブスクの利用枠から消費** (1日1回・短いプロンプトなので利用枠への影響は軽微) |
| Discord Webhook | 無料 |

> サブスクリプション利用枠で動作するため、**追加課金は発生しません**。利用枠に余裕がない月は APIキー方式 (`ANTHROPIC_API_KEY`) に一時切替する選択肢もあります。

## 7. トークンのローテーション

OAuthトークンの有効期限は **1年間** です。失効するとジョブが突然失敗するため、定期的なローテーションを推奨します。

| 推奨 | 内容 |
|---|---|
| カレンダー登録 | トークン発行から11ヶ月後に再発行リマインダ |
| 再発行手順 | ローカルで `claude setup-token` を再実行 → 新トークンをSecret `CLAUDE_CODE_OAUTH_TOKEN` で上書き |
| サブスク解約時 | トークンも同時に無効化される(切替忘れに注意) |

## 8. アンインストール

1. GitHub Actions の Settings からワークフローを無効化、またはファイル削除
2. Discord 側で Webhook を削除
3. リポジトリのSecrets `CLAUDE_CODE_OAUTH_TOKEN` を削除
4. （リポジトリも不要であれば）リポジトリを削除

> OAuthトークン自体は Anthropic 側で個別失効する手段が用意されていません。アカウント側で `/logout` するか、サブスクを解約することで失効します。
