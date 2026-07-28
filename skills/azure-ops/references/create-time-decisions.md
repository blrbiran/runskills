# Create-time-only decisions

Some Azure properties cannot be changed after creation without replacing the resource — and
replacing it means a new address, a new name, or a data move. These are not bugs you fix; they are
rebuilds. Decide them **before** writing the `create` command.

The recurring failure is not ignorance of these facts. It is deciding a property implicitly by
accepting a CLI default, then discovering later that the default was a decision.

## The list worth checking every time

| Resource | Property | Why it cannot wait |
|---|---|---|
| Public IP | **SKU** (`Basic`/`Standard`) and allocation | Standard is static by definition; Basic defaults to dynamic. A dynamic address is **released on every deallocate** and comes back different, staling SSH config, NSG documentation and any allowlist. Changing SKU means replacing the address |
| VM | **size family** | Resizing is constrained by the host cluster, by the family's quota, and by whether the region will sell that family at all — three separate limits, distinguished in `references/preflight-and-iac.md`. Building at the intended production spec avoids a migration-inside-a-migration |
| VM | **SSH key** / auth mode | The key is baked at provisioning. Wrong or lost key on a VM with password auth disabled means no way in |
| VM | **OS disk `--os-disk-delete-option`** | Defaults to `Delete`. If the disk holds hand-built config you cannot regenerate, `Detach` means an accidental VM delete is survivable |
| VM / NIC | **NSG placement** (subnet vs NIC) | If both exist, effective rules are the *intersection*. A rule added to the subnet NSG then appears not to work, and the cause is invisible in the rule you are staring at. Prefer exactly one |
| Cosmos DB | **API and `serverVersion`** | Not upgradable in place. A clean restart is the cheapest moment to leave a deprecated version behind |
| Storage | **account kind**, **replication**, **hierarchical namespace** | Replication changes within limits; kind does not. HNS is the one to state precisely: it is not a flag you can set later, but it is also **not a rebuild** — enabling it on an existing account is a one-way migration (`az storage account hns-migration start`, validation pass first) with prerequisites and no route back. Calling it impossible invites planning a rebuild that is not required |
| Service Bus / Event Hub | **tier**, **partitioning**, **zone redundancy** | Partitioning and zone redundancy are fixed at namespace creation |
| AKS | **network plugin/policy**, **RBAC mode**, **node subnet** | Cluster-level and effectively permanent |
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
- ACR **SKU** can be changed later (`az acr update --sku`), but it gates features you may have already
  designed around — geo-replication and scope maps are Premium-only. Choose it against the features
  you intend to use rather than against today's storage footprint.
- ACR **admin user** is off by default and is a toggle, not a rebuild — but it is a standing
  credential, and enabling it "just to get one pull working" is how it becomes permanent. A
  repository-scoped token fits the same username/password fields; see
  `references/images-and-registries.md`.
