#!/usr/bin/env bash
# Everything a fresh machine or session needs, and safe to rerun: okc (the challenge's CLI),
# Qwen Code, google-genai in .venv for the hosted harness, SGLang's source at the judge's commit
# (vendor/sglang, for the agent to read), and any of the five problems not yet in problems/ (okc
# init would overwrite a submission.py).
#
#   scripts/setup.sh
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
qwen_version=0.26.1
genai_version=2.33.0
sglang_commit=a55ab7d5ae1bba59ac351e55026fe7f7644ecc5f
problems=(muse_bf16_proj muse_attention_decode muse_moe_w4a16 muse_decode_layer muse_prefill_layer)
okc=$HOME/.okc/bin/okc
if [ -f "$root/.env" ]; then set -a; . "$root/.env"; set +a; fi

if [ ! -x "$okc" ]; then
  curl -fsSL https://openkernelchallenge.dev/install.sh | OKC_NO_MODIFY_PATH=1 sh
fi
echo "okc: $("$okc" version)"

if [ "$(qwen --version 2>/dev/null)" != "$qwen_version" ]; then
  npm install -g "@qwen-code/qwen-code@$qwen_version"
fi
echo "qwen: $(qwen --version)"

# google-genai for the hosted harness (managed/agent.py, through scripts/managed.sh)
if ! "$root/.venv/bin/python" -c "import google.genai" 2> /dev/null; then
  python3 -m venv "$root/.venv"
  "$root/.venv/bin/pip" install -q "google-genai==$genai_version"
fi
echo "google-genai: $("$root/.venv/bin/python" -c 'import google.genai as g; print(g.__version__)')"

src=$root/vendor/sglang
if [ "$(git -C "$src" rev-parse HEAD 2>/dev/null)" != "$sglang_commit" ]; then
  mkdir -p "$src"
  git -C "$src" init -q
  git -C "$src" remote get-url origin > /dev/null 2>&1 ||
    git -C "$src" remote add origin https://github.com/sgl-project/sglang
  GIT_LFS_SKIP_SMUDGE=1 git -C "$src" fetch -q --depth 1 origin "$sglang_commit"
  GIT_LFS_SKIP_SMUDGE=1 git -C "$src" checkout -q FETCH_HEAD
fi
echo "sglang: $(git -C "$src" log -1 --format='%h %s')"

for p in "${problems[@]}"; do
  if [ ! -f "$root/problems/$p/TASK.md" ]; then
    (cd "$root/problems" && "$okc" init "$p" "$p")
  fi
done
echo "problems: ${problems[*]}"

[ -n "${GEMINI_API_KEY:-}" ] || echo "GEMINI_API_KEY isn't set: put it in .env (see .env.example), then run scripts/smoke.sh"
[ -n "${OKC_TOKEN:-}" ] || echo "OKC_TOKEN isn't set: put it in .env (see .env.example)"
