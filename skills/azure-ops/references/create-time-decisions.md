# Create-time-only decisions

Some Azure properties cannot be changed after creation without replacing the resource — and
replacing it means a new address, a new name, or a data move. These are not bugs you fix; they are
rebuilds. Decide them **before** writing the `create` command.

The recurring failure is not ignorance of these facts. It is deciding a property implicitly by
accepting a CLI default, then discovering later that the default was a decision.

**The durable half of this file is the property list; the verdicts are leads.** Which properties are
worth deciding before you create does not change. Whether each one is still immutable does — see the
capability-claims rule in `SKILL.md`, and confirm the verdict you are about to act on rather than
the whole table. That the claims decay is not hypothetical here: every "cannot be changed" below was
re-checked against `az ... --help` on CLI 2.83.0 and the check moved five of them — SSH key, NSG
placement, Cosmos `serverVersion`, Service Bus tier and the AKS network plugin all had an update
path the table denied. Where a flag exists but its conditions are unclear, this file says so instead
of guessing: a flag proves the property is not create-time-only; it does not prove the transition is
unconditional.

## The list worth checking every time

| Resource | Property | Why it cannot wait |
|---|---|---|
| Public IP | **allocation** (and, with conditions, SKU) | Standard is static by definition; Basic defaults to dynamic. A dynamic address is **released on every deallocate** and comes back different, staling SSH config, NSG documentation and any allowlist. That behaviour is the decision to get right up front. SKU is the softer half: `az network public-ip update --sku` accepts `Basic`/`Standard`/`StandardV2`, so a change is not automatically a new address — but the transition carries conditions the CLI does not state, so plan it rather than assume it |
| VM | **size family** | Resizing is constrained by the host cluster, by the family's quota, and by whether the region will sell that family at all — three separate limits, distinguished in `references/preflight-and-iac.md`. Building at the intended production spec avoids a migration-inside-a-migration |
| VM | **auth mode** (key-only vs password) | The mode is what you are deciding; the key itself is **recoverable**. `az vm user update --ssh-key-value` resets a user's key through the VMAccess extension, from the control plane, so a lost key on a password-disabled VM is not a rebuild. Do not plan one |
| VM | **OS disk `--os-disk-delete-option`** | Defaults to `Delete`. If the disk holds hand-built config you cannot regenerate, `Detach` means an accidental VM delete is survivable. **Unverified** whether it is settable afterwards — there is no first-class flag on `az vm update`, only the generic `--set`. Setting it at create time costs nothing either way |
| Cosmos DB | **API** | The API (Mongo / SQL / Cassandra / …) is fixed at account creation. **`serverVersion` is not** — `az cosmosdb update --server-version` accepts `3.2` through `7.0` for Mongo accounts, so a deprecated version is an upgrade, not a rebuild. A clean restart is still the cheapest moment to take it, but it is not the only one |
| Storage | **account kind**, **replication**, **hierarchical namespace** | Replication changes within limits; kind does not (`az storage account update` exposes no `--kind`). HNS is the one to state precisely: it is not a flag you can set later, but it is also **not a rebuild** — enabling it on an existing account is a one-way migration (`az storage account hns-migration start`, validation pass first) with prerequisites and no route back. Calling it impossible invites planning a rebuild that is not required |
| Service Bus / Event Hub | **partitioning**, **zone redundancy** | Both are fixed at namespace creation. **Tier is not** — `az servicebus migration` exists specifically to move a Standard namespace to Premium |
| AKS | **node subnet** | Effectively permanent. The other cluster-level network choices are **not**: `az aks update --network-plugin-mode overlay` migrates a cluster to Azure CNI Overlay and `--network-policy` changes the policy engine, so treat plugin and policy as constrained migrations rather than as rebuilds |
| Any global-DNS resource | **name** | Storage accounts, ACR, Key Vault, Cosmos take a globally unique DNS label. Renaming = recreate + data move |

## How to use this

Before running a `create`, write down the properties above that apply, with the value you intend and
one clause on why. If you cannot justify a value, you have not decided it — you are accepting a
default. That is fine for genuinely unimportant properties, and dangerous for these.

Put every create-time decision into **one** command where the CLI allows it. Splitting them across
"create now, configure after" reintroduces exactly the retrofit problem, and some properties are
simply not settable afterwards.

## Related traps that look create-time but are not

- `az functionapp create` yields `httpsOnly=false` regardless of intent — set it explicitly
  afterwards and verify.
- Storage TLS floor and anonymous-blob-access default to permissive values on older API versions.
  Set them explicitly; they *are* changeable, so this is a checklist item rather than a rebuild.
- Tags are always changeable, but applying them at create time is the only way they stay consistent
  — a later sweep always misses something.
- **NSG placement** (subnet vs NIC) is freely changeable — `az network nic update --network-security-group`
  and `az network vnet subnet update --network-security-group` both exist — so it is not a create-time
  decision. It belongs here because the *trap* is real: if both a subnet NSG and a NIC NSG exist,
  effective rules are the **intersection**, so a rule added to one appears not to work and the cause is
  invisible in the rule you are staring at. Prefer exactly one, and check which one is actually bound.
- ACR **SKU** can be changed later (`az acr update --sku`), and it gates fewer features than is often
  assumed. **Scope maps and repository-scoped tokens are not Premium-only** — they work on a
  **Standard** registry, confirmed against a live one. Older documentation still says otherwise, and
  believing it is expensive: it pushes you toward enabling the registry **admin user**, the standing
  credential this skill tells you to avoid, to get a pull working. Geo-replication does remain a
  higher-tier feature. Choose the SKU against the features you intend to use rather than against
  today's storage footprint.
- ACR **admin user** is off by default and is a toggle, not a rebuild — but it is a standing
  credential, and enabling it "just to get one pull working" is how it becomes permanent. A
  repository-scoped token fits the same username/password fields; see
  `references/images-and-registries.md`.
