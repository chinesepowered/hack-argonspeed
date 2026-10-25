#!/usr/bin/env bash
# First thing to run once GEMINI_API_KEY is set: can Argon, through Qwen Code in headless mode,
# run a command, read a file, edit it and run the command again? Uses no judge checks.
#
#   scripts/smoke.sh
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
if [ -f "$root/.env" ]; then set -a; . "$root/.env"; set +a; fi
: "${GEMINI_API_KEY:?set GEMINI_API_KEY in the environment or .env}"

work=$(mktemp -d)
cd "$work"
git init -q
printf 'def mean(xs):\n    return sum(xs) / (len(xs) - 1)\n' > stats.py
printf 'from stats import mean\nassert mean([1, 2, 3, 6]) == 3, mean([1, 2, 3, 6])\nprint("tests pass")\n' > test_stats.py

echo "smoke test in $work (a few minutes at most)"
. "$root/scripts/lib/qwen.sh"
rc=0
env "${qwen_env[@]}" qwen "Run python3 test_stats.py. It fails: find the bug in stats.py, fix it, \
and run the test again to confirm it passes. Then reply with one line saying what the bug was." \
  "${qwen_flags[@]}" --max-wall-time 10m --max-tool-calls 25 \
  > transcript.jsonl 2> stderr.log || rc=$?

python3 - transcript.jsonl "$rc" <<'EOF'
import json, sys
events = []
for line in open(sys.argv[1], errors="replace"):
    try:
        events.append(json.loads(line))
    except ValueError:
        pass
result = next((e for e in reversed(events) if e.get("type") == "result"), {})
model = next((e.get("model") for e in events if e.get("type") == "system" and e.get("model")), "?")
tools = [b.get("name") for e in events if e.get("type") == "assistant"
         for b in (e.get("message") or {}).get("content") or [] if b.get("type") == "tool_use"]
print(f"model {model} | exit {sys.argv[2]} | outcome {result.get('subtype')} | turns {result.get('num_turns')}"
      f" | usage {json.dumps(result.get('usage'))}")
print(f"tool calls ({len(tools)}): {', '.join(tools) or 'none'}")
if result.get("is_error"):
    print(f"error: {result.get('error')}")
print(f"answer: {(result.get('result') or '').strip()[:300]}")
EOF

if python3 test_stats.py > /dev/null 2>&1; then
  echo "PASS: Argon ran the test, edited stats.py and the test passes now"
else
  echo "FAIL: the test still fails. Transcript: $work/transcript.jsonl, stderr: $work/stderr.log"
  exit 1
fi
