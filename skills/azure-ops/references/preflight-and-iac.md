# Preflight and declarative deployments

## Preview before you write: `what-if`

ARM and Bicep deployments have a built-in dry run. It reports, per resource, what would be created,
deleted, modified or left alone — before anything is applied. This is the cheapest possible check on
a create-time decision, because it shows you the diff without spending the resource.

Pick the command from the template's `targetScope`:

| `targetScope` | Command |
|---|---|
| `resourceGroup` (default) | `az deployment group what-if -g <rg> --template-file <f> --parameters <p>` |
| `subscription` | `az deployment sub what-if -l <region> --template-file <f> --parameters <p>` |
| `managementGroup` | `az deployment mg what-if -l <region> -m <mg-id> --template-file <f> --parameters <p>` |
| `tenant` | `az deployment tenant what-if -l <region> --template-file <f> --parameters <p>` |

For `azd` projects (an `azure.yaml` in the root), the equivalent is `azd provision --preview`.

Read the change symbols carefully — two of them are routinely misread:

| Symbol | Meaning |
|---|---|
| `+` | create |
| `-` | **delete** |
| `~` | modify |
| `=` | no change |
| `*` | **ignored — not analyzed** |
| `!` | **deploy — changes unknown** |

`-` is the one worth stopping for. A deployment in Complete mode deletes resources that are absent
from the template, and an unintended delete is the most expensive thing this command can catch for
you.

`*` and `!` mean *not analyzed*, not *nothing will happen*. Reading them as "no change" is exactly
the class of error this skill exists to prevent: a check ran, passed, and did not cover what you
assumed it covered.

## Validating without full deploy rights

`--validation-level Provider` runs provider-side validation including the RBAC preflight. If it
fails on **permissions** rather than on the template, retry with `ProviderNoRbac`, which skips the
RBAC check:

```bash
az deployment group what-if -g <rg> --template-file <f> --validation-level ProviderNoRbac
```

This is useful precisely because it lets you validate without first requesting broader rights.

Record which level produced the result. A pass at `ProviderNoRbac` is a statement about the template
alone — it is **not** evidence that the deployment will be permitted. Name what your evidence covers.

## Imperative or declarative

Both are correct in different phases, and the useful question is not which is better but which the
current work is:

- **Exploration and one-off investigation** — imperative `az` is right. You are discovering the
  shape of an estate, and a template written before you understand it is a guess.
- **Anything that must be reproducible, reviewed, or rebuilt elsewhere** — declarative. A migration's
  whole value proposition is "we can stand this up again", and a shell history is not that.

A practical middle path: build imperatively while learning, author templates for the parts you
intend to keep, then run `what-if` against the live estate to see whether template and reality
actually agree.

That last step doubles as a **drift detector**. A non-empty diff on a template you believed was
current means the estate was changed out of band — worth knowing before you rely on the template for
a rebuild or a rollback.

Caveat on exports: `az group export` and friends produce templates that carry runtime state, drop
dependencies, and frequently will not redeploy as-is. Treat an exported template as a first draft to
edit, not as an artifact you can trust.

## Run the whole validation pass before reporting

When you are **validating**, continue past failures and collect every issue, then report once.
Stopping at the first error produces serial round-trips in which each fix only reveals the next
problem — expensive when each cycle involves a human.

This is deliberately the opposite of the rule for **executing**, where a failed step must halt the
sequence because the steps after it assume it succeeded. Validation changes nothing, so it carries
no such dependency.

## Confirm the tools before trusting their absence

```bash
az --version        # 2.76.0+ for --validation-level
azd version         # only relevant for azure.yaml projects
bicep --version     # syntax check: bicep build <file> --stdout
```

If a tool is missing, say so in the report and note which check was therefore **not run**. Silently
skipping a validation and reporting the remaining ones as a pass is how an unvalidated template
reaches production.
