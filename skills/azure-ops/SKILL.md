---
name: azure-ops
description: Plan and execute Azure work safely — creating infrastructure with `az`, migrating resources between subscriptions or tenants, and maintaining running services on it. Use whenever the task involves `az` CLI commands, ARM resources, subscription or tenant moves, standing up VMs / storage / ACR / ACI / Cosmos / Service Bus / AKS, container registries and image promotion, quota and RBAC questions, firewall or private-endpoint changes, shadow or staging environments that mirror production, or diagnosing why a deployed Azure service stopped working. Also use when the user says "migrate to a new Azure account", "build this in the target subscription", "why did my ACI container fail", "the deploy succeeded but nothing works", or asks for a runbook, cutover plan, or rollback plan for cloud infrastructure — even if they do not name Azure explicitly but the resources are clearly Azure.
---

# Azure Operations

## Outcome

Azure changes that are **reversible, evidence-backed, and cheap to hand off**. Every write is
preceded by an assertion about *where* it lands, and followed by a check against the resource
itself — not against the command's exit code.

Most expensive Azure mistakes are not typos. They are confident conclusions drawn from the wrong
evidence: a command that returned zero, a resource list that was empty for a different reason than
you assumed, an IP address reported by a service that answered over a different network path. This
skill is mostly about not doing that.

## The four rules that prevent the expensive failures

Each exists because the failure it prevents is **silent**: the command succeeds, and a wrong
conclusion survives unchallenged for hours. Understand why each holds and you can derive the rest.

**1. Assert the target by ID before every write.**
Subscription *names* are mutable metadata and are routinely duplicated across tenants. A
name-pinned script silently retargets the first time someone renames something. Worse: two
subscriptions in different tenants cannot both be visible — one `az login` sees exactly one side, so
"the resource isn't there" and "you are looking at the wrong tenant" are indistinguishable without
an explicit check.

```bash
az account show --query id -o tsv    # compare to the expected GUID, then proceed
```

The same hole exists one scope down, and there it is worse. A short name (`--vnet-name`, a bare
`--subnet`) resolves inside the command's own `-g` and is never searched for across the subscription
— and finding nothing is not an error. `az` **invents** the missing resource and proceeds, under the
name you asked for, so every later check by name agrees with you. Reference resources in another
resource group by full ID, and verify by address rather than by name; see
`references/networking-and-egress.md`.

**2. A create is *accepted*, not *ready*.**
`az ... create` returns when the control plane accepts the request. Firing a dependent create
immediately is a race you will lose intermittently — which is worse than losing it every time,
because it looks like flakiness. Gate on a terminal state (`provisioningState=Succeeded`,
`PowerState/running`) before anything that depends on it.

The mirror case is a command that never returns. The CLI's own wait can expire while the operation is
still **in flight**, so read `provisioningState` before concluding anything: `Deleting` or `Updating`
means it is proceeding and the move is to poll to a terminal state. Re-issuing a destructive command
you assumed had failed is the expensive mistake here.

**3. Verify against the resource, not the exit code.**
This applies doubly to *reverts*. A revert that exits non-zero may have partially applied; a revert
that exits zero may have been swallowed while the resource was still provisioning. Only `az ... show`
output is evidence. If you are about to write "done" or "reverted", run the read first and quote it.
Read the *binding*, not only the object — an **orphan** NSG, route table or diagnostic setting
attached to nothing reports `Succeeded` exactly like a working one, so check the association from
both sides.

Deletes fail the same way in the other direction, and there `ResourceNotFound` is the misleading
read: several services soft-delete, so the resource stays restorable and its **name stays held**
while every `show` reports it gone. Ask the service for its deleted list at the moment of use — per
the capability-claims rule below — and read the purge date: it is both the deadline for an undo and
the date the name comes back. Deleting the last child leaves an **orphan** in the mirror direction —
a container with nothing left in it, reporting healthy. Count what remains at the scope.

**4. Never blind-wait. Poll the real data plane, and keep the error bodies.**
Propagation delays are real, so the instinct is to `sleep 600`. Resist it: polling is both faster and
diagnostic. A flat line of identical failures is a *stable rejection*, not slow propagation — that
distinction is often the whole diagnosis. Azure's `403` bodies name precisely which rule rejected
you; discarding them turns a five-minute fix into a multi-session mystery.

This holds when *reading*, too, and there it is easier to miss because the answer looks conclusive
rather than pending. Log and metric surfaces ingest behind the operation, so a missing row is a
sample, not a fact: re-query before concluding an event never happened. Where a resource read
answers the same question, prefer it — the resource is current, the log is not.

## Workflow

**Understand the ground truth before planning.** Read the live resources rather than the docs
describing them — inventories drift. Management-plane reads (`az ... list`, `... show`) are free,
read-only, and need no data-plane role, so there is rarely an excuse for guessing. If the session has
Azure MCP tools (`azmcp-*`), prefer them for reads: they return structured results instead of text
you have to parse, which is one less place to misread an answer.

**Separate plan from evidence from execution record.** Three different documents with three
different lifetimes: the plan says what should happen, the evidence captures what the source looked
like, the execution record says what actually happened and what broke. Collapsing them produces a
document nobody trusts, because a reader cannot tell intent from observation.

**Decide the create-time-only choices before creating anything.** Some Azure properties cannot be
changed after creation without replacing the resource. Getting these wrong is not a bug you fix; it
is a rebuild. See `references/create-time-decisions.md` — check it before writing any `create`
command.

**Treat this skill's capability claims as leads, not verdicts.** "Cannot be changed after creation",
"needs a higher tier", "there is no flag for it" — Azure only ever adds in-place migrations and
lowers tier gates, so these decay in one direction: toward a rebuild you did not need, or a tier you
already have. Confirm at the moment of use with `az <group> update --help`, plus a look for an
`az <group> migration` subcommand. That check is local, free and needs no subscription, which is why
it belongs in the flow rather than in a periodic sweep — a swept file is only current on the day it
was swept.

**Preview the write before making it.** Where the change is expressed as a template, `what-if` shows
the per-resource diff — including deletions — without spending anything. It is the only check that
catches a create-time mistake while it is still free. See `references/preflight-and-iac.md`.

**Grant the narrowest privilege, revert in the same session, verify the revert.** Never open a
permission speculatively "in case it's needed". If a temporary grant or firewall opening is
required, arm a detached watchdog that reverts unconditionally on a deadline *before* opening
anything — a shell `trap` dies with its shell, which is exactly how environments get left open when
a session is interrupted. Details in `references/least-privilege-and-secrets.md`.

**Prove the thing end to end, and be precise about what your evidence covers.** A green pipeline is
not evidence that a service works. A created container is not evidence that anything answered. State
explicitly which link in the chain each piece of evidence covers, and name the first link you have
*not* proven. See `references/verification-and-evidence.md`.

## Reference material

Read the one that matches what you are about to do — each is short and specific.

| File | Read it when |
|---|---|
| `references/create-time-decisions.md` | before any `az ... create` — the properties you cannot change later |
| `references/preflight-and-iac.md` | `what-if`, `--validate` before an imperative create, a create refused as quota or capacity, Bicep/ARM/azd, and drift |
| `references/verification-and-evidence.md` | designing acceptance gates, confirming a delete or a revert, or when an "impossible" result appears |
| `references/least-privilege-and-secrets.md` | any RBAC grant, firewall change, credential, or `.env` |
| `references/networking-and-egress.md` | IP allowlists, NSGs and subnets, private endpoints, DNS, or "it works from here but not there" |
| `references/images-and-registries.md` | ACR, container images, tags, or promoting an image between accounts |
| `references/service-maintenance.md` | a deployed service misbehaves, or you are diagnosing config that "should" be right |

## Migrating between subscriptions or tenants

Scope work as **project × environment** units that are independently rebuildable, and finish one
before starting the next. A half-migrated estate is harder to reason about than either end state.

Prefer **clean restart over data copy** wherever the data is reconstructible — it is the cheapest
moment to fix deprecated settings you are otherwise stuck with (an old Cosmos `serverVersion`, a
TLS floor, an anonymous-access default). Note the ones you are deliberately changing, so the
difference is a decision rather than a discrepancy someone finds later.

When the new environment must run alongside the old one, build it as a **shadow**: same shape, no
traffic. The dangerous shortcut is copying production configuration and deleting the parts you don't
want. Active workers are active by default — given production credentials they will poll real
queues, claim real work, and write into real databases within seconds of starting. Build the config
**key by key from what the code actually reads**, then verify key-by-key what must be *absent*. The
absent list is the safety property, so make it explicit and check it, rather than trusting that you
remembered.

That rule has a second half, and it bites even when you have followed the first: **the source config
is evidence of what was once set, not of what is read.** A live config accumulates keys nothing
consumes, and a key naming a resource is not proof the resource is used — acting on one sends you
provisioning a container, queue or share the code never asks for, and the mistake survives review
because the config and the plan agree with each other. Confirm the consumer in the code before
treating any key as a requirement.

Before cutover, know these and say them out loud: what carries traffic today, what the rollback is,
what is irreversible, and what the standing cost is on both sides.

## Communicating results

Report what the commands returned, not what they were supposed to return. When a finding contradicts
a stated premise — including the user's — say so plainly once, with the evidence, then continue.
Re-test premises rather than inheriting them: ask what evidence each one rests on. "This service has
active callers" may rest on request counts with no result codes attached. "DNS is broken" may rest
on one zone standing in for all of them. "The subscription lapsed" may rest on an inference the
subscription record itself contradicts.

If an action is irreversible, costly, or outward-facing — deleting a resource, cutting traffic over,
opening a firewall, starting a billable VM — confirm before doing it, and confirm again for the
*timing* if the user reserved that decision. Approval of a mechanism is not approval of a moment.
