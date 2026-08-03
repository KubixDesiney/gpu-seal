# GPU-SEAL — Ghost Meter Control Room

The operational dashboard for the GPU-SEAL research framework. It presents the
project's local evidence, independent report-card grades, provider-policy gates,
probe catalogue, safety invariants, and allowlisted local run plans without
inventing cloud measurements or collapsing evidence into a composite score.

## Local development

Requires Node.js 22.13 or newer.

    npm install
    npm run dev

The dashboard is available at http://localhost:3000.

## Validation

    npm test
    npm audit

The test task builds the Cloudflare-compatible vinext output and verifies the
server-rendered product surface, metadata, social assets, and accessibility
guardrails.

## Operational boundary

The hosted dashboard prepares schema-aligned experiment drafts and allowlisted
commands. It does not execute Python against a local GPU, provision cloud
instances, or claim that simulated fixtures are measurement evidence. Real runs
remain in the parent repository's bounded local runners.
