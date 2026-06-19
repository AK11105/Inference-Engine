# Issue Planner

One branch per issue. Branch naming: `fix/<number>-<short-description>` for bugs, `feat/<number>-<short-description>` for enhancements.

---

## Tier 1 — Bugs (fix in order)

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #14 | Inspector exits non-zero and discards all metadata on any exception | `fix/14-inspector-exception-handling` | ✅ Done |
| #15 | Inspector uses pickle.load for all formats, crashing on ONNX and PyTorch `.pt` | `fix/15-inspector-format-routing` | ✅ Done |
| #21 | `_parse_methods` conflates load() and predict() into one block | `fix/21-parse-methods` | ✅ Done |
| #20 | `_splice_methods` regex corrupts definition.py when class has helper methods | `fix/20-splice-methods` | ✅ Done |
| #23 | Reused temp dir across validation retries causes stale module state | `fix/23-validator-stale-module` |✅ Done |
| #18 | sample_input passed as raw string to validate_pipeline, breaking numeric models | `fix/18-sample-input-type` | |
| #22 | write_scaffold crashes with KeyError when ArtifactMetadata fields are None | `fix/22-write-scaffold-none-fields` | |
| #19 | fix command exits immediately in CI / non-interactive mode | `fix/19-fix-command-ci-mode` | |

## Tier 2 — Enhancements (after all bugs are closed)

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #16 | Add LLM interpretation stage between inspection and codegen | `feat/16-llm-interpretation-stage` | |
| #17 | Add --framework flag to deploy to override framework detection | `feat/17-framework-flag` | |
| #24 | Add --yes flag for CI mode | `feat/24-yes-flag` | |
| #25 | Include sample_input in generate(), fix(), and interpretation prompts | `feat/25-sample-input-in-prompts` | |
| #36 | Extend LLM interpretation to suggest sample_input | `feat/36-suggest-sample-input` | |
| #35 | Cache LLM generation results by artifact hash | `feat/35-llm-cache` | |
| #34 | Add GET /models/{name}/{version}/metadata endpoint | `feat/34-metadata-endpoint` | |
| #33 | Add inference-engine benchmark command | `feat/33-benchmark-command` | |
| #32 | Add --dry-run flag to fix command | `feat/32-fix-dry-run` | |
| #31 | Add POST /admin/reload endpoint | `feat/31-admin-reload` | |
| #30 | Add --explain flag to deploy | `feat/30-explain-flag` | |
| #28 | Add inference-engine snippets command | `feat/28-snippets-command` | |
| #27 | Add inference-engine export command | `feat/27-export-command` | |
| #26 | Add inference-engine package command | `feat/26-package-command` | |

## Tier 3 — Security

| # | Title | Branch | Status |
|---|-------|--------|--------|
| #42 | Path traversal in deploy via --name / --version flags | `fix/42-path-traversal` | |
