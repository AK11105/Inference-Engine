# Inspector Overhaul v2

## Problem Summary

The current inspector is a single monolithic subprocess script that attempts to identify an artifact, infer framework behavior, and drive deployment generation in one step.

This design creates several issues:

* Any exception can poison the entire deploy flow
* Framework detection is tightly coupled to artifact loading
* Large artifacts (multi-GB models) are impractical to inspect deeply
* Metadata extraction and interpretation are mixed together
* The deployment pipeline depends too heavily on successful artifact deserialization
* Repeated deploy attempts repeatedly inspect the same artifact

The result is a brittle first-stage experience that scales poorly as model size and framework diversity increase.

---

## Revised Design Principles

### 1. Inspection is Fact Collection

The inspector extracts measurable facts.

It does not decide:

* how to deploy
* what framework semantics mean
* how predict() should behave

Interpretation belongs elsewhere.

---

### 2. Deployment Must Not Depend on Model Loading

Deployment should be possible without loading weights.

Large models should be deployable through metadata and deployment specifications alone.

---

### 3. Artifact Inspection is an Onboarding Accelerator

Artifact introspection is a convenience feature.

It is not the primary deployment mechanism.

The primary deployment contract is a deployment package.

---

### 4. Partial Knowledge is Valuable

Inspection should never fail the deploy flow.

Any information successfully extracted remains useful.

---

### 5. Explicit Uncertainty

Unknown information should remain unknown.

Confidence is attached to every interpretation stage.

---

### 6. Scale-Aware Inspection

Inspection behavior changes based on artifact size and format.

The system should not deserialize large artifacts merely to identify them.

---

# High-Level Architecture

```text
Artifact
    ↓
Inspector
    ↓
RawFacts
    ↓
DeploymentSpec Builder
    ↓
LLM Interpretation (optional)
    ↓
DeploymentSpec
    ↓
Code Generation
    ↓
Validation
    ↓
Deploy
```

The inspector produces facts.

The deployment system consumes a DeploymentSpec.

---

# Deployment Package First

Canonical deployment:

```bash
inference-engine deploy my-model/
```

Structure:

```text
my-model/
├── deploy.yaml
├── artifacts/
├── src/
│   └── handler.py
├── requirements.txt
```

Artifact inspection is primarily used by:

```bash
inference-engine init model.pkl
```

which generates the deployment package.

---

# Inspection Layers

## Layer 0 — Filesystem Facts

Always succeeds.

Extract:

* path
* size
* extension
* directory/file status
* checksum

Output:

```json
{
  "artifact_path": "...",
  "artifact_size_mb": 123,
  "artifact_hash": "..."
}
```

---

## Layer 1 — Format Detection

Identify:

* pickle
* joblib
* pytorch
* onnx
* safetensors
* huggingface directory
* tf savedmodel
* generic

Detection uses:

* extension
* magic bytes
* directory signatures

---

## Layer 2 — Structural Inspection

Format-specific extraction.

Goal:

Extract structure without loading weights whenever possible.

Examples:

### ONNX

* opset
* graph inputs
* graph outputs
* operator types

### Safetensors

* tensor names
* tensor shapes
* metadata

### HuggingFace

* config.json
* tokenizer config
* architecture hints

### PyTorch

* state_dict keys
* layer names
* parameter counts

---

## Layer 3 — Deep Inspection

Only for small artifacts.

Examples:

* sklearn
* xgboost
* lightgbm
* catboost

Extract:

* feature count
* classes
* estimators
* pipeline structure

Failures remain localized.

---

# Inspection Modes

Every artifact receives an inspection mode.

```python
inspection_mode
```

Possible values:

```text
metadata
structural
loaded
```

---

### metadata

No artifact loading.

Examples:

* HF models
* safetensors
* large files

---

### structural

Graph/header inspection.

No full deserialization.

---

### loaded

Artifact deserialized.

Only used for small artifacts.

---

# Artifact Size Policy

## ≤ 100 MB

Full inspection allowed.

Examples:

* sklearn
* xgboost
* lightgbm

---

## 100 MB – 1 GB

Metadata and structural inspection only.

No model loading.

---

## > 1 GB

Deployment-spec workflow only.

No automatic deserialization.

Inspector remains metadata-only.

---

# Inspection Cost

New field:

```python
inspection_cost
```

Values:

```text
low
medium
high
```

Allows downstream logic to understand inspection expense.

---

# Capability Detection

Inspector extracts capabilities independently from framework.

Example:

```json
{
  "capabilities": [
    "predict",
    "predict_proba"
  ]
}
```

Future examples:

```json
{
  "capabilities": [
    "embeddings",
    "text_generation"
  ]
}
```

This becomes more useful than framework detection alone.

---

# Safety Classification

Every artifact receives a safety assessment.

```json
{
  "safety": {
    "deserialization_risk": "high",
    "execution_risk": "medium"
  }
}
```

Examples:

* pickle → high
* ONNX → low
* safetensors → low

This information is surfaced to users.

---

# Confidence Separation

Current design uses a single confidence value.

This is replaced with:

```json
{
  "inspection_confidence": "high",
  "interpretation_confidence": "medium"
}
```

Reason:

The inspector may be certain about structure while the LLM remains uncertain about semantics.

---

# Deployment Readiness

Introduce:

```python
deployment_readiness
```

Values:

```text
ready
needs_clarification
unsupported
```

Examples:

### ready

Known ONNX model with valid graph.

### needs_clarification

Framework known but input format ambiguous.

### unsupported

Unknown artifact type.

---

# DeploymentSpec Generation

The inspector now produces a DeploymentSpec candidate.

Example:

```json
{
  "framework": "sklearn",
  "artifact_type": "pickle",
  "required_packages": [
    "scikit-learn"
  ],
  "capabilities": [
    "predict"
  ],
  "deployment_readiness": "ready"
}
```

This becomes the durable contract passed downstream.

---

# Inspection Cache

Inspection results are cached.

Cache key:

```python
artifact_hash
```

Stored:

```json
{
  "artifact_hash": "...",
  "raw_facts": {...},
  "deployment_spec": {...}
}
```

Benefits:

* faster retries
* cheaper deploy cycles
* reduced artifact loading

---

# LLM Interpretation Stage

Runs only when:

```text
inspection_confidence < high
```

or

```text
deployment_readiness == needs_clarification
```

The LLM receives:

* raw_facts
* inspection errors
* sample_input
* framework hint
* deployment spec candidate

and returns:

* enriched DeploymentSpec
* clarifying question (optional)

---

# Clarification Rules

Maximum:

```text
2 questions
```

Questions must materially affect deployment.

Examples:

Good:

```text
Does predict() receive raw text or tokenized inputs?
```

Bad:

```text
What is this model for?
```

---

# Extractor Plugin System

All extractors implement:

```python
class BaseExtractor:
    def can_handle(...)
    def extract(...)
```

Examples:

```text
extractors/
├── pickle/
├── sklearn/
├── xgboost/
├── pytorch/
├── onnx/
├── transformers/
├── tf_savedmodel/
```

This allows ecosystem growth without modifying inspector core logic.

---

# Summary

The inspector evolves from a framework detector into a scalable deployment intelligence layer.

Its responsibilities become:

1. Collect facts
2. Assess safety
3. Determine deployment readiness
4. Build DeploymentSpec candidates
5. Feed interpretation when needed

Artifact introspection remains a powerful onboarding feature, but production deployment ultimately depends on DeploymentSpecs rather than artifact loading.
