# Argon Speed

**AI that makes itself faster.** Five Gemini 4 Argon agents work around the clock on Google's
Managed Agents. Each one optimizes one GPU kernel of a frontier model's serving stack. Today
that stack is Muse Spark Open's, an 816B-parameter MoE served by SGLang, and the kernels are the
five problems of the [Open Kernel Challenge](https://openkernelchallenge.dev). The challenge's
independent judge measures every result on a real H200 against SGLang's own production kernels.
Nobody's laptop is involved, and we have no GPU of our own.

Point the same loop at Argon's own serving and every speedup makes the next iteration cheaper and
faster, so the rate of improvement compounds. That's the speed in Argon Speed.

**Pitch:** [slides](pitch/slides.html) (open in a browser, arrow keys to move) ·
[2-minute narrated video](pitch/argon-speed.mp4)

## How we use Gemini 4 Argon: million-token engineering

- **The whole stack in context.** Each run gives Argon a 1.5M-token budget for:
  - SGLang's source at the judge's exact commit;
  - the challenge's spec, tests and judge environment;
  - the judge's per-shape profiles with speed-of-light bounds;
  - its own lab notebook from earlier runs.

  So far that's 31M tokens over 28 hosted runs, 93% of them served from cache.
- **Engineering, not chat.** Argon runs the whole loop itself:
  - designs a change and writes the CUDA or Triton;
  - compiles it for the H200 in its sandbox before spending a judge check;
  - reads the judge's profile and records what it learned.

  In one session it turned a design spec into a 742-line CUDA kernel that passed every hidden test
  on its first check, then profiled it and fixed what held it back.
- **Cheap enough to leave on.** $8.98 for all 28 hosted runs so far, thanks to the cache. All five
  agents around the clock come to about $66 a day.

## How we use Managed Agents: a kernel team that never sleeps

```
Google trigger, hourly per problem (staggered :05 :17 :29 :41 :53)
  └─ Antigravity agent (gemini-4-argon) in that problem's persistent sandbox
       ├─ bootstrap: the judge's CLI, CUDA 13.4 nvcc, SGLang's source (all under /workspace)
       ├─ reads NOTES.md, takes the next step: design, implement, compile, check, learn
       ├─ okc check ──────────> the judge: hidden tests + CUDA-graph timing on an H200 vs SGLang
       └─ archives the check, updates NOTES.md for the next run
we sync results back (Files API) ─> scripts/results.py ─> results/, the deck and the video
```

- **One persistent sandbox per problem.** Five agents run in parallel, never two on the same
  problem. `/workspace` persists, so each run picks up where the last one stopped.
- **Triggers make it 24/7.** A run lasts at most 10 minutes, so the work is a long chain of short
  runs that hand over through each problem's `NOTES.md`. A judge check that outlasts a run is
  collected by the next one.
- **Secrets stay out of the sandbox.** The judge's token is a Managed Agents credential that the
  egress proxy attaches only to requests for the judge's domain. Inside the sandbox, the agent's
  CLI runs with a stand-in value.
- **Guardrails in the agent's CLI** (`scripts/bin/okc`):
  - read and check commands only;
  - a check budget per time window (the judge allows 20 checks per problem per day);
  - no check for code that doesn't compile;
  - identical code returns its earlier result for free;
  - every checked kernel is archived with its result.

  Scored runs are a person's decision (`scripts/submit.sh`). The playbook every run follows,
  `problems/AGENTS.md`, carries the challenge's rules against gaming the judge.
- **Every token accounted for.** Each interaction's tokens and cost go into `runs/ledger.jsonl`,
  with an alert at $25.

## Results

As of 2:50 pm PT, Oct 25. On the judge's leaderboards within its first afternoon, **faster than SGLang on all five
problems**, #588 of 1,145 teams overall. Speedups are against SGLang's own kernel for the same
problem, on an H200.

| problem | SGLang's distance from speed of light | our best check | our scored run | leaderboard |
|---|---|---|---|---|
| Dense BF16 projections (`muse_bf16_proj`) | 2.5x | 1.09x | 1.09x | #916 of 1,002 |
| Attention decode, paged FP8 cache (`muse_attention_decode`) | 11.4x | 1.26x | 1.13x | #685 of 734 |
| Routed experts, NVFP4 weights (`muse_moe_w4a16`) | 4.4x | 1.32x | 1.32x | #559 of 783 |
| Whole decoder layer, decode (`muse_decode_layer`) | 3.9x | 1.23x | 1.23x | #524 of 683 |
| Whole decoder layer, prefill (`muse_prefill_layer`) | 3.0x | 1.03x | 1.02x | #364 of 420 |

**What it's worth at scale.** Our decode-layer speedup of 1.23x makes each decode step about 14%
faster. On 50,000 GPUs that's about $86M a year, and it saves users about 12,787 years of waiting
every year. The assumptions are in `results/impact.json`; they're illustrative, not measured.

Every check, its 95% interval and the cost are in [results/README.md](results/README.md).

The kernels and the agents' lab notebooks aren't in this repo: we're competing in the challenge
with them, and kernel submissions close Nov 4.

## Running it

```bash
scripts/setup.sh                       # the judge's CLI, google-genai, SGLang's source, the five problems
cp .env.example .env                   # GEMINI_API_KEY and OKC_TOKEN
scripts/managed.sh credential          # store the judge's token as a Managed Agents credential
scripts/managed.sh schedule all --every 60 --checks 1 --now   # a trigger and a sandbox per problem
scripts/managed.sh status              # schedules, latest runs, tokens and spend
scripts/managed.sh sync all && scripts/results.py               # pull results back, regenerate results/
scripts/slides.py && scripts/video.py  # the deck, and the video narrated with ElevenLabs
```

| path | what it is |
|---|---|
| `managed/agent.py` | the hosted harness: credential, sandboxes, triggers, one-off runs, sync, spend |
| `managed/bootstrap.sh` | runs at the start of every run in the sandbox: toolchain, the agent's CLI and its budget |
| `scripts/bin/okc` | the agent's judge CLI, with the guardrails above |
| `problems/AGENTS.md` | the playbook every run follows |
| `scripts/` | setup, scored runs, results, the deck and video generators, and a local Qwen Code fallback harness |
| `pitch/` | the slides and the narrated video |
| `results/` | the judge's numbers and the impact model |
| `runs/ledger.jsonl` | every run's tokens and cost |
