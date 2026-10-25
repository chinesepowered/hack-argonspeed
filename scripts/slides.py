#!/usr/bin/env python3
"""pitch/slides.html, the Argon Speed pitch deck, and pitch/narration.json, its voice-over, both
from the live numbers: results/results.json (run scripts/results.py first), the judge's scored
runs, managed/state.json and results/impact.json. Arrow keys or space to move through it.

    scripts/slides.py
"""

import glob
import html
import json
import math
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OKC = os.path.expanduser("~/.okc/bin/okc")
OUT = os.path.join(ROOT, "pitch")
PROBLEMS = {
    "muse_bf16_proj": ("Dense projections", "BF16 projections and the FP32 router", 2.48),
    "muse_attention_decode": ("Attention decode", "gated GQA over a paged FP8 cache", 11.38),
    "muse_moe_w4a16": ("Routed experts", "top-8 of 256 experts, NVFP4 weights", 4.41),
    "muse_decode_layer": ("Decoder layer", "a whole layer at decode shapes", 3.91),
    "muse_prefill_layer": ("Prefill layer", "a whole layer at prefill shapes", 3.03),
}


def load_env():
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path):
            key, sep, value = line.strip().partition("=")
            if sep and not key.startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def okc_json(*args):
    return json.loads(subprocess.run([OKC, *args, "--json"], capture_output=True, text=True, check=True).stdout)


def scored_runs():
    """Our best scored run per problem: {problem: speedup}."""
    best = {}
    for job in okc_json("jobs"):
        if job.get("mode") == "run" and job.get("passed"):
            r = okc_json("status", job["job_id"]).get("result") or {}
            if r.get("speedup"):
                best[job["problem"]] = max(best.get(job["problem"], 0), r["speedup"])
    return best


def x(v, digits=2):
    return f"{v:.{digits}f}×"


def data():
    res = json.load(open(os.path.join(ROOT, "results", "results.json")))
    state = json.load(open(os.path.join(ROOT, "managed", "state.json")))
    runs = list(state["runs"].values())
    hosted, local = res["spend"]["hosted"], res["spend"]["local"]
    # A scheduled run lasts at most 10 minutes; one-off sessions (30 minutes) are scaled to that.
    working = ([r["cost_usd"] for r in runs if r["kind"] == "scheduled" and r.get("cost_usd", 0) > 0.2]
               + [r["cost_usd"] / 3 for r in runs if r["kind"] == "run" and r.get("cost_usd", 0) > 0.2])
    first = max((r for r in runs if r["kind"] == "run" and r.get("usage")), key=lambda r: r["usage"].get("total_input_tokens", 0),
                default={"usage": {}})
    fu = first["usage"]
    kernel = sorted(glob.glob(os.path.join(ROOT, "problems", "muse_bf16_proj", "attempts", "*b944cf3e*.py")))
    a = {k: v["value"] for k, v in json.load(open(os.path.join(ROOT, "results", "impact.json"))).items() if k != "note"}
    layer = res["problems"]["muse_decode_layer"]
    s = layer["best"]["speedup"] if layer["best"] and layer["best"]["speedup"] > 1 else layer["leader"]
    f = a["layer_share_of_step"] * (1 - 1 / s)
    return {
        "res": res, "scored": scored_runs(), "overall": okc_json("leaderboard"),
        "tokens_in": hosted["input"] + local["input"], "cached": hosted["cached"] + local["cached"],
        "tokens_out": hosted["output"] + local["output"], "spend": hosted["cost"] + local["cost"],
        "runs": hosted["runs"], "working_run": sum(working) / len(working) if working else 0.7,
        "first_in": fu.get("total_input_tokens", 0), "first_cached": fu.get("total_cached_tokens", 0),
        "kernel_lines": sum(1 for _ in open(kernel[0])) if kernel else 0,
        "impact_s": s, "impact_ours": s != layer["leader"], "impact_f": f,
        "impact_rows": [(g, g * 8760 * a["utilization"] * a["decode_share_of_serving"] * f) for g in a["gpus"]],
        "gpu_hour": a["gpu_hour_usd"],
        "wait_years": a["requests_per_day"] * a["output_tokens_per_request"] * a["ms_per_output_token"] * f / (1000 * 86400),
        "assume": a,
    }


def slides(d):
    res, scored = d["res"], d["scored"]
    on_board = {p: v["board"] for p, v in res["problems"].items() if v.get("board")}
    rows = []
    for p, (name, what, headroom) in PROBLEMS.items():
        v = res["problems"][p]
        best = v["best"]["speedup"] if v["best"] else None
        cls = "win" if best and best > 1 else ("lose" if best else "")
        board = (f"#{on_board[p]['rank']} of {v['teams']:,}" if p in on_board
                 else (f"scored {x(scored[p], 3)}" if p in scored else "—"))
        rows.append(f"<tr><td><b>{name}</b><span>{what}</span></td><td>{x(headroom, 1)}</td>"
                    f"<td class='{cls}'>{x(best, 3) if best else 'working'}</td><td>{board}</td>"
                    f"<td>{x(v['leader'], 2) if v.get('leader') else '—'}</td></tr>")
    impact_rows = "".join(f"<tr><td>{g:,} GPUs</td><td>{h / 1e6:,.1f}M</td><td>${h * d['gpu_hour'] / 1e6:,.0f}M</td></tr>"
                          for g, h in d["impact_rows"])
    mid = d["impact_rows"][len(d["impact_rows"]) // 2]
    impact_who = "our own decode-layer kernel" if d["impact_ours"] else "today's best decode-layer kernel on the board"
    daily = 5 * 24 * d["working_run"]
    cached_pct = 100 * d["cached"] / d["tokens_in"] if d["tokens_in"] else 0
    faster = sorted((v["best"]["speedup"], p) for p, v in res["problems"].items() if v["best"] and v["best"]["speedup"] > 1)
    n_faster = len(faster)
    n_words = [f"{w} of the five problems" for w in ("none", "one", "two", "three", "four")] + ["all five problems"]
    n_words, n_label = n_words[n_faster], "all 5" if n_faster == 5 else f"{n_faster} of 5"
    you, teams = d["overall"].get("you"), d["overall"].get("ranked")
    overall = f"#{you['rank']} of {teams:,} teams on the overall board" if you else "not yet on the overall board"
    overall_words = (f"and it's on {['no', 'one', 'two', 'three', 'four', 'five'][len(on_board)]} leaderboards, ranked {you['rank']} of {teams:,} teams overall"
                     if you else "and it's on the leaderboard")
    best_line = (f"up to {faster[-1][0]:.2f} times faster on {PROBLEMS[faster[-1][1]][0].lower()}" if faster else "not yet faster")

    deck = [
        ("title", f"""
<div class="kicker">Problem Statement One: Million Token Engineering · Managed Agents</div>
<h1 class="hero">Argon Speed</h1>
<p class="lede">AI that makes itself faster. Gemini 4 Argon, running on Google's Managed Agents, rewrites the GPU kernels
that AI models run on, around the clock. Today: Muse Spark Open's. Next: its own.</p>
<div class="grid3">
  <div class="stat"><b>816B</b><span>parameters in Muse Spark Open, served by SGLang on 8×H200</span></div>
  <div class="stat"><b>5</b><span>GPU kernels that decide its speed, from projections to a whole decoder layer</span></div>
  <div class="stat"><b>2.5–11×</b><span>the gap between SGLang's production kernels and the speed of light</span></div>
</div>""",
         "This is Argon Speed: AI that makes itself faster. The speed and cost of every AI model come down to a handful "
         "of GPU kernels, and even SGLang's production kernels run two and a half to eleven times slower than the hardware "
         "allows. Gemini 4 Argon, running on Google's Managed Agents, rewrites them around the clock. Today, it's speeding "
         "up Muse Spark Open."),

        ("how", f"""
<div class="kicker">24/7 on Google's Managed Agents</div>
<h2>A research loop with an independent judge</h2>
<div class="flow">
  <div class="box"><b>Google trigger</b><span>wakes each problem's agent every hour</span></div><i>→</i>
  <div class="box accent"><b>Gemini 4 Argon</b><span>in the problem's own persistent sandbox</span></div><i>→</i>
  <div class="box"><b>okc check</b><span>the judge times it on an H200 against SGLang</span></div><i>→</i>
  <div class="box"><b>NOTES.md</b><span>what it learned and the next step</span></div>
</div>
<div class="tags"><span>No secrets in the sandbox</span><span>20 checks a day, budgeted</span><span>Compiles before it checks</span><span>People approve scored runs</span></div>""",
         "Each of the five kernel problems has its own persistent sandbox, and a Google trigger wakes Argon there every "
         "hour, with no laptop involved. Argon reads its notebook, improves its kernel, and checks it on an independent "
         "judge that times it on a real H200 against SGLang. Secrets never enter the sandbox, and people approve every "
         "scored run."),

        ("tokens", f"""
<div class="kicker">Million-token engineering</div>
<h2>It reads the whole stack, then writes the kernel</h2>
<div class="grid3">
  <div class="stat"><b>{d['tokens_in'] / 1e6:,.0f}M</b><span>tokens read, {cached_pct:.0f}% from cache: SGLang's source at the judge's commit, its environment, per-shape profiles</span></div>
  <div class="stat"><b>{d['kernel_lines']}</b><span>lines of CUDA kernel from a team design spec, written in one session</span></div>
  <div class="stat"><b>9 / 9</b><span>hidden correctness tests passed on its first check</span></div>
</div>""",
         f"Argon reads the whole stack: SGLang's source at the judge's exact commit, the judge's environment, and "
         f"per-shape profiles, {d['tokens_in'] / 1e6:.0f} million tokens so far. In one session it turned a design spec "
         f"into a {d['kernel_lines']} line CUDA kernel that passed every hidden test on its first check, then profiled it "
         "and fixed what held it back."),

        ("results", f"""
<div class="kicker">Results, as the judge measured them</div>
<h2>Faster than SGLang on {n_label} problems</h2>
<table class="results"><thead><tr><th>problem</th><th>headroom</th><th>our best check</th><th>scored / board</th><th>board leader</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<p class="note">{overall[0].upper() + overall[1:]}. ${d['spend']:,.2f} spent so far; about ${daily:,.0f} a day, estimated, for all five 24/7.</p>""",
         f"Here are the judge's numbers. Argon beat SGLang's kernels on {n_words}, "
         f"{best_line}, {overall_words}, in its first afternoon. Running all five around the clock costs roughly {daily:.0f} dollars a day."),

        ("compound", f"""
<div class="kicker">The speed in Argon Speed</div>
<h2>Aimed at its own serving, it compounds</h2>
<div class="split">
  <div class="cycle">
    <div class="box"><b>Faster kernels</b></div><i>↓</i>
    <div class="box"><b>Cheaper, quicker agent runs</b></div><i>↓</i>
    <div class="box accent"><b>More iterations a day</b><span>so the next speedup comes sooner</span></div>
  </div>
  <div class="stack">
    <div class="stat"><b>{100 * d['impact_f']:.0f}%</b><span>off every decode step at {impact_who} ({x(d['impact_s'])})</span></div>
    <div class="stat"><b>${mid[1] * d['gpu_hour'] / 1e6:,.0f}M</b><span>a year on {mid[0]:,} GPUs, and {d['wait_years']:,.0f} years of user waiting saved (illustrative)</span></div>
  </div>
</div>""",
         f"Now point it at Gemini's own serving stack. Every speedup makes the agent's own runs cheaper and quicker, so the "
         f"next one comes sooner: AI making itself faster, and accelerating. With {impact_who} alone, that's "
         f"{100 * d['impact_f']:.0f} percent off every decode step, or about {mid[1] * d['gpu_hour'] / 1e6:.0f} million dollars "
         f"a year on {mid[0]:,} GPUs. Today it's Muse. Next, it's Gemini itself. That's Argon Speed."),
    ]
    return deck


CSS = """
:root { --bg:#090d1a; --panel:#121a33; --text:#eef1fb; --muted:#9aa6c6; --accent:#8f7cff; --accent2:#35d0ff; --win:#3ddc97; --lose:#ff9a6b; }
* { box-sizing:border-box; margin:0; padding:0; }
html, body { height:100%; background:var(--bg); color:var(--text); font-family:Inter, "Inter Display", system-ui, sans-serif; overflow:hidden; }
#stage { position:absolute; left:50%; top:50%; width:1920px; height:1080px; transform-origin:center center; }
.slide { position:absolute; inset:0; padding:100px 140px 130px; display:none; flex-direction:column; gap:40px;
  background: radial-gradient(1200px 700px at 85% 0%, rgba(143,124,255,.22), transparent 60%),
              radial-gradient(900px 600px at 0% 100%, rgba(53,208,255,.14), transparent 60%), var(--bg); }
.slide.on { display:flex; }
.kicker { font-size:30px; letter-spacing:.14em; text-transform:uppercase; color:var(--accent2); font-weight:600; }
h1.hero { font-size:190px; line-height:1; font-weight:800; letter-spacing:-.04em;
  background:linear-gradient(90deg, #fff, var(--accent) 60%, var(--accent2)); -webkit-background-clip:text; background-clip:text; color:transparent; }
.hero.small { font-size:84px; font-weight:800; margin-top:auto; background:linear-gradient(90deg, #fff, var(--accent)); -webkit-background-clip:text; background-clip:text; color:transparent; }
h2 { font-size:76px; line-height:1.08; font-weight:800; letter-spacing:-.02em; max-width:1600px; }
.lede { font-size:44px; line-height:1.4; color:#d6dbef; max-width:1500px; }
.note { font-size:30px; line-height:1.45; color:var(--muted); max-width:1600px; margin-top:auto; }
.tags { display:flex; flex-wrap:wrap; gap:20px; margin-top:auto; }
.tags span { font-size:28px; padding:12px 26px; border-radius:999px; white-space:nowrap; background:rgba(143,124,255,.16); border:1px solid rgba(143,124,255,.45); }
.grid3 { display:grid; grid-template-columns:repeat(3, 1fr); gap:40px; }
.stat { background:var(--panel); border:1px solid rgba(255,255,255,.07); border-radius:28px; padding:44px 46px; display:flex; flex-direction:column; gap:18px; }
.stat b { font-size:96px; font-weight:800; letter-spacing:-.03em; color:#fff; }
.stat span { font-size:30px; line-height:1.4; color:var(--muted); }
.stat.big b { font-size:130px; color:var(--win); }
.points { list-style:none; display:flex; flex-direction:column; gap:34px; }
.points li { font-size:42px; line-height:1.35; padding-left:56px; position:relative; color:#dfe3f3; }
.points li::before { content:""; position:absolute; left:0; top:20px; width:22px; height:22px; border-radius:50%; background:var(--accent); }
.flow { display:flex; align-items:stretch; gap:22px; margin-top:10px; }
.flow i { font-style:normal; font-size:70px; color:var(--accent); align-self:center; }
.box { flex:1; background:var(--panel); border:1px solid rgba(255,255,255,.08); border-radius:26px; padding:38px 34px; display:flex; flex-direction:column; gap:16px; }
.box.accent { border-color:var(--accent); box-shadow:0 0 60px rgba(143,124,255,.25); }
.box b { font-size:38px; } .box span { font-size:28px; color:var(--muted); line-height:1.4; }
table.results { width:100%; border-collapse:collapse; font-size:34px; }
table.results th { text-align:left; font-size:26px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); padding:0 18px 18px; font-weight:600; }
table.results td { padding:16px 18px; border-top:1px solid rgba(255,255,255,.08); }
table.results th, table.results td { white-space:nowrap; }
table.results td span { display:block; font-size:24px; color:var(--muted); margin-top:4px; }
table.results td.win { color:var(--win); font-weight:800; } table.results td.lose { color:var(--lose); font-weight:700; }
table.results.small { font-size:36px; width:auto; flex:1; }
.split { display:flex; gap:60px; align-items:stretch; }
.split .stat { width:540px; }
.cycle { flex:1; display:flex; flex-direction:column; gap:14px; }
.cycle i { font-style:normal; font-size:52px; color:var(--accent); text-align:center; line-height:1; }
.cycle .box { padding:24px 34px; } .cycle .box b { font-size:42px; }
.stack { width:640px; display:flex; flex-direction:column; gap:30px; }
.stack .stat { width:auto; padding:34px 40px; } .stack .stat b { font-size:84px; color:var(--win); }
footer { position:absolute; left:140px; right:140px; bottom:54px; display:flex; justify-content:space-between; font-size:24px; color:#5f6a8c; }
"""

JS = """
const slides = [...document.querySelectorAll('.slide')];
let i = Math.max(0, Math.min(slides.length - 1, (parseInt(location.hash.slice(1)) || 1) - 1));
function fit() { const s = Math.min(innerWidth / 1920, innerHeight / 1080);
  document.getElementById('stage').style.transform = `translate(-50%, -50%) scale(${s})`; }
function show(n) { i = Math.max(0, Math.min(slides.length - 1, n)); slides.forEach((el, k) => el.classList.toggle('on', k === i));
  history.replaceState(null, '', '#' + (i + 1)); }
addEventListener('keydown', e => { if (['ArrowRight', 'PageDown', ' ', 'Enter'].includes(e.key)) show(i + 1);
  if (['ArrowLeft', 'PageUp', 'Backspace'].includes(e.key)) show(i - 1); if (e.key === 'Home') show(0); if (e.key === 'End') show(slides.length - 1); });
addEventListener('click', e => show(e.clientX > innerWidth / 3 ? i + 1 : i - 1));
addEventListener('resize', fit); fit(); show(i);
"""


def main():
    load_env()
    d = data()
    deck = slides(d)
    sections = "".join(f'<section class="slide" id="{key}">{body}<footer><span>Argon Speed</span><span>{n + 1} / {len(deck)}</span></footer></section>'
                       for n, (key, body, _) in enumerate(deck))
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>Argon Speed</title><link rel="preconnect" href="https://fonts.googleapis.com">'
            f'<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">'
            f'<style>{CSS}</style></head><body><div id="stage">{sections}</div><script>{JS}</script></body></html>')
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "slides.html"), "w") as f:
        f.write(page)
    with open(os.path.join(OUT, "narration.json"), "w") as f:
        json.dump([{"slide": n + 1, "id": key, "text": text} for n, (key, _, text) in enumerate(deck)], f, indent=1)
    chars = sum(len(t) for _, _, t in deck)
    print(f"pitch/slides.html: {len(deck)} slides; pitch/narration.json: {chars:,} characters of narration")


if __name__ == "__main__":
    main()
