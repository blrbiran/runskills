# Least privilege and secrets

## Never open a permission speculatively

The temptation is to grant something broad "so the next step doesn't fail". The cost is that broad
grants are forgotten, and a forgotten grant is indistinguishable from an intended one to whoever
reads the estate later.

Grant the **narrowest role, at the narrowest scope, for the shortest time**. If the narrow one turns
out to be insufficient, that failure is cheap and informative. If the broad one works, you learn
nothing and leave a hole.

If a wider grant seems genuinely necessary, stop and ask rather than deciding unilaterally — and
say which specific operation needs it.

## Finding the narrowest role, rather than guessing at it

"Use the narrowest role" is only actionable if you can find it. Work from the **operations**, not
from a description of the job:

1. **Name the operations the code actually performs.** Read the calls, do not infer from the feature.
   `az provider operation show --namespace Microsoft.ContainerInstance` lists every operation a
   provider exposes, and marks which are data-plane rather than management-plane — the distinction
   that catches people out below.
2. **Search built-in roles for the smallest that covers them.**
   ```bash
   az role definition list --custom-role-only false -o json \
     --query "[?contains(to_string(permissions[0].actions), 'Microsoft.ContainerInstance')].{role:roleName, actions:permissions[0].actions}"
   ```
3. **Prefer a built-in role.** Define a custom role only when no built-in covers the set without
   also granting materially more. A custom role is yours to maintain, and it silently falls behind
   as the provider adds operations.
4. **Scope beats role.** A broader built-in role at a **single resource group** is usually both safer
   and simpler to reason about than a hand-cut custom role at subscription scope. Reach for the
   scope dial before the role dial.

When you settle on something wider than the minimum, write down the specific operation that forced
it. That sentence is what lets a reviewer agree or narrow it later; without it, the grant becomes
permanent by default.

## Owner is not data plane

Subscription `Owner` grants management-plane rights and, on several services, **no data access at
all**. This surprises people repeatedly:

- **Storage** — `--auth-mode login` forces the Entra path, so a blob read fails with an
  authorization error **whether or not the account allows shared keys**; `allowSharedKeyAccess`
  decides only whether a fallback exists. That path needs `Storage Blob Data Reader`, which Owner
  does not include, and the failure goes to stderr — a projection like `--query "length(@)"` then
  prints nothing at all, which reads like an empty container.
- **AKS with Azure RBAC for Kubernetes** — Owner grants no Kubernetes `dataActions`; `kubectl`
  returns `Forbidden`. The narrow fix is a temporary `Azure Kubernetes Service RBAC Writer` scoped
  to a single **namespace**. Prefer `az aks command invoke` over a local kubeconfig: nothing lands
  on disk and no admin certificate is downloaded. Do **not** reach for `--admin` credentials — they
  are cluster-wide and effectively unrevokable, i.e. worse than the scoped grant.
- **AI Search / Cognitive Search** — with `disableLocalAuth=true`, key auth is off and Entra data
  roles are mandatory.

A consequence worth exploiting: **prefer management-plane commands when they exist.** Creating
containers and file shares via `az storage container-rm create` / `az storage share-rm create`
avoids needing a data-plane role at all.

The read side has a sibling too: `--auth-mode key` reaches the data plane through a management-plane
`listKeys` an Owner already holds, so a blob or share *read* needs no grant either. Reach for it
**before** opening a role for yourself — the authorization error names the roles that would fix it,
which invites exactly the speculative grant this file opens by warning against. Its limit is the
condition above: with `allowSharedKeyAccess=false` there is no key to list, and the Entra role is
genuinely required.

An AKS-specific note: after revoking a Kubernetes RBAC grant, the authorization webhook keeps
honouring the old decision for roughly five minutes. A `kubectl` call that still succeeds right
after the revoke is that cache, not a failed revert — verify with the role assignment list.

## The mirror: a data-plane role hides the resource instead of refusing you

Everything above is a management-plane identity that cannot reach data, and it announces itself — an
authorization error, usually naming the role that would fix it. **The reverse does not present as a
permission failure at all**, which is what makes it expensive.

A role scoped to a service's *operations* may carry no management-plane **read** of the resource
those operations act on. The CLI resolves the resource through ARM before it ever reaches the data
plane, so the command fails at that first step with *the resource could not be found in subscription
`<the one you meant>`* — a confident sentence, naming the right subscription, which sends the reader
looking for a deleted resource, a typo, or the wrong tenant. It is the same not-found ambiguity rule
1 opens on, arriving through the one door rule 1's own check cannot close.

**Read a role's `actions`, not its name.** A name describing what the role lets you *do* says nothing
about whether it includes the `Microsoft.<provider>/<type>/read` that tooling needs to find the
resource in the first place, and the two are routinely packaged apart. Server-side build and task
commands need a third thing again: queueing work is its own action, distinct from both planes, so a
role granting the read and the data-plane write can still leave those commands failing.

Separating the two causes costs one read: ask for the same resource as an identity holding
management-plane rights. If it appears, the resource exists and the caller's role is the gap — and
the fix is the narrowest role whose `actions` cover the operations actually run, which is usually not
the one named after the thing you are trying to do.

## A missing login fails only half the commands

An unattended host that shells out to `az` — a worker creating containers, a job draining a queue —
depends on the CLI's login the way it depends on a package being installed, and nothing declares it.
When that login goes, `az` does not stop. It splits.

Commands that **carry their own credential** — `--account-key`, `--connection-string`, a SAS — never
consult the login. Commands that resolve through ARM do. With `AZURE_CONFIG_DIR` pointed at an empty
directory, `az storage container list --account-key <a deliberately invalid key>` answers
*Authentication failure … invalid account key, connection string or sas token* — it reached the
service and evaluated the key — while `az storage account list` in the same shell answers *Please run
`az login`*. Two commands seconds apart, disagreeing about whether the CLI is usable. That check is
free and needs no real key, which makes it a quick way to tell a credential problem from a permission
one.

Note which way this cuts against the `--auth-mode key` route above: **that** one reaches the data
plane through a management-plane `listKeys`, so it does need the login. A key handed to the command
directly does not.

So **a subset of `az` still working is not evidence the CLI is authenticated**, and on a busy host the
key-carrying calls are usually the majority — the failure then looks like one broken operation rather
than a lost credential. `az account show` is the reading. A populated `~/.azure` is not: a logout
leaves the token caches on disk and empties only the profile's subscription list, so the directory
looks much the same either way.

The repair the error text invites — `az login` — restores the same dependency with a fresh expiry,
because a user login is one person's session and renewing it is interactive. Where the host has a
**managed identity**, `az login --identity` mints from the instance metadata endpoint with no user
credential in the loop. Whether that identity can do the work is the separate question the next
section answers; assignment and access are not the same thing.

## An assignment list is the intent; the principal's own reads are the access

`az role assignment list` answers "what did we grant, at the scopes we asked about". That is not the
same question as "what can this principal do", and the gap is not hypothetical: assignments made at a
higher scope **inherit downward** without appearing in a scope-local query, and deny assignments do
not show up alongside the grants they override.

When a narrow scope is the safety property — the reason it is safe to hand an identity to something
untrusted — prove it by **acting as the principal**, in both directions:

```bash
# on the host holding the identity
az login --identity --only-show-errors
az account show --query id -o tsv                 # the expected subscription
az resource list -g <the group it SHOULD reach>   # must succeed, and parse as JSON
az resource list -g <the group it must NOT reach> # must fail; keep the body
```

The refusal is the half worth collecting: an `AuthorizationFailed` body names the principal's object
ID, the action and the scope, which is a far stronger record than a list that merely failed to
mention a role. **Run the positive case too** — a probe that only ever fails proves nothing about
whether you tested anything, since a broken login also fails both ways.

Parse the success case rather than counting its lines. Piping a list into `wc -l` prints `0` both for
an authorized query against an empty group and for an authorization error, because the pipe discards
the exit code — the same class of mistake as trusting an exit code in the first place.

## Temporary grants and openings need a watchdog, not a trap

A shell `trap` fires on the script's own exit paths. It cannot help if the session itself dies — and
a session dying mid-run is exactly how environments get left open.

Before opening any firewall or granting any temporary role, arm a **detached** process that reverts
unconditionally after a hard deadline:

```bash
nohup bash -c 'sleep 2400; <revert commands>' >/dev/null 2>&1 &
WATCHDOG=$!
# ... do the work, then run the real revert, verify it, and only then:
kill $WATCHDOG
```

Order matters when opening network access, and the safe order differs per service:

- **Storage** has a `defaultAction`. If it is `Allow`, enabling public access *first* exposes the
  account to the internet for the seconds before your IP rule lands. Correct order:
  `defaultAction=Deny` → add the IP rule → enable public access. On the way out, reverse it.
- **AI Search has no `defaultAction`.** `publicNetworkAccess=enabled` with an **empty** IP rule list
  means open to everyone. Set the rules and enable in **one** call; on the way out, disable public
  access **first**, then clear rules. Also: `--ip-rules ""` does not clear the list (it fails with an
  opaque error) — use `--set networkRuleSet.ipRules='[]'`. And `az search service update` is
  long-running and fails opaquely if the service is still provisioning from a previous update, so
  serialize updates and poll `provisioningState`.

Then verify the revert against the resource, and check that **zero** assignments remain at the scope
— not merely that the delete returned success.

## Secrets

- **Never into a repository.** Not in a file, not in a commit message, not in a doc. Record key
  *names*, resource IDs and non-secret routing values instead.
- **Never into stdout.** Redirect generated credentials straight to their destination file rather
  than printing and copying. To confirm a private key is usable, `ssh-keygen -l -f <file>` prints a
  fingerprint; `cat` prints the key.
- **Never into a transcript.** Do not ask a user to paste a live credential into a chat.
- **Beware shell interpolation.** A secret embedded in a remote `bash -lc "...$KEY..."` string can
  land in shell history and is visible in the process list on the remote host while it runs. Prefer
  piping it over stdin, or writing it with a heredoc that the remote shell reads directly.
- **Prefer scoped, revocable credentials over standing ones.** For ACR, a repository-scoped token
  with `content/read` fits username/password fields without enabling the admin user. This matters
  most when the credential is passed onward — anything handed to a container through environment
  variables is readable by anyone who can `show` that container.
- **A SAS's revocability is fixed at the moment it is issued.** A service SAS can reference a
  container **stored access policy**, which keeps expiry and permissions server-side: one policy
  update extends or revokes every SAS pointing at it, with nothing reissued and nothing redeployed.
  An account SAS has no policy to reference — look for a `--policy-name` on the generating command
  before assuming either way — so its expiry is signed in, and the only way to cut it short is
  rotating the account key, **which invalidates every other SAS signed with that key at the same
  time.** Reach for the policy whenever the credential will outlive the session that issued it: a
  long-dated policy-less SAS in a deployment secret is a bearer credential with no off switch, and
  its expiry is a deadline nothing observes — it surfaces as authorization failures wherever that
  credential is consumed, which is rarely where anyone is watching.
- **A credential committed to a private repository is still exposed.** Private is a configuration,
  not a property: a collaborator change or a visibility flip detonates it. Treat it as a rotation
  task with a deadline, not a resolved issue.
