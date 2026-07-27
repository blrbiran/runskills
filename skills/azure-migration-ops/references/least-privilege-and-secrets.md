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

## Owner is not data plane

Subscription `Owner` grants management-plane rights and, on several services, **no data access at
all**. This surprises people repeatedly:

- **Storage** — with `allowSharedKeyAccess=false`, reading blobs needs an Entra data role
  (`Storage Blob Data Reader`), which Owner does not include.
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

An AKS-specific note: after revoking a Kubernetes RBAC grant, the authorization webhook keeps
honouring the old decision for roughly five minutes. A `kubectl` call that still succeeds right
after the revoke is that cache, not a failed revert — verify with the role assignment list.

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
- **A credential committed to a private repository is still exposed.** Private is a configuration,
  not a property: a collaborator change or a visibility flip detonates it. Treat it as a rotation
  task with a deadline, not a resolved issue.
