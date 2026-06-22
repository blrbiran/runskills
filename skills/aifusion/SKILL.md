---
name: aifusion
description: Multi-model fusion — dispatch a parallel panel of subagents at different model tiers (Opus, Sonnet, Haiku) plus a Fable Judge that cross-examines their outputs, then synthesize a grounded final answer. Costs ~3-4× the prompt/response tokens of a single pass (more once investigation tokens are counted) and 2-4x the latency, so it is a heavy tool to be used sparingly. PRIMARILY manually invoked: use it when the user explicitly asks for "fusion", "multi-model analysis", "multiple perspectives", "second opinions", "/aifusion", or otherwise clearly requests that several models work the same problem. Only auto-invoke without an explicit request in the rare case where the problem is genuinely high-stakes AND a single wrong pass would be expensive to recover from (e.g. an irreversible architecture decision, a security review of a subtle change, a cross-cutting bug where a miss is costly) — and even then, briefly tell the user you are spending the extra tokens before dispatching. Do NOT auto-invoke for routine hard problems, ordinary code review, debugging you can do directly, or anything you can answer well in one pass; the token and latency cost is rarely justified otherwise.
---

# Fusion — Multi-Model Panel + Judge Synthesis

## Why this works

A single model reasoning through a hard problem locks into one reasoning path, one set of tool calls, one framing of the tradeoffs. Multi-model ensemble and self-consistency research, plus practical fusion experiments, consistently find that synthesizing the outputs of several models outperforms even the strongest single model — and, crucially for this skill, that independent runs of the *same* model also tend to beat its solo pass, because each run takes a different reasoning path. (Effect size varies by model and task; what matters here is the direction, not a guaranteed margin.) The lift comes from **diversity of reasoning path**: independent runs notice different things, chase different hypotheses, and miss different blind spots; genuinely different models (when the panel actually is different models) widen the diversity further. The synthesis step then catches contradictions and merges unique insights that no single panelist had in full.

One assumption to keep in mind: `opus`/`sonnet`/`haiku`/`fable` are **dispatch aliases, not guarantees about the underlying model**. In your config they may be Anthropic models, other providers' models, or even the same model exposed under several names. The panel still helps regardless — the robust mechanism is independent reasoning paths, not four distinct Anthropic tiers — but the more genuinely different the panelists are, the bigger the lift.

The goal of this skill is to capture that lift inside Claude Code: dispatch a panel of subagents at different tiers in parallel, have a Judge model cross-examine their outputs, then you (the main loop) write the final answer grounded in the Judge's analysis.

## When to use

**Default to NOT using fusion.** It is a heavy, manually-invoked tool (~3–4× tokens, 2–4× latency). Reach for it when the user explicitly asks for it ("fusion", "multi-model", "multiple perspectives", "second opinions", "/aifusion"), or — only rarely — when all three of these hold:

1. The user clearly wants the extra cost (or you've flagged it and they said go ahead)
2. Getting the answer wrong is genuinely expensive to recover from
3. The problem has real surface area for divergent analysis:

   - Architecture / design decisions with non-obvious tradeoffs and irreversible consequences
   - Subtle cross-cutting bugs where a miss is costly and the root cause is unknown
   - Security review of non-trivial changes
   - Hard research questions that span many sources

When in doubt, answer in one pass and offer fusion as an option ("want me to run a multi-model fusion pass on this for a second opinion?") rather than spending the tokens unprompted.

Do **not** use fusion for: simple lookups, single-file edits with a clear spec, typos, running a known command, or anything you can already nail in one pass. Fusion costs ~3–4× the tokens and latency of a single call — only spend that when the problem warrants it.

## The pipeline

```
                       ┌──────────────────────────┐
   hard problem  ─────►│  prepare panel prompt    │
                       └────────────┬─────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
     ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
     │  Opus agent  │        │ Sonnet agent │        │  Haiku agent │
     │  (parallel)  │        │  (parallel)  │        │  (parallel)  │
     └───────┬──────┘        └───────┬──────┘        └───────┬──────┘
            └───────────────────────┼───────────────────────┘
                                    ▼
                       ┌──────────────────────────┐
                       │  Judge (Fable) reads all │
                       │  3 panel outputs →        │
                       │  structured analysis      │
                       └────────────┬─────────────┘
                                    ▼
                       ┌──────────────────────────┐
                       │  You write final answer  │
                       │  grounded in Judge       │
                       └──────────────────────────┘
```

> Boxes are tier aliases — `opus`/`sonnet`/`haiku` map to whatever models your config provides (see *Why this works*).

### Step 1 — Prepare the panel prompt

First, create a **unique run directory** for this fusion invocation. This is what keeps two concurrent Claude Code windows running aifusion from clobbering each other's panel/judge files. Create it with a failure guard and capture a git baseline for the later read-only check:

```bash
RUN_DIR=$(mktemp -d /tmp/aifusion.XXXXXX) || { echo "FATAL: mktemp failed" >&2; exit 1; }
[ -d "$RUN_DIR" ] || { echo "FATAL: run dir not created" >&2; exit 1; }
git status --porcelain > "$RUN_DIR/git-baseline" 2>/dev/null || echo "no git repo — baseline check disabled" > "$RUN_DIR/git-baseline"
```

The `XXXXXX` is a `mktemp` **template**, not a literal — at runtime the OS replaces it with 6 random chars and atomically creates the dir (e.g. `/tmp/aifusion.K3pQ9x`). Capture the returned path into `RUN_DIR` and use it for every panel/judge file path below. Do not hardcode `/tmp/fusion-panel-A.md` etc. — always substitute the real `$RUN_DIR`.

**Expand `$RUN_DIR` to the literal absolute path before embedding it in any subagent prompt.** Subagents do not inherit your shell variables — if you write `$RUN_DIR/panel-A.md` verbatim into a panelist's prompt, the panelist will create a file literally named `$RUN_DIR/panel-A.md` (dollar sign and all), not under your run dir, and the run-dir isolation silently fails. So in the prompt you actually dispatch, substitute the resolved path (e.g. `/tmp/aifusion.68pv9P/panel-A.md`). Same for the judge's panel-file list and judge output path.

**The same applies to your own later Bash calls.** Claude Code's Bash tool starts a fresh shell per call — `$RUN_DIR` does not persist across your subsequent Bash invocations any more than it does across subagent prompts. After `mktemp` returns, treat the resolved path (e.g. `/tmp/aifusion.K3pQ9x`) as a literal string and paste it into every later Bash command and every subagent prompt. The Step 1 snippet only works because `mktemp` and the baseline `git status` run in the *same* call. (Convention: `$RUN_DIR` in bash snippets, `<RUN_DIR>` in prompt templates — both refer to the same resolved path.)

Then write a single shared prompt that any panelist can act on without seeing the others. It must contain:

- **The problem**, stated precisely (not just "fix it" — what's the goal, what's the constraint, what's the success criterion).
- **The relevant context**: file paths, the snippet under question, error output, prior decisions. Point panelists at where to look rather than dumping everything — they have full tools (Read, Grep, codegraph, Bash, WebSearch) and should investigate themselves.
- **What to produce**: an independent analysis, not a final answer. Each panelist must hand back *reasoning and evidence*, not just a verdict.

Keep the prompt identical across panelists — the diversity comes from the models, not from different inputs.

### Step 2 — Dispatch the panel in parallel

Launch all three panelists **in a single message** with three `Agent` tool calls so they run concurrently. Each gets a different model tier:

| Panelist | model param | subagent_type | Intended role |
|---|---|---|---|
| Panelist A | `opus` | `general-purpose` | Deep, careful reasoning on subtle correctness |
| Panelist B | `sonnet` | `general-purpose` | Strong all-rounder; a different reasoning path than Panelist A |
| Panelist C | `haiku` | `general-purpose` | Lightweight; cheap insurance, often surfaces a different framing |

The "Intended role" describes the **slot**, not the model behind it. If your config aliases several tiers to the same model, the panelists still diverge via independent reasoning paths (see *Why this works*) — just less than genuinely different models would.

> **fable is reserved for the Judge**, not the panel — it's the strongest available tier and the best fit for judgment work. A same-tier Judge is fine if fable is unavailable: two runs of the same model take different reasoning paths (independent runs of one model still beat its solo pass), so an opus Judge judging an opus panelist isn't redundant. What matters is that the Judge is a separate *role* (cross-examiner, not answerer), not a separate *tier*.

Each panelist's prompt MUST instruct it to **write its full analysis to a file** (e.g. `$RUN_DIR/panel-A.md`) and return only a 2–3 line summary. In this environment subagent final messages are truncated — a deliverable that lives only in the return value is lost. Tell the panelist: *"Write your complete analysis to <path>. Return only a 2–3 line summary + the file path."*

> **Panelists are READ-ONLY on the project — including Bash — and work alone.** A panelist may only write its own output file under `$RUN_DIR/`. Read-only is enforced by an **allowlist principle**, not a denylist: a Bash command is forbidden if it would create, delete, truncate, or overwrite any file other than the panelist's own output file — when unsure, don't run it. This is stronger than a denylist, which can never be exhaustive (`git commit`/`git reset --hard`/`git rm`, `perl -i`, `awk -i inplace`, `python -c "open(...).write"`, `node -e`, `touch`/`rm`/`ln`, `npm`/`pip install`, `tar -xf` all slip through a literal list). Write/Edit on project files are likewise forbidden.
>
> Three more invariants, each load-bearing:
> - **No sub-agents.** A panelist must NOT dispatch sub-agents — no `Agent` tool, no delegation to another model. The panel's value is YOUR reasoning at YOUR tier; an Opus panelist delegating to a Sonnet sub-agent turns 3× tokens into one model pass and silently destroys the diversity guarantee.
> - **No peeking at siblings.** A panelist must NOT list, read, or access any other file under `$RUN_DIR` or any sibling `aifusion.*` dir — "you will not see the other panelists' work" is enforced by isolation, not trust.
> - **Instructional, not capability-enforced.** The `general-purpose` subagent type carries Write/Edit/Bash with no per-path restriction, so this read-only rule is enforced by instruction, not by tooling. Don't rationalize around it; if you feel an urge to edit project code, write the diff into your output file and stop.
>
> If a panelist wants to propose a code/doc change, it writes that proposal **as a diff/patch (or a precisely described edit) inside its output file**, never applied. The actual implementation is done later by a single executor (see Step 5), after fusion has settled on one plan.

> **Residual risk — be honest with yourself about this.** The read-only rule is instructional, not capability-enforced. A panelist *can* technically read a sibling's file or dispatch a sub-agent; both silently corrupt the diversity guarantee, and neither is caught by the git-baseline check (which only catches tracked-file *writes*). Treat fusion output as diverse-but-not-cryptographically-isolated. The discipline above is what makes the lift real in practice; if a panelist rationalizes around it, that panelist's contribution is suspect.

The panelist prompt template is in `references/panelist-prompt.md` — read it and adapt it to the problem.

### Step 2.5 — Verify the panel before dispatching the Judge

Before Step 3, confirm all three panelists actually produced output. A panelist can crash, time out, write to a literal `$RUN_DIR/...` path (ignoring the expand instruction), or return an empty file — and the Judge would otherwise run blind against missing inputs.

Check each `$RUN_DIR/panel-{A,B,C}.md` exists and is substantive — not just `wc -l ≥ ~10` (10 lines of "I couldn't investigate" passes that). Use a structural check, e.g. `grep -qE '^#|recommend|confidence' "$RUN_DIR/panel-X.md"`. If one is missing, empty, or non-substantive:
1. Look at that panelist's return message for a clue.
2. Re-dispatch it once (transient failures happen).
3. If still missing, proceed with N=2 — but **explicitly tell the Judge which panelist is missing** so it records the gap in Blind spots. Note *which tier* is missing: a missing Opus panelist means no deep-reasoning tier (consider re-dispatching with a longer timeout before accepting N=2); a missing Haiku panelist just loses one diversity angle.
4. Never proceed with N<2 — abort fusion and answer in one pass instead.

Also verify read-only held: `git status --porcelain` should match `$RUN_DIR/git-baseline` (no project-file changes attributable to panelists). If there are unexpected changes, a panelist violated read-only — investigate before trusting the synthesis.

### Step 3 — Dispatch the Judge

Once all three panelists return, launch a single Judge agent with `model: fable`. The Judge reads all three panel files and produces a **structured cross-examination** — not a merged answer, but an analysis of *how the panelists relate to each other*:

- **Consensus** — points all panelists agreed on (high-confidence core of the answer)
- **Contradictions** — points where panelists disagreed (the Judge must not paper over these; flag them explicitly)
- **Unique insights** — contributions only one panelist made (often the highest-value findings)
- **Blind spots** — things *none* of the panelists covered (gaps in the panel itself)
- **Recommended resolution** — for each contradiction, the Judge's best-evidence call

The Judge writes **two files**: (1) the synthesis-ready summary to `$RUN_DIR/judge-summary.md` — a small file you Read in full (no head-only parsing, no truncation risk); (2) the full cross-examination to `$RUN_DIR/judge.md` — the drill-down source you Read only when the summary flags a section worth examining. Splitting them dissolves the whole class of "head-only Read clipped the navigation note" bugs. The summary file's first line must be `## Synthesis-Ready Summary` — no preamble, no title, no frontmatter above it. Subagent return messages truncate aggressively (often to "Done."), so the summary must live in the file, not in the return.

The synthesis-ready summary must carry enough to write the final answer: the consensus core (bullet form), each unresolved contradiction with the Judge's lean + confidence, the one or two highest-value unique insights (which panelist, one line each), and a note on which sections of `$RUN_DIR/judge.md` are worth Reading if you need precise quotes/evidence. Keep it tight (~20–30 lines). The judge prompt template is in `references/judge-prompt.md`.

> **Judge tier fallback**: the session-model `[1m]` suffix cannot be inherited by subagents, so you MUST pass an explicit `model` on every Agent call. Use `fable` first (strongest available tier, best fit for judgment). If a fable dispatch fails, fall back `opus` → `sonnet` → `haiku` — strongest available wins. Don't avoid opus just because Panelist A is also opus: two runs of the same model take different reasoning paths (a same-model panel still beats the solo pass), so a same-tier Judge is fine. Flag the degradation to the user when you fall back. Never omit the `model` param.
>
> **If every tier fails**, don't silently collapse to a one-pass answer — the panel's tokens are already spent. Read the three panel files yourself and synthesize directly from them, and tell the user the Judge was skipped.

### Step 4 — Synthesize the final answer yourself

This step is **yours** — do not delegate it. The main loop holds the full conversation context — what the user actually asked, the constraints already established, the project conventions. A subagent started fresh would lose that. Your job is to reconcile the Judge's panel-derived analysis with the conversation's reality.

**Sanity-check the file first**: `[ -s "$RUN_DIR/judge-summary.md" ] && head -1 "$RUN_DIR/judge-summary.md" | grep -q '^## Synthesis-Ready Summary'`. If that fails (Judge crashed, wrote to the wrong path, or omitted the header), fall back to Reading `$RUN_DIR/judge.md` directly with a `limit` — don't Read garbage.

**Read `$RUN_DIR/judge-summary.md` in full** — it's a small file (~20–30 lines), the whole thing is the synthesis-ready summary. In the common case that's enough to write the final answer. Only Read `$RUN_DIR/judge.md` (the full cross-examination) when the summary explicitly flags an unresolved contradiction or a unique insight you need to quote precisely — and even then, prefer re-Reading just the relevant section by offset rather than the whole file. The three panel files (`$RUN_DIR/panel-*.md`) are even further removed — Read one only if you need to verify a specific claim the Judge cited.

Why a separate summary file and not the Judge's return message: subagent return messages in this environment truncate to a few characters, so the summary can't live there. A dedicated small file lets you Read the whole summary cheaply with no truncation risk — better than guessing a `limit` for a head-only Read of the full analysis.

Write the final answer grounded in the Judge's consensus and unique insights, explicitly flagging any unresolved contradictions rather than silently picking one side.

**After you deliver the answer, treat `$RUN_DIR` as transient scratch.** Do not re-Read its files in later turns of the conversation — their content has already been folded into your synthesis, and re-reading just re-bloats main-loop context. If a later turn needs a detail, recall it from your synthesis (or re-derive it from the codebase), not from the scratch files. If you find yourself wanting to re-Read them, that's a signal the original synthesis should have captured the point more completely.

**Defer `rm -rf "$RUN_DIR"` until after Step 5's executor (if any) has finished.** The executor may need to read the panelists' proposed diffs from `$RUN_DIR/panel-*.md` to apply the reconciled plan. Cleaning up too early loses those diffs. Once the plan is applied (or the user declines implementation), you should `rm -rf "$RUN_DIR"` — leaving it is harmless (it is unique per invocation, so it won't collide with future runs), but cleaning up keeps `/tmp` tidy.

### Step 5 — (Optional) Apply changes via a single executor

If the user wants the synthesized plan implemented — code fixes, doc updates, refactors — do the work with a **single** executor, not by handing it back to the panelists. **First, in Step 4, write the reconciled implementation plan yourself** — a concrete edit list or set of diffs, grounded in the Judge's Recommended resolution plus the conversation context only you have. `judge.md` is a cross-examination, not an implementation plan, so don't hand it raw to an executor. If the panelists proposed diffs, pull them from `$RUN_DIR/panel-*.md` and reconcile them into your plan. Then either apply the plan yourself in the main loop, or dispatch one `general-purpose` subagent (e.g. `model: sonnet`) to apply it. Never let multiple panelists each apply their own version — that is exactly the concurrent-write corruption the read-only rule (Step 2) prevents.

A spot-check after the executor runs: `git diff` to confirm the edits match the synthesized plan and nothing unexpected was touched. Compare against `$RUN_DIR/git-baseline` — the only project-file changes should be the executor's intended ones; any others mean a panelist/judge violated read-only.

## What to tell the user

When fusion runs, tell the user briefly what's happening — that you're dispatching a multi-model panel and it'll take longer than usual (parallel subagents + judge = ~2–4× a normal call). Then deliver the synthesized answer. If a contradiction survived the Judge, surface it: *"Opus and Sonnet disagreed on X; here's the resolution I'm going with and why."* Users trust fusion answers more when they can see where the models agreed and where they didn't.

## Cost / latency reality check

- Panel (3 parallel agents) + Judge (1 agent) + your synthesis ≈ 4 subagent calls worth of prompt/response tokens. Investigation tokens (Read/Grep/codegraph) sit on top and can push the real total to 5–10× on research-heavy problems.
- Wall-clock is gated by the slowest panelist (usually Opus) plus the Judge — typically 2–4× a single Sonnet call.
- That's the right tradeoff for a hard problem and the wrong one for an easy one. When in doubt, ask yourself: *"If I just answered this in one pass and got it slightly wrong, how bad is the recovery?"* Bad recovery → use fusion.

## References

- `references/panelist-prompt.md` — the exact prompt template to give each panelist (with the file-write instruction baked in)
- `references/judge-prompt.md` — the exact prompt template to give the Judge
- Read both before your first fusion run; after that you'll have the shape in memory and can adapt inline.
