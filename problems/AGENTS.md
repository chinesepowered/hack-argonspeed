# Working on a kernel problem

You're making one problem's `submission.py` faster than SGLang's kernel (`baseline.py`) on an
NVIDIA H200, with results the judge accepts. Your working directory is that problem's folder.
Its `TASK.md` and `AGENTS.md` are the challenge's own spec and notes; this file is the team's.

## Where you are

- There's no GPU here. The only way to run code is the judge: `okc check` sends a file to one
  H200 running SGLang's own image and returns the tests' results, each shape's time against
  SGLang's, and a profile. A check takes one to ten minutes.
- Checks are scarce: 20 per problem per day, shared by every session, and this session has a
  budget that `okc check` enforces and reports. Treat each check like an hour of a kernel
  engineer's time. Think, design and review before you check. Never spend a check on a typo,
  a wrong signature or a shape mistake you could have found by reading.
- Checking code identical to an earlier check is free: the judge returns the earlier result.
- You can't run `okc submit`: a person decides which runs are scored. When a passing check
  beats the best run so far, mark it in NOTES.md as a submission candidate.

## Files

In this folder:

- `TASK.md`: the problem, its shapes, tolerances, how a run is timed, and the rules. Read it
  first and follow it exactly.
- `AGENTS.md`: the challenge's notes for agents.
- `reference.py` and `checks.py`: exactly what the judge checks. Its tests include harder
  shapes than the scored ones.
- `baseline.py`: SGLang's kernel, the one you race. `nvfp4.py`: the NVFP4 helper, on the
  NVFP4 problems.
- `submission.py`: your kernel. Keep its first line.
- `NOTES.md`: the lab notebook. Read it before anything else and update it after every check.
- `attempts/`: every checked file with its full result JSON, written by `okc check`. Don't
  edit it.
- `profiles/`: the judge's profile of each passing run, `<file>.<job>.txt`: SGLang's time,
  yours and the speed-of-light bound for every scored shape, then the kernels that took the
  time. `baseline.<job>.txt` profiles SGLang's own kernel on this problem.

Elsewhere, read-only:

- `../specs/`: the team's design specs. NOTES.md says which ones apply to this problem; when
  one does, it's the starting point, and its measured numbers are what to beat.
- `../../vendor/sglang/python/sglang/`: SGLang at the exact commit the judge runs. Read the
  source of whatever `baseline.py` imports (for example `kernels/ops/muse_spark_v12/` and
  `kernels/ops/moe/moe_wna16_marlin.py`) before you call it or try to beat it.
- `../../docs/judge-env.md`: the judge's exact versions. In short: torch 2.14.1 on CUDA 13.0,
  Triton 3.8.0, FlashInfer 0.7.0, CuTe DSL 4.8.0, TileLang 0.1.12, DeepGEMM, sgl-kernel 0.4.9,
  quack-kernels, FlashAttention 4 and CuPy. Nothing else is installed and there's no network.
  Write native CUDA with `torch.utils.cpp_extension.load_inline`; its compile time counts
  toward the run's 10-minute limit, though not toward your score.

## How to work

1. Read NOTES.md, TASK.md and AGENTS.md, then reference.py and baseline.py, then the profile
   of the best run so far (or SGLang's, `profiles/baseline.*.txt`).
2. Find where the time goes. In the profile, compare each shape's time with its speed-of-light
   bound: the biggest gaps on the heaviest loads are the opportunity. Pick one idea and write
   it in NOTES.md before coding: what changes, why it should be faster, the gain you expect.
3. Implement it in submission.py. Keep a correct path for every shape the tests use, including
   the harder test shapes TASK.md lists, not only the scored ones.
4. Review before you check: every output's shape and dtype, the CUDA-graph rules (no host
   syncs such as `.item()`, `.cpu()` or printing a tensor; no allocating or branching on input
   values), and every library call against its source in vendor/. Then run
   `python3 -m py_compile submission.py`, and compile your CUDA source with nvcc for sm_90a
   (`nvcc -arch=sm_90a -c kernel.cu`) when nvcc is available: there's no GPU to run it, but a
   compile error found here doesn't cost a check. Keeping the kernels in a source string that
   compiles on its own, apart from the torch binding, makes that easy.
5. `okc check submission.py`. It prints the job id first; if the command is cut off, run
   `okc status <job> --wait`.
6. Read the result: the first failing test and why, or each shape's time against SGLang's,
   then the profile. Record it in NOTES.md: the job id, the change, the result (the speedup
   with its 95% interval, or the failure) and what you learned. A gain inside the interval
   may be noise.
7. Repeat while you have checks and promising ideas. Before you finish, leave submission.py at
   the best passing version and end your NOTES.md entry with the best run so far (job id and
   speedup) and the ideas you'd try next, best first.

## Rules

These come from the challenge's rules and its final review. Breaking them gets the team's
runs removed.

- Real speedups only. Don't patch timing, read harness frames, touch the harness's I/O or
  secrets, edit loaded modules, import reference.py, start processes or use the network.
- Every call gets fresh inputs: never cache or replay outputs, or anything derived from the
  inputs. The only work allowed outside the timed call is repacking weights in `prepare()`.
- Weights stay at their precision: NVFP4 stays NVFP4 and BF16 stays BF16 (lossless
  compression and dequantizing inside your kernels are fine). The router may run as a BF16
  hi + lo pair with FP32 accumulation. Activations stay BF16 wherever SGLang keeps them BF16,
  the KV cache stays FP8, and attention's queries may round to FP8 E4M3 but nothing coarser.
- Attention attends to every key it should, the whole window or the whole context: no top-k,
  sparse or block-skipping attention, and no skipping values by their weight.
- The final review reruns the top entries on held-out data and on nearby shapes. Branching on
  shapes is fine, but keep every shape fast, not only the scored ones.
- Work only in this folder. Never print environment variables or tokens.

## Hints

- The judge replays each shape as a CUDA graph and starts every replay with a cold L2. At
  these sizes, launches and HBM traffic dominate; TASK.md's floors are the
  bandwidth-or-compute bound.
- Choose tile sizes and other configs deterministically per shape. Runtime autotuning would
  benchmark during graph capture.
- The image's libraries (FlashInfer, FA3 through sgl_kernel, DeepGEMM, CUTLASS and CuTe DSL,
  TileLang, quack) are fair building blocks. Fusing the work around them is often the
  cheapest win.
