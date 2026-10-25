#!/usr/bin/env bash
# A scored run, made by a person: shows how this exact code did when it was checked, asks, then
# submits it with the real okc (the agent's okc refuses to).
#
#   scripts/submit.sh <problem> [file]     (file defaults to the problem's submission.py)
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
problem=${1:?usage: scripts/submit.sh <problem> [file]}
dir=$root/problems/$problem
file=$(realpath "${2:-$dir/submission.py}")
[ -f "$file" ] || { echo "no file $file" >&2; exit 2; }
if [ -f "$root/.env" ]; then set -a; . "$root/.env"; set +a; fi
: "${OKC_TOKEN:?set OKC_TOKEN in the environment or .env}"

# Checks of identical code, newest first.
python3 - "$file" "$dir/attempts" <<'EOF'
import glob, hashlib, json, os, sys
digest = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
want = digest(sys.argv[1])
same = [p for p in sorted(glob.glob(os.path.join(sys.argv[2], "*.py")), reverse=True) if digest(p) == want]
if not same:
    print("This exact code was never checked: a scored run would be its first test.")
for p in same:
    res = p[:-3] + ".json"
    if not os.path.exists(res):
        print(f"checked as {os.path.basename(p)}, result not saved (okc status <job>)")
        continue
    r = json.load(open(res)).get("result") or {}
    ci = r.get("speedup_ci") or [None, None]
    print(f"checked as {os.path.basename(p)}: passed={r.get('passed')} speedup={r.get('speedup')}"
          f" 95%=[{ci[0]}, {ci[1]}] flagged={((r.get('checks') or {}).get('flagged'))}")
EOF
"$HOME/.okc/bin/okc" problems | grep -E "^$problem " || true

read -r -p "Submit ${file#"$root"/} as a scored run on $problem? [y/N] " answer
[ "$answer" = y ] || { echo "not submitted"; exit 1; }
"$HOME/.okc/bin/okc" submit "$problem" "$file"
