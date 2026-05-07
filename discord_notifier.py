"""
Discord通知モジュール

Discord Incoming Webhook経由で、Claude が生成した
要約JSON (summary.json) を Embed 形式で投稿します。

入力JSONスキーマ:
{
  "date": "2026-05-07",
  "count": 12,
  "items": [
    {
      "category": "general" | "research" | "vendor",
      "title": "...",
      "url": "https://...",
      "source": "ITmedia AI+",
      "region": "jp" | "global",
      "summary": "1〜2文の日本語要約"
    },
    ...
  ]
}
"""
import json
import os
import sys
import time
from typing import List, Optional

import requests


# カテゴリ別カラー (Discord Embed用 10進数値)
CATEGORY_COLORS = {
    "general": 0x3498DB,   # blue
    "research": 0x9B59B6,  # purple
    "vendor": 0x2ECC71,    # green
}
DEFAULT_COLOR = 0x95A5A6   # gray (フォールバック)

# Discord Embedの仕様上限
MAX_EMBEDS_PER_MESSAGE = 10
MAX_TITLE_LEN = 256
MAX_DESCRIPTION_LEN = 4096
MAX_AUTHOR_NAME_LEN = 256
MAX_FOOTER_TEXT_LEN = 2048
MAX_TOTAL_CHARS_PER_MESSAGE = 6000


def _truncate(text: str, max_len: int) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def build_embed(item: dict, today: Optional[str] = None) -> dict:
    """1記事をDiscord Embedに変換。"""
    category = item.get("category", "general")
    region = item.get("region", "")
    source = item.get("source", "")

    footer_parts = [category]
    if region:
        footer_parts.append("国内" if region == "jp" else "海外")
    if today:
        footer_parts.append(today)
    footer_text = " · ".join(footer_parts)

    embed: dict = {
        "color": CATEGORY_COLORS.get(category, DEFAULT_COLOR),
        "title": _truncate(item.get("title", ""), MAX_TITLE_LEN),
        "description": _truncate(item.get("summary", ""), MAX_DESCRIPTION_LEN),
        "footer": {"text": _truncate(footer_text, MAX_FOOTER_TEXT_LEN)},
    }
    url = item.get("url", "")
    if url:
        embed["url"] = url
    if source:
        embed["author"] = {"name": _truncate(source, MAX_AUTHOR_NAME_LEN)}
    return embed


def _embed_char_count(embed: dict) -> int:
    """1embedの文字数 (title + description + author.name + footer.text)。"""
    total = 0
    total += len(embed.get("title", ""))
    total += len(embed.get("description", ""))
    total += len(embed.get("author", {}).get("name", ""))
    total += len(embed.get("footer", {}).get("text", ""))
    return total


def batch_embeds(embeds: List[dict]) -> List[List[dict]]:
    """
    Discordの「1メッセージあたり10 embed / 6000文字」制約に合わせて分割。
    """
    batches: List[List[dict]] = []
    current: List[dict] = []
    current_chars = 0
    for embed in embeds:
        ec = _embed_char_count(embed)
        if (
            len(current) >= MAX_EMBEDS_PER_MESSAGE
            or current_chars + ec > MAX_TOTAL_CHARS_PER_MESSAGE
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(embed)
        current_chars += ec
    if current:
        batches.append(current)
    return batches


class DiscordNotifier:
    """Discord WebhookにEmbedメッセージを送信するクラス"""

    REQUEST_TIMEOUT_SEC = 15
    RETRY_COUNT = 3

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        if not self.webhook_url:
            raise ValueError(
                "Discord Webhook URL is required. "
                "Set DISCORD_WEBHOOK_URL environment variable."
            )

    def _post(self, payload: dict) -> bool:
        """1メッセージをPOST。リトライ付き。"""
        for attempt in range(1, self.RETRY_COUNT + 1):
            try:
                response = requests.post(
                    self.webhook_url,
                    json=payload,
                    timeout=self.REQUEST_TIMEOUT_SEC,
                )
                if response.status_code == 429:
                    retry_after = float(
                        response.json().get("retry_after", 1.0)
                    )
                    print(
                        f"⏳ Rate limited. Retrying after {retry_after}s "
                        f"(attempt {attempt}/{self.RETRY_COUNT})"
                    )
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()
                return True

            except requests.exceptions.RequestException as e:
                print(
                    f"❌ Discord send error (attempt {attempt}/{self.RETRY_COUNT}): {e}",
                    file=sys.stderr,
                )
                if attempt < self.RETRY_COUNT:
                    time.sleep(2 ** attempt)
        return False

    def send_summary_json(
        self,
        summary: dict,
        username: str = "AI News Bot",
    ) -> bool:
        """
        summary.json の内容をDiscordへEmbed形式で投稿。

        Args:
            summary: summary.jsonをパースしたdict
            username: Webhook表示ユーザ名

        Returns:
            すべてのメッセージが成功したらTrue
        """
        date = summary.get("date", "")
        count = summary.get("count", len(summary.get("items", [])))
        items = summary.get("items", [])

        if not items:
            print("⚠️  items が空のため投稿をスキップします。")
            return True

        # カテゴリ順 (general → research → vendor → その他) でソート
        category_order = {"general": 0, "research": 1, "vendor": 2}
        items = sorted(
            items,
            key=lambda x: category_order.get(x.get("category", ""), 99),
        )

        embeds = [build_embed(item, today=date) for item in items]
        batches = batch_embeds(embeds)
        header = f"📅 {date} のAIニュース ({count}件)" if date else f"📅 AIニュース ({count}件)"

        print(f"📤 {len(batches)}メッセージ / {len(embeds)} embeds で送信します")

        all_ok = True
        for idx, batch in enumerate(batches, 1):
            payload: dict = {
                "username": username,
                "embeds": batch,
                "allowed_mentions": {"parse": []},
            }
            # 先頭メッセージにだけヘッダ文を載せる
            if idx == 1:
                payload["content"] = header

            ok = self._post(payload)
            status_icon = "✅" if ok else "❌"
            print(
                f"   {status_icon} メッセージ {idx}/{len(batches)} "
                f"({len(batch)} embeds)"
            )
            all_ok = all_ok and ok
            if idx < len(batches):
                time.sleep(0.5)

        return all_ok


def main() -> int:
    """CLIエントリポイント。要約JSONファイルを読み込んでDiscordへ投稿。"""
    summary_path = os.environ.get("SUMMARY_PATH", "summary.json")

    if not os.path.exists(summary_path):
        print(f"❌ 要約ファイルが見つかりません: {summary_path}", file=sys.stderr)
        return 1

    with open(summary_path, "r", encoding="utf-8") as f:
        try:
            summary = json.load(f)
        except json.JSONDecodeError as e:
            print(f"❌ 要約JSONのパースに失敗: {e}", file=sys.stderr)
            return 1

    items = summary.get("items", [])
    if not items:
        print("⚠️  要約JSONに items がありません。投稿をスキップします。")
        return 0

    print("=" * 80)
    print("📤 Discord Notifier - 要約をEmbedでDiscordに投稿")
    print("=" * 80)
    print(f"要約ファイル: {summary_path} ({len(items)}件)")

    try:
        notifier = DiscordNotifier()
    except ValueError as e:
        print(f"❌ 設定エラー: {e}", file=sys.stderr)
        return 1

    success = notifier.send_summary_json(summary)

    if success:
        print("\n🎉 すべてのメッセージ送信に成功しました。")
        return 0
    else:
        print("\n❌ 一部メッセージの送信に失敗しました。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
