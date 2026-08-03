# GPU-SEAL — Public Research Portal

The public product surface for the GPU-SEAL research framework. Visitors can
understand the method, inspect a result-bundle envelope entirely in their
browser, browse the probe catalogue, review safety boundaries, and prepare a
bounded local run without the site pretending it can access their GPU.

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

## Product boundary

The hosted portal never uploads an inspected bundle, executes Python against a
visitor GPU, provisions cloud instances, or presents simulations and local
examples as provider evidence. Real measurements remain in the parent
repository's bounded local runners.
