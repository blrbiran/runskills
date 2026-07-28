# Container images and registries

## Content-addressed tags make CI reuse images — which is a feature and a trap

A common CI pattern names a base image by content:

```
tag = <version-file>-<md5(Dockerfile) first N>
reuse if the registry already has it; BUILD IT IF NOT
```

This is why such builds are stable for months: the Dockerfile does not change, so the tag does not
change, so the same image is reused — and whatever unpinned dependency it installed at build time
stays frozen inside it.

The trap is the **empty registry**. Point that CI at a new registry and the lookup misses, so it
builds — and every unpinned `latest` in the Dockerfile resolves to whatever is current *that day*.
The first deploy into a new account is therefore the single most likely moment for silent dependency
drift, precisely when you are least able to tell a migration bug from a version bug.

Two mitigations, in order:

1. **Import the known-good image under its exact expected tag** before the first deploy. CI then
   finds it and reuses it, and the migration is tested without a simultaneous version change.
2. **Pin the version** (`@scope/pkg@x.y.z`, `apt-get install pkg=version`) as a separate change. The
   argument is reproducibility, not that `latest` is broken: today the same commit and the same
   Dockerfile can produce different images on different days with no commit recording the
   difference. That non-reproducibility is what makes such outages expensive to diagnose.

## `az acr import` is a free server-side copy

It moves layers registry-to-registry without pulling them locally, needs no local Docker, and does
not consume local bandwidth. Because it is free, escrowing a single-copy image into a second
registry is close to costless insurance — worth doing for any image that exists in exactly one place
and cannot be rebuilt byte-identically.

When escrowing, **mirror the source repository path** rather than renaming. Relocating later is then
a second free import rather than a rename that breaks references.

`az acr import` writes to the target under your RBAC identity and reads the source with credentials
you supply, so no new token is needed on the target side and the source side stays read-only.

## Verify by digest, not exit code

A successful `import` command is not evidence about the image. Compare digests:

```bash
az acr repository show -n <registry> --image <repo>:<tag> --query digest -o tsv
```

Target digest must equal source digest. This is the same rule as everywhere else in Azure work: the
command's exit status describes the request, not the resource.

## Do not overwrite an escrowed tag when rebuilding

If you escrow a known-good image and later rebuild "the same" image to test a fresh dependency set,
a content-addressed tag scheme will produce **the same tag** — because the Dockerfile has not
changed. Building into it destroys the fallback the experiment depends on.

Build the experiment to a **distinct tag** and point configuration at it. Then a failure costs one
config line to roll back, and the known-good image is still there.

### Checking whether a tag was overwritten, when no digest was recorded

A retag reuses the tag name, so a list of tag names cannot tell an intact escrow from one that was
built over — both show exactly the name you expect. The digest comparison above is the strong check,
but it needs a reference value someone wrote down at escrow time, and often nobody did.

The registry keeps its own timestamps, which need no far-side value:

```bash
az acr repository show-tags -n <registry> --repository <repo> --detail \
  --query "[].{tag:name, created:createdTime, updated:lastUpdateTime}" -o json
```

`lastUpdateTime` equal to `createdTime` is consistent with a tag nothing has written since it was
created. It is weaker than a digest comparison — it speaks to *when*, not to *what* — so report it as
that. Only the unchanged direction has been observed; **before relying on this to catch an
overwrite, confirm the stamp actually moves when a tag is repointed.** A check whose positive case
you have never seen fire is an assumption wearing a command.

## An escrowed copy is a snapshot, not a mirror

`az acr import` copies an image once. Afterwards the two registries have no link, so neither reports
that they have diverged — and under a content-addressed tag scheme they diverge on the first
Dockerfile edit: the tag moves, the source builds the new one, and the escrow still holds the old
tag under the old name.

This does not weaken the escrow as a **fallback**; the image it holds is as good as the day it was
copied. What expires is its **equivalence** — it quietly stops being a copy of what the source
currently runs, with no event anywhere to notice. Before treating an escrow as "what production
runs", read the source's current tag rather than the escrow's age.

## Registry hostnames hide in places a secret cannot fix

Migrating a registry usually means changing a variable. Check for hardcoded hostnames in places that
do not read that variable — a `docker pull` line inside a workflow, a Kubernetes manifest, a
`FROM` in a Dockerfile that was not parameterized. Those are code changes, and no amount of image
importing fixes them. Grep for the registry hostname across the repo before declaring the move
complete.

## One repository can be written by two projects

A repository path is not owned by whoever pushes most often. Check what tags actually exist before
applying any retention or cleanup policy — a rule aimed at one project's version tags can take
another project's tags with it. Separating the two into different registries removes that coupling
permanently.

## Credentials for pulling

Prefer a **repository-scoped token** with `content/read` over enabling the registry admin user: it
fits username/password fields, is revocable, and is scoped to specific repositories. Verify the
scope map really is read-only after creating it — any `content/write`, `content/delete` or
`metadata/write` action means the credential can mutate the registry.

This matters most because pull credentials are usually passed onward to the compute that pulls, where
anyone able to inspect that compute can read them back.
