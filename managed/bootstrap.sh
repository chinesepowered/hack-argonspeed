#!/usr/bin/env bash
# Runs inside a problem's hosted sandbox at the start of every scheduled run; safe to rerun.
# Everything lives under /workspace, the part of the sandbox that persists between runs: okc, the
# team's wrapper around it with this run's check budget, the judge's CUDA compiler, and SGLang's
# source at the judge's commit.
#
#   bash /workspace/hack-argmu/managed/bootstrap.sh <window minutes> <checks per window>
set -euo pipefail

root=/workspace/hack-argmu
real=/workspace/.okc/bin/okc
window=${1:?usage: bootstrap.sh <window minutes> <checks per window>}
checks=${2:?usage: bootstrap.sh <window minutes> <checks per window>}
sglang_commit=a55ab7d5ae1bba59ac351e55026fe7f7644ecc5f

if [ ! -x "$real" ]; then
  curl -fsSL https://openkernelchallenge.dev/install.sh |
    OKC_INSTALL_DIR="$(dirname "$real")" OKC_NO_MODIFY_PATH=1 sh > /dev/null
fi

# okc on PATH is the wrapper, with the schedule's budget: checks per window of wall clock. Its
# OKC_TOKEN is a stand-in, not a secret: okc wants one set, and the sandbox's egress proxy puts the
# team's real token on every request to the judge.
cat > /usr/local/bin/okc <<EOF
#!/bin/sh
export OKC_REAL=$real OKC_TOKEN=kc_proxy_injected OKC_BUDGET_WINDOW_MINUTES=$window OKC_CHECK_BUDGET=$checks
exec $root/scripts/bin/okc "\$@"
EOF
chmod +x /usr/local/bin/okc "$root/scripts/bin/okc"

# The judge's nvcc (CUDA 13.4.92): there's no GPU here to run a kernel, but compiling one catches the
# errors that would otherwise cost a check.
cuda=/workspace/.cuda/nvidia/cu13
if [ ! -x "$cuda/bin/nvcc" ]; then
  python3 -m pip install -q --target /workspace/.cuda nvidia-cuda-nvcc==13.4.92 nvidia-cuda-runtime==13.4.92
fi
if ! command -v g++ > /dev/null; then
  (apt-get update -qq && apt-get install -y -qq g++) > /dev/null 2>&1
fi
cat > /usr/local/bin/nvcc <<EOF
#!/bin/sh
PATH=$cuda/bin:\$PATH exec $cuda/bin/nvcc -I$cuda/include "\$@"
EOF
chmod +x /usr/local/bin/nvcc

src=$root/vendor/sglang
if [ "$(git -C "$src" rev-parse HEAD 2>/dev/null)" != "$sglang_commit" ]; then
  mkdir -p "$src"
  git -C "$src" init -q
  git -C "$src" remote get-url origin > /dev/null 2>&1 ||
    git -C "$src" remote add origin https://github.com/sgl-project/sglang
  git -C "$src" fetch -q --depth 1 origin "$sglang_commit"
  git -C "$src" checkout -q FETCH_HEAD
fi

echo "ready: okc $("$real" version | awk '{print $2}') signed in as $(okc whoami)," \
  "$checks check(s) per $window minutes, sglang $(git -C "$src" rev-parse --short HEAD)," \
  "nvcc $(nvcc --version | sed -n 's/.*release \([0-9.]*\).*/\1/p')." \
  "Compile your CUDA for sm_90a with nvcc (nvcc -arch=sm_90a -c kernel.cu) before you spend a check."
