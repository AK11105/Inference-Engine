# Roadmap
*Last updated: 2026-06-23*

---

## What the project is

```
Take a trained model artifact
↓
Generate serving layer
↓
Validate it
↓
Deploy it
↓
Get an endpoint
```

The engine is the product. The CLI is a convenience layer built on top of it.

---

## v1.0 — Engine

**Goal:** `artifact → endpoint`, reliably, for the four most common formats.

**Ship condition:** someone can run `inference-engine deploy model.pkl` and get `http://localhost:8000/predict` for sklearn, XGBoost, ONNX, and PyTorch models.

### In scope

- Artifact formats: `.pkl`, `.joblib`, `.onnx`, `.pt` / `.pth`
- Inspector v2 — layered extraction, always-return-JSON, per-layer failure handling, raw facts, confidence, framework hints, sample input support
- LLM interpretation stage — `facts → framework + load strategy`
- Code generation — `load()` and `predict()`
- Validation loop — generate → execute → fix → retry
- Local deployment — `http://localhost:8000`
- LAN exposure — `--mode lan` / `--host 0.0.0.0` → `http://192.168.x.x:8000` (cheap, actually useful)

### Issues

Bug (required): **#19** fix command CI mode

Inspector overhaul: **#43** field provenance, **#44** extractor registry, **#45** deployment spec candidate, **#46** pickle safety gate, **#16** LLM interpretation stage

CLI hardening: **#17** `--framework` flag, **#24** `--yes` flag, **#25** sample_input in prompts

Security: **#42** path traversal

### Not in v1.0

- `deploy.yaml` / `init` command
- `package` and `export` commands
- Inspection cache, LLM generation cache
- Deployment adapters (cloud)
- Target recommendation engine
- Ngrok / Cloudflare exposure
- Capability taxonomy, deployment readiness scoring

---

## v1.1 — Packaging

**Goal:** `artifact → deployment package → endpoint`

Introduces the deployment package as a portable, reproducible unit. Separates inspection from deployment so re-deploys don't re-inspect.

### In scope

- `inference-engine init` + `deploy.yaml` lifecycle — **#47**
- `inference-engine package` command — **#26**
- Inspection result cache by artifact hash — **#48**
- LLM generation cache by artifact hash — **#35**

---

## v2 — Portability

**Goal:** `deployment package → multiple deployment targets`

### In scope

- `inference-engine export --target bentoml/ray/docker/sagemaker` — **#27**
- Deployment adapter base + local/Docker adapters — **#49**, **#50**
- Modal adapter (Level 3 automated) — **#51**
- Replicate adapter (Level 2 guided) — **#52**
- `--target` flag on deploy — **#53**

---

## v2.1 — Developer Experience

Reduce friction across the board. Can ship alongside v2 or after.

### In scope

- LLM-suggested sample_input — **#36**
- `inference-engine snippets` command — **#28**
- `--explain` flag on deploy — **#30**
- `POST /admin/reload` endpoint — **#31**
- `fix --dry-run` — **#32**
- Benchmark CLI — **#33**
- `GET /models/{name}/{version}/metadata` — **#34**

---

## v3 — Exposure

**Goal:** `endpoint → public endpoint`

### In scope

- Exposure provider base — **#55**
- Ngrok + Cloudflare providers — **#56**
- `inference-engine expose` command — **#57**
- `--mode` flag on deploy (local / lan / public) — **#58**

---

## v4 — Intelligence

**Goal:** `model → best deployment strategy`

### In scope

- Target recommendation engine — **#54**
- Capability detection taxonomy
- Deployment readiness scoring
- Inspection cache improvements
- Rich `DeploymentSpec`

---

## Phase reference

| Phase (impl-plan) | Maps to | Key deliverable |
|---|---|---|
| Pre | ✅ shipped | Async Postgres, shutdown safety |
| Phase 8 | **v1.0** | Inspector v2, CLI bug fixes, `--framework`, `--yes` |
| Phase 9 | v1.1 + v2 | `package`, `export`, `deploy.yaml` |
| Phase 10 | v2.1 | Snippets, explain, benchmark, hot reload |
| Phase 11 | v2.1 | Metadata API, caches |
| Phase 12 | v2 | Deployment adapters, target recommender |
| Phase 13 | v3 | Public endpoint exposure |
