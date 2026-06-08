#!/usr/bin/env python3
"""
GitHub Profile README Auto-Updater  v2.0
=========================================
Fetches 4 categories, patches README anchors, makes individual commits.

Sources
-------
  history  : Wikipedia On This Day REST API      (no key)
  leetcode : LeetCode GraphQL API                (no key)
  ainews   : HackerNews Algolia API              (no key)
  news     : BBC World RSS  ➜  Reuters  ➜  Al Jazeera  (fallback chain)

Translation: deep-translator  (free, no key)
"""

import re
import sys
import json
import subprocess
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from deep_translator import GoogleTranslator

# ──────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────
README_PATH = "README.md"

SECTIONS = {
    "history":  ("<!-- HISTORY_START -->",  "<!-- HISTORY_END -->"),
}

COMMIT_MESSAGES = {
    "history":  "update: history",
}

# News RSS fallback chain — tried in order until one succeeds
NEWS_SOURCES = [
    {
        "name": "BBC World",
        "url":  "https://feeds.bbci.co.uk/news/world/rss.xml",
    },
    {
        "name": "Reuters",
        "url":  "https://feeds.reuters.com/reuters/topNews",
    },
    {
        "name": "Al Jazeera",
        "url":  "https://www.aljazeera.com/xml/rss/all.xml",
    },
    {
        "name": "AP News",
        "url":  "https://rsshub.app/apnews/topics/apf-topnews",
    },
]

# Realistic browser User-Agent — critical for BBC (blocks bot UAs)
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

TRANSLATOR = GoogleTranslator(source="en", target="tr")


# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────

def http_get(url: str, extra_headers: dict | None = None, timeout: int = 20) -> bytes:
    """GET with a realistic browser UA; merges extra_headers on top."""
    headers = {
        "User-Agent":      _UA,
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "Connection":      "keep-alive",
    }
    if extra_headers:
        headers.update(extra_headers)

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def safe_translate(text: str) -> str:
    """Translate to Turkish; silently falls back to original on any error."""
    if not text or not text.strip():
        return text
    try:
        return TRANSLATOR.translate(text[:4500])
    except Exception as exc:
        print(f"    [warn] translation failed: {exc}")
        return text


def details_block(tr_content: str) -> str:
    """Wrap content in a collapsible GitHub Markdown <details> block."""
    return (
        "\n<details>\n"
        "<summary>🇹🇷 Türkçe Çevirisi</summary>\n\n"
        f"{tr_content}\n\n"
        "</details>\n"
    )


def update_section(readme: str, key: str, new_content: str) -> str:
    """Replace everything between START/END anchors with new_content."""
    start_tag, end_tag = SECTIONS[key]
    pattern = re.compile(
        rf"{re.escape(start_tag)}.*?{re.escape(end_tag)}",
        re.DOTALL,
    )
    if not re.search(pattern, readme):
        raise ValueError(f"Anchor not found in README: {start_tag}")
    return re.sub(pattern, f"{start_tag}\n{new_content}\n{end_tag}", readme)


def read_readme() -> str:
    with open(README_PATH, "r", encoding="utf-8") as f:
        return f.read()


def write_readme(content: str) -> None:
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)


def git_commit(message: str) -> None:
    subprocess.run(["git", "add", README_PATH], check=True)
    no_diff = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], capture_output=True
    )
    if no_diff.returncode == 0:
        print(f"    [skip] nothing changed — skipping commit: {message}")
        return
    subprocess.run(["git", "commit", "-m", message], check=True)
    print(f"    [ok] committed: {message}")


# ──────────────────────────────────────────────────────────────
# RSS PARSER  (handles BBC's CDATA <link> quirk)
# ──────────────────────────────────────────────────────────────

def _parse_rss_items(raw_bytes: bytes, max_items: int = 3) -> list[dict]:
    """
    Parse RSS feed bytes → list of {title, link, description}.

    BBC wraps <link> in CDATA which confuses ElementTree because
    <link> is also an Atom namespace tag.  Strategy:
      1. Strip all namespace declarations so XPath is simple.
      2. For each <item>, extract <link> via regex on the raw XML
         slice between <item> … </item> as a fallback when ET
         returns an empty string.
    """
    raw_str = raw_bytes.decode("utf-8", errors="replace")

    # Remove namespace declarations so ET doesn't mangle tag names
    cleaned = re.sub(r'\s+xmlns(?::\w+)?="[^"]+"', "", raw_str)
    # Also strip namespace prefixes from tags (e.g. <atom:link …/>)
    cleaned = re.sub(r"</?[a-zA-Z]+:", "<", cleaned)

    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError as exc:
        raise ValueError(f"RSS XML parse error: {exc}") from exc

    # Split raw text into per-item chunks for regex link extraction
    raw_item_chunks = re.findall(r"<item>(.*?)</item>", raw_str, re.DOTALL)

    results = []
    for idx, item in enumerate(root.findall(".//item")):
        if len(results) >= max_items:
            break

        title = (item.findtext("title") or "").strip()
        if not title or title.lower() == "rss":
            continue

        # ET link extraction
        link = (item.findtext("link") or "").strip()

        # Fallback: regex on raw chunk (handles CDATA-wrapped links)
        if not link and idx < len(raw_item_chunks):
            chunk = raw_item_chunks[idx]
            m = re.search(
                r"<link>(?:<!\[CDATA\[)?(https?://[^\]<\s]+)(?:\]\]>)?</link>",
                chunk, re.IGNORECASE,
            )
            if m:
                link = m.group(1).strip()

        # Last resort: <guid> often duplicates the link
        if not link:
            link = (item.findtext("guid") or "").strip()

        desc = re.sub(r"<[^>]+>", "", item.findtext("description") or "").strip()
        desc = re.sub(r"\s+", " ", desc)

        results.append({"title": title, "link": link, "description": desc})

    return results


# ──────────────────────────────────────────────────────────────
# FETCHERS
# ──────────────────────────────────────────────────────────────

def fetch_history() -> str:
    """Wikipedia On This Day — one curated event."""
    now = datetime.now(timezone.utc)
    url = (
        "https://en.wikipedia.org/api/rest_v1/feed/onthisday/selected"
        f"/{now.month:02d}/{now.day:02d}"
    )
    print("  [fetch] Wikipedia On This Day …")
    raw  = http_get(url)
    data = json.loads(raw)

    events = data.get("selected", [])
    if not events:
        return "_No historical event found for today._"

    event = events[0]
    year  = event.get("year", "?")
    text  = event.get("text", "").strip()
    pages = event.get("pages", [])
    link  = ""
    if pages:
        page_url = (
            pages[0]
            .get("content_urls", {})
            .get("desktop", {})
            .get("page", "")
        )
        if page_url:
            link = f"  \n🔗 [Read on Wikipedia]({page_url})"

    date_label = now.strftime("%B %d")
    en_block   = f"**{date_label} — {year}:** {text}{link}"
    tr_text    = safe_translate(f"{date_label} — {year}: {text}")
    tr_block   = f"**{tr_text}**"

    return (
        f"### 📅 On This Day\n\n"
        f"{en_block}"
        f"{details_block(tr_block)}"
        f"\n*Updated: {now.strftime('%Y-%m-%d %H:%M')} UTC*"
    )


def fetch_leetcode() -> str:
    """LeetCode Problem of the Day via public GraphQL."""
    url     = "https://leetcode.com/graphql"
    payload = json.dumps({
        "query": """
        query {
          activeDailyCodingChallengeQuestion {
            date
            link
            question {
              title
              difficulty
              topicTags { name }
            }
          }
        }
        """
    }).encode()
    headers = {
        "Content-Type": "application/json",
        "Referer":      "https://leetcode.com",
    }
    print("  [fetch] LeetCode POTD …")

    req = urllib.request.Request(
        url, data=payload, headers={**{"User-Agent": _UA}, **headers}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()

    data = json.loads(raw)
    potd  = data["data"]["activeDailyCodingChallengeQuestion"]
    q     = potd["question"]
    title = q["title"]
    diff  = q["difficulty"]
    link  = f"https://leetcode.com{potd['link']}"
    tags  = ", ".join(t["name"] for t in q.get("topicTags", [])[:4])

    BADGE = {"Easy": "🟢 Easy", "Medium": "🟡 Medium", "Hard": "🔴 Hard"}
    badge = BADGE.get(diff, diff)

    en_block = (
        f"**[{title}]({link})**  \n"
        f"Difficulty: {badge}"
        + (f"  \nTopics: `{tags}`" if tags else "")
    )
    tr_block = (
        f"**[{safe_translate(title)}]({link})**  \n"
        f"Zorluk: {badge}"
        + (f"  \nKonular: `{safe_translate(tags)}`" if tags else "")
    )

    now = datetime.now(timezone.utc)
    return (
        f"### 💻 LeetCode — Problem of the Day\n\n"
        f"{en_block}"
        f"{details_block(tr_block)}"
        f"\n*Updated: {now.strftime('%Y-%m-%d %H:%M')} UTC*"
    )


def fetch_ainews() -> str:
    """HackerNews Algolia API — top 2 AI/ML stories."""
    url = (
        "https://hn.algolia.com/api/v1/search"
        "?tags=story&query=artificial+intelligence+machine+learning"
        "&hitsPerPage=6"
    )
    print("  [fetch] HackerNews AI stories …")
    raw  = http_get(url)
    data = json.loads(raw)
    hits = [h for h in data.get("hits", []) if h.get("title") and h.get("url")][:2]

    if not hits:
        return "_No AI/ML stories found._"

    now   = datetime.now(timezone.utc)
    lines = []
    for i, h in enumerate(hits, 1):
        title  = h["title"]
        link   = h["url"]
        points = h.get("points", 0)
        lines.append(
            f"{i}. **[{title}]({link})** ⬆️ {points}"
            f"{details_block(f'**{safe_translate(title)}**')}"
        )

    return (
        f"### 🤖 AI & Tech — Top Stories\n\n"
        + "\n".join(lines)
        + f"\n\n*Updated: {now.strftime('%Y-%m-%d %H:%M')} UTC*"
    )


def fetch_news() -> str:
    """
    Top 2 world headlines — tries NEWS_SOURCES in order until one works.
    Each attempt:
      • sends realistic browser headers (bypasses BBC bot-block)
      • uses the robust CDATA-aware RSS parser
    """
    last_error = None

    for source in NEWS_SOURCES:
        name = source["name"]
        url  = source["url"]
        print(f"  [fetch] {name} RSS …")

        try:
            raw   = http_get(url)
            items = _parse_rss_items(raw, max_items=2)

            if not items:
                print(f"    [warn] {name}: feed parsed but no items found — trying next")
                continue

            now   = datetime.now(timezone.utc)
            lines = []
            for i, item in enumerate(items, 1):
                title = item["title"]
                link  = item["link"]
                desc  = item["description"]

                tr_title = safe_translate(title)
                tr_desc  = safe_translate(desc) if desc else ""

                link_md = f"[{title}]({link})" if link else title
                lines.append(
                    f"{i}. **{link_md}**"
                    + (f"  \n{desc}" if desc else "")
                    + details_block(
                        f"**{tr_title}**"
                        + (f"  \n{tr_desc}" if tr_desc else "")
                    )
                )

            return (
                f"### 🌍 Breaking News — {name}\n\n"
                + "\n".join(lines)
                + f"\n\n*Updated: {now.strftime('%Y-%m-%d %H:%M')} UTC*"
            )

        except Exception as exc:
            last_error = exc
            print(f"    [warn] {name} failed: {exc} — trying next source")
            continue

    # All sources exhausted
    raise RuntimeError(
        f"All news sources failed. Last error: {last_error}"
    )


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────

TASKS = [
    ("history",  fetch_history),
]


def main() -> None:
    # Pre-flight: confirm all anchors exist
    readme = read_readme()
    missing = [
        start
        for key, (start, end) in SECTIONS.items()
        if start not in readme or end not in readme
    ]
    if missing:
        print("[ERROR] Missing anchors in README:")
        for tag in missing:
            print(f"  {tag}")
        sys.exit(1)

    errors = []
    for key, fetcher in TASKS:
        print(f"\n[{key.upper()}]")
        try:
            content = fetcher()
            readme  = read_readme()
            updated = update_section(readme, key, content)
            write_readme(updated)
            git_commit(COMMIT_MESSAGES[key])
        except Exception as exc:
            msg = f"{key}: {exc}"
            print(f"  [ERROR] {msg}")
            errors.append(msg)

    print("\n" + "─" * 50)
    if errors:
        print(f"⚠️  Completed with {len(errors)} error(s):")
        for e in errors:
            print(f"   • {e}")
        sys.exit(1)
    else:
        print("✅  All 4 sections updated successfully.")


if __name__ == "__main__":
    main()
