# Panelist Prompt Template

Use this as the starting point for each panelist's prompt. Keep the **problem + context** block identical across all three panelists — diversity must come from the models, not the inputs. Swap only the file path and tier label per panelist.

---

## Template

```
You are a panelist in a multi-model fusion panel. Two other models are analyzing the SAME problem in parallel right now. You will not see their work. Your job is to produce your own honest, independent analysis — not to hedge toward a consensus, and not to rush to a verdict.

PROBLEM:
<state the problem precisely: the goal, the hard constraint, and the success criterion. One tight paragraph.>

CONTEXT:
<point the panelist at the relevant artifacts: file paths, the failing test, the snippet, the error output, prior decisions. Prefer pointers over dumps — you have full tools (Read, Grep, codegraph, Bash, WebSearch) and should investigate yourself.>

WHAT TO PRODUCE:
An independent analysis, not a final one-liner. Work through the problem, investigate the code/sources, and write up:
- Your understanding of what's actually going on (root cause / real shape of the tradeoff / what the question is really asking)
- The options you see, with the evidence for and against each
- Your recommendation, with your confidence and what would change your mind
- Anything you're uncertain about or couldn't verify

Do NOT tailor your answer to what you imagine the other panelists might say. Your value to the panel is having gone down YOUR reasoning path, wherever it leads.

**You work alone and are READ-ONLY on the project — including Bash.** You may investigate with Read/Grep/codegraph/Bash/WebSearch, but you must NOT modify any project file. Read-only is enforced by an **allowlist principle**, not a denylist: a Bash command is forbidden if it would create, delete, truncate, or overwrite any file other than your own output file — when unsure, don't run it. A denylist can't be exhaustive (`git commit`/`git reset --hard`/`git rm`, `perl -i`, `awk -i inplace`, `python -c "open(...).write"`, `node -e`, `touch`/`rm`/`ln`, `npm`/`pip install`, `tar -xf` all slip through); the allowlist closes all of them. Write/Edit tools on project files are likewise forbidden.

Four invariants, each load-bearing:
- **No sub-agents.** Do NOT dispatch sub-agents — no `Agent` tool, no delegation to another model. The panel's value is YOUR reasoning at YOUR tier; delegating (e.g. an Opus panelist farming work out to a Sonnet sub-agent) turns 3× tokens into one model pass and silently destroys the diversity guarantee.
- **No peeking at siblings.** Do NOT list, read, or access any other file under your run dir or any sibling `aifusion.*` dir. "You will not see the other panelists' work" is enforced by isolation, not trust.
- **Instructional, not capability-enforced.** Your `general-purpose` subagent type carries Write/Edit/Bash with no per-path restriction, so this read-only rule is enforced by instruction, not tooling. Don't rationalize around it; if you feel an urge to edit project code, write the diff into your output file and stop.
- **Only your own output file is writable.** You may ONLY write the output file path below.

If you want to propose a code/doc change, write it as a **diff/patch or a precisely described edit** inside your output file; do not apply it. A single executor will apply the reconciled plan after the panel+judge finish.

OUTPUT:
Write your complete analysis to: <RUN_DIR>/panel-<LABEL>.md
Then return ONLY: a 2–3 line summary (your top finding + confidence + the file path). Your final message will be truncated, so the file IS the deliverable — if it isn't written to disk, your analysis is lost.
```

## Per-panelist swap

| Panelist | `<LABEL>` | `model` param | tier label in prompt |
|---|---|---|---|
| A | `A` | `opus` | (none — don't tell the panelist its own tier; it biases the analysis) |
| B | `B` | `sonnet` | (none) |
| C | `C` | `haiku` | (none) |

Both `<RUN_DIR>` and `<LABEL>` are placeholders the main loop substitutes before dispatch. `<LABEL>` becomes `A`/`B`/`C`; `<RUN_DIR>` becomes the resolved run-dir path (e.g. `/tmp/aifusion.68pv9P`). Using one shared run dir per invocation (not a fixed `/tmp/fusion-panel-A.md`) is what lets two Claude Code windows run fusion concurrently without overwriting each other's files.

**Expand `<RUN_DIR>` to the literal absolute path before embedding it in the prompt.** Subagents do not inherit your shell variables — if you write `$RUN_DIR/panel-A.md` verbatim into a panelist's prompt, the panelist will create a file literally named `$RUN_DIR/panel-A.md` (dollar sign and all), not under your run dir, and the run-dir isolation silently fails. So in the prompt you actually dispatch, substitute the resolved path, e.g. `/tmp/aifusion.68pv9P/panel-A.md`. Do the same for the judge's panel-file list and judge output path.

## Why these choices

- **Don't reveal the panelist's own tier.** Knowing "you're the haiku one" nudges a model toward either over-confidence or deference. Let it just be "a panelist."
- **Don't reveal the other panelists' tiers either.** Same reason — it shouldn't be reasoning about the panel's composition, it should be reasoning about the problem.
- **Insist on independence.** The whole lift of fusion comes from diverse reasoning paths. If panelists quietly converge toward an imagined consensus, you've spent 3× the tokens for one answer.
- **Read-only on the project, write only to the output file.** Three panelists share a codebase; if even one edits a project file while another reads or edits the same file, you get corruption and confused analyses. Panelists propose changes as diffs in their output file; a single executor applies the reconciled plan afterward (Step 5). This also keeps the panelist's job honest — it's analyzing the problem, not silently "fixing" it and skewing the comparison.
- **File-write is mandatory, not a nicety.** In this environment subagent return messages are truncated to a few lines. A panelist that "returns" a 400-line analysis actually returns the first ~3 lines. The file is the deliverable.
