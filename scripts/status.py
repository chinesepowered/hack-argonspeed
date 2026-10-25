#!/usr/bin/env python3
"""Where the team stands: today's limits, board positions, best checks and what sessions cost.

    scripts/status.py
"""

import glob
import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OKC = os.path.expanduser("~/.okc/bin/okc")


def load_env():
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path):
            key, sep, value = line.strip().partition("=")
            if sep and not key.startswith("#"):
                os.environ.setdefault(key.removeprefix("export ").strip(), value.strip().strip("'\""))


def okc_json(*args):
    out = subprocess.run([OKC, *args, "--json"], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def best_check(problem):
    """The fastest passing check in problems/<problem>/attempts/, and how many there are."""
    runs = []
    for path in glob.glob(os.path.join(ROOT, "problems", problem, "attempts", "*.json")):
        r = json.load(open(path)).get("result") or {}
        if r.get("passed") and r.get("speedup"):
            runs.append((r["speedup"], os.path.basename(path)[:-5]))
    return (max(runs) if runs else None), len(glob.glob(os.path.join(ROOT, "problems", problem, "attempts", "*.py")))


def main():
    load_env()
    print(f"{'problem':23} {'checks':>7} {'runs':>5}  {'board (ours / leader)':24} best check")
    for p in okc_json("problems")["problems"]:
        name, limits = p["name"], p["limits"]
        board = okc_json("leaderboard", name)
        you, leader = board.get("you"), board.get("leader") or {}
        ours = f"#{you['rank']} {you['speedup']:.3f}x" if you else "none"
        lead = f"{leader['speedup']:.3f}x" if leader.get("speedup") else "-"
        best, n = best_check(name)
        best_s = f"{best[0]:.3f}x  ({best[1]})" if best else "-"
        print(f"{name:23} {limits['checks']['left']:>3}/{limits['checks']['per_day']:<3} "
              f"{limits['scored']['left']:>2}/{limits['scored']['per_day']:<2}  "
              f"{ours + ' / ' + lead:24} {best_s}  [{n} checked]")

    ledger = os.path.join(ROOT, "runs", "ledger.jsonl")
    sessions = [json.loads(line) for line in open(ledger)] if os.path.exists(ledger) else []
    tokens_in = sum((s.get("usage") or {}).get("input_tokens") or 0 for s in sessions)
    tokens_out = sum((s.get("usage") or {}).get("output_tokens") or 0 for s in sessions)
    checks = sum(s.get("checks_used") or 0 for s in sessions)
    print(f"\n{len(sessions)} agent sessions: {tokens_in:,} input and {tokens_out:,} output tokens, "
          f"{checks} checks (runs/ledger.jsonl)")


if __name__ == "__main__":
    main()
