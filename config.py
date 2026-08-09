"""
MicroBountyHarvest Configuration
Centralized configuration settings for bounty scouting, solving, and claiming.
"""

import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
WORKSPACE_DIR = BASE_DIR / "workspace"

DATA_DIR.mkdir(exist_ok=True)
WORKSPACE_DIR.mkdir(exist_ok=True)

# Load .env if present
env_file = BASE_DIR / ".env"
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

# Bounty Scout Settings
MIN_BOUNTY_USD = float(os.getenv("MIN_BOUNTY_USD", "10"))
MAX_BOUNTY_USD = float(os.getenv("MAX_BOUNTY_USD", "500"))
TARGET_LANGUAGES = ["typescript", "javascript", "python", "markdown", "docs", "go", "rust"]

# Solvability Criteria
PREFER_DOCS_AND_SIMPLE_BUGS = True
MAX_OPEN_PR_COMPETITORS = 5

# AI Solver Settings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")  # default solver model
MAX_SOLVER_RETRIES = 3

# Claimer & Git Settings
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
DRY_RUN = os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")

# Files
OPEN_BOUNTIES_FILE = DATA_DIR / "open_bounties.json"
SOLVED_BOUNTIES_FILE = DATA_DIR / "solved_bounties.json"
