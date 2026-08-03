# GPU-SEAL native probe slice

This directory is the first ADR-001 port boundary. `gpu_seal_native.cu`
contains the memory-touching path that must be native before provider testing:

- CUDA allocation, release, and host/device copies;
- the ADR-002 128-byte canary wire format;
- keyed BLAKE2b-256 ownership authentication;
- a secure host buffer whose destructor scrubs unknown bytes;
- aggregate-only direct-driver output.

The native binary supports `--mint` and `--authenticate` for cross-language
conformance and `--run` for a local direct-driver smoke test. It does not yet
produce signed result bundles; the Python controller remains the result
orchestration layer until conformance covers the complete safety suite.

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
