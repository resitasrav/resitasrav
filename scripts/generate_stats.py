#!/usr/bin/env python3
"""
generate_stats.py
=================
Queries the GitHub GraphQL API (using GITHUB_TOKEN from Actions env)
and renders two clean SVG cards into assets/:

  assets/stats-card.svg       — commits, PRs, issues, stars, rank
  assets/langs-card.svg       — top languages by bytes of code

No external stats service needed — zero rate-limit risk.
"""

import os
import json
import urllib.request
import urllib.error
from pathlib import Path
from collections import defaultdict

# ── Config ────────────────────────────────────────────────────────────────────
USERNAME   = "resitasrav"
ASSETS_DIR = Path("assets")
TOKEN      = os.environ.get("GITHUB_TOKEN", "")

ASSETS_DIR.mkdir(exist_ok=True)

HEADERS = {
    "Authorization": f"bearer {TOKEN}",
    "Content-Type":  "application/json",
    "User-Agent":    "profile-readme-stats-generator",
}

# ── GitHub GraphQL helper ─────────────────────────────────────────────────────
def gql(query: str, variables: dict | None = None) -> dict:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload, headers=HEADERS, method="POST"
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


# ── Fetch user stats ──────────────────────────────────────────────────────────
def fetch_stats() -> dict:
    q = """
    query($login: String!) {
      user(login: $login) {
        name
        repositories(ownerAffiliations: OWNER, isFork: false, first: 100) {
          nodes {
            stargazerCount
            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
              edges { size node { name color } }
            }
          }
        }
        contributionsCollection {
          totalCommitContributions
          totalPullRequestContributions
          totalIssueContributions
          totalPullRequestReviewContributions
        }
        repositoriesContributedTo(contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, REPOSITORY], first: 1) {
          totalCount
        }
      }
    }
    """
    data = gql(q, {"login": USERNAME})
    user  = data["data"]["user"]
    cc    = user["contributionsCollection"]
    repos = user["repositories"]["nodes"]

    total_stars = sum(r["stargazerCount"] for r in repos)

    # Aggregate language bytes
    lang_bytes: dict[str, int]  = defaultdict(int)
    lang_color: dict[str, str]  = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name  = edge["node"]["name"]
            color = edge["node"]["color"] or "#858585"
            lang_bytes[name]  += edge["size"]
            lang_color[name]   = color

    total_bytes = sum(lang_bytes.values()) or 1
    langs = sorted(lang_bytes.items(), key=lambda x: -x[1])[:6]

    return {
        "name":     user["name"] or USERNAME,
        "commits":  cc["totalCommitContributions"],
        "prs":      cc["totalPullRequestContributions"],
        "issues":   cc["totalIssueContributions"],
        "reviews":  cc["totalPullRequestReviewContributions"],
        "stars":    total_stars,
        "repos":    user["repositoriesContributedTo"]["totalCount"],
        "langs":    [(n, b, lang_color[n], round(b / total_bytes * 100, 1)) for n, b in langs],
    }


# ── SVG helpers ───────────────────────────────────────────────────────────────
BG      = "#0d1117"
SURFACE = "#161b22"
BORDER  = "#30363d"
TEXT1   = "#e6edf3"
TEXT2   = "#8b949e"
ACCENT  = "#3b82f6"
GREEN   = "#3fb950"

def _card_wrap(width: int, height: int, content: str) -> str:
    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}"
     xmlns="http://www.w3.org/2000/svg" role="img">
  <title>GitHub Stats — {USERNAME}</title>
  <rect width="{width}" height="{height}" rx="10" fill="{BG}" stroke="{BORDER}" stroke-width="1"/>
  <rect x="1" y="1" width="{width-2}" height="{height-2}" rx="9" fill="{SURFACE}" opacity="0.6"/>
{content}
</svg>"""

def _text(x, y, val, size=13, color=TEXT1, weight="normal", anchor="start"):
    return f'  <text x="{x}" y="{y}" font-family="Segoe UI,Ubuntu,sans-serif" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{val}</text>\n'

def _stat_row(x, y, label, value, icon):
    out  = _text(x+24, y+4, icon, 14, ACCENT)
    out += _text(x+42, y+4, label, 12, TEXT2)
    out += _text(x+42, y+17, str(value), 11, TEXT1)
    return out


# ── Render stats card ─────────────────────────────────────────────────────────
def render_stats_card(s: dict) -> str:
    W, H = 380, 175
    rows = [
        ("Total Commits (this year)", s["commits"],  "◉"),
        ("Pull Requests",             s["prs"],      "⤴"),
        ("Issues Opened",             s["issues"],   "◎"),
        ("Total Stars Earned",        s["stars"],    "★"),
        ("Contributed to",            s["repos"],    "▣"),
    ]
    body = ""
    body += _text(20, 32, "GitHub Stats", 15, TEXT1, "600")
    body += _text(20, 46, f"@{USERNAME}", 11, TEXT2)

    # Two-column grid
    col = [(20, 65), (200, 65), (20, 115), (200, 115), (20, 155)]
    for i, ((x, y), (label, value, icon)) in enumerate(zip(col, rows)):
        body += _stat_row(x, y, label, value, icon)

    # Accent line
    body += f'  <line x1="20" y1="55" x2="360" y2="55" stroke="{BORDER}" stroke-width="0.8"/>\n'

    return _card_wrap(W, H, body)


# ── Render languages card ─────────────────────────────────────────────────────
def render_langs_card(s: dict) -> str:
    W  = 380
    H  = 60 + len(s["langs"]) * 28 + 20
    body = ""
    body += _text(20, 32, "Most Used Languages", 15, TEXT1, "600")
    body += f'  <line x1="20" y1="42" x2="360" y2="42" stroke="{BORDER}" stroke-width="0.8"/>\n'

    y = 58
    bar_w = 300
    for name, _, color, pct in s["langs"]:
        # Label + percent
        body += _text(20, y, name, 12, TEXT2)
        body += _text(360, y, f"{pct}%", 11, TEXT1, anchor="end")
        # Bar background
        body += f'  <rect x="20" y="{y+4}" width="{bar_w}" height="7" rx="3" fill="{BORDER}"/>\n'
        # Bar fill
        filled = max(4, int(bar_w * pct / 100))
        body += f'  <rect x="20" y="{y+4}" width="{filled}" height="7" rx="3" fill="{color}"/>\n'
        y += 28

    return _card_wrap(W, H, body)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not TOKEN:
        print("[ERROR] GITHUB_TOKEN not set — skipping stats generation")
        return

    print("[stats] Fetching GitHub data via GraphQL …")
    stats = fetch_stats()
    print(f"  commits={stats['commits']}  stars={stats['stars']}  langs={len(stats['langs'])}")

    stats_svg = render_stats_card(stats)
    langs_svg = render_langs_card(stats)

    (ASSETS_DIR / "stats-card.svg").write_text(stats_svg, encoding="utf-8")
    (ASSETS_DIR / "langs-card.svg").write_text(langs_svg, encoding="utf-8")
    print(f"[stats] SVGs written to {ASSETS_DIR}/")


if __name__ == "__main__":
    main()
