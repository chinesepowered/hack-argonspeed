#!/usr/bin/env bash
# One headless Qwen Code session (Gemini 4 Argon) on a problem, or one per problem in parallel.
#
#   scripts/agent.sh <problem> [--checks N] [--hours H]
#   scripts/agent.sh all [--checks N] [--hours H]
#
# --checks is the session's judge budget (default 4, never more than the problem has left
# today); --hours its wall-clock limit (default 2). Needs GEMINI_API_KEY and OKC_TOKEN, from the
# environment or a .env at the repo root. Each session writes runs/<problem>/<time>/ and adds a
# line to runs/ledger.jsonl.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
problems=(muse_bf16_proj muse_attention_decode muse_moe_w4a16 muse_decode_layer muse_prefill_layer)
usage="usage: scripts/agent.sh <problem|all> [--checks N] [--hours H]"

problem=${1:?$usage}
shift
checks=4 hours=2
while [ $# -gt 0 ]; do
  case $1 in
    --checks) checks=$2; shift 2 ;;
    --hours) hours=$2; shift 2 ;;
    *) echo "$usage" >&2; exit 2 ;;
  esac
done

if [ "$problem" = all ]; then
  for p in "${problems[@]}"; do "$0" "$p" --checks "$checks" --hours "$hours" & done
  wait
  exit 0
fi
[ -d "$root/problems/$problem" ] || { echo "no problem $problem; one of: ${problems[*]}" >&2; exit 2; }

if [ -f "$root/.env" ]; then set -a; . "$root/.env"; set +a; fi
: "${GEMINI_API_KEY:?set GEMINI_API_KEY in the environment or .env}"
: "${OKC_TOKEN:?set OKC_TOKEN in the environment or .env}"

left=$("$HOME/.okc/bin/okc" problems --json | python3 -c 'import json, sys
print(next(p["limits"]["checks"]["left"] for p in json.load(sys.stdin)["problems"] if p["name"] == sys.argv[1]))' "$problem")
[ "$checks" -le "$left" ] || checks=$left
[ "$checks" -gt 0 ] || { echo "$problem: no checks left today (they reset at 00:00 UTC)" >&2; exit 1; }

run=$root/runs/$problem/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$run"
echo 0 > "$run/checks_used"
echo "$problem: session in ${run#"$root"/}, $checks checks, ${hours}h"

prompt="This session works on $problem. You have $checks judge checks (okc check enforces the \
budget) and about $hours hours. Follow ../AGENTS.md, starting with NOTES.md. Aim for the \
largest real speedup over SGLang, leave submission.py at your best passing version, and finish \
by updating NOTES.md."

. "$root/scripts/lib/qwen.sh"
started=$(date -u +%FT%TZ)
cd "$root/problems/$problem"
rc=0
env "${qwen_env[@]}" PATH="$root/scripts/bin:$PATH" OKC_SESSION_DIR="$run" OKC_CHECK_BUDGET="$checks" \
  qwen "$prompt" "${qwen_flags[@]}" --max-wall-time "${hours}h" \
  --include-directories "$root/vendor/sglang/python/sglang" --include-directories "$root/docs" \
  > "$run/transcript.jsonl" 2> "$run/stderr.log" || rc=$?

python3 "$root/scripts/lib/ledger.py" "$run" "$problem" "$started" "$rc" >> "$root/runs/ledger.jsonl"
tail -n 1 "$root/runs/ledger.jsonl"
