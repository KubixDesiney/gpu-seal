# Security Policy

GPU-SEAL repository: <https://github.com/KubixDesiney/gpu-seal>. The current
public status is pre-alpha; see [`docs/STATUS.md`](docs/STATUS.md).

This file is about vulnerabilities **in GPU-SEAL itself**. For findings
*about a provider*, see [`DISCLOSURE.md`](DISCLOSURE.md).

## The bug class that matters most

Any way to make GPU-SEAL render, retain, serialise, transmit, or otherwise
materialise memory it did not write is the most serious defect this project
can have. It is worse than a crash, worse than a wrong result, and worse than
a false finding about a provider — because the entire ethical basis of the
project is that it cannot do those things.

Examples of what we want to hear about:

- A route around `SafeBuffer`'s refusals — any expression that yields raw bytes
- A path where unknown memory reaches a log, a file, a socket, or a traceback
- A way to make the canary matcher accept a marker the experiment did not mint
- A way to bypass the `SAFE_AGGREGATE_KEYS` egress allowlist
- A way to clear a `sensitive_observation` run for publication
- A static-analysis check that can be trivially evaded while still violating
  the rule it enforces
- Any aggregate statistic that leaks more about buffer content than intended

That last one is subtle and worth stating explicitly: the byte histogram and
entropy estimate are on the allowlist because they were judged non-revealing.
If you can show a realistic reconstruction attack against those statistics, we
want to know, and we will remove them.

## Reporting

Please report privately. Open a GitHub security advisory on the repository, or
use the maintainer contact configured in the repository settings. Do not invent
or publish a contact address, and do not open a public issue for a safety-layer
bypass.

Include: what you did, what happened, and — if you have one — a failing test.
A test that goes red on the current tree is the most useful possible report.

## What we will do

- Acknowledge within a few days
- Reproduce and confirm
- Fix, and add a regression test to `tests/safety/`
- Add the violation to `lab/verify-safety-suite.sh` so the suite proves it can
  detect the class in future
- Credit you, unless you prefer otherwise

## Scope note

GPU-SEAL is pre-alpha research software in local instrument-validation phase.
No provider measurement or provider validation is claimed. There is no
deployed service, no user data, and no production instance. The security
surface is the library and its guarantees.
