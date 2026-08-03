# English AI-tell patterns

Rule IDs match `scripts/scan.py`. **red** = almost always slop, fix on sight. **amber** = the legitimate use looks identical, so judge the context.

**This file holds only what the scanner can't give you**: verdicts, exemptions, boundaries. Each rule's "why" and "fix" is printed alongside its hits, so it isn't repeated here.

Adapted from `stop-slop` by Hardik Pandya (MIT), with the absolute bans relaxed into judgment calls where a blanket rule was doing more damage than the pattern it banned.

---

## en-opener Throat-clearing (red)

Here's the thing / Here's what (why, how) / The truth is / The uncomfortable truth is /
It turns out / Let me be clear / Can we talk about / In today's [X] / In a world where /
At its core / At the end of the day / When it comes to

Any `here's what/this/that` construction announces a point instead of making it. The sentence after the opener is usually the real first sentence.

---

## en-emphasis Emphasis crutch (red)

Full stop. / Period. / Let that sink in. / Make no mistake / This matters because /
Here's why that matters / It's worth noting

---

## en-vague Vague declarative (red)

The reasons are structural / The implications are significant / The stakes are high /
The consequences are real / This is the deepest problem / actually matters /
This is what [leadership] actually looks like

Grammatically complete, looks like a conclusion, names nothing. "The implications are significant" → "Every client that pinned v2 has to re-auth."

---

## en-jargon Business jargon (red)

| Avoid | Use |
|---|---|
| navigate (challenges) | handle, address |
| unpack | explain, examine |
| lean into | accept, commit to |
| landscape | situation, field |
| game-changer | significant |
| double down | commit, increase |
| deep dive | analysis |
| take a step back | reconsider |
| moving forward | next, from now on |
| circle back | revisit |
| on the same page | agreed |

**Exemption:** a term with a fixed technical meaning in the doc is not jargon. "Deep dive" as a section title is jargon; "dive" in a diving-physics paper is not.

---

## en-meta Meta-commentary (red)

The rest of this essay explains… / Let me walk you through… / In this section, we'll… /
As we'll see… / I want to explore… / Plot twist / Spoiler / Hint:

The piece narrates its own structure instead of moving. Readers can see the headings.

---

## en-contrast Binary contrast (amber, highest false-positive rate)

Not X, it's Y / It isn't X. It's Y. / Not because X, but because Y /
The question isn't X, it's Y / not just X but Y / stops being X and starts being Y /
It feels like X. It's actually Y.

**The only test: would a reader plausibly believe X?**

| Sentence | Verdict | Why |
|---|---|---|
| Tokens aren't characters; the model splits text into subword units | keep | readers really do assume characters |
| This isn't a caching bug, it's a clock-skew bug | keep | caching was the reasonable first guess |
| This isn't a technology problem, it's an organizational one | fix | nobody claimed it was purely technological |
| It's not just a library, it's a philosophy | fix | "a philosophy" is empty on its own |

Drop the negation, state Y. If Y then looks flat, Y was always flat and X was propping it up: replace both halves with something specific, don't just delete X.

---

## en-adverb Adverbs and hedges (amber)

really / just / literally / genuinely / honestly / simply / actually / deeply / truly /
fundamentally / inherently / inevitably / interestingly / importantly / crucially

**Exemption — adverbs carrying real precision.** These are deliberately absent from the scanner's pattern, so it won't flag them; the exemption is here for when you're reading by eye:

- "**mostly** works" ≠ "works" — concedes exceptions
- "**theoretically** supported" ≠ "supported" — flags that nobody tested it
- "**roughly** 300ms" ≠ "300ms" — states the precision honestly

Test: does deleting it make the claim stronger? If it does, and the evidence doesn't support the stronger claim, keep the word.

---

## en-passive Passive voice (amber)

was created / were made / is believed that / the decision was reached / mistakes were made /
was implemented / were conducted

**Exemption:** when the actor is genuinely irrelevant or unknown, passive is correct. "The field was deprecated in v3" — who deprecated it doesn't matter.

---

## en-agency False agency (amber)

the data tells us / the market rewards / the culture shifts / the conversation moves toward /
the decision emerges / a complaint becomes a fix / a bet lives or dies

Inanimate things given human verbs, which avoids naming the actor: the one thing the reader wants. "The team shipped it that Friday" beats "the complaint becomes a fix." No specific person fits? Use "you" and put the reader in the seat.

---

## en-wh-start Wh- sentence openers (amber)

Sentences starting with What / When / Where / Which / Who / Why / How.

"What makes this hard is…" buries the subject behind a wind-up clause, and it becomes a reflex fast: three of them in one section is a giveaway. Lead with the subject, or better, name the thing. "What makes this hard is the retry budget" → "The retry budget is the hard part."

**Exemption:** actual questions, and headings phrased as questions. A rhetorical "What if we cached it?" that immediately gets answered is still slop.

---

## Structural patterns (no regex; check by reading)

**Negative listing** — "Not a framework. Not a library. A protocol." A rhetorical striptease. State what it is.

**Dramatic fragmentation** — "[Noun]. That's it. That's the whole API." / "X. And Y. And Z." Manufactured profundity through sentence fragments. Use complete sentences.

**Rhetorical setups** — "What if we thought about it differently?" / "Think about it:" / "Here's what I mean:" / "And that's okay." These announce insight instead of delivering it.

**Rule of three** — three-item lists everywhere. Three scans as rhythmic, so AI defaults to it. Two items are usually more honest; if you have four, say four.

**Uniform rhythm** — every paragraph ending on a short punchy line, every sentence about the same length. Vary it.

**Parallel headings** — every heading built on the same template. Each heading should say what its section covers; matching shapes is not a virtue.

---

## Density limits

Not listed here. The scanner prints every threshold and what exceeding it means (`DENSITY_LIMITS` in `scan.py` is the single source), and the retention lists for bold / dashes / emoji are in SKILL.md step 1. The rule there is **过线即停**: fix what's over the line, stop once it's back under.
