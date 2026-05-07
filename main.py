#!/usr/bin/env python3
"""
ローカル実行用エントリポイント

本番(GitHub Actions)では以下の3ジョブで実行されます:
  1. fetch-news    : news_fetcher.py が news.json を生成
  2. summarize     : claude-code-action@v1 が news.json を読んで summary.json を生成
  3. notify-discord: discord_notifier.py が summary.json を Discord に Embed 投稿

ローカルでも全フローを通したいケース(動作確認用)のため、
要約ステップは Anthropic API を直接呼ぶ簡易実装でフォールバックします。
出力スキーマは .github/workflows/post-news.yml と揃えてあります。
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from news_fetcher import main as fetch_news_main
from discord_notifier import DiscordNotifier


SUMMARY_PROMPT_TEMPLATE = """\
あなたはAIニュースを日本のビジネス読者向けに要約する編集者です。
以下のJSONはRSSから取得した直近のAI関連ニュース一覧です。

{news_json}

このJSONを読み、Discord Embed投稿用の構造化要約データを作成してください。

# 出力スキーマ (厳守)
{{
  "date": "{today}",
  "count": {count},
  "items": [
    {{
      "category": "general" | "research" | "vendor",
      "title": "<元記事のタイトルそのまま>",
      "url": "<元記事のURLそのまま>",
      "source": "<出典名>",
      "region": "jp" | "global",
      "summary": "<日本語1〜2文の要約>"
    }}
  ]
}}

# 注意
- 出力は**純粋なJSONのみ**。前置き・後書き・コードブロックフェンスは禁止
- title / url / source / region / category は news.json の値を改変せずそのまま使う
- news.json に無い情報を創作しない
- 各 summary は1〜2文・日本語・150文字以内を目安
- items の並び順は news.json の順序に従う
"""


def _extract_json(text: str) -> str:
    """LLM応答から最初のJSONオブジェクトを抜き出す (```json フェンス対策)。"""
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)
    obj_match = re.search(r"\{.*\}", text, re.DOTALL)
    if obj_match:
        return obj_match.group(0)
    return text


def run_local_summarize(news_json_path: str, summary_path: str) -> bool:
    """
    ローカル動作確認用: Anthropic APIを直接呼んで要約JSONを生成。
    本番(GitHub Actions)では claude-code-action@v1 がこのステップを担う。
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        print(
            "❌ anthropic パッケージが必要です: pip install anthropic",
            file=sys.stderr,
        )
        return False

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY が設定されていません", file=sys.stderr)
        return False

    news_json = Path(news_json_path).read_text(encoding="utf-8")
    news_data = json.loads(news_json)

    prompt = SUMMARY_PROMPT_TEMPLATE.format(
        news_json=news_json,
        today=datetime.now().strftime("%Y-%m-%d"),
        count=news_data.get("count", 0),
    )

    print("🧠 Anthropic APIで要約JSONを生成中...")
    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw_text = "".join(
        block.text for block in message.content if hasattr(block, "text")
    )

    json_str = _extract_json(raw_text)
    try:
        summary = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"❌ Claude応答のJSONパースに失敗: {e}", file=sys.stderr)
        print("--- 応答抜粋 ---", file=sys.stderr)
        print(raw_text[:500], file=sys.stderr)
        return False

    if not isinstance(summary.get("items"), list) or not summary["items"]:
        print("❌ 要約JSONに items がありません", file=sys.stderr)
        return False

    Path(summary_path).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✅ {summary_path} に要約を保存しました ({len(summary['items'])}件)")
    return True


def main() -> int:
    """ローカルで fetch → summarize → Discord投稿 を一気通貫で実行する。"""
    print("=" * 80)
    print("🤖 AI News to Discord (Local Runner)")
    print("=" * 80)

    load_dotenv()

    news_path = "news.json"
    summary_path = "summary.json"

    # Step 1: ニュース取得
    print("\n[1/3] ニュース取得")
    print("-" * 80)
    os.environ.setdefault("NEWS_OUTPUT_PATH", news_path)
    if fetch_news_main() != 0:
        return 1

    # Step 2: 要約 (ローカルではAnthropic API直接呼び出し)
    print("\n[2/3] ニュース要約 (ローカル: Anthropic API直接呼び出し)")
    print("-" * 80)
    if not run_local_summarize(news_path, summary_path):
        return 1

    # Step 3: Discord投稿
    print("\n[3/3] Discord投稿")
    print("-" * 80)
    try:
        notifier = DiscordNotifier()
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    if not summary.get("items"):
        print("⚠️  要約が空のため投稿をスキップ")
        return 0

    success = notifier.send_summary_json(summary)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
