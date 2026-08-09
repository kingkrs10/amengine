"""
MicroBountyHarvest - Scout Module
Discovers, filters, and ranks open micro-bounties on Algora & GitHub.
"""

import json
import os
import re
import ssl
import subprocess
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, List

import config


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


def fetch_github_bounties(limit: int = 30) -> List[Dict[str, Any]]:
    """Fetches open GitHub issues tagged with 'bounty' using gh CLI."""
    cmd = [
        "gh",
        "search",
        "issues",
        "bounty",
        "--state",
        "open",
        "--limit",
        str(limit),
        "--json",
        "url,title,repository,labels,body,number",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        items = json.loads(res.stdout)
        bounties = []
        for item in items:
            repo = item.get("repository", {})
            body = item.get("body", "")
            title = item.get("title", "")

            # Extract dollar reward if mentioned
            reward_match = re.search(r"\$(\d+)", title + " " + body)
            reward_usd = float(reward_match.group(1)) if reward_match else 50.0

            bounties.append(
                {
                    "id": f"gh-{repo.get('nameWithOwner', '')}-{item.get('number')}",
                    "title": title,
                    "url": item.get("url", ""),
                    "repo_owner": repo.get("nameWithOwner", "").split("/")[0]
                    if "/" in repo.get("nameWithOwner", "")
                    else "",
                    "repo_name": repo.get("name", ""),
                    "issue_number": item.get("number", 0),
                    "org_handle": repo.get("nameWithOwner", "").split("/")[0]
                    if "/" in repo.get("nameWithOwner", "")
                    else "",
                    "org_name": repo.get("nameWithOwner", ""),
                    "body": body,
                    "reward_usd": reward_usd,
                    "reward_formatted": f"${reward_usd:.0f}",
                    "tech": [
                        l.get("name", "") for l in item.get("labels", []) if isinstance(l, dict)
                    ],
                    "status": "active",
                }
            )
        return bounties
    except Exception as e:
        print(f"[!] GitHub issue search error: {e}", file=sys.stderr)
        return []


def score_bounty_solvability(bounty: Dict[str, Any]) -> float:
    """
    Computes a solvability score (0.0 to 100.0) based on:
    - Language / tech stack match
    - Reward range appropriateness ($10 to $500)
    - Clear title/description details
    - Docs or simple fix keywords
    """
    score = 50.0

    title = (bounty.get("title") or "").lower()
    body = (bounty.get("body") or "").lower()
    tech = [t.lower() for t in bounty.get("tech") or []]
    reward_usd = bounty.get("reward_usd", 0.0)

    if config.MIN_BOUNTY_USD <= reward_usd <= config.MAX_BOUNTY_USD:
        score += 15.0
    elif reward_usd < config.MIN_BOUNTY_USD:
        score -= 20.0

    # Tech stack bonus
    matched_tech = any(
        lang in tech or any(lang in t for t in tech) for lang in config.TARGET_LANGUAGES
    )
    if matched_tech:
        score += 20.0

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
        score += 15.0

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
    """Scans Algora & GitHub for open bounties, filters and sorts by solvability score."""
    print(f"[*] Scouting open micro-bounties (Algora + GitHub, limit={limit})...")

    # Combine Algora + GitHub bounties
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

    gh_bounties = fetch_github_bounties(limit=limit)

    all_bounties = formatted_algora + gh_bounties

    filtered = []
    for item in all_bounties:
        item["solvability_score"] = score_bounty_solvability(item)
        if config.MIN_BOUNTY_USD <= item["reward_usd"] <= config.MAX_BOUNTY_USD:
            filtered.append(item)

    # Sort by solvability score descending
    filtered.sort(key=lambda x: x["solvability_score"], reverse=True)

    # Save to disk
    with open(config.OPEN_BOUNTIES_FILE, "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2)

    print(f"[+] Found {len(filtered)} eligible micro-bounties. Saved to {config.OPEN_BOUNTIES_FILE}")
    return filtered


if __name__ == "__main__":
    bounties = scan_bounties(limit=30)
    print("\n--- TOP SCOUTED BOUNTIES ---")
    for idx, b in enumerate(bounties[:10], 1):
        print(f"{idx}. [{b['reward_formatted']}] Score: {b['solvability_score']:.1f}/100 | {b['title']}")
        print(f"   URL: {b['url']} (Repo: {b['repo_owner']}/{b['repo_name']})")
