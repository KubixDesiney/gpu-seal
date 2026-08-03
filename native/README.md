# GPU-SEAL native probe slice

This directory is the first ADR-001 port boundary. `gpu_seal_native.cu`
contains the memory-touching path that must be native before provider testing:

- CUDA allocation, release, and host/device copies;
- the ADR-002 128-byte canary wire format;
- keyed BLAKE2b-256 ownership authentication;
- a secure host buffer whose destructor scrubs unknown bytes;
- aggregate-only direct-driver output.

The native binary supports `--mint`, `--authenticate`, `--sha256`, and
`--safety-check` for cross-language conformance and `--run` for a local
direct-driver aggregate stream. The Python controller seals that stream into
a signed local validation bundle; it remains the result orchestration layer.

Build inside the pinned CUDA development container:

```text
nvcc -std=c++17 -O2 -Xcompiler -Wall,-Wextra \
  native/gpu_seal_native.cu -o /tmp/gpu-seal-native
```

The `--run` command requires `--local-only` and is for researcher-owned local
hardware only while the ethics and provider-policy gates are pending:

```text
/opt/gpu-seal/bin/gpu-seal-native --run --local-only \
  --size-mib 8 --cycles 2 --stride-mib 4
```

The Python controller can seal the aggregate stream into a signed local
validation bundle:

    python3 lab/local-runner/run_native_local.py --size-mib 8 --cycles 2

That bundle deliberately remains publication-cleared false. It validates the
native-to-controller bridge; it is not the Phase 1 control battery and is not
provider evidence.
