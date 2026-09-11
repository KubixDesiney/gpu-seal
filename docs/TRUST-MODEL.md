# Trust model and evidence verification

GPU-SEAL has two different inspection modes. They answer different questions.

## Structural dashboard inspection

The public dashboard is a browser-only inspection surface. It can show the
shape of a result envelope, report-card fields, declared measurement paths,
publication markers, and the safety assertions exposed by the portal. It does
not access a visitor's GPU, run Python, upload a bundle, or establish that a
provider ran the measurement. A dashboard-rendered label such as “internally
consistent” is not cryptographic provenance.

Structural inspection is useful for readability and for detecting an obviously
malformed or disallowed record. It is not a trusted keyring, an attestation
verifier, or provider validation.

## Cryptographically trusted verification

For trust in a particular signed bundle, obtain the expected Ed25519 public
key through an independent trusted channel and pass that key explicitly:

```bash
python -m gpu_seal verify ./out/<run-id>.result.json --public-key ./trusted-ed25519.pem
```

The CLI validates the published result schema, recomputes the canonical
payload hash, verifies the signature with the supplied external key, and
reports whether the embedded public-key value matches that trusted key. The
embedded key alone is not an out-of-band trust anchor.

Verification proves integrity and signer-key agreement for the bundle. It does
not prove that the signer is a provider, that the provider approved the test,
that the hardware is the claimed model, or that the measurement generalises
beyond its declared boundary. Those claims require the policy, ownership,
hardware, and study evidence described in [`STATUS.md`](STATUS.md).

## Signing-key sources and fingerprint trust

Operator-facing local and native runners require an explicit signing source.
The supported direct source is a caller-selected Ed25519 PEM file. The source
is read when the run starts; private-key bytes are not printed, put in bundle
metadata, or copied into the evidence directory. The `Signer` interface is
also the extension point for an OS key store or KMS, where signing can remain
inside the external system and private bytes need not be exported.

The runner prints the public-key fingerprint (`sha256:<64 lowercase hex>`), and
the signed bundle carries the same public identity. Before accepting a bundle,
the owner or reviewer must compare that fingerprint with a value received
through an independent channel, such as a separately controlled key registry,
signed release record, or direct authenticated exchange. A fingerprint read
from the same untrusted output is not an out-of-band trust anchor.

An ephemeral development key is available only with the explicit
`--unsafe-development-ephemeral` option. Its output is marked
`provenance_suitable: false` and is unsuitable for provenance claims; it is
for local plumbing tests only.

## Shared-provider boundary

Shared-provider use remains blocked unless the security-remediation tests and
the exact release-artifact checks pass, the specific provider policy permits
the planned probes, ownership and budget are confirmed, any written permission
is recorded, and the project owner has approved the ethics/launch decision.

## Hardware-specific claims

- MIG temporal isolation requires controlled A100/H100 MIG hardware.
- H100 confidential-computing and attestation claims require H100 CC hardware
  and validation of freshness, reference measurements, debug status, and
  application-channel binding.
- Same-model physical-die claims require multiple instances of one model and
  the pre-registered D5 separability evaluation against ground truth.
- Topology or location output without those validations is reported only as
  “consistent with” the observed class or coarse region, never as proof.
