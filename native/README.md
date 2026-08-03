# GPU-SEAL native probe slice

This directory is the first ADR-001 port boundary. `gpu_seal_native.cu`
contains the memory-touching path that must be native before provider testing:

- CUDA allocation, release, and host/device copies;
- the ADR-002 128-byte canary wire format;
- keyed BLAKE2b-256 ownership authentication;
- a secure host buffer whose destructor scrubs unknown bytes;
- aggregate-only direct-driver output;
- reuse, fresh-allocation, and explicit-zero negative controls.

The native binary supports --mint, --authenticate, --sha256, and
--safety-check for cross-language conformance and --run for a bounded
direct-driver aggregate stream. A run must declare exactly one scope:
--local-only for researcher-owned hardware or --shared-infrastructure when
invoked by the controller after the provider policy, ownership, budget, and
ethics gates have passed.

The native binary never decides whether a provider is authorised. The Python
NativeProviderRunner is the only provider-facing entry point: it calls the
policy matrix and scheduler before launch, passes the hard duration limit to
the provider adapter, and terminates the allocation in a finally path.

Build inside the pinned CUDA development container:

```text
nvcc -std=c++17 -O2 -Xcompiler -Wall,-Wextra \
  native/gpu_seal_native.cu -o /tmp/gpu-seal-native
```

Researcher-owned local validation:

```text
/opt/gpu-seal/bin/gpu-seal-native --run --local-only \
  --mode reuse --size-mib 8 --cycles 2 --stride-mib 4
```

The controller-owned provider command uses the shared scope and is not meant
to be run directly:

    [binary, --run, --shared-infrastructure, --json,
     --mode, reuse, --size-mib, 64, --cycles, 10, --stride-mib, 1]

Build-time verification runs the native canary/hash/safety vectors and the
complete Python suite in the same pinned image:

    python3 lab/check-native-conformance.py \
        --binary /opt/gpu-seal/bin/gpu-seal-native --full-suite

The native-to-controller bundle path remains subject to the normal signed
evidence and publication gates.
