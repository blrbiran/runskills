# Networking, egress and DNS

## Your egress IP is not what an IP-echo service tells you

`api.ipify.org` and friends report the address *their* request arrived from. If the machine runs a
transparent proxy or VPN — Clash, Surge, WARP-style "fake-IP" modes are common — different
destinations take different routes, so the address Azure enforces against can differ from the one
the echo service saw. An IP allowlist built on that answer never matches, and the failure looks
exactly like slow propagation.

The cheap check is to ask about the connection you actually care about:

```bash
curl -s -o /dev/null -w '%{local_ip} %{remote_ip}\n' https://<the-azure-host>
```

An address in **`198.18.0.0/15`** (the RFC 2544 benchmarking range) means a transparent proxy is
intercepting and you are not seeing the real path. Also check whether IPv6 is in play — a v4/v6
mismatch produces the same symptom.

Two consequences:

1. **Make the proxy irrelevant rather than guessing the address** — bypass it for the specific Azure
   hostnames, then re-detect and confirm `remote_ip` is a real Azure address.
2. **If you instead allowlist a proxy exit node, understand it is probably shared.** That admits
   every other client of that exit node — materially wider than "only my machine", and a decision
   the resource owner has to make knowingly.

When an allowlist cannot work from a given machine, say so and choose a different mechanism (run
from inside the VNet, use a private endpoint, or use key-only SSH rather than IP-restricted SSH)
rather than retrying the same approach.

## Private endpoints: check the record layer, not just the link layer

A private-endpoint DNS failure has two very different causes and the diagnosis is quick:

- **Link layer** — is the `privatelink.*` private DNS zone linked to the VNet, and is the endpoint
  `Approved`? Usually fine.
- **Record layer** — does the zone actually contain an **A record** for the host?

A zone with only an SOA record and an endpoint in state `Disconnected` almost always means **the
backing resource was deleted**. Azure drops the A record, in-VNet clients get NXDOMAIN, and every
consumer crashes at connect time. The symptom presents as "DNS is broken" and the cause is a
deleted resource.

Check each zone separately before generalizing. "DNS is broken in this VNet" is usually too broad —
one zone is broken and the others resolve fine, and that difference is the entire diagnosis.

```bash
az network private-dns record-set a list -g <rg> -z privatelink.<service>.<suffix> -o table
az network private-endpoint show -g <rg> -n <pe> \
  --query 'privateLinkServiceConnections[].privateLinkServiceConnectionState' -o json
```

## Joining a resource to a VNet in another resource group

`--vnet-name` and a bare `--subnet` name resolve inside the command's own `-g`. They do not search
the subscription, and finding nothing is not an error — `az vm create` will build a fresh VNet and
subnet under exactly the names you gave and join the host to that instead. The result carries the
intended names and the wrong address space, so every check by name confirms it as correct, and the
invented subnet carries no NSG.

Pass the subnet as a full resource ID and omit `--vnet-name` entirely:

```bash
--subnet /subscriptions/<sub>/resourceGroups/<net-rg>/providers/Microsoft.Network/virtualNetworks/<vnet>/subnets/<subnet>
```

Then verify by **address**: the private IP the create returned must fall inside the prefix you
designed. An invented VNet takes Azure's default address space, which will not match it — and that
mismatch, visible in the create's own output, is often the only sign anything is wrong.

## An `update` that takes a list **replaces** it

`--address-prefixes`, `--tags`, `--dns-servers` and their siblings set the whole collection rather
than adding to it. Passing only the value you are adding removes everything already there — on a
live subnet, that is the prefix its running hosts are addressed from.

The read and the write disagree about the field name, which is what makes this expensive. A
single-stack subnet reports its range as `addressPrefix` (**singular**); the plural
`addressPrefixes` returns `null`, so the query whose name matches the write flag answers "there is
nothing here" about a subnet that is carrying traffic. Act on that answer and the update drops the
range instead of extending it.

```bash
az network vnet subnet show … --query "{singular:addressPrefix,plural:addressPrefixes}" -o json
```

Read both forms, pass every existing value back alongside the new one, then read the resulting list
and confirm the earlier values are still in it. A VNet's `addressSpace.addressPrefixes` is plural in
both directions, so checking one is not evidence about the other.

## A single-stack VNet cannot reach an AAAA-only endpoint

A VNet carries IPv4 only unless it was given IPv6 space, and some managed services publish **only**
an AAAA record for their direct endpoint. A host in that VNet fails at connect with `ENETUNREACH`
(errno 101) — no timeout, no refusal, no TLS exchange — which reads like an NSG rule, a firewall or a
missing private endpoint and sends the diagnosis to the wrong place entirely.

Ask what the name resolves to, and whether the host has a route at all:

```bash
getent ahostsv4 <host>      # empty -> there is no A record to reach
getent ahostsv6 <host>
ip -6 route show default    # empty -> no IPv6 path regardless of DNS
```

Dual-stacking is **additive** and does not replace the VM: IPv6 space on the VNet, a `/64` on the
subnet, a **Standard** SKU IPv6 public IP, and a second `ipConfiguration` on the NIC. Confirm those
capabilities at the moment of use rather than trusting this paragraph. The guest may need no
configuration — an Azure Linux image picks the address up over DHCPv6 — but read `ip -6 addr` rather
than assuming it did.

Where the service also publishes a dual-stacked pooler or proxy hostname, reaching that over IPv4 is
the smaller change. Either path still has to satisfy the service's own TLS chain, which is a separate
question from reachability.

## NSGs

- **Zero NSGs in the path is the dangerous case, and it is silent.** An NSG can exist, report
  `provisioningState=Succeeded`, carry exactly the rules you intended, and be attached to nothing —
  `subnets` and `networkInterfaces` both `null`. It is then an **orphan** and governs no traffic.
  Creating a VM with no NIC-level NSG *on the assumption the subnet already carries one* leaves a
  host with no filtering at all, and a check that the NIC has no NSG confirms that state as correct.
  Nothing looks wrong at any step. Read the association from both sides before relying on it:
  ```bash
  az network vnet subnet show -g <rg> --vnet-name <vnet> -n <subnet> \
    --query networkSecurityGroup.id -o tsv
  az network nsg show -g <rg> -n <nsg> \
    --query '{subnets:subnets[].id, nics:networkInterfaces[].id}' -o json
  ```
- If both a subnet NSG and a NIC NSG exist, effective access is the **intersection**. A rule you
  added to one appears not to work, and nothing in that rule explains why. Prefer exactly one NSG in
  the path.
- Rules are evaluated by priority, lowest number first, and the first match wins. A permissive rule
  at a lower number silences a restrictive one below it.
- Use `az network nic list-effective-nsg` when the intended and actual behaviour disagree — it shows
  the merged, evaluated view rather than the rules you think are in force.

## Reaching resources that are not publicly accessible

When a resource has `publicNetworkAccess=Disabled`, there are two routes, and the choice should turn
on **where the bytes need to end up**, not only on which needs fewer permissions:

- **Run from inside the VNet** — no firewall change, no propagation race, and an existing identity
  may already hold the data roles. But output has to get out somehow; returning large volumes
  through a command-invoke channel is not viable.
- **Temporarily allowlist an address** — lands data directly on your machine, at the cost of a
  firewall opening and temporary roles, both of which must be reverted and verified in the same
  session. Requires the egress question above to be settled first.
