# MicroBountyHarvest 🎯🤖

> **Autonomous AI Micro-Bounty Hunter Engine**
> Automatically scouts, solves, verifies, and claims open micro-bounties ($10–$500) from platforms like **Algora** and **GitHub**.

---

## 🚀 Features

- **The Scout (`scout.py`)**: Automatically queries Algora tRPC API and GitHub bounties (`gh search issues`). Scores issues based on solvability (language match, bounty size, title keywords).
- **The Solver (`solver.py`)**: Clones target repos into isolated workspace, uses Gemini AI to analyze issues and write code patches, then executes local test runners (`npm test`, `pytest`, `cargo test`, `go test`).
- **The Claimer (`claimer.py`)**: Creates target git branch, commits changes, and opens Pull Requests referencing issue numbers (`Fixes #<id>`) to claim rewards automatically.
- **Safety Modes**: Full `--auto-dry-run` support ensures safe execution without pushing external git changes until verified.
- **24/7 Automation**: GitHub Actions workflow included for scheduled automated scanning.

---

## 🛠️ Requirements & Setup

1. **Python 3.10+ & Node 18+**
2. **GitHub CLI (`gh`)** logged in (`gh auth login`)
3. Optional: Set `GEMINI_API_KEY` for AI solver code generation

---

## 📖 Usage Commands

### 1. Scout Open Bounties
```bash
python3 main.py --scan --limit 30
```

### 2. Solve Highest Scored Bounty
```bash
python3 main.py --solve
```

### 3. Claim Solved Bounty (Dry Run)
```bash
python3 main.py --claim
```

### 4. Full Autonomous Pipeline (Dry Run)
```bash
python3 main.py --auto-dry-run --limit 20
```

### 5. Full Autonomous Pipeline (Live Mode)
```bash
python3 main.py --auto-live --limit 20
```

---

## 📂 Project Structure

```
MicroBountyHarvest/
├── config.py           # Centralized configuration & threshold settings
├── scout.py            # Bounty discovery & solvability scoring engine
├── solver.py           # AI solver, git clone & local unit test runner
├── claimer.py          # GitHub PR submission & bounty claimer
├── main.py             # CLI orchestrator
├── data/               # Stores open_bounties.json & solved_bounties.json
├── workspace/          # Local workspace for cloned target repos
└── .github/workflows/  # GitHub Actions workflow for 24/7 automation
```
