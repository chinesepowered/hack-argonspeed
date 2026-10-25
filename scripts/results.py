#!/usr/bin/env python3
"""results/README.md and results/results.json: what the agents achieved and what it cost, as the
judge measured it. Numbers only, never kernels, techniques or job ids (a job's record holds its
code), so results/ can be published.

    scripts/results.py
"""

import glob
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OKC = os.path.expanduser("~/.okc/bin/okc")
PROBLEMS = ["muse_bf16_proj", "muse_attention_decode", "muse_moe_w4a16", "muse_decode_layer", "muse_prefill_layer"]
PRICE_INPUT, PRICE_CACHED, PRICE_OUTPUT = 2.00, 0.10, 10.00  # Argon's introductory $ per 1M tokens


def load_env():
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path):
            key, sep, value = line.strip().partition("=")
            if sep and not key.startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def okc_json(*args):
    with tempfile.TemporaryDirectory() as tmp:  # okc status leaves the job's profile where it runs
        return json.loads(subprocess.run([OKC, *args, "--json"], capture_output=True, text=True, check=True,
                                         cwd=tmp).stdout)


def checks(problem, jobs):
    """Every check of the problem, oldest first: (time, passed, speedup, interval). From the archive
    okc check writes, plus the finished checks the judge lists after the newest archived one: the
    ones no sync has brought back yet. (Earlier checks it lists that aren't archived are ours, not the
    agents': SGLang's own kernel, the smoke test.)"""
    out, seen, latest = [], set(), None
    for path in sorted(glob.glob(os.path.join(ROOT, "problems", problem, "attempts", "*.json"))):
        d = json.load(open(path))
        r = d.get("result") or {}
        seen.add(d.get("id"))
        stamp = os.path.basename(path)[:16]
        when = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        latest = max(latest or when, when)
        out.append({"time": when.strftime("%Y-%m-%d %H:%M"), "passed": bool(r.get("passed")),
                    "speedup": r.get("speedup"), "interval": r.get("speedup_ci")})
    for job in jobs:
        when = datetime.fromtimestamp(job["submitted_at"], timezone.utc)
        if (job["problem"] == problem and job["mode"] == "check" and job["status"] == "done"
                and job["job_id"] not in seen and (latest is None or when > latest)):
            r = okc_json("status", job["job_id"]).get("result") or {}
            out.append({"time": when.strftime("%Y-%m-%d %H:%M"), "passed": bool(r.get("passed")),
                        "speedup": r.get("speedup"), "interval": r.get("speedup_ci")})
    return sorted(out, key=lambda c: c["time"])


def spend():
    hosted = {"runs": 0, "input": 0, "cached": 0, "output": 0, "cost": 0.0}
    state = os.path.join(ROOT, "managed", "state.json")
    for run in (json.load(open(state))["runs"].values() if os.path.exists(state) else []):
        u = run.get("usage") or {}
        hosted["runs"] += 1
        hosted["input"] += u.get("total_input_tokens") or 0
        hosted["cached"] += u.get("total_cached_tokens") or 0
        hosted["output"] += (u.get("total_output_tokens") or 0) + (u.get("total_thought_tokens") or 0)
        hosted["cost"] += run.get("cost_usd") or 0
    local = {"sessions": 0, "input": 0, "cached": 0, "output": 0, "cost": 0.0}
    ledger = os.path.join(ROOT, "runs", "ledger.jsonl")
    for line in (open(ledger) if os.path.exists(ledger) else []):
        s = json.loads(line)
        if s.get("harness", "qwen") != "qwen":
            continue
        u = s.get("usage") or {}
        inp, cached, out = u.get("input_tokens") or 0, u.get("cache_read_input_tokens") or 0, u.get("output_tokens") or 0
        out += max(0, (u.get("total_tokens") or 0) - inp - out)  # thinking
        local["sessions"] += 1
        local["input"] += inp
        local["cached"] += cached
        local["output"] += out
        local["cost"] += ((inp - cached) * PRICE_INPUT + cached * PRICE_CACHED + out * PRICE_OUTPUT) / 1e6
    return hosted, local


def main():
    load_env()
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows, data = [], {"generated": generated, "problems": {}}
    jobs = okc_json("jobs")
    for p in PROBLEMS:
        cs = checks(p, jobs)
        passing = [c for c in cs if c["passed"] and c["speedup"]]
        best = max(passing, key=lambda c: c["speedup"]) if passing else None
        board = okc_json("leaderboard", p)
        you, leader = board.get("you"), board.get("leader") or {}
        you = {k: v for k, v in you.items() if k != "team"} if you else you  # numbers, not names
        data["problems"][p] = {"checks": len(cs), "passing": len(passing), "best": best, "history": cs,
                               "board": you, "leader": leader.get("speedup"), "teams": board.get("ranked")}
        best_s = f"{best['speedup']:.3f}x" if best else "-"
        interval = f"{best['interval'][0]:.3f}-{best['interval'][1]:.3f}" if best and best["interval"] else "-"
        ours = f"#{you['rank']} at {you['speedup']:.3f}x" if you else "none yet"
        lead = f"{leader['speedup']:.3f}x of {board.get('ranked')}" if leader.get("speedup") else "-"
        rows.append(f"| `{p}` | {best_s} | {interval} | {len(passing)} of {len(cs)} | {ours} | {lead} |")
    hosted, local = spend()
    data["spend"] = {"hosted": hosted, "local": local}

    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    with open(os.path.join(ROOT, "results", "results.json"), "w") as f:
        json.dump(data, f, indent=1)
    total_in = hosted["input"] + local["input"]
    cached = hosted["cached"] + local["cached"]
    md = [
        "# Results",
        "",
        f"Generated {generated} by `scripts/results.py` from the judge's records and the harness's own",
        "ledger. Every speedup is the judge's measurement on an H200 against SGLang's kernel for the same",
        "problem; numbers only, no kernels or techniques.",
        "",
        "## Speedup over SGLang",
        "",
        "| problem | best check | 95% interval | checks passing | our board position | board leader |",
        "|---|---|---|---|---|---|",
        *rows,
        "",
        "## What it took",
        "",
        f"- Hosted runs (Gemini 4 Argon as Google's managed Antigravity agent): {hosted['runs']}",
        f"- Local sessions (Qwen Code): {local['sessions']}",
        f"- Tokens: {total_in:,} input ({100 * cached / total_in if total_in else 0:.0f}% cached),"
        f" {hosted['output'] + local['output']:,} output and thinking",
        f"- Estimated spend at Argon's introductory prices: ${hosted['cost'] + local['cost']:.2f}",
        "",
        "## Every check, oldest first",
        "",
    ]
    for p in PROBLEMS:
        cs = data["problems"][p]["history"]
        if cs:
            best = 0.0
            md += [f"### `{p}`", "", "| time (UTC) | result | best so far |", "|---|---|---|"]
            for c in cs:
                if c["passed"] and c["speedup"]:
                    best = max(best, c["speedup"])
                result = f"{c['speedup']:.3f}x" if c["passed"] and c["speedup"] else "failed"
                md.append(f"| {c['time']} | {result} | {f'{best:.3f}x' if best else '-'} |")
            md.append("")
    md += impact(data)
    with open(os.path.join(ROOT, "results", "README.md"), "w") as f:
        f.write("\n".join(md))
    print("\n".join(md[:20]))


def impact(data):
    """The 'what it's worth at scale' section: results/impact.json's assumptions applied to the
    decode-layer speedup, ours and the board leader's, with the arithmetic shown."""
    a = {k: v["value"] for k, v in json.load(open(os.path.join(ROOT, "results", "impact.json"))).items() if k != "note"}
    layer = data["problems"]["muse_decode_layer"]
    cases = [("the board leader's today", layer["leader"])]
    if layer["best"]:
        cases.insert(0, ("ours", layer["best"]["speedup"]))
    md = ["## What it's worth at scale (illustrative)", "",
          "A decode-layer speedup s saves a fraction f = g (1 - 1/s) of each decode step, where g is the share",
          f"of the step spent in the layer's kernels (g = {a['layer_share_of_step']}). The other inputs are in",
          "`results/impact.json`, with where each comes from; they are assumptions, not measurements.", "",
          "| decode-layer speedup | step time saved | GPU-hours saved per year | at $/GPU-hour | wait time saved per year |",
          "|---|---|---|---|---|"]
    for label, s in cases:
        f = a["layer_share_of_step"] * (1 - 1 / s)
        wait_years = a["requests_per_day"] * a["output_tokens_per_request"] * a["ms_per_output_token"] * f / (1000 * 86400)
        for gpus in a["gpus"]:
            hours = gpus * 8760 * a["utilization"] * a["decode_share_of_serving"] * f
            md.append(f"| {s:.2f}x ({label}), {gpus:,} GPUs | {100 * f:.0f}% | {hours / 1e6:,.1f}M |"
                      f" ${hours * a['gpu_hour_usd'] / 1e6:,.0f}M | {wait_years:,.0f} years |")
    return md + [""]


if __name__ == "__main__":
    main()
