#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""arc-agent-escrow 自动提交脚本"""

import subprocess
import json
import os
from datetime import datetime

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
PROJECT_DIR = r"D:\币圈项目\arc空投\arc-agent-escrow"

COMMITS = [
    {
        "files": ["escrow_engine.py"],
        "message": "feat: implement ERC-8183 escrow engine with full job lifecycle state machine",
        "description": "Core escrow engine implementing ERC-8183 Agent Commerce Protocol with 11 states (open->funded->assigned->submitted->verified->settled), escrow ledger, agent reputation tracking, and SQLite persistence."
    },
    {
        "files": ["evaluator.py"],
        "message": "feat: add AI evaluator with multi-category quality assessment",
        "description": "AI evaluation engine with category-specific checks (translation, code, analysis, writing), weighted scoring, keyword relevance, format validation, and configurable pass threshold."
    },
    {
        "files": ["escrow_sdk.py"],
        "message": "feat: add Python SDK for 3-line agent integration",
        "description": "AgentEscrow SDK with post_job, accept_job, submit_work, verify_job methods plus quick_hire/quick_work convenience flows. Zero-dependency Python SDK using only stdlib."
    },
    {
        "files": ["app.py", "templates/index.html", "templates/job.html"],
        "message": "feat: add Flask application with REST API and job dashboard",
        "description": "Flask app with full REST API (create/fund/accept/submit/verify/settle), AI auto-evaluation on verify, web dashboard with stats cards and job table, and detailed job view page."
    },
    {
        "files": ["README.md", "requirements.txt", ".gitignore"],
        "message": "docs: add README with ERC-8183 architecture, SDK usage, and API reference",
        "description": "Comprehensive documentation covering problem statement, Arc advantages, ERC-8183 job lifecycle, SDK quickstart, full API reference, and development roadmap."
    },
]


def run_git(args):
    return subprocess.run(["git"] + args, cwd=PROJECT_DIR, capture_output=True, text=True)


def get_step():
    try:
        with open(f"{PROJECT_DIR}/commit_state.json", "r") as f:
            return json.load(f).get("completed_count", 0)
    except FileNotFoundError:
        return 0


def save_step(n):
    with open(f"{PROJECT_DIR}/commit_state.json", "w") as f:
        json.dump({"completed_count": n}, f)


def main():
    step = get_step()
    if step >= len(COMMITS):
        print("All done!")
        return

    c = COMMITS[step]
    print(f"[{step+1}/{len(COMMITS)}] {c['message']}")

    for f in c["files"]:
        run_git(["add", f])

    msg = f"{c['message']}\n\n{c['description']}\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
    run_git(["commit", "-m", msg])
    run_git(["push", "origin", "main"])
    save_step(step + 1)
    print(f"  Pushed! ({len(COMMITS) - step - 1} remaining)")


if __name__ == "__main__":
    main()
