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

## Evidence gallery

`/evidence-gallery` lists every run committed under
[`../examples/evidence/`](../examples/evidence/) and opens any one in the same
in-browser inspector used for a visitor's own file. Each card shows host kind,
GPU model, NVIDIA driver, CUDA runtime and driver API versions, run date, probe
count, and a real-vs-simulated marker derived from `backend_is_real` by the same
function (`app/lib/evidence.ts`) that labels an uploaded bundle. The list and
the marker are server-rendered, and the verification banner is present on this
route like every other.

- **The marker is the bundle's own claim.** It reads "Real GPU · self-declared"
  and states the field it came from. The site checks no signature, so it never
  reads "verified".
- **Two fields are unsigned.** Host kind and NVIDIA driver come from the
  `environment.json` the operator's host wrote beside the bundle, which the
  signature does not cover. Everything else comes from the bundle. The bundle
  records the CUDA runtime as `12090` (12.9) where that manifest says `13.0`;
  the card shows the bundle's value.
- **Opening a bundle is one same-origin `GET`** of `/evidence-gallery/bundles/<directory>`,
  which serves the committed file unchanged and accepts no other method. Nothing
  is uploaded, no Python runs, no instance is provisioned.
- **The build reads `../examples/evidence/`.** The Worker has no filesystem, so
  the bundles are compiled into the server build (never the client build).
  Build from a full checkout of the repository, not a copy of `dashboard/`. A new
  run directory appears on the next build; the Python test that guards that
  directory is what keeps a bad bundle out.
- **`npm test` runs one suite under `--experimental-strip-types`** so the pure
  origin logic can be unit-tested from its TypeScript source. The flag is
  available from Node 22.6, inside the supported range; releases that strip
  types by default do not need it.

## Mutation battery

`/mutation-battery` shows every case of the negative-control battery that
`lab/verify-safety-suite.sh` runs: what was injected, which test failed because
of it, and the caught/missed verdict, grouped by the test file that guards each
case. The headline count leads, every group is open on arrival (native
`<details open>`, so it works without JavaScript), and two sentences of the
page's own copy explain why a suite that passes against deliberately broken
code is not testing anything.

- **The page is rendered from `../badges/mutation-battery-summary.json`, and
  nothing else.** That is the file the safety workflow's `mutation-summary` job
  builds from the shard logs and its `publish-mutation-badge` job commits beside
  `../badges/mutation-battery.svg`, so the page and the badge come from one CI
  run. No case and no count is typed into the dashboard; the home, safety and
  run pages read the same numbers. `app/lib/mutation-battery.ts` rejects a file
  whose `total`, `caught` or `missed` disagrees with its own cases, which fails
  the build instead of showing a headline the cases do not support.
- **It reports what CI recorded; it runs nothing.** The page shows the time in
  the file and says so. The file is only replaced when a case, a verdict or a
  count changes (the timestamp alone does not), and only by a push to `main`.
  A branch that adds or changes a battery case therefore shows the old summary
  until it merges and CI records the new one.
- **A case the suite did not catch is impossible to miss.** The headline drops
  below the total, an alert appears, and the groups holding a failure are listed
  first. Verdicts are `Caught`, `Missed`, `Failed the wrong test`,
  `Harness error` and `Not run`, matching the statuses
  `lab/summarize-mutation-results.py` writes.
- **Grouping uses the summary's `test_file` field**, which the summarizer
  resolves from each case's expected test. The dashboard does not read the
  Python tests.
- **Like the evidence gallery, the build reads outside `dashboard/`.** The
  summary is compiled into the server build. Build from a full checkout.
- **`test:browser` asserts the case count on the page equals the count in the
  JSON**, reading the JSON itself rather than restating a number, with
  JavaScript disabled and enabled.

## Deployment

    npm run deploy:dry-run
    npm run deploy

Deployment targets Cloudflare Workers. The Worker configuration is generated
at build time into `dist/server/wrangler.json` from `vite.config.ts`; there is
no checked-in `wrangler.toml`. `compatibility_date` is pinned in
`vite.config.ts` deliberately, so that it does not silently track whichever
`workerd` version happens to be installed.

Authenticate once with `npx wrangler login`. Run both commands from this
directory, not from the repository root, which has no `package.json`. The build
also reads `../examples/evidence/` (see [Evidence gallery](#evidence-gallery)),
so it needs the rest of the repository checked out beside this directory.
`deploy:dry-run` validates the config and bundling without publishing.

The `workers.dev` URL is public and reachable by link as soon as it is
deployed. The portal ships `noindex, nofollow` and a disallow-all
`robots.txt` while it is pre-alpha, which asks crawlers to stay away but does
not restrict access. To require sign-in, put
[Cloudflare Access](https://developers.cloudflare.com/workers/configuration/cloudflare-access/)
in front of the Worker.

### Deployment record

| | |
|---|---|
| Worker | `gpu-seal-dashboard` |
| URL | <https://gpu-seal-dashboard.gpu-seal.workers.dev> |
| First deployed | 2026-09-20 |
| Version ID | `fa6c7ad1-6b34-4b96-8775-b13223fe7b2c` |
| Source | the `dashboard/` tree at commit `3d50393` |
| Wrangler | 4.127.1 |
| Custom domain | none |
| Cloudflare Access | none, the URL is public |

This is the record of the first deployment. Later deployments supersede the
version ID above; `npx wrangler deployments list` shows the current one.

Checks run against that build: `npm test` (3/3), `npm run test:browser`
(3/3), `npm run lint`, `npm run typecheck`, and
`npm audit --omit=dev --audit-level=high` (0 vulnerabilities). On the deployed
URL, the page returned 200 and every referenced CSS and JavaScript asset
returned 200. The verification banner, with the exact `gpu-seal verify`
command, was present in the served HTML and in the browser, and the console
was clean. `test:browser` ran against a local production server, not the
deployed URL. Uploading a bundle through the deployed UI was not exercised.

#### Second deployment: evidence gallery

| | |
|---|---|
| Deployed | 2026-09-20 |
| Version ID | `d6aea006-b11d-49a4-be25-220e52b9f298` |
| Source | the tree at commit `869b196` (branch `dashboard-evidence-gallery`; a squash merge will give the same tree a different hash) |
| Wrangler | 4.127.1 |
| Adds | `/evidence-gallery` and `/evidence-gallery/bundles/<directory>` |

Checks run against that build: `npm test` (22/22), `npm run test:production`
(1/1), `npm run test:browser` (10/10), `npm run lint`, `npm run typecheck`, and
`npm run deploy:dry-run`. `npm audit` was not run for this deployment; no
dependencies changed. On the deployed URL, over HTTP: the gallery returned 200
with both cards, both real-vs-simulated markers, the verification banner and the
exact `gpu-seal verify` command in the served HTML; both committed bundles
returned 200 at the same size as the files in the repository; an unknown bundle
id returned 404 and a POST returned 405; the home page and every CSS and
JavaScript asset the gallery references returned 200. Opening a bundle in the
inspector through the deployed UI, in a browser, was not exercised; that flow
was tested against a local production server only.

#### Third deployment: mutation battery

| | |
|---|---|
| Deployed | 2026-09-21 |
| Version ID | `46d16016-a2fc-40eb-8e0d-e6a41dafcd87` |
| Source | the tree at commit `f6a7730` (branch `dashboard-mutation-battery`, PR #9; a squash merge will give the same tree a different hash) |
| Wrangler | 4.127.1 |
| Adds | `/mutation-battery`; the injected-violation count on the home, safety and run pages now comes from `badges/mutation-battery-summary.json` |

Deployed from the branch, at the maintainer's instruction, while the PR's CI
was still running. Checks run against that build before deploying: `npm test`
(33/33), `npm run test:browser` (15/15), `npm run lint`, `npm run typecheck`,
`npm run deploy:dry-run`, and the Python suite (477 passed). `npm audit` was
not run; the only `package.json` change is the `test` script. On the deployed
URL, over HTTP: `/mutation-battery` returned 200 with a headline, 39 rows, 39
caught rows and 18 open groups that all equal the committed summary, plus the
verification banner and the exact `gpu-seal verify` command; the home page
quotes the same count; the gallery and both bundles still returned 200; every
CSS and JavaScript asset the page references returned 200; a POST returned 405.
In Chromium against the deployed URL, at desktop and phone widths: the page
hydrated, all 39 rows were visible on arrival, a group collapsed and reopened,
there was no sideways scroll, and the console was clean. The Safety-page link
to the battery was tested against a local production server only.

## Product boundary

The hosted portal never uploads an inspected bundle, executes Python against a
visitor GPU, provisions cloud instances, or presents simulations and local
examples as provider evidence. Real measurements remain in the parent
repository's bounded local runners.
