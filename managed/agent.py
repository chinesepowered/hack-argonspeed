"""The hosted harness: Gemini 4 Argon as Google's Antigravity managed agent, one persistent sandbox
per problem, woken on a schedule by Google's triggers. It runs without our machine; we only push
instructions, pull results and read the bill.

    scripts/managed.sh credential                   store OKC_TOKEN as a managed credential
    scripts/managed.sh provision <problem|all>      create each problem's sandbox and upload its workspace
    scripts/managed.sh push <problem|all>           re-upload the harness files (instructions, specs, scripts)
    scripts/managed.sh run <problem> [--minutes M] [--checks N] [--focus TEXT]
                                                    one run now (pause the schedule first); prints the answer
    scripts/managed.sh schedule <problem|all> [--every MIN] [--checks N] [--now]
    scripts/managed.sh pause|resume|unschedule <problem|all>
    scripts/managed.sh sync <problem|all>           pull NOTES.md, submission.py, attempts/, profiles/ back
    scripts/managed.sh status                       schedules, recent runs, tokens and spend

The sandbox owns each problem's state once it's provisioned (NOTES.md, submission.py, attempts/,
profiles/): `push` never overwrites it, and `sync` copies it here.
"""

import argparse
import fcntl
import io
import json
import os
import subprocess
import tarfile
import time
import warnings
from datetime import datetime, timezone

import httpx

warnings.filterwarnings("ignore", message=".*experimental.*")
warnings.filterwarnings("ignore", message="Pydantic serializer warnings")  # the SDK's own env typing
from google import genai  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "managed", "state.json")
LEDGER = os.path.join(ROOT, "runs", "ledger.jsonl")
PROBLEMS = ["muse_bf16_proj", "muse_attention_decode", "muse_moe_w4a16", "muse_decode_layer", "muse_prefill_layer"]
OFFSETS = dict(zip(PROBLEMS, (5, 17, 29, 41, 53)))  # each problem's minute past the hour, to spread runs
AGENT = "antigravity-preview-09-2026"
MODEL = "gemini-4-argon"
CREDENTIAL = "okc-bearer"
# The judge's token never enters a sandbox: Google's egress proxy adds it to requests to the judge.
NETWORK = {"allowlist": [{"domain": "openkernelchallenge.dev", "credential": CREDENTIAL}, {"domain": "*"}]}
REMOTE = "/workspace/hack-argmu"  # /workspace is the part of a sandbox that persists between runs
API = "https://generativelanguage.googleapis.com/v1beta"
RUN_TOKENS = 1_500_000  # agent_config.max_total_tokens: a best-effort cap per run (cached tokens are free of it)
TRIGGER_SECONDS = 600  # the longest a triggered run may last
# Gemini 4 Argon's introductory prices through Nov 30, 2026, in $ per 1M tokens (thinking bills as output).
PRICE_INPUT, PRICE_CACHED, PRICE_OUTPUT = 2.00, 0.10, 10.00
SPEND_ALERT = 25.0
ACTIVE = ("in_progress", "queued", "running")

HOSTED = """# Hosted runs

You are Google's Antigravity agent, working on one problem of the Open Kernel Challenge, {problem}, in
a sandbox that belongs to it. {cadence} Each run has at most {minutes} minutes before it is stopped, so
the work is a chain of short runs, and NOTES.md is how one run hands over to the next.

- The problem's folder is {remote}/problems/{problem}. Work there: cd into it in every shell command.
  The paths the instructions below give as ../../vendor/sglang/python/sglang/ and ../../docs/ are
  {remote}/vendor/sglang/python/sglang/ and {remote}/docs/.
- Start every run with `bash {remote}/managed/bootstrap.sh {every} {checks}`, then read NOTES.md and
  take the next step of its plan: design, implement, check, or learn from a result.
- Save as you go: update NOTES.md after every step, not only at the end, because a run can be
  stopped mid-step. Keep a short "Next run" section at the top of NOTES.md that says exactly what to
  do next.
- Keep unfinished work in files of your own, such as candidate.py (with the same first line as
  submission.py), and submission.py at the best passing version. `okc check candidate.py` works the
  same way and is archived the same way.
- A check can outlast a run. Write its job id in NOTES.md as soon as `okc check` prints it; the next
  run collects the result with `okc status <job> --wait`.
- `okc check` allows {checks} check(s) per {every} minutes and refuses more.

"""


def load_env():
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path):
            key, sep, value = line.strip().partition("=")
            if sep and not key.startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def load_state():
    return json.load(open(STATE)) if os.path.exists(STATE) else {"problems": {}, "runs": {}}


def update_state(change):
    """Apply change(state) to managed/state.json under a lock, so commands running at the same
    time (a long run, a provision, status) never overwrite each other's updates."""
    with open(STATE + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = load_state()
        result = change(state)
        with open(STATE + ".tmp", "w") as f:
            json.dump(state, f, indent=1, sort_keys=True)
            f.write("\n")
        os.replace(STATE + ".tmp", STATE)
        return result


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def instructions(problem, every, checks, minutes, scheduled=True):
    cadence = (f"A schedule wakes you about every {every} minutes." if scheduled
               else "This is a one-off run, outside the schedule.")
    team = open(os.path.join(ROOT, "problems", "AGENTS.md")).read()
    challenge = open(os.path.join(ROOT, "problems", problem, "AGENTS.md")).read()
    return (HOSTED.format(problem=problem, cadence=cadence, minutes=minutes, remote=REMOTE, every=every, checks=checks)
            + team + "\n# The challenge's notes for agents\n\n" + challenge)


def prompt(problem):
    return (f"Run on {problem}. Follow your instructions: bootstrap, read NOTES.md, take the next step, and keep "
            "NOTES.md current so the next run can continue. End with two or three sentences on what this run did.")


def labels(problem):
    return {"project": "hack-argmu", "problem": problem}


def agent_config():
    return {"type": "antigravity", "model": MODEL, "max_total_tokens": RUN_TOKENS}


def workspace_tar(problem, with_state):
    """The sandbox's /workspace/hack-argmu: the harness files, plus the problem's own files when with_state."""
    paths = ["problems/AGENTS.md", "docs/judge-env.md", "scripts/bin/okc", "managed/bootstrap.sh"]
    for d in ["problems/specs"] + ([f"problems/{problem}"] if with_state else []):
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, d)):
            dirnames[:] = [n for n in dirnames if n != "__pycache__"]
            paths += [os.path.relpath(os.path.join(dirpath, n), ROOT) for n in filenames]
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for rel in sorted(paths):
            tar.add(os.path.join(ROOT, rel), arcname=f"hack-argmu/{rel}")
    return buf.getvalue()


def upload(client, env_id, data):
    client.environments.files.upload(environment_id=env_id, path=REMOTE.lstrip("/").rsplit("/", 1)[0],
                                     file=data, mime_type="application/x-tar", extract=True, overwrite=True)


def wait(client, ia, seconds):
    start = time.time()
    while ia.status in ACTIVE and time.time() - start < seconds:
        time.sleep(5)
        ia = client.interactions.get(ia.id)
    return ia


def cost(usage):
    """Estimated $ for one interaction's usage, at Argon's introductory prices."""
    u = usage or {}
    inp, cached = u.get("total_input_tokens") or 0, u.get("total_cached_tokens") or 0
    out = (u.get("total_output_tokens") or 0) + (u.get("total_thought_tokens") or 0)
    tool = u.get("total_tool_use_tokens") or 0
    return ((inp - cached + tool) * PRICE_INPUT + cached * PRICE_CACHED + out * PRICE_OUTPUT) / 1e6


def record(ia, problem, kind, trigger=None):
    """Remember an interaction so status can count it. Once it has finished, cache its usage and
    cost and add it to the ledger, once."""
    done = ia.status not in ACTIVE
    d = ia.model_dump(exclude_none=True, warnings=False) if done else {}

    def change(state):
        run = state["runs"].setdefault(ia.id, {"problem": problem, "kind": kind, "created": now()})
        if trigger:
            run["trigger"] = trigger
        run["status"] = ia.status
        if done and not run.get("ledger"):
            run["usage"] = d.get("usage") or {}
            run["cost_usd"] = round(cost(run["usage"]), 4)
            run["summary"] = (getattr(ia, "output_text", None) or "").strip()[-600:]
            os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
            with open(LEDGER, "a") as f:
                f.write(json.dumps({"harness": "managed", "problem": problem, "kind": kind, "interaction": ia.id,
                                    "trigger": trigger, "recorded": now(), "status": ia.status,
                                    "usage": run["usage"], "cost_usd": run["cost_usd"]}) + "\n")
            run["ledger"] = True
        return dict(run)
    return update_state(change)


def cron(problem, every):
    offset = OFFSETS[problem]
    if every < 60 and 60 % every == 0:
        minutes = sorted((offset + k * every) % 60 for k in range(60 // every))
        return f"{','.join(map(str, minutes))} * * * *"
    if every % 60 == 0 and 24 % (every // 60) == 0:
        return f"{offset} */{every // 60} * * *" if every > 60 else f"{offset} * * * *"
    raise SystemExit("--every must divide an hour, or be a whole number of hours that divides a day")


def cmd_credential(client, args):
    fields = dict(type="bearer_token", token=os.environ["OKC_TOKEN"])  # sent as Authorization: Bearer <token>
    try:
        client.credentials.get(id=CREDENTIAL)
        client.credentials.update(id=CREDENTIAL, **fields)
        print(f"credential {CREDENTIAL}: updated")
    except Exception:
        client.credentials.create(id=CREDENTIAL, **fields)
        print(f"credential {CREDENTIAL}: created")


def setup_env(client, env, problem, every=60, checks=1):
    """Make env the problem's sandbox: upload the workspace from problems/ (the local mirror), set
    the network rule that authenticates the judge, and bootstrap. Returns the bootstrap's report."""
    upload(client, env, workspace_tar(problem, with_state=True))
    ia = client.interactions.create(
        agent=AGENT, environment={"type": "remote", "environment_id": env, "network": NETWORK},
        agent_config={"type": "antigravity", "model": MODEL}, labels=labels(problem), background=True,
        input=f"Run `bash {REMOTE}/managed/bootstrap.sh {every} {checks}` and reply with the last line it prints, verbatim.")
    ia = wait(client, ia, 600)
    record(ia, problem, "provision")
    return (ia.output_text or "").strip()[-300:]


def cmd_provision(client, args):
    for problem in args.problems:
        env = load_state()["problems"].get(problem, {}).get("environment")
        if env:
            print(f"{problem}: sandbox {env} already provisioned")
            continue
        env = client.environments.create().id
        update_state(lambda s: s["problems"].setdefault(problem, {}).update(environment=env))
        print(f"{problem}: sandbox {env}: {setup_env(client, env, problem)}")


def cmd_push(client, args):
    problems = load_state()["problems"]
    for problem in args.problems:
        upload(client, problems[problem]["environment"], workspace_tar(problem, with_state=False))
        print(f"{problem}: harness files uploaded (the problem's own state left as it is)")


def cmd_run(client, args):
    """One run outside the schedule, with its own time and check budget, and optionally a focus.
    Pause the problem's schedule first, so two agents never work in one sandbox at once."""
    problem = args.problems[0]
    p = load_state()["problems"][problem]
    text = prompt(problem) + (f"\n\nFocus for this run: {args.focus}" if args.focus else "")
    ia = client.interactions.create(
        agent=AGENT, input=text, environment=p["environment"], agent_config=agent_config(),
        system_instruction=instructions(problem, args.minutes, args.checks, args.minutes, scheduled=False),
        labels=labels(problem), background=True)
    record(ia, problem, "run")
    print(f"{problem}: run {ia.id} started; waiting up to {args.minutes} minutes", flush=True)
    ia = wait(client, ia, args.minutes * 60 + 120)
    run = record(ia, problem, "run")
    print(f"{problem}: {ia.status}, ${run.get('cost_usd', 0):.2f}\n{(ia.output_text or '').strip()[-1500:]}")


def run_trigger(client, trigger):
    """Start one run of the trigger now. The endpoint sometimes drops the connection after starting
    the run, so retry only when no run has started."""
    before = len(client.triggers.list_executions(trigger_id=trigger).trigger_executions or [])
    for _ in range(3):
        try:
            return client.triggers.run(trigger_id=trigger)
        except Exception:
            time.sleep(10)
            if len(client.triggers.list_executions(trigger_id=trigger).trigger_executions or []) > before:
                return None
    raise SystemExit("couldn't start the trigger's run")


def first_sandbox(client, trigger):
    """A trigger makes its sandbox on its first run and reuses it after that, whatever environment it
    was given. Start that first run (it finds an empty sandbox and stops) and return the sandbox."""
    run_trigger(client, trigger)
    deadline = time.time() + TRIGGER_SECONDS + 120
    while time.time() < deadline:
        time.sleep(15)
        runs = client.triggers.list_executions(trigger_id=trigger).trigger_executions or []
        env = client.triggers.get(id=trigger).environment_id
        if runs and env and all(r.status not in ACTIVE for r in runs):
            return env
    raise SystemExit("the trigger's first run didn't finish")


def cmd_schedule(client, args):
    """Schedule a problem: a trigger, then its sandbox, set up from problems/ (any earlier sandbox's
    state is synced back first)."""
    for problem in args.problems:
        p = load_state()["problems"].get(problem, {})
        if p.get("environment") and sync_problem(p["environment"], problem)[1]:
            raise SystemExit(f"{problem}: couldn't read all of its sandbox's files; try again in a few minutes")
        if p.get("trigger"):
            client.triggers.delete(id=p["trigger"])
        t = client.triggers.create(
            display_name=f"hack-argmu {problem}", schedule=cron(problem, args.every), time_zone="UTC",
            execution_timeout_seconds=TRIGGER_SECONDS, max_consecutive_failures=5,
            interaction={"agent": AGENT, "input": prompt(problem), "agent_config": agent_config(), "labels": labels(problem),
                         "system_instruction": instructions(problem, args.every, args.checks, TRIGGER_SECONDS // 60)})
        update_state(lambda s: s["problems"].setdefault(problem, {}).update(
            trigger=t.id, every=args.every, checks=args.checks))
        env = first_sandbox(client, t.id)
        update_state(lambda s: s["problems"][problem].update(environment=env))
        print(f"{problem}: sandbox {env}: {setup_env(client, env, problem, args.every, args.checks)}")
        print(f"{problem}: every {args.every} min ({cron(problem, args.every)} UTC), {args.checks} check(s) per run,"
              f" next {getattr(t, 'next_run_time', '?')}")
        if args.now:
            run_trigger(client, t.id)
            print(f"{problem}: and one run now")


def set_trigger(client, args, status):
    for problem in args.problems:
        trigger = load_state()["problems"].get(problem, {}).get("trigger")
        if not trigger:
            continue
        if status == "deleted":
            client.triggers.delete(id=trigger)
            update_state(lambda s: s["problems"][problem].pop("trigger", None))
        else:
            client.triggers.update(id=trigger, status=status)
        print(f"{problem}: schedule {status}")


def download(env_id, path):
    """One file from the sandbox, or None if it can't be read reliably now. For a while after a run, a
    sandbox lists its files but answers 404 for their contents, or answers with the right number of
    bytes from somewhere else. So a file counts only once two reads agree and it reads as text, which
    every synced file is."""
    last = None
    for attempt in range(6):
        r = httpx.get(f"{API}/environments/{env_id}/files/{path}", params={"alt": "media"},
                      headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]}, timeout=300, follow_redirects=True)
        if r.status_code != 200:
            time.sleep(10 * (attempt + 1))
            continue
        if r.content == last and b"\0" not in last:
            try:
                last.decode("utf-8")
                return last
            except UnicodeDecodeError:
                pass
        last = r.content
    return None


SYNCED = (".md", ".py", ".json", ".txt", ".log", ".cu", ".cuh", ".h", ".hpp", ".cpp", ".c")  # no build output


def remote_files(env, path):
    """Every file under path in the sandbox, as (path, size)."""
    files, token = [], None
    while True:
        params = {"recursive": "true", **({"page_token": token} if token else {})}
        r = httpx.get(f"{API}/environments/{env}/files/{path}", params=params,
                      headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]}, timeout=120)
        if r.status_code == 404:  # nothing uploaded there yet
            return files
        r.raise_for_status()
        d = r.json()
        files += [(f["path"], int(f.get("size_bytes") or 0)) for f in d.get("files") or [] if f.get("type") == "FILE"]
        token = d.get("next_page_token")
        if not token:
            return files


def sync_problem(env, problem):
    """Copy the problem's folder from its sandbox into problems/<problem>/, file by file (a tar of a
    folder that an agent is writing to can come back misaligned), keeping only source, notes and
    results, and checking each result against the judge's record. Returns the files copied and the
    ones that couldn't be read, whose local copies are left as they were."""
    remote = f"{REMOTE.lstrip('/')}/problems/{problem}"
    local = os.path.join(ROOT, "problems", problem)
    n, missed = 0, []
    for path, size in remote_files(env, remote):
        name = path[len(remote) + 1:] if path.startswith(remote + "/") else None
        if not name or ".." in name.split("/") or "__pycache__" in name or not name.endswith(SYNCED) or size > 8 << 20:
            continue
        data = download(env, path)
        if data is None:
            missed.append(name)
            continue
        if name.startswith("attempts/") and name.count("/") == 1 and name.endswith(".json"):
            try:
                whole = "result" in json.loads(data)
            except ValueError:  # still being written
                whole = False
            if not whole:  # or rewritten by hand: take the judge's own record of the job
                job = name.rsplit("-", 1)[-1][:-5]
                data = subprocess.run([os.path.expanduser("~/.okc/bin/okc"), "status", job, "--json"],
                                      capture_output=True, check=True).stdout
        dest = os.path.join(local, name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
        n += 1
    return n, missed


def cmd_sync(client, args):
    problems = load_state()["problems"]
    for problem in args.problems:
        n, missed = sync_problem(problems[problem]["environment"], problem)
        print(f"{problem}: {n} files synced into problems/{problem}/"
              + (f"; couldn't read {len(missed)} now, kept the local copies: {', '.join(missed)}" if missed else ""))


def cmd_status(client, args):
    print("schedules (UTC):")
    for problem in PROBLEMS:
        p = load_state()["problems"].get(problem)
        if not p:
            print(f"  {problem:22} not provisioned")
            continue
        line = f"  {problem:22} sandbox {p['environment'][:8]}"
        if p.get("trigger"):
            t = client.triggers.get(id=p["trigger"])
            line += (f"  every {p['every']} min, {p['checks']} check(s)  {t.status}  next {t.next_run_time}"
                     f"  failures {getattr(t, 'consecutive_failure_count', 0)}")
            new = {}
            for ex in client.triggers.list_executions(trigger_id=p["trigger"]).trigger_executions or []:
                if ex.error:
                    line += f"\n    {str(ex.start_time)[:16]} run failed: {ex.error[:160]}"
                if ex.interaction_id:
                    start = ex.start_time.strftime("%Y-%m-%dT%H:%M:%SZ") if ex.start_time else now()
                    new[ex.interaction_id] = {"problem": problem, "kind": "scheduled", "trigger": p["trigger"],
                                              "created": start}
            update_state(lambda s: [s["runs"].setdefault(k, v) for k, v in new.items()])
        else:
            line += "  not scheduled"
        print(line)
    for iid, run in load_state()["runs"].items():
        if not run.get("ledger"):
            try:
                record(client.interactions.get(iid), run["problem"], run["kind"], run.get("trigger"))
            except Exception as e:
                print(f"  could not read run {iid[:12]}: {str(e)[:160]}")

    runs = sorted(load_state()["runs"].values(), key=lambda r: r["created"])
    print("\nlatest runs:")
    for run in runs[-args.last:]:
        u = run.get("usage") or {}
        print(f"  {run['created'][:16]}  {run['problem']:22} {run['kind']:9} {run.get('status', '?'):10}"
              f" {u.get('total_input_tokens', 0):>9,} in ({u.get('total_cached_tokens', 0):,} cached)"
              f" {u.get('total_output_tokens', 0) + u.get('total_thought_tokens', 0):>7,} out  ${run.get('cost_usd', 0):.2f}")
    hosted = sum(r.get("cost_usd", 0) for r in runs)
    local = 0.0
    if os.path.exists(LEDGER):
        for line in open(LEDGER):
            s = json.loads(line)
            if s.get("harness", "qwen") == "qwen":
                u = s.get("usage") or {}
                inp, cached, out = u.get("input_tokens") or 0, u.get("cache_read_input_tokens") or 0, u.get("output_tokens") or 0
                think = max(0, (u.get("total_tokens") or 0) - inp - out)
                local += ((inp - cached) * PRICE_INPUT + cached * PRICE_CACHED + (out + think) * PRICE_OUTPUT) / 1e6
    total = hosted + local
    print(f"\nspend (estimated at Argon's introductory prices): hosted ${hosted:.2f} over {len(runs)} runs,"
          f" local ${local:.2f}, total ${total:.2f}")
    if total > SPEND_ALERT:
        print(f"PAST ${SPEND_ALERT:.0f}: if runs still succeed, the key isn't capped at ${SPEND_ALERT:.0f}")


def main():
    load_env()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["credential", "provision", "push", "run", "schedule", "pause", "resume",
                                            "unschedule", "sync", "status"])
    parser.add_argument("problem", nargs="?", default="all")
    parser.add_argument("--every", type=int, default=60, help="minutes between scheduled runs (default 60)")
    parser.add_argument("--checks", type=int, default=1, help="judge checks per run (default 1)")
    parser.add_argument("--minutes", type=int, default=30, help="a one-off run's time limit (default 30)")
    parser.add_argument("--last", type=int, default=12, help="runs to list in status (default 12)")
    parser.add_argument("--now", action="store_true", help="schedule: also start one run right away")
    parser.add_argument("--focus", help="run: extra direction for this run, appended to its prompt")
    args = parser.parse_args()
    args.problems = PROBLEMS if args.problem == "all" else [args.problem]
    if args.problem != "all" and args.problem not in PROBLEMS:
        parser.error(f"unknown problem {args.problem}")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    commands = {"credential": cmd_credential, "provision": cmd_provision, "push": cmd_push, "run": cmd_run,
                "schedule": cmd_schedule, "sync": cmd_sync, "status": cmd_status,
                "pause": lambda c, a: set_trigger(c, a, "paused"),
                "resume": lambda c, a: set_trigger(c, a, "active"),
                "unschedule": lambda c, a: set_trigger(c, a, "deleted")}
    commands[args.command](client, args)


if __name__ == "__main__":
    main()
