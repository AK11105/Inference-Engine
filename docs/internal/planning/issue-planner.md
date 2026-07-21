# Issue Planner 

One branch per issue. Branch naming: `fix/<number>-<short-description>` for bugs, `feat/<number>-<short-description>` for enhancements.

Issue detail files: `docs/internal/issues/<number>-<short-description>.md`

See `docs/internal/planning/roadmap.md` for release scope decisions.

---

## Tier 1 — Bugs (fix in order)

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #14 | Inspector exits non-zero and discards all metadata on any exception | `fix/14-inspector-exception-handling` | ✅ Done |
| #15 | Inspector uses pickle.load for all formats, crashing on ONNX and PyTorch `.pt` | `fix/15-inspector-format-routing` | ✅ Done |
| #21 | `_parse_methods` conflates load() and predict() into one block | `fix/21-parse-methods` | ✅ Done |
| #20 | `_splice_methods` regex corrupts definition.py when class has helper methods | `fix/20-splice-methods` | ✅ Done |
| #23 | Reused temp dir across validation retries causes stale module state | `fix/23-validator-stale-module` | ✅ Done |
| #18 | sample_input passed as raw string to validate_pipeline, breaking numeric models | `fix/18-sample-input-type` | ✅ Done |
| #22 | write_scaffold crashes with KeyError when ArtifactMetadata fields are None | `fix/22-write-scaffold-none-fields` | ✅ Done |
| #19 | fix command exits immediately in CI / non-interactive mode | `fix/19-fix-command-ci-mode` |✅ Done |
| #3 | Deployed models invisible to Docker containers (named volume, not bind mount) and `reload()` can't discover models deployed after startup | `fix/3-models-volume-and-reload-discovery` | ✅ Done |

---

## Tier 2 — Enhancements

### v1.0 — Engine (artifact → endpoint)

*Phase 8 work. Ship condition: `inference-engine deploy model.pkl` reliably returns `http://localhost:8000/predict` for pkl/joblib/onnx/pt.*

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #56 | Add FieldValue provenance to ArtifactMetadata interpreted fields | `feat/56-field-provenance` | ✅ Done |
| #57 | Add ExtractorRegistry for plugin-based format discovery | `feat/57-extractor-registry` | ✅ Done |
| #58 | Add DeploymentSpecCandidate builder and _derive_readiness rules | `feat/58-deployment-spec-builder` | ✅ Done |
| #59 | Add pickle safety gate and --allow-load flag | `feat/59-pickle-safety-gate` | ✅ Done |
| #16 | Add LLM interpretation stage between inspection and codegen | `feat/16-llm-interpretation-stage` | ✅ Done |
| #17 | Add --framework flag to deploy to override framework detection | `feat/17-framework-flag` | ✅ Done |
| #24 | Add --yes flag for CI mode | `feat/24-yes-flag` | ✅ Done  |
| #25 | Include sample_input in generate(), fix(), and interpretation prompts | `feat/25-sample-input-in-prompts` | ✅ Done  |
| #90 | Multi-modal sample input | `feat/90-mult-modal-sample-input` | ✅ Done  |

### v1.0 — Reliability & Persistent Logging

*Cross-cutting. Ship condition: every deployment and inference operation produces a durable, structured, queryable execution record.*

| # | Title | Branch | Status |
|---|-------|--------|--------|
| | [Epic] Reliability & Persistent Logging | | |
| | Logging core: structured logger, SQLite sink, and configuration | `feat/logging-core` | |
| | Runtime event instrumentation: middleware access logs & prediction lifecycle | `feat/runtime-event-instrumentation` | |
| | Deployment event instrumentation: CLI deployment lifecycle | `feat/deployment-event-instrumentation` | |
| | `inference-engine logs` CLI command: query interface for log store | `feat/logs-cli-command` | |

### v1.0 — Inference Playground

*Ship condition: after `inference-engine deploy model.pkl`, user opens `/playground` and can immediately test predictions in-browser.*

| # | Title | Branch | Status |
|---|-------|--------|--------|
| | Inference Playground — interactive testing UI | `feat/inference-playground` | |

### v1.0 — Documentation & Positioning

| # | Title | Branch | Status |
|---|-------|--------|--------|
| | Reposition README and public docs for developer-first audience | `docs/reposition-developer-first` | |

### v1.1 — Packaging (artifact → deployment package → endpoint)

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #60 | Add inference-engine init command and deploy.yaml lifecycle | `feat/60-init-command-deploy-yaml` | |
| #26 | Add inference-engine package command | `feat/26-package-command` | |
| #61 | Add inspection result cache by artifact hash | `feat/61-inspection-cache` | |
| #35 | Cache LLM generation results by artifact hash | `feat/35-llm-cache` | |

### v2 — Portability (deployment package → multiple targets)

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #27 | Add inference-engine export command | `feat/27-export-command` | |
| #62 | Add BaseDeploymentAdapter ABC and deployment lifecycle interface | `feat/62-deployment-adapter-base` | |
| #63 | Add local and Docker deployment adapters (Level 3 automated) | `feat/63-adapters-local-docker` | |
| #64 | Add Modal deployment adapter (Level 3 automated) | `feat/64-adapter-modal` | |
| #65 | Add Replicate deployment adapter (Level 2 guided) | `feat/65-adapter-replicate` | |
| #66 | Add --target flag to deploy command | `feat/66-deploy-target-flag` | |

### v2.1 — Developer Experience

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #36 | Extend LLM interpretation to suggest sample_input | `feat/36-suggest-sample-input` | |
| #28 | Add inference-engine snippets command | `feat/28-snippets-command` | |
| #30 | Add --explain flag to deploy | `feat/30-explain-flag` | |
| #31 | Add POST /admin/reload endpoint | `feat/31-admin-reload` | |
| #32 | Add --dry-run flag to fix command | `feat/32-fix-dry-run` | |
| #33 | Add inference-engine benchmark command | `feat/33-benchmark-command` | |
| #34 | Add GET /models/{name}/{version}/metadata endpoint | `feat/34-metadata-endpoint` | |

### v3 — Exposure (endpoint → public endpoint)

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #68 | Add BaseExposureProvider ABC and exposure provider interface | `feat/68-exposure-provider-base` | |
| #69 | Add ngrok and cloudflared exposure providers | `feat/69-providers-ngrok-cloudflared` | |
| #70 | Add inference-engine expose command | `feat/70-expose-command` | |
| #71 | Add --mode flag to deploy command (local / lan / public) | `feat/71-deploy-mode-flag` | |

### v4 — Intelligence (model → best deployment strategy)

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #67 | Add target recommendation engine based on artifact metadata | `feat/67-target-recommender` | |

---

## Tier 4 — Testing

*Execution order: #96 → #95 → #97 → #98. Infrastructure first, then coverage, then integration, then reorganize.*

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #96 | chore: consolidate test infrastructure and fixtures | `chore/96-test-infrastructure` | |
| #95 | test: cover untested production paths | `test/95-coverage-gaps` | |
| #97 | test: add integration and E2E test layer | `test/97-integration-e2e` | |
| #98 | chore: reorganize test suite by module | `chore/98-test-reorganization` | |

---

## Tier 3 — Security

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #42 | Path traversal in deploy via --name / --version flags | `fix/42-path-traversal` | |
