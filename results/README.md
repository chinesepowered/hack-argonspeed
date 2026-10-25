# Results

Generated 2026-10-25 22:39 UTC by `scripts/results.py` from the judge's records and the harness's own
ledger. Every speedup is the judge's measurement on an H200 against SGLang's kernel for the same
problem; numbers only, no kernels or techniques.

## Speedup over SGLang

| problem | best check | 95% interval | checks passing | our board position | board leader |
|---|---|---|---|---|---|
| `muse_bf16_proj` | 1.092x | 1.075-1.108 | 5 of 7 | #921 at 1.093x | 1.610x of 1007 |
| `muse_attention_decode` | 1.260x | 1.241-1.283 | 4 of 4 | #693 at 1.130x | 2.910x of 742 |
| `muse_moe_w4a16` | 1.323x | 1.303-1.343 | 4 of 6 | #568 at 1.322x | 2.548x of 791 |
| `muse_decode_layer` | 1.226x | 1.207-1.244 | 2 of 3 | #534 at 1.228x | 2.312x of 690 |
| `muse_prefill_layer` | 1.062x | 1.046-1.078 | 2 of 3 | #368 at 1.024x | 1.963x of 425 |

## What it took

- Hosted runs (Gemini 4 Argon as Google's managed Antigravity agent): 32
- Local sessions (Qwen Code): 0
- Tokens: 57,984,048 input (94% cached), 559,966 output and thinking
- Estimated spend at Argon's introductory prices: $18.12

## Every check, oldest first

### `muse_bf16_proj`

| time (UTC) | result | best so far |
|---|---|---|
| 2026-10-25 18:57 | 0.663x | 0.663x |
| 2026-10-25 19:25 | failed | 0.663x |
| 2026-10-25 20:06 | 1.072x | 1.072x |
| 2026-10-25 20:13 | 0.938x | 1.072x |
| 2026-10-25 20:17 | 1.092x | 1.092x |
| 2026-10-25 21:16 | 0.943x | 1.092x |
| 2026-10-25 22:13 | failed | 1.092x |

### `muse_attention_decode`

| time (UTC) | result | best so far |
|---|---|---|
| 2026-10-25 19:42 | 1.123x | 1.123x |
| 2026-10-25 20:25 | 0.770x | 1.123x |
| 2026-10-25 20:38 | 1.187x | 1.187x |
| 2026-10-25 20:52 | 1.260x | 1.260x |

### `muse_moe_w4a16`

| time (UTC) | result | best so far |
|---|---|---|
| 2026-10-25 19:55 | 1.323x | 1.323x |
| 2026-10-25 20:26 | failed | 1.323x |
| 2026-10-25 20:29 | 1.221x | 1.323x |
| 2026-10-25 20:40 | 1.237x | 1.323x |
| 2026-10-25 21:46 | failed | 1.323x |
| 2026-10-25 22:29 | 1.307x | 1.323x |

### `muse_decode_layer`

| time (UTC) | result | best so far |
|---|---|---|
| 2026-10-25 19:51 | failed | - |
| 2026-10-25 19:59 | 1.226x | 1.226x |
| 2026-10-25 21:51 | 1.156x | 1.226x |

### `muse_prefill_layer`

| time (UTC) | result | best so far |
|---|---|---|
| 2026-10-25 20:07 | failed | - |
| 2026-10-25 20:21 | 1.033x | 1.033x |
| 2026-10-25 21:42 | 1.062x | 1.062x |

## What it's worth at scale (illustrative)

A decode-layer speedup s saves a fraction f = g (1 - 1/s) of each decode step, where g is the share
of the step spent in the layer's kernels (g = 0.75). The other inputs are in
`results/impact.json`, with where each comes from; they are assumptions, not measurements.

| decode-layer speedup | step time saved | GPU-hours saved per year | at $/GPU-hour | wait time saved per year |
|---|---|---|---|---|
| 1.23x (ours), 10,000 GPUs | 14% | 4.4M | $17M | 12,787 years |
| 1.23x (ours), 50,000 GPUs | 14% | 21.8M | $86M | 12,787 years |
| 1.23x (ours), 100,000 GPUs | 14% | 43.6M | $172M | 12,787 years |
| 2.31x (the board leader's today), 10,000 GPUs | 43% | 13.4M | $53M | 39,413 years |
| 2.31x (the board leader's today), 50,000 GPUs | 43% | 67.1M | $265M | 39,413 years |
| 2.31x (the board leader's today), 100,000 GPUs | 43% | 134.2M | $530M | 39,413 years |
