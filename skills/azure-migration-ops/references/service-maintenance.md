# Maintaining services running on Azure

## Configuration you "removed" is often still there

Many config loaders **fill gaps rather than overwrite**: they set a key only if it is not already
set, and they walk *every ancestor directory* of both the working directory and the process's
current directory, loading each config file they find.

The consequence is counter-intuitive and costs whole debugging rounds: **you cannot delete a
variable by removing it from the file you edited.** A stale file anywhere up either chain silently
re-supplies it, so a deploy that "removed" a credential leaves the service still using it.

When a service behaves as though it has configuration you deleted, enumerate the actual files before
theorizing:

```bash
find / -name ".env" -type f 2>/dev/null      # or the relevant config filename
```

The rule that follows: on a host that should have exactly one config file, **verify that it has
exactly one**, rather than assuming.

## `/proc/<pid>/environ` cannot see runtime injection

A process that sets its own environment at runtime does not change the region the kernel exposes at
`/proc/<pid>/environ`. So a process can read completely clean there while the code sees the
variable.

This matters because it means such a diagnostic **exonerates the actual culprit**. If you are
hunting a variable that "isn't set anywhere", inspect the config files on the ancestor chains
instead — and be suspicious of any evidence that clears the thing you most suspect.

## Read the error text, not just the status code

Two `401`s can mean opposite things:

- *"Missing bearer or basic authentication in header"* — **no credential was sent**. Look at
  credential selection, injection, or a client that strips the variable.
- *"Incorrect API key provided"* — **a bad credential was sent**. Look at the value.

These point at completely different halves of the system, and conflating them is a full debugging
round. The same applies to `403` bodies, which usually name the exact rule that rejected you.

## Find the logs the diagnostics actually go to

Diagnostic output frequently goes to **stderr** while the log you are reading is stdout. A process
supervisor typically splits them into separate files, so reading only the `-out` log produces long
unexplained silences that look like hangs. Ask for both, always.

For test harnesses, make sure output is not being captured and discarded — many test runners
swallow it unless explicitly told not to.

## Stopping compute: `stop` is not `deallocate`

- `az vm stop` halts the OS but leaves the VM **allocated** — compute keeps billing.
- `az vm deallocate` releases the compute. The OS disk and everything on it persist, and start-up
  brings it back in a couple of minutes.

The state to reach is `Stopped (deallocated)`, and the way to confirm it is
`az vm get-instance-view` — not the command's exit code.

Remember what a deallocate/start cycle changes: a **dynamic** public IP is released and comes back
different. A Standard-SKU (static) address survives.

Deallocating rather than deleting is usually right for anything whose configuration was expensive to
build: the disk cost is a small fraction of the compute cost, and deleting throws away exactly the
work that was just verified.

## Idle cost lives in provisioned things

Consumption-tier and per-second resources cost approximately nothing when idle. Standing costs come
from things provisioned by the hour regardless of traffic — registry SKUs, provisioned database
throughput, always-on node pools, allocated VMs. When asked "what does this cost while parked",
answer from that list rather than from the resource count.

Watch for **cost leaks in failing systems**: a job that crash-loops every few minutes on dedicated
nodes bills exactly as much as a working one. A workload producing nothing is not a workload costing
nothing.

## Before deciding a service can be retired

Establish, with evidence rather than inference:

- has it had a **successful** request in the observable window (result codes, not counts)?
- what is the longest window the metrics API will actually return?
- if there is a caller, can it be named — and if not, is "no identified consumer" an acceptable
  conclusion for the owner?
- is its state stored anywhere that is already gone? (If so, any export is partial by definition,
  which usually strengthens the case rather than complicating it.)
