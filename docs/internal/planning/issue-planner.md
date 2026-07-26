# Issue Planner

> **Status:** Frozen as of 2026-07-26
>
> Active development paused. All open issues are deferred until the project resumes.
> See `project-freeze.md` for context and resumption instructions.

One branch per issue. Branch naming: `fix/<number>-<short-description>` for bugs, `feat/<number>-<short-description>` for enhancements.

Issue detail files: `docs/internal/issues/<number>-<short-description>.md`

See `docs/internal/planning/roadmap.md` for release scope decisions.

---

## Tier 1 — Bugs (all resolved)

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #14 | Inspector exits non-zero and discards all metadata on any exception | `fix/14-inspector-exception-handling` | ✅ Done |
| #15 | Inspector uses pickle.load for all formats, crashing on ONNX and PyTorch `.pt` | `fix/15-inspector-format-routing` | ✅ Done |
| #21 | `_parse_methods` conflates load() and predict() into one block | `fix/21-parse-methods` | ✅ Done |
| #20 | `_splice_methods` regex corrupts definition.py when class has helper methods | `fix/20-splice-methods` | ✅ Done |
| #23 | Reused temp dir across validation retries causes stale module state | `fix/23-validator-stale-module` | ✅ Done |
| #18 | sample_input passed as raw string to validate_pipeline, breaking numeric models | `fix/18-sample-input-type` | ✅ Done |
| #22 | write_scaffold crashes with KeyError when ArtifactMetadata fields are None | `fix/22-write-scaffold-none-fields` | ✅ Done |
| #19 | fix command exits immediately in CI / non-interactive mode | `fix/19-fix-command-ci-mode` | ✅ Done |
| #3 | Deployed models invisible to Docker containers and `reload()` can't discover post-startup models | `fix/3-models-volume-and-reload-discovery` | ✅ Done |
| #50 | fix: resolve 34 failing tests — lifespan job store init, Redis retry race, Groq key skip guard | `fix/50-failing-tests` | ✅ Done |
| #40 | infra: add memory limit to api service and parameterize DB/Redis credentials | `fix/40-docker-compose-hardening` | ✅ Done |
| #38 | fix(ci): pip-audit auditing system Python instead of project venv | `fix/38-pip-audit-venv` | ✅ Done |

---

## Tier 2 — Enhancements

### v1.0 — Engine (artifact → endpoint) ✅ Complete

*Phase 8 work. Ship condition: `inference-engine deploy model.pkl` reliably returns `http://localhost:8000/predict` for pkl/joblib/onnx/pt.*

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #56 | Add FieldValue provenance to ArtifactMetadata interpreted fields | `feat/56-field-provenance` | ✅ Done |
| #57 | Add ExtractorRegistry for plugin-based format discovery | `feat/57-extractor-registry` | ✅ Done |
| #58 | Add DeploymentSpecCandidate builder and _derive_readiness rules | `feat/58-deployment-spec-builder` | ✅ Done |
| #59 | Add pickle safety gate and --allow-load flag | `feat/59-pickle-safety-gate` | ✅ Done |
| #16 | Add LLM interpretation stage between inspection and codegen | `feat/16-llm-interpretation-stage` | ✅ Done |
| #17 | Add --framework flag to deploy to override framework detection | `feat/17-framework-flag` | ✅ Done |
| #24 | Add --yes flag for CI mode | `feat/24-yes-flag` | ✅ Done |
| #25 | Include sample_input in generate(), fix(), and interpretation prompts | `feat/25-sample-input-in-prompts` | ✅ Done |
| #90 | Multi-modal sample input | `feat/90-multimodal-sample-input` | ✅ Done |

### v1.0 — Reliability & Persistent Logging ✅ Complete

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #82 | [Epic] Reliability & Persistent Logging | — | ✅ Done |
| #83 | Logging core: structured logger, SQLite sink, and configuration | `feat/83-logging-core` | ✅ Done |
| #84 | Runtime event instrumentation: middleware access logs & prediction lifecycle | `feat/84-runtime-event-instrumentation` | ✅ Done |
| #85 | Deployment event instrumentation: CLI deployment lifecycle | `feat/85-deployment-event-instrumentation` | ✅ Done |
| #86 | `inference-engine logs` CLI command: query interface for log store | `feat/86-logs-cli-command` | ✅ Done |

### v1.0 — Inference Playground ✅ Complete

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #87 | Inference Playground — interactive testing UI | `feat/87-inference-playground` | ✅ Done |

### v1.0 — Security ✅ Complete

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #42 | Path traversal in deploy via --name / --version flags | `fix/42-path-traversal` | ✅ Done |

### v1.0 — Binary Transport (frozen)

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #104 | Native binary input transport (`_bytes` envelope) | `feat/104-bytes-envelope` | 🧊 Frozen |

### v1.0 — Rename (frozen)

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #105 | Rename project from Inference Engine to ServEasy | `feat/105-rename-serveasy` | 🧊 Frozen |

### v1.0 — Documentation & Positioning (frozen)

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #88 | Reposition README and public docs for developer-first audience | `docs/88-reposition-developer-first` | 🧊 Frozen |

### v1.1 — Packaging (frozen)

*artifact → deployment package → endpoint*

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #60 | Add inference-engine init command and deploy.yaml lifecycle | `feat/60-init-command-deploy-yaml` | 🧊 Frozen |
| #26 | Add inference-engine package command | `feat/26-package-command` | 🧊 Frozen |
| #61 | Add inspection result cache by artifact hash | `feat/61-inspection-cache` | 🧊 Frozen |
| #35 | Cache LLM generation results by artifact hash | `feat/35-llm-cache` | 🧊 Frozen |

### v2 — Portability (frozen)

*deployment package → multiple targets*

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #27 | Add inference-engine export command | `feat/27-export-command` | 🧊 Frozen |
| #62 | Add BaseDeploymentAdapter ABC and deployment lifecycle interface | `feat/62-deployment-adapter-base` | 🧊 Frozen |
| #63 | Add local and Docker deployment adapters (Level 3 automated) | `feat/63-adapters-local-docker` | 🧊 Frozen |
| #64 | Add Modal deployment adapter (Level 3 automated) | `feat/64-adapter-modal` | 🧊 Frozen |
| #65 | Add Replicate deployment adapter (Level 2 guided) | `feat/65-adapter-replicate` | 🧊 Frozen |
| #66 | Add --target flag to deploy command | `feat/66-deploy-target-flag` | 🧊 Frozen |

### v2.1 — Developer Experience (frozen)

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #36 | Extend LLM interpretation to suggest sample_input | `feat/36-suggest-sample-input` | 🧊 Frozen |
| #28 | Add inference-engine snippets command | `feat/28-snippets-command` | 🧊 Frozen |
| #30 | Add --explain flag to deploy | `feat/30-explain-flag` | 🧊 Frozen |
| #31 | Add POST /admin/reload endpoint | `feat/31-admin-reload` | 🧊 Frozen |
| #32 | Add --dry-run flag to fix command | `feat/32-fix-dry-run` | 🧊 Frozen |
| #33 | Add inference-engine benchmark command | `feat/33-benchmark-command` | 🧊 Frozen |
| #34 | Add GET /models/{name}/{version}/metadata endpoint | `feat/34-metadata-endpoint` | 🧊 Frozen |

### v3 — Exposure (frozen)

*endpoint → public endpoint*

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #68 | Add BaseExposureProvider ABC and exposure provider interface | `feat/68-exposure-provider-base` | 🧊 Frozen |
| #69 | Add ngrok and cloudflared exposure providers | `feat/69-providers-ngrok-cloudflared` | 🧊 Frozen |
| #70 | Add inference-engine expose command | `feat/70-expose-command` | 🧊 Frozen |
| #71 | Add --mode flag to deploy command (local / lan / public) | `feat/71-deploy-mode-flag` | 🧊 Frozen |

### v4 — Intelligence (frozen)

*model → best deployment strategy*

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #67 | Add target recommendation engine based on artifact metadata | `feat/67-target-recommender` | 🧊 Frozen |

---

## Tier 3 — Observability & Infrastructure (frozen)

*Pre-existing issues from early project setup. Open on GitHub, not prioritized before freeze.*

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #4 | Add Loki + Alloy to the observability stack for structured log aggregation | `feat/4-loki-alloy` | 🧊 Frozen |
| #11 | Ship Prometheus alerting rules for key inference metrics | `feat/11-prometheus-alerting-rules` | 🧊 Frozen |

---

## Tier 4 — Testing (frozen)

*Execution order: #96 → #95 → #97 → #98. Infrastructure first, then coverage, then integration, then reorganize.*

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #96 | chore: consolidate test infrastructure and fixtures | `chore/96-test-infrastructure` | 🧊 Frozen |
| #95 | test: cover untested production paths | `test/95-coverage-gaps` | 🧊 Frozen |
| #97 | test: add integration and E2E test layer | `test/97-integration-e2e` | 🧊 Frozen |
| #98 | chore: reorganize test suite by module | `chore/98-test-reorganization` | 🧊 Frozen |

---

## CI & DevOps (all resolved)

| # | Title | Status |
|---|-------|--------|
| #1 | feat: Docker Compose support for full stack deployment | ✅ Done |
| #6 | Add CI workflow for pytest, coverage, and dependency audit | ✅ Done |
| #7 | Add CI workflow to build Docker image, smoke test, and Trivy scan | ✅ Done |
| #8 | Add CodeQL static analysis to CI for automated security scanning | ✅ Done |
| #9 | Docker Compose and Dockerfile container hygiene hardening | ✅ Done |
| #10 | Fail fast on misconfigured DATABASE_URL and REDIS_URL at startup | ✅ Done |
| #5 | Ship a pre-built Grafana dashboard for Prometheus metrics | ✅ Done |

---

## Summary

| Category | Done | Frozen | Total |
|---|---|---|---|
| Bugs | 12 | 0 | 12 |
| v1.0 Engine | 9 | 0 | 9 |
| v1.0 Logging | 5 | 0 | 5 |
| v1.0 Playground | 1 | 0 | 1 |
| v1.0 Security | 1 | 0 | 1 |
| v1.0 Binary Transport | 0 | 1 | 1 |
| v1.0 Rename | 0 | 1 | 1 |
| v1.0 Docs | 0 | 1 | 1 |
| v1.1 Packaging | 0 | 4 | 4 |
| v2 Portability | 0 | 6 | 6 |
| v2.1 DX | 0 | 7 | 7 |
| v3 Exposure | 0 | 4 | 4 |
| v4 Intelligence | 0 | 1 | 1 |
| Observability/Infra | 0 | 2 | 2 |
| Testing | 0 | 4 | 4 |
| CI & DevOps | 7 | 0 | 7 |
| **Total** | **35** | **31** | **66** |
