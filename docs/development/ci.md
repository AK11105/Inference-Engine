# CI Workflows

All workflows live in `.github/workflows/` and run on GitHub-hosted `ubuntu-latest` runners. Public repo — no minute limits.

---

## Workflows

### `docker.yml` — Docker build, smoke test, and image scan

Triggers on every push to any branch and on pull requests to `main`.

**`build-and-test` job**

1. Builds the image: `docker build -t inference-engine:ci .`
2. Starts a standalone container with `API_KEYS` set and SQLite fallback (no Postgres or Redis needed)
3. Waits up to 60s for `GET /health` to return 200
4. Asserts `GET /health` → 200
5. Asserts `POST /predict` with the echo model returns the input unchanged
6. Removes the container (`if: always()` — runs even on failure)

**`trivy-scan` job**

Runs only if `build-and-test` passes (`needs: build-and-test`).

1. Rebuilds the image
2. Scans with [Trivy](https://trivy.dev) for HIGH and CRITICAL CVEs
3. Fails on findings that have a fix available (`ignore-unfixed: true` — unfixed CVEs are reported but do not block)
4. Uploads the scan report as a workflow artifact (`trivy-report`) — visible in the Actions run summary even on failure

---

### `docs.yml` — Documentation deployment

Triggers on push to `main` when files under `docs/` or `mkdocs.yml` change.

Builds and deploys the MkDocs site to GitHub Pages via `mkdocs gh-deploy`.

---

## When a job fails

| Failure | Likely cause | Fix |
|---|---|---|
| `Build image` | Dockerfile syntax error or missing dependency | Check the build output |
| `Wait for healthcheck` | Container crashes at startup | Check `docker logs ie` output in the step — printed automatically on timeout |
| `Smoke test POST /predict` | Echo model not loading or auth broken | Check app startup logs in the wait step |
| `trivy-scan` | Fixable HIGH/CRITICAL CVE found | Check the `trivy-report` artifact, update the affected package or base image |

---

## Trivy and unfixed CVEs

The scan uses `ignore-unfixed: true`. CVEs with no available fix in the Debian package repos are included in the report artifact but do not fail the job — there is nothing actionable to do until upstream ships a patch.

The Dockerfile runs `apt-get upgrade` on every build to pick up all available OS package patches automatically.

---

## Adding a new workflow

Follow the existing trigger pattern:

```yaml
on:
  push:
    branches: ["**"]
  pull_request:
    branches: [main]
```

Use `actions/checkout@v6` and `actions/upload-artifact@v7` (Node 24 — required from June 2026).
