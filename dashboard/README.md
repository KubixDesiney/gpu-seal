# GPU-SEAL — Public Research Portal

The public product surface for the GPU-SEAL research framework. Visitors can
understand the method, inspect a result-bundle envelope entirely in their
browser, browse the probe catalogue, review safety boundaries, and prepare a
bounded local run without the site pretending it can access their GPU.

## Local development

Requires Node.js 22.13 or newer.

The parent Python package is `0.1.0.dev0`; this private npm package uses the
equivalent npm prerelease spelling `0.1.0-dev.0`.

    npm ci
    npm run dev

The dashboard is available at http://localhost:3000.

## Validation

    npm test
    npm run lint
    npm run typecheck
    npm run test:production
    npm run test:browser
    npm audit --omit=dev --audit-level=high

`npm ci` does not download Playwright's browser binaries, so on a clean
checkout `test:browser` fails with `Executable doesn't exist` until they are
fetched once:

    npx playwright install chromium

The test task builds the Cloudflare-compatible vinext output and verifies the
server-rendered product surface, metadata, social assets, and accessibility
guardrails. `test:production` verifies every CSS and JavaScript asset referenced
by the production HTML is served successfully. `test:browser` starts the built
production server and exercises hydration, local evidence inspection, dialog
focus, skip-link focus, and mobile navigation state.

`test:browser` also guards the verification boundary: that the
non-dismissible banner is server-rendered on every page, that it carries the
exact `gpu-seal verify` command with an external key, and that a bundle
declaring `backend_is_real=false` is labelled as simulated in the UI rather
than only in the JSON.

## Deployment

    npm run deploy:dry-run
    npm run deploy

Deployment targets Cloudflare Workers. The Worker configuration is generated
at build time into `dist/server/wrangler.json` from `vite.config.ts`; there is
no checked-in `wrangler.toml`. `compatibility_date` is pinned in
`vite.config.ts` deliberately, so that it does not silently track whichever
`workerd` version happens to be installed.

Authenticate once with `npx wrangler login`. Run both commands from this
directory, not from the repository root, which has no `package.json`.
`deploy:dry-run` validates the config and bundling without publishing.

The `workers.dev` URL is public and crawlable as soon as it is deployed. To
require sign-in, put [Cloudflare Access](https://developers.cloudflare.com/workers/configuration/cloudflare-access/)
in front of the Worker.

## Product boundary

The hosted portal never uploads an inspected bundle, executes Python against a
visitor GPU, provisions cloud instances, or presents simulations and local
examples as provider evidence. Real measurements remain in the parent
repository's bounded local runners.
