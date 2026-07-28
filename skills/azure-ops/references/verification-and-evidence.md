# Verification and evidence

The recurring pattern in expensive cloud debugging is not a missing check. It is a check that was
run, passed, and did not mean what everyone assumed it meant.

## State what each piece of evidence actually covers

A chain like `service → container → model API → database` has several links. Evidence about one link
says nothing about the next. Name the link, and name the first link you have **not** proven.

Concretely, these are all true simultaneously and routinely confused:

- the pipeline is green — the code compiled and deployed
- the deploy succeeded — files landed on the host
- routing is confirmed — the process chose the intended provider
- a container was created — compute started
- **something answered** — the only one that proves the chain

Design acceptance gates so the last one is a separate, explicit gate with its own evidence, and say
plainly that the earlier gates do not substitute for it. If the deliverable is "a model/service
responded", the evidence is the **quoted response**, not a green test.

## Absence of evidence is usually about retention, not reality

Before concluding "it never happened", ask what would have deleted it.

- **Ephemeral resources are deleted by their own orchestrator.** A runner that tears down its
  container on completion leaves an empty `az container list` after both success *and* failure. The
  **Activity Log** is the authority for anything short-lived:
  ```bash
  az monitor activity-log list --namespace Microsoft.ContainerInstance \
    --start-time <ISO8601> \
    --query '[].{op:operationName.value, status:status.value, t:eventTimestamp}' -o table
  ```
- **That authority is eventually consistent, and it reads exactly like a failure while it catches
  up.** The Activity Log ingests behind the operation: minutes after a run has demonstrably finished,
  the terminal `Succeeded` row and the subsequent `delete` can both still be missing, while the
  `Started` and `Accepted` rows are already there. A half-populated sequence is the *normal*
  appearance of a recent success, not the signature of one that failed partway. **Re-query before
  concluding anything from an absence** — this is rule 4 in the read direction: an absence is a
  sample, and one sample cannot tell latency from a fact. Where a resource read answers the same
  question, prefer it: the resource is current, the log is not. Reading "is anything left over?" off
  a live `list` is sound; reading "did it ever happen?" off that same empty `list` is not.
- **Platform metrics cap the window they return** regardless of the range you request — a 90-day
  request may quietly return 31 days. State the window you actually got, not the one you asked for.
- **Empty ≠ zero.** `az vm list-usage` returns an empty list, not an error, when
  `Microsoft.Compute` is unregistered. Several `list` commands behave this way. An empty result
  means "check why", not "there is nothing".

## Counts are not outcomes

Request counts cannot distinguish a consumer from a vulnerability scanner, or from a caller that
fails every single time. Always pull **result codes** before concluding a service has users:
tens of thousands of requests that are 100% `4xx` is an internet scanner hitting a public hostname,
not a dependency. This single distinction is often what separates "do not delete, it has active
callers" from a clean retirement.

Similarly, **duration is not success**. A process that retries ten times before giving up runs
*longer* than one that works. Do not read a long-lived container or a slow request as a healthy one.

## Correlation needs a control

Two things on the same interval look causal. The cheap test is to stop one and watch the other: if
suspending a job changes the other signal by zero requests, the correlation is dead. Do this before
building any theory on top of it — and record the disproof, so it is not resurrected later.

## Distinguishing propagation from rejection

When a change should have taken effect and has not:

- **Propagation** produces jitter and eventual success.
- **Stable rejection** produces an identical response every time.

Poll, keep every response body, and look at the *variance*. A flat line across many samples means
the change landed and something else is refusing you — usually a different rule than the one you
edited. Azure `403` bodies name the rule; read them rather than logging "failed".

## An equality check needs its reference value written down

"Verified equal" is a claim about two values, so it survives only if the value you compared against
was recorded at the moment of comparison — a digest, a quota, a config field. There is usually no way
back to it later: cross-tenant work in particular sees one side per login, so the **recorded constant
is the evidence**. Without it the check silently degrades into an existence check — "a digest is
there" — that reads exactly like the original equality claim to anyone who comes after.

Two things make a reference value worthless even when it was recorded:

- **It names something mutable.** A moving tag, a `latest`, a display name — the far side is expected
  to change, so a later difference proves nothing about the copy and a match is luck.
- **It was truncated for readability.** A matching prefix corroborates; it does not verify.

When the reference value genuinely cannot be obtained, record the near-side value as a **new
baseline and label it unverifiable**. An unverifiable check declared as one is useful; the same check
filed alongside real ones is worse than no check.

## Verifying a revert

A revert that exits non-zero may have partially applied. A revert that exits zero may have been
swallowed because the resource was still provisioning from the previous update. Neither exit code is
evidence.

Read the resource, quote the fields that matter, and check for leftovers explicitly — for example
that **zero** role assignments remain at the scope you granted, not merely that the delete command
succeeded.
