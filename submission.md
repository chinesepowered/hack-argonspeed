# Argon Speed: submission answers

## Project Description:

**Argon Speed: AI that makes itself faster.**

Argon Speed is a GPU kernel engineering team made of five Gemini 4 Argon agents. It runs around
the clock on Gemini Managed Agents, with no laptop involved and no GPU of our own. Each agent owns
one problem in the Open Kernel Challenge: the kernels that serve Muse Spark Open, an
816B-parameter mixture-of-experts model, on SGLang.

Each run, an agent:

- reads SGLang's source at the judge's exact commit, the judge's per-shape profiles and its own lab
  notebook;
- designs a change and writes it in CUDA or Triton;
- compiles it in its sandbox;
- sends it to the challenge's independent judge, which runs hidden tests and times it on a real
  H200 against SGLang's own production kernel.

An hourly trigger wakes each agent, and every run leaves notes for the next one. Guardrails keep
it honest: a check budget, the judge's token never enters a sandbox, and only a person can make a
scored run.

In its first afternoon it beat SGLang on all five problems and got onto all five public
leaderboards. Scored runs are 1.02x to 1.32x faster than SGLang. It read 58M tokens to get there,
for $18.

The point is where this goes next. Aimed at a model's own serving stack, every speedup makes the
next iteration cheaper and faster, so the rate of improvement compounds. That's the speed in Argon
Speed.

## Describe your use of Google products to build the submitted project:

**Gemini 4 Argon** does all of the engineering; no person wrote kernel code.

- Each run gets a 1.5M-token budget for SGLang's source, the challenge's spec and tests, the
  judge's profiles and its own notebook.
- Across 32 hosted runs it read 58M tokens, 94% of them served from cache. That's what makes
  leaving it on affordable: $18 so far, about $134 a day for all five agents.

**Gemini Managed Agents** is the whole runtime. We use the Antigravity agent through the
Interactions API and the google-genai Python SDK, with:

- **Environments:** one persistent sandbox per problem. A bootstrap script installs the judge's
  CLI, CUDA 13.4's nvcc and SGLang's source under `/workspace`, so each run picks up where the
  last one stopped.
- **Triggers:** an hourly schedule per problem, staggered across the hour, keeps it running 24/7
  without our machines.
- **Credentials:** the judge's API token is a bearer credential that the network allowlist's egress
  proxy attaches only to requests for the judge's domain. Inside the sandbox, the CLI runs with a
  stand-in value.
- **Environment files:** we upload each sandbox's workspace, and sync its notebook, checks and
  results back to build the results pages, the deck and the video.
- **Interactions:**
  - a system instruction and labels per problem;
  - background runs for one-off work;
  - each run's usage feeds a token and cost ledger with a $25 alert.

## Do you have any feedback for the Google Deepmind team on Argon?

**On Argon, the model**

- Long context plus caching is what makes this practical. Runs re-read millions of tokens of source
  code and logs, and 94% of those tokens come from cache.
- Argon is a capable systems programmer. In one session it turned a design spec into a 742-line
  CUDA kernel that passed all of the judge's hidden tests on its first check. It then worked from
  the judge's profiles until the kernel beat SGLang.
- It doesn't track wall-clock time. Told it had 10 minutes per run, it sometimes kept working for
  an hour. Telling the agent how much time it has left, or stopping it, would help.

**On Managed Agents**

1. **Trigger timeouts.** `execution_timeout_seconds` is capped at 600, yet one triggered run kept
   working for about an hour, so the next hourly run could start in the same sandbox. Several
   executions also failed with "Deadline expired before operation could complete", and those count
   toward `max_consecutive_failures`, so a trigger can switch itself off. Two things would make
   schedules safe:
   - an option to skip a firing while the previous run is still active;
   - a clear rule for what the timeout actually stops.
2. **Run budgets.** `max_total_tokens` doesn't count cached tokens, so a run capped at 1.5M
   reported 15.8M input tokens, 15.1M of them cached. Caching keeps that cheap, but the cap doesn't
   bound how long a run goes or what it costs, and usage only appears once an interaction ends. A
   cap on a run's cost or wall-clock time, plus live usage, would make 24/7 agents easier to budget.
3. **Reading environment files.** For a while after a run ends, downloading a file can fail in two
   ways:
   - a 404 ("No such object .../snapshot.tar");
   - a 200 with the right length but another file's bytes.

   The second is silent corruption. We now read every file twice and check results against the
   judge. A checksum in the file listing or a response header, or a snapshot version to read
   against, would make syncing trustworthy.
4. **Worth stating prominently in the docs:**
   - A trigger creates its own environment on its first execution, rather than using the
     `environment_id` it's given.
   - Environment-variable credentials attach only when an environment is created; a bearer
     credential through the network allowlist works on existing ones.
   - Only `/workspace` persists between runs.

   Each of these cost us time.
5. **Client-side reliability.** `triggers.run` sometimes drops the connection after starting the
   run, and execution records lag behind. A careful client has to poll before retrying, or it may
   start the run twice.
