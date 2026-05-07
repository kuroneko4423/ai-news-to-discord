"""
AIニュース取得モジュール

国内外の複数RSSフィードからAI関連ニュースを取得し、
カテゴリ分類した上でJSONとして保存します。
このモジュールはGitHub Actionsの「fetch-news」ジョブから実行されます。
"""
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Dict, Optional

import feedparser


# ============================================================
# RSSフィード定義
# 国内外をバランスよく、カテゴリでグルーピング
# ============================================================
RSS_FEEDS: List[Dict[str, str]] = [
    # --- 国内: 一般向けAIニュース ---
    {
        "name": "ITmedia AI+",
        "url": "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml",
        "region": "jp",
        "category": "general",
    },
    {
        "name": "ZDNET Japan AI",
        "url": "https://japan.zdnet.com/rss/sp_ai/index.rdf",
        "region": "jp",
        "category": "general",
    },
    # --- 海外: 一般向けAIニュース ---
    {
        "name": "TechCrunch AI",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "region": "global",
        "category": "general",
    },
    {
        "name": "The Verge AI",
        "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        "region": "global",
        "category": "general",
    },
    # --- 海外: リサーチ/技術深掘り ---
    {
        "name": "MIT Technology Review (AI)",
        "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
        "region": "global",
        "category": "research",
    },
    # --- 公式ブログ ---
    {
        "name": "Google AI Blog",
        "url": "https://blog.google/technology/ai/rss/",
        "region": "global",
        "category": "vendor",
    },
    {
        "name": "OpenAI Blog",
        "url": "https://openai.com/blog/rss.xml",
        "region": "global",
        "category": "vendor",
    },
]


@dataclass
class NewsItem:
    """1件のニュース記事"""
    title: str
    link: str
    summary: str
    published: str
    source: str
    region: str
    category: str
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict:
        return asdict(self)


class NewsFetcher:
    """複数のRSSフィードからAIニュースを取得・分類するクラス"""

    SUMMARY_MAX_LEN = 300

    def __init__(self, feeds: Optional[List[Dict[str, str]]] = None):
        self.feeds = feeds if feeds is not None else RSS_FEEDS

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        """テキストを指定長で切り詰め(末尾に...)"""
        if not text:
            return ""
        text = text.strip()
        if len(text) <= max_len:
            return text
        return text[:max_len].rstrip() + "..."

    def _fetch_single_feed(
        self, feed_def: Dict[str, str], per_feed_limit: int
    ) -> List[NewsItem]:
        """単一RSSフィードから記事を取得"""
        items: List[NewsItem] = []
        try:
            parsed = feedparser.parse(feed_def["url"])
            if parsed.bozo and not parsed.entries:
                print(
                    f"⚠️  Warning: failed to parse feed {feed_def['name']}: "
                    f"{getattr(parsed, 'bozo_exception', 'unknown error')}",
                    file=sys.stderr,
                )
                return items

            for entry in parsed.entries[:per_feed_limit]:
                items.append(
                    NewsItem(
                        title=entry.get("title", "").strip(),
                        link=entry.get("link", "").strip(),
                        summary=self._truncate(
                            entry.get("summary", "") or entry.get("description", ""),
                            self.SUMMARY_MAX_LEN,
                        ),
                        published=entry.get("published", "")
                        or entry.get("updated", ""),
                        source=feed_def["name"],
                        region=feed_def["region"],
                        category=feed_def["category"],
                    )
                )
        except Exception as e:
            print(
                f"❌ Error fetching feed {feed_def['name']}: {e}",
                file=sys.stderr,
            )
        return items

    def fetch_all(
        self, per_feed_limit: int = 3, total_limit: int = 15
    ) -> List[NewsItem]:
        """
        全フィードから取得し、カテゴリバランスを取って総件数を制限する。

        Args:
            per_feed_limit: 各フィードからの最大取得数
            total_limit: 全体の最大件数

        Returns:
            ニュース記事リスト
        """
        all_items: List[NewsItem] = []
        for feed_def in self.feeds:
            fetched = self._fetch_single_feed(feed_def, per_feed_limit)
            print(f"   - {feed_def['name']}: {len(fetched)}件取得")
            all_items.extend(fetched)

        # 重複除去(URL基準)
        seen_links = set()
        deduped: List[NewsItem] = []
        for item in all_items:
            if item.link and item.link not in seen_links:
                seen_links.add(item.link)
                deduped.append(item)

        # 件数制限
        return deduped[:total_limit]

    @staticmethod
    def group_by_category(items: List[NewsItem]) -> Dict[str, List[Dict]]:
        """カテゴリ別にグルーピング"""
        grouped: Dict[str, List[Dict]] = {}
        for item in items:
            grouped.setdefault(item.category, []).append(item.to_dict())
        return grouped


def main() -> int:
    """CLIエントリポイント。news.json を出力する。"""
    output_path = os.environ.get("NEWS_OUTPUT_PATH", "news.json")
    per_feed_limit = int(os.environ.get("PER_FEED_LIMIT", "3"))
    total_limit = int(os.environ.get("TOTAL_LIMIT", "15"))

    print("=" * 80)
    print("📰 News Fetcher - 複数RSSフィードからAIニュースを取得")
    print("=" * 80)
    print(f"出力先: {output_path}")
    print(f"フィード数: {len(RSS_FEEDS)}")
    print(f"取得設定: per_feed={per_feed_limit}, total={total_limit}\n")

    fetcher = NewsFetcher()
    items = fetcher.fetch_all(per_feed_limit=per_feed_limit, total_limit=total_limit)

    if not items:
        print("⚠️  取得できたニュースがありません。")
        # ニュースが0件でも空ファイルを出力(後段ジョブで判定)
        payload: Dict = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "count": 0,
            "categories": {},
            "items": [],
        }
    else:
        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "count": len(items),
            "categories": NewsFetcher.group_by_category(items),
            "items": [item.to_dict() for item in items],
        }
        print(f"\n✅ 合計{len(items)}件のニュースを取得しました。")
        for category, group in payload["categories"].items():
            print(f"   - [{category}] {len(group)}件")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n💾 {output_path} に保存しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
