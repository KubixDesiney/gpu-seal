# Contributing to GPU-SEAL

GPU-SEAL is pre-alpha research software. Contributions are welcome when they
preserve the canary-only safety boundary and the distinction between local
instrument validation and provider evidence.

## Before changing code

1. Read [`ETHICS.md`](ETHICS.md), [`SECURITY.md`](SECURITY.md), and the
   [trust model](docs/TRUST-MODEL.md).
2. Check the current [status](docs/STATUS.md) and preserve unrelated worktree
   changes.
3. For safety-sensitive changes, add a focused regression test under
   `tests/safety/` and a mutation to `lab/verify-safety-suite.sh` when the
   change creates a new policy that the battery should catch.

Do not add provider credentials, real provider names, raw unknown GPU memory,
or claims of provider validation to source, tests, fixtures, or documentation.
Provider experiments require the owner-approved policy, permission, budget,
ownership, ethics, and release gates.

## Local checks

Python 3.10 or newer is supported by the package. From the repository root,
install the development extras in an isolated environment and run:

```bash
python -m pip install --no-build-isolation -e ".[dev]"
python -m pytest tests -q
python lab/check-mutation-coverage.py
python lab/scorecard.py --no-history
python lab/check-docs.py
```

Run the full mutation battery from Linux, WSL2, or Git Bash:

```bash
PYTHON_BIN="$(command -v python)" bash lab/verify-safety-suite.sh
```

If you change the dashboard, run these from `dashboard/`:

```bash
npm ci
npm run lint
npm run typecheck
npm test
npm run test:browser
```

The dashboard is a browser-only inspection surface. It must not upload bundles,
run cloud jobs, or turn a structural label into cryptographic or provider
trust.

## Pull requests

- Describe the evidence that supports the change and its limits.
- State which checks you ran and the exact result.
- Keep public provider identifiers pseudonymous (`provider-a`, etc.).
- Keep generated bundles, keys, credentials, build output, and coverage files
  out of commits.
- Do not commit, push, tag, publish, deploy, or use cloud credentials as part
  of an ordinary contribution.

For a safety-layer vulnerability, follow [`SECURITY.md`](SECURITY.md) rather
than opening a public issue.
