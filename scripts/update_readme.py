#!/usr/bin/env python3
"""
GitHub Profile README Auto-Updater
Fetches 4 data categories and makes individual commits for each.

Sources:
  - Wikipedia On This Day API  (no key needed)
  - LeetCode GraphQL API       (no key needed)
  - HackerNews Algolia API     (no key needed)
  - BBC World RSS              (no key needed)

Translation: deep-translator (free, no key needed)
"""

import os
import re
import sys
import json
import subprocess
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from deep_translator import GoogleTranslator

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
README_PATH = "README.md"

SECTIONS = {
    "history":  ("<!-- HISTORY_START -->",  "<!-- HISTORY_END -->"),
    "leetcode": ("<!-- LEETCODE_START -->", "<!-- LEETCODE_END -->"),
    "ainews":   ("<!-- AINEWS_START -->",   "<!-- AINEWS_END -->"),
    "news":     ("<!-- NEWS_START -->",     "<!-- NEWS_END -->"),
}

COMMIT_MESSAGES = {
    "history":  "update: history",
    "leetcode": "update: leetcode",
    "ainews":   "update: ai news",
    "news":     "update: news",
}

TRANSLATOR = GoogleTranslator(source="en", target="tr")


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def http_get(url: str, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers=headers or {
        "User-Agent": "Mozilla/5.0 (GitHub-Actions; profile-readme-updater)"
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()


def safe_translate(text: str) -> str:
    """Translate text to Turkish; return original on failure."""
    try:
        return TRANSLATOR.translate(text[:4500])  # API limit guard
    except Exception as e:
        print(f"  [warn] Translation failed: {e}")
        return text


def details_block(tr_content: str) -> str:
    """Wrap Turkish translation in a collapsible <details> block."""
    return (
        "\n<details>\n"
        "<summary>🇹🇷 Türkçe Çevirisi</summary>\n\n"
        f"{tr_content}\n\n"
        "</details>\n"
    )


def update_section(readme: str, key: str, new_content: str) -> str:
    """Replace content between START/END anchors."""
    start_tag, end_tag = SECTIONS[key]
    pattern = re.compile(
        rf"{re.escape(start_tag)}.*?{re.escape(end_tag)}",
        re.DOTALL
    )
    replacement = f"{start_tag}\n{new_content}\n{end_tag}"
    if not re.search(pattern, readme):
        raise ValueError(f"Anchor not found: {start_tag}")
    return re.sub(pattern, replacement, readme)


def read_readme() -> str:
    with open(README_PATH, "r", encoding="utf-8") as f:
        return f.read()


def write_readme(content: str) -> None:
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)


def git_commit(message: str) -> None:
    subprocess.run(["git", "add", README_PATH], check=True)
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        capture_output=True
    )
    if result.returncode == 0:
        print(f"  [skip] No changes to commit for: {message}")
        return
    subprocess.run(["git", "commit", "-m", message], check=True)
    print(f"  [ok] Committed: {message}")


# ─────────────────────────────────────────────
# FETCHERS
# ─────────────────────────────────────────────

def fetch_history() -> str:
    """Wikipedia On This Day — returns a Markdown block."""
    now = datetime.now(timezone.utc)
    url = (
        f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/selected"
        f"/{now.month:02d}/{now.day:02d}"
    )
    print("  [fetch] Wikipedia On This Day...")
    raw = http_get(url)
    data = json.loads(raw)
    events = data.get("selected", [])
    if not events:
        return "_No historical event found for today._"

    event = events[0]
    year  = event.get("year", "?")
    text  = event.get("text", "No description available.")
    pages = event.get("pages", [])
    link  = ""
    if pages:
        slug = pages[0].get("content_urls", {}).get("desktop", {}).get("page", "")
        if slug:
            link = f"\n🔗 [Wikipedia]({slug})"

    en_block  = f"**{now.strftime('%B %d')} — {year}:** {text}{link}"
    tr_text   = safe_translate(f"{now.strftime('%B %d')} — {year}: {text}")
    tr_block  = f"**{tr_text}**"

    return (
        f"### 📅 On This Day\n\n"
        f"{en_block}"
        f"{details_block(tr_block)}"
        f"\n*Updated: {now.strftime('%Y-%m-%d %H:%M')} UTC*"
    )


def fetch_leetcode() -> str:
    """LeetCode Problem of the Day via GraphQL — returns a Markdown block."""
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
        "User-Agent":   "Mozilla/5.0 (GitHub-Actions; profile-readme-updater)",
        "Referer":      "https://leetcode.com",
    }
    print("  [fetch] LeetCode POTD...")
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
    data = json.loads(raw)

    potd  = data["data"]["activeDailyCodingChallengeQuestion"]
    q     = potd["question"]
    title = q["title"]
    diff  = q["difficulty"]
    link  = f"https://leetcode.com{potd['link']}"
    tags  = ", ".join(t["name"] for t in q.get("topicTags", [])[:4])

    DIFF_BADGE = {
        "Easy":   "🟢 Easy",
        "Medium": "🟡 Medium",
        "Hard":   "🔴 Hard",
    }
    diff_badge = DIFF_BADGE.get(diff, diff)

    en_block = (
        f"**[{title}]({link})**  \n"
        f"Difficulty: {diff_badge}"
        + (f"  \nTopics: `{tags}`" if tags else "")
    )

    tr_title = safe_translate(title)
    tr_tags  = safe_translate(tags) if tags else ""
    tr_block = (
        f"**[{tr_title}]({link})**  \n"
        f"Zorluk: {diff_badge}"
        + (f"  \nKonular: `{tr_tags}`" if tr_tags else "")
    )

    now = datetime.now(timezone.utc)
    return (
        f"### 💻 LeetCode — Problem of the Day\n\n"
        f"{en_block}"
        f"{details_block(tr_block)}"
        f"\n*Updated: {now.strftime('%Y-%m-%d %H:%M')} UTC*"
    )


def fetch_ainews() -> str:
    """HackerNews Algolia API — top 3 AI/ML stories."""
    url = (
        "https://hn.algolia.com/api/v1/search"
        "?tags=story&query=artificial+intelligence+machine+learning"
        "&hitsPerPage=5&numericFilters=created_at_i>0"
    )
    print("  [fetch] HackerNews AI news...")
    raw  = http_get(url)
    data = json.loads(raw)
    hits = [
        h for h in data.get("hits", [])
        if h.get("title") and h.get("url")
    ][:3]

    if not hits:
        return "_No AI/ML news found._"

    lines = []
    for i, h in enumerate(hits, 1):
        title  = h["title"]
        link   = h["url"]
        points = h.get("points", 0)
        tr     = safe_translate(title)

        lines.append(
            f"{i}. **[{title}]({link})** ⬆️ {points}"
            f"{details_block(f'**{tr}**')}"
        )

    now = datetime.now(timezone.utc)
    return (
        f"### 🤖 AI & Tech — Top Stories\n\n"
        + "\n".join(lines)
        + f"\n\n*Updated: {now.strftime('%Y-%m-%d %H:%M')} UTC*"
    )


def fetch_news() -> str:
    """BBC World RSS — top 3 headlines."""
    url = "https://feeds.bbci.co.uk/news/world/rss.xml"
    print("  [fetch] BBC World RSS...")
    raw  = http_get(url)

    # Strip default namespace to simplify XPath
    raw_str = raw.decode("utf-8")
    raw_str = re.sub(r'\s+xmlns(?::\w+)?="[^"]+"', "", raw_str)
    root    = ET.fromstring(raw_str)

    items = root.findall(".//item")[:3]
    if not items:
        return "_No news headlines found._"

    lines = []
    for i, item in enumerate(items, 1):
        title = (item.findtext("title") or "").strip()
        link  = (item.findtext("link")  or "").strip()
        desc  = (item.findtext("description") or "").strip()
        if not title:
            continue

        tr_title = safe_translate(title)
        tr_desc  = safe_translate(desc) if desc else ""

        lines.append(
            f"{i}. **[{title}]({link})**"
            + (f"  \n{desc}" if desc else "")
            + details_block(
                f"**{tr_title}**"
                + (f"  \n{tr_desc}" if tr_desc else "")
            )
        )

    now = datetime.now(timezone.utc)
    return (
        f"### 🌍 Breaking News — BBC World\n\n"
        + "\n".join(lines)
        + f"\n\n*Updated: {now.strftime('%Y-%m-%d %H:%M')} UTC*"
    )


# ─────────────────────────────────────────────
# MAIN — sequential fetch → patch → commit
# ─────────────────────────────────────────────

TASKS = [
    ("history",  fetch_history),
    ("leetcode", fetch_leetcode),
    ("ainews",   fetch_ainews),
    ("news",     fetch_news),
]


def main() -> None:
    # Validate anchors exist before fetching anything
    readme = read_readme()
    for key, (start, end) in SECTIONS.items():
        if start not in readme or end not in readme:
            print(f"[ERROR] Anchor missing in README: {start}")
            sys.exit(1)

    for key, fetcher in TASKS:
        print(f"\n[{key.upper()}]")
        try:
            content = fetcher()
            readme  = read_readme()          # re-read (previous commit may change nothing)
            updated = update_section(readme, key, content)
            write_readme(updated)
            git_commit(COMMIT_MESSAGES[key])
        except Exception as e:
            print(f"  [error] {key}: {e}")
            # Continue with next task even if one fails
            continue

    print("\n✅ All sections processed.")


if __name__ == "__main__":
    main()
