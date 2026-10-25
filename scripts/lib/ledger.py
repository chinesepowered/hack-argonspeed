"""One runs/ledger.jsonl line for a finished agent session.

    python3 scripts/lib/ledger.py <run dir> <problem> <started, UTC ISO> <qwen exit code>

Reads the session's stream-json transcript and its check counter, and the problem's attempts/
for the checks it made, so the ledger records what each session cost and what it found.
"""

import glob
import json
import os
import sys
from datetime import datetime, timezone

run, problem, started, rc = sys.argv[1:5]
root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

events = []
with open(os.path.join(run, "transcript.jsonl"), errors="replace") as f:
    for line in f:
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
result = next((e for e in reversed(events) if e.get("type") == "result"), {})
model = next((e.get("model") for e in events if e.get("type") == "system" and e.get("model")), None)

# This session's attempts: archived since it started (names begin with a UTC timestamp).
since = started.replace("-", "").replace(":", "")
attempts = []
for path in sorted(glob.glob(os.path.join(root, "problems", problem, "attempts", "*.json"))):
    name = os.path.basename(path)
    if name[:16] < since[:16]:
        continue
    d = json.load(open(path))
    r = d.get("result") or {}
    attempts.append({"job": d.get("id"), "passed": r.get("passed"), "speedup": r.get("speedup")})
passing = [a["speedup"] for a in attempts if a["passed"] and a["speedup"]]

with open(os.path.join(run, "checks_used")) as f:
    checks_used = int(f.read().strip() or 0)
error = result.get("error") if result.get("is_error") else None
if isinstance(error, dict):
    error = error.get("message")

print(json.dumps({
    "problem": problem,
    "started": started,
    "finished": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "run": os.path.relpath(run, root),
    "model": model,
    "exit_code": int(rc),
    "outcome": result.get("subtype"),
    "error": error,
    "turns": result.get("num_turns"),
    "duration_s": round(result["duration_ms"] / 1000) if result.get("duration_ms") else None,
    "usage": result.get("usage"),
    "checks_used": checks_used,
    "attempts": attempts,
    "best_speedup": max(passing) if passing else None,
}))
