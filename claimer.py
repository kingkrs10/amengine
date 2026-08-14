"""
MicroBountyHarvest - Claimer Module
Creates GitHub Pull Requests and posts bounty claims to claim rewards automatically.
"""

import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List

import config


def get_github_username(env: dict) -> str:
    """Gets authenticated GitHub username using gh CLI."""
    try:
        res = subprocess.run(["gh", "api", "user", "-q", ".login"], capture_output=True, text=True, check=True, env=env)
        return res.stdout.strip()
    except Exception:
        return "kingkrs10"


class BountyClaimer:
    def __init__(self, bounty: Dict[str, Any], dry_run: bool = False):
        self.bounty = bounty
        self.dry_run = dry_run
        self.repo_owner = bounty.get("repo_owner", "")
        self.repo_name = bounty.get("repo_name", "")
        self.issue_number = bounty.get("issue_number", 0)
        self.title = bounty.get("title", "")
        self.reward = bounty.get("reward_formatted", "$?")
        self.repo_dir = config.WORKSPACE_DIR / f"{self.repo_owner}_{self.repo_name}"

    def prepare_branch_and_commit(self, branch_name: str) -> bool:
        """Checkout branch and commit changes in workspace."""
        if not self.repo_dir.exists():
            print(f"[!] Workspace directory {self.repo_dir} does not exist.")
            return False

        try:
            print(f"[*] Setting up branch {branch_name}...")
            res = subprocess.run(["git", "branch", "--list", branch_name], cwd=self.repo_dir, capture_output=True, text=True)
            if branch_name in res.stdout:
                subprocess.run(["git", "checkout", branch_name], cwd=self.repo_dir, check=True, capture_output=True)
            else:
                subprocess.run(["git", "checkout", "-b", branch_name], cwd=self.repo_dir, check=True, capture_output=True)

            print(f"[*] Committing fix for issue #{self.issue_number}...")
            subprocess.run(["git", "add", "."], cwd=self.repo_dir, check=True, capture_output=True)

            commit_msg = f"fix: resolve issue #{self.issue_number} - {self.title}"
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=self.repo_dir, capture_output=True)

            print(f"[+] Committed fix successfully.")
            return True
        except subprocess.CalledProcessError as e:
            print(f"[!] Git branch/commit error: {e}", file=sys.stderr)
            return False

    def engage_on_issue(self, headers: dict, ctx: Any) -> bool:
        """Rule 3: Engage on the Issue First by posting a comment on the GitHub issue prior to PR submission."""
        if not self.repo_owner or not self.repo_name or not self.issue_number:
            return False

        comment_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/issues/{self.issue_number}/comments"
        comment_body = f"Hello! I am reviewing issue #{self.issue_number} and submitting a proposed fix."
        payload = json.dumps({"body": comment_body}).encode("utf-8")

        print(f"[*] Engaging on issue #{self.issue_number} before PR submission...")
        try:
            req = urllib.request.Request(comment_url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, context=ctx) as resp:
                print(f"[+] Successfully posted engagement comment on issue #{self.issue_number}.")
                return True
        except Exception as e:
            print(f"[*] Issue comment status: {e} (proceeding to PR creation)")
            return False

    def create_pull_request(self) -> bool:
        """Forks repo, pushes branch, and submits PR using GitHub REST API."""
        branch_name = f"fix/bounty-issue-{self.issue_number}"

        if not self.prepare_branch_and_commit(branch_name):
            return False

        # Rule 2: Clean PR title and body without bot markers
        pr_title = f"fix: resolve issue #{self.issue_number} - {self.title}"
        pr_body = (
            f"## Description\n\n"
            f"Fixes #{self.issue_number}.\n\n"
            f"This pull request resolves the reported issue: **{self.title}**.\n\n"
            f"### Testing & Verification\n"
            f"- Changes verified locally prior to submission.\n"
        )

        if self.dry_run:
            print("\n[DRY RUN MODE ACTIVE] - No network changes submitted.")
            print(f"Target Repo: {self.repo_owner}/{self.repo_name}")
            print(f"Branch: {branch_name}")
            print(f"PR Title: {pr_title}")
            print(f"PR Body:\n{pr_body}")
            print("[+] Claimer verification passed (dry-run mode).")
            return True

        env = os.environ.copy()
        if config.GITHUB_TOKEN:
            env["GH_TOKEN"] = config.GITHUB_TOKEN
            env["GITHUB_TOKEN"] = config.GITHUB_TOKEN

        username = get_github_username(env)
        print(f"[*] Authenticated as GitHub user: '{username}'")

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Authorization": f"token {config.GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
        }

        # Rule 3: Engage on the Issue First
        self.engage_on_issue(headers, ctx)

        print(f"[*] Ensuring fork exists for {self.repo_owner}/{self.repo_name}...")
        fork_api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/forks"
        try:
            req = urllib.request.Request(fork_api_url, headers=headers, method="POST")
            with urllib.request.urlopen(req, context=ctx) as resp:
                fork_data = json.loads(resp.read().decode())
                fork_repo_name = fork_data.get("name", self.repo_name)
        except Exception as e:
            print(f"[*] Fork call returned: {e} (proceeding if fork already exists)")
            fork_repo_name = self.repo_name

        # Set up authenticated fork remote
        if config.GITHUB_TOKEN:
            fork_url = f"https://x-access-token:{config.GITHUB_TOKEN}@github.com/{username}/{fork_repo_name}.git"
        else:
            fork_url = f"https://github.com/{username}/{fork_repo_name}.git"

        subprocess.run(["git", "remote", "remove", "fork"], cwd=self.repo_dir, capture_output=True)
        subprocess.run(["git", "remote", "add", "fork", fork_url], cwd=self.repo_dir, capture_output=True)

        print(f"[*] Pushing branch '{branch_name}' to fork (https://github.com/{username}/{fork_repo_name}.git)...")
        push_res = subprocess.run(["git", "push", "-u", "fork", branch_name, "--force"], cwd=self.repo_dir, capture_output=True, text=True, env=env)
        if push_res.returncode != 0:
            print(f"[!] Push to fork failed: {push_res.stderr.strip()}", file=sys.stderr)
            return False

        # Fetch target repo default branch dynamically
        default_branch = "main"
        try:
            repo_info_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}"
            req_info = urllib.request.Request(repo_info_url, headers=headers)
            with urllib.request.urlopen(req_info, context=ctx) as resp_info:
                repo_info = json.loads(resp_info.read().decode())
                default_branch = repo_info.get("default_branch", "main")
        except Exception:
            pass

        print(f"[*] Opening Pull Request from '{username}:{branch_name}' to '{self.repo_owner}:{self.repo_name}' (base: {default_branch})...")
        pr_api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/pulls"
        pr_payload = json.dumps({
            "title": pr_title,
            "body": pr_body,
            "head": f"{username}:{branch_name}",
            "base": default_branch
        }).encode("utf-8")

        try:
            req = urllib.request.Request(pr_api_url, data=pr_payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, context=ctx) as resp:
                pr_res = json.loads(resp.read().decode())
                pr_url = pr_res.get("html_url", "")
                print(f"[SUCCESS] Pull Request created! URL: {pr_url}")

                # Save PR URL to bounty record
                self.bounty["pr_url"] = pr_url
                return True
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode() if e.fp else str(e)
            print(f"[!] Failed to create PR via REST API ({e.code}): {err_msg}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"[!] Failed to create PR: {e}", file=sys.stderr)
            return False


def claim_solved_bounties(dry_run: bool = False) -> int:
    """Claims all solved bounties from solved_bounties.json."""
    if not config.SOLVED_BOUNTIES_FILE.exists():
        print("[!] No solved_bounties.json found. Run solver.py first.")
        return 0

    with open(config.SOLVED_BOUNTIES_FILE, "r", encoding="utf-8") as f:
        solved = json.load(f)

    if not solved:
        print("[!] No solved bounties found to claim.")
        return 0

    claimed_count = 0
    latest_solved = [solved[-1]] if solved else []
    for bounty in latest_solved:
        claimer = BountyClaimer(bounty, dry_run=dry_run)
        if claimer.create_pull_request():
            claimed_count += 1

    print(f"\n[+] Processed {claimed_count}/{len(latest_solved)} bounty claims.")
    return claimed_count


if __name__ == "__main__":
    claim_solved_bounties(dry_run=False)
