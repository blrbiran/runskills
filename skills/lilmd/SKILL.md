---
name: lilmd
description: |
  Read and edit large Markdown files section by section instead of loading the whole file. Use this skill whenever a Markdown file is too big to read whole — issue ledgers, ADRs, changelogs, specs, meeting notes, knowledge bases, memory files — or whenever the user asks to find / read / update just one section of a .md file, or says the file is 太大 / 太乱 / 读不动 / 只想看某一段. Also use it when a task only needs one entry from a long list (one issue, one decision, one runbook step), when you need to locate which section mentions some code or term, or when you are about to write to a large .md and want a section-scoped edit instead of a full rewrite. Trigger even if the user never says "lilmd" — the signal is "big Markdown, need one slice of it".
---

# lilmd — treat Markdown as addressable sections

`lilmd` reads a Markdown file by heading instead of by byte. A 120 KB file with
46 sections costs ~4 KB to survey (~270 B with `--depth 2`) and ~5 KB to read one
section, so an agent can work on one entry without paying for the other 45.

The rule that matters: **survey → select → read one section → edit one section.**
Never `cat` a large file as the first move; you lose the ability to choose.

## Check the tool first

```bash
command -v lilmd || npm install -g lilmd --registry=https://registry.npmmirror.com
```

Use that registry line as-is when the default npm registry is slow or blocked —
it is the mirror that works from this machine. After installing, `lilmd` with no
arguments prints the full help; keep `lilmd --help` in mind as the source of truth
if a flag below stops working.

If `lilmd` is unavailable and cannot be installed, fall back to `rg -n '^#{1,6} '`
for the outline and `sed -n 'A,Bp'` for one section. Say so once, then continue;
don't burn turns reinstalling.

## The loop

### 1. Survey (cheap, always first)

```bash
lilmd FILE                      # TOC + line ranges
lilmd FILE --depth 2            # stop at H2 when H3s are noise
lilmd FILE --flat               # long flat list, easier to scan than a tree
lilmd FILE --json               # {headings:[{level,title,line_start,line_end,path}]}
```

The TOC gives every heading's `line_start`/`line_end`, so you can also jump with
`sed -n '310,376p' FILE` when you want the raw bytes without lilmd's delimiters.

### 2. Select a section

Selectors, cheapest to most precise:

| Selector | Meaning | Use when |
|---|---|---|
| `Install` | fuzzy, case-insensitive substring | you half-remember the title |
| `=Install` | exact title, case-insensitive | several titles share a word |
| `/^Issue 230:/` | JS regex, flags default to `i` | titles carry numbers, colons, brackets |
| `##Install` | headings at that level only | the same word appears at several levels |
| `Guide > Install` | any depth under `Guide` | you know the parent |
| `Guide >> Install` | direct child only | you must not match a grandchild |

Selectors match **titles only**, never body text. That is why `lilmd grep` exists:
`lilmd FILE "Beta"` finds a section titled Beta even if ten other bodies mention
it, and `lilmd grep FILE "Beta"` is how you find those mentions.

Two selector traps found by testing:

- **`#` is a level filter, not part of the title.** `##Alpha` means "H2s whose
  title contains Alpha". `#Alpha` is an H1 filter and matches nothing when the
  section is an H2. If you copy a heading from a rendered document, drop its
  leading `#`s — `"## Alpha"` (with a space) also works, but `"# Alpha"` silently
  returns nothing.
- **A bare word can match several sections.** When titles repeat or share a word,
  `=Exact` and `/^Title:/` disambiguate. Check with `--no-body` before writing.

If your selector matches nothing the exit code is 1 — widen the selector rather
than assuming the file changed.

### 3. Read one section

```bash
lilmd FILE "/Issue 230:/"            # whole section, subsections included
lilmd FILE "=A" --body-only          # only this heading's own body
lilmd FILE "=A" --no-body            # headings only, to see the shape
lilmd FILE "/Issue 230:/" --max-lines 40   # truncate a huge body
lilmd FILE "=A" --raw                # drop the ── file Lx-y ── delimiters
```

`--max-lines` prints `… N more lines (use --max-lines=0 for full)`, which tells you
the section is bigger than what you got. Don't assume truncation means the end.

Read the TOC before reading a section when the file is unfamiliar; reading the
wrong section twice costs more than the 4 KB outline.

### 4. Search when you don't know the section

```bash
lilmd grep FILE "runLoop"            # matches grouped by section
lilmd grep FILE "runLoop" --json     # [{file,line,text,section:{...}}]
lilmd links FILE                     # every link, with its section path
lilmd code FILE "/Issue 230:/"       # fenced blocks only
lilmd code FILE --lang ts            # filter by fence language
lilmd ls FILE "=Guide"               # direct children of one section
```

`lilmd grep` is the right first move when the question is "which section talks
about `blockRun()`" rather than "read section X". Its JSON form carries the
enclosing section, so one call both finds the hit and tells you what to read.

### 5. Edit one section

```bash
lilmd set    FILE "=A" --body '
new body
'                                    # replace this section's body, keep its children
lilmd append FILE "=A" --body '
extra paragraph
'                                    # keep existing body, add at the end
lilmd insert FILE --after "=A" --body '
## New section

body
'                                    # add a sibling after A
lilmd rm     FILE "=B"               # delete B and its subsections
lilmd rename FILE "=Old" "New title"
lilmd mv     FILE "=B" "=A"          # re-parent B under A, fixing heading levels
lilmd promote FILE "=Kid"            # H3 -> H2
lilmd demote  FILE "=A"              # H2 -> H3
```

Every write takes `--dry-run`, which prints a unified diff and touches nothing.
**Run `--dry-run` first on any non-trivial edit**: the diff is the cheapest way to
catch a selector that matched two sections or a body that lost its blank lines.

## The one writing rule: pad `--body` with a newline on both ends

`lilmd` writes the body literally and splices it against the surrounding
headings. Without padding, the blank line between a heading and its body
disappears, and a following heading ends up glued to your last line:

```text
--body 'X'              →      --body '\nX\n'   →

## A                           ## A
X                              (blank)
### Kid                        X
                               (blank)
                               ### Kid
```

Both are valid Markdown only in the second form. So write bodies like this:

```bash
lilmd set    FILE "=A" --body '
new body
'
lilmd append FILE "=A" --body '
extra paragraph
'
lilmd insert FILE --after "=A" --body '
## New section

body
'
```

The trailing newline matters even more than the leading one: it is what keeps the
next heading from being swallowed into your body. Same for `insert`, which
otherwise glues the new section onto the following one. (`insert` with padded
body leaves one extra blank line before the new section — harmless, and stable.)

Since the body is literal, single-quote it so the shell does not expand
backticks, `$`, or newlines. Heredocs and stdin pipes do **not** work for writes
— don't try to pipe a file into `set`:

```text
$ printf 'piped body\n' | lilmd set FILE "=A"
lilmd set: --body <text> is required (or pipe content via stdin)
$ echo $?
2
```

That message claims stdin is supported, but it isn't (as of 0.5.0) — the pipe,
`< file`, and `< /dev/null` all fail with exit 2. Use `--body`.

## Ambiguity: the failure mode worth guarding

Duplicate headings make writes ambiguous, and `lilmd` will happily edit the first
match (for `rm`, the first match and leave the rest). Before writing, prove the
selector is unique:

```bash
lilmd FILE "=Dup" --no-body        # count the blocks it prints
```

If more than one block prints, switch to a regex that anchors the title, or
`rename` one of them first. For `rm` on a duplicated title, this is the difference
between deleting one section and deleting a group.

## Working inside a repo

- Read-only commands are safe to run anywhere. `set` / `append` / `insert` / `rm`
  / `mv` / `rename` / `promote` / `demote` modify the file in place; run them only
  on files you intend to change, and prefer `--dry-run` when unsure.
- After any write to a file with structure that other things assert on (an issue
  ledger with a status table, a doc with a required heading order), re-read the
  TOC and confirm the section count and order are what you expect.
- Don't rewrite a large file with `Write`/`Edit` wholesale just because the change
  is small — that is the case this tool exists for, and a wholesale rewrite
  silently reformats sections you never touched.

## Quick reference

```bash
lilmd FILE                                   # survey
lilmd FILE "/Issue 230:/"                    # read one
lilmd FILE "=Issue 230:" --body-only         # exact, body only
lilmd grep FILE "pattern" --json             # locate
lilmd ls FILE "=Parent"                      # children
lilmd code FILE "/Issue 230:/" --lang ts     # code blocks
lilmd set FILE "=A" --body '
body
' --dry-run                                  # preview a write
lilmd rm FILE "=A"                           # delete a section
```

Exit code is 1 when nothing matches. `lilmd --help` lists every flag.
