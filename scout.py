"""
MicroBountyHarvest - Scout Module
Discovers, filters, and ranks open micro-bounties across Algora, Polar.sh, Gitcoin, Opire, IssueHunt & GitHub.
"""

import json
import os
import re
import ssl
import subprocess
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Set

import config

SEARCH_PLATFORMS = ["bounty", "gitcoin", "polar.sh", "opire", "issuehunt"]


def get_ssl_context():
    """Returns SSL context that bypasses macOS certificate verification issues."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_algora_bounties(limit: int = 50) -> List[Dict[str, Any]]:
    """Fetches active bounties from Algora tRPC API."""
    params = {"json": {"limit": limit}}
    input_str = urllib.parse.quote(json.dumps(params))
    url = f"https://algora.io/api/trpc/bounty.list?input={input_str}"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
    )

    ctx = get_ssl_context()
    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            data = json.loads(resp.read().decode())
            res = data[0] if isinstance(data, list) else data
            json_data = res.get("result", {}).get("data", {}).get("json", {})
            return json_data.get("items", [])
    except Exception as e:
        print(f"[!] Algora tRPC fetch error: {e}", file=sys.stderr)
        return []


def fetch_github_bounties_multi(limit_per_query: int = 15) -> List[Dict[str, Any]]:
    """Fetches open GitHub issues across multiple bounty platform keywords (Gitcoin, Polar, Opire, Algora, IssueHunt)."""
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    if config.GITHUB_TOKEN:
        headers["Authorization"] = f"token {config.GITHUB_TOKEN}"

    all_items = []
    seen_urls: Set[str] = set()
    ctx = get_ssl_context()

    for keyword in SEARCH_PLATFORMS:
        query_str = urllib.parse.quote(f"{keyword} state:open type:issue")
        url = f"https://api.github.com/search/issues?q={query_str}&per_page={limit_per_query}"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx) as resp:
                data = json.loads(resp.read().decode())
                items = data.get("items", [])
                for item in items:
                    html_url = item.get("html_url", "")
                    if html_url and html_url not in seen_urls:
                        seen_urls.add(html_url)

                        repo_url = item.get("repository_url", "")
                        repo_parts = repo_url.split("/repos/")[-1].split("/") if "/repos/" in repo_url else ["", ""]
                        repo_owner = repo_parts[0] if len(repo_parts) > 0 else ""
                        repo_name = repo_parts[1] if len(repo_parts) > 1 else ""

                        body = item.get("body") or ""
                        title = item.get("title") or ""

                        # Extract reward if specified
                        reward_match = re.search(r"\$(\d+)", title + " " + body)
                        reward_usd = float(reward_match.group(1)) if reward_match else 50.0

                        all_items.append(
                            {
                                "id": f"gh-{repo_owner}/{repo_name}-{item.get('number')}",
                                "title": title,
                                "url": html_url,
                                "platform": keyword,
                                "repo_owner": repo_owner,
                                "repo_name": repo_name,
                                "issue_number": item.get("number", 0),
                                "org_handle": repo_owner,
                                "org_name": f"{repo_owner}/{repo_name}",
                                "body": body,
                                "reward_usd": reward_usd,
                                "reward_formatted": f"${reward_usd:.0f}",
                                "tech": [
                                    l.get("name", "")
                                    for l in item.get("labels", [])
                                    if isinstance(l, dict)
                                ],
                                "status": "active",
                            }
                        )
        except Exception as e:
            print(f"[!] GitHub search error for keyword '{keyword}': {e}", file=sys.stderr)

    return all_items


def check_maintainer_activity(repo_owner: str, repo_name: str, days: int = 30) -> bool:
    """Verifies if repository maintainers have recent commits or merged PRs within the last N days."""
    if not repo_owner or not repo_name:
        return False
    
    headers = {"User-Agent": "Mozilla/5.0"}
    if config.GITHUB_TOKEN:
        headers["Authorization"] = f"token {config.GITHUB_TOKEN}"

    ctx = get_ssl_context()
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits?per_page=3"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx) as resp:
            commits = json.loads(resp.read().decode())
            import datetime
            now = datetime.datetime.now(datetime.timezone.utc)
            cutoff = now - datetime.timedelta(days=days)
            for c in commits:
                date_str = c.get("commit", {}).get("committer", {}).get("date")
                if date_str:
                    c_date = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    if c_date >= cutoff:
                        return True
    except Exception:
        pass
    return False


def score_bounty_solvability(bounty: Dict[str, Any]) -> float:
    """
    Computes a solvability score (0.0 to 100.0) based on:
    - Target active maintainers (merged PRs / commits in last 30 days)
    - Language / tech stack match
    - Reward range appropriateness ($10 to $500)
    - Clear title/description details
    """
    score = 50.0

    title = (bounty.get("title") or "").lower()
    body = (bounty.get("body") or "").lower()
    tech = [t.lower() for t in bounty.get("tech") or []]
    reward_usd = bounty.get("reward_usd", 0.0)
    repo_owner = bounty.get("repo_owner", "")
    repo_name = bounty.get("repo_name", "")

    # Rule 1: Target Active Maintainers check
    if check_maintainer_activity(repo_owner, repo_name, days=30):
        score += 25.0
    else:
        score -= 20.0

    if config.MIN_BOUNTY_USD <= reward_usd <= config.MAX_BOUNTY_USD:
        score += 15.0
    elif reward_usd < config.MIN_BOUNTY_USD:
        score -= 20.0

    # Tech stack bonus
    matched_tech = any(
        lang in tech or any(lang in t for t in tech) for lang in config.TARGET_LANGUAGES
    )
    if matched_tech:
        score += 15.0

    # Platform reputational bonus
    platform = bounty.get("platform", "").lower()
    if platform in ["polar.sh", "opire", "gitcoin"]:
        score += 10.0

    # Ease keywords bonus
    easy_keywords = [
        "doc",
        "readme",
        "fix typo",
        "update",
        "bump",
        "export",
        "ui bug",
        "css",
        "type",
        "refactor",
        "cors",
    ]
    if any(kw in title or kw in body for kw in easy_keywords):
        score += 10.0

    # Penalize complex or vague keywords
    hard_keywords = [
        "architecture redesign",
        "migration",
        "security audit",
        "flaky test",
        "race condition",
    ]
    if any(kw in title for kw in hard_keywords):
        score -= 25.0

    return max(0.0, min(100.0, score))


def scan_bounties(limit: int = 50) -> List[Dict[str, Any]]:
    """Scans Algora, Polar.sh, Gitcoin, Opire & GitHub for open bounties."""
    print(f"[*] Scouting multi-platform micro-bounties (Algora, Polar, Gitcoin, Opire, IssueHunt, limit={limit})...")

    # Fetch Algora tRPC bounties
    algora_raw = fetch_algora_bounties(limit=limit)
    formatted_algora = []
    for raw in algora_raw:
        task = raw.get("task") or {}
        org = raw.get("org") or {}
        reward = raw.get("reward") or {}
        reward_usd = (reward.get("amount") or 0) / 100.0
        formatted_algora.append(
            {
                "id": task.get("id") or f"bounty-{task.get('number')}",
                "title": task.get("title") or "Untitled",
                "url": task.get("url") or "",
                "platform": "algora",
                "repo_owner": task.get("repo_owner") or org.get("handle") or "",
                "repo_name": task.get("repo_name") or "",
                "issue_number": task.get("number") or 0,
                "org_handle": org.get("handle") or "",
                "org_name": org.get("display_name") or org.get("name") or "",
                "body": task.get("body") or "",
                "reward_usd": reward_usd,
                "reward_formatted": raw.get("reward_formatted") or f"${reward_usd:.0f}",
                "tech": raw.get("tech") or [],
                "status": task.get("status") or "active",
            }
        )

    # Fetch multi-platform GitHub bounties
    gh_bounties = fetch_github_bounties_multi(limit_per_query=15)

    all_bounties = formatted_algora + gh_bounties

    filtered = []
    seen_ids = set()

    for item in all_bounties:
        item["solvability_score"] = score_bounty_solvability(item)
        item_id = item.get("id")
        if item_id not in seen_ids and config.MIN_BOUNTY_USD <= item["reward_usd"] <= config.MAX_BOUNTY_USD:
            seen_ids.add(item_id)
            filtered.append(item)

    # Sort by solvability score descending
    filtered.sort(key=lambda x: x["solvability_score"], reverse=True)

    # Save to disk
    with open(config.OPEN_BOUNTIES_FILE, "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2)

    print(f"[+] Found {len(filtered)} eligible micro-bounties across all platforms. Saved to {config.OPEN_BOUNTIES_FILE}")
    return filtered


if __name__ == "__main__":
    bounties = scan_bounties(limit=50)
    print("\n--- TOP MULTI-PLATFORM BOUNTIES SCOUTED ---")
    for idx, b in enumerate(bounties[:10], 1):
        print(f"{idx}. [{b['reward_formatted']}] ({b.get('platform', 'bounty').upper()}) Score: {b['solvability_score']:.1f}/100 | {b['title']}")
        print(f"   URL: {b['url']} (Repo: {b['repo_owner']}/{b['repo_name']})")
