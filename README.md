# Inference Engine — Task-Agnostic ML Serving Backend

## Overview

This project is a **general, task-agnostic ML inference engine** designed to serve machine learning models in production environments.

It is **not** a demo app and **not** a model-specific API.

The system treats **models as pluggable artifacts** and provides a clean, scalable execution and orchestration layer for online inference, independent of:

* ML framework (PyTorch, TensorFlow, sklearn, etc.)
* Task type (NLP, vision, tabular, graph, anomaly detection)
* Transport (HTTP today, gRPC/CLI later)

FastAPI (or any transport) is an **adapter**, not the core of the system.

---

## Scope

### In Scope

This repository is responsible for:

* Online inference orchestration
* Model execution (sync / async)
* Preprocessing and postprocessing pipelines
* Model versioning and routing
* Model lifecycle at **serving time**
* Observability hooks (metrics, logs, tracing)
* Performance and concurrency control

---

### Explicitly Out of Scope

The following are **not implemented here by design**:

* Model training pipelines
* Feature engineering workflows
* Experiment tracking logic (MLflow, W&B)
* Data drift detection algorithms
* Model governance / approval workflows
* Offline evaluation pipelines

This system **consumes trained artifacts** — it does not produce them.

---

## Architectural Principles (Invariants)

These invariants **must never be violated** as the system evolves.

### 1. Transport Independence

* Core ML logic must not import FastAPI, Pydantic, or HTTP concepts
* Transport layers are replaceable adapters

### 2. Model Ignorance

* Models do not know:

  * where inputs originate
  * how outputs are used
  * that they are served over HTTP

### 3. Explicit Pipelines

* Preprocessing and postprocessing are explicit, first-class components
* No hidden transformations inside models

### 4. Version Is First-Class

* Every model is identified by `(name, version)`
* “latest” is a routing decision, not a default behavior

---

## Conceptual Data Flow

```
Raw Input
   ↓
Preprocessor
   ↓
Model
   ↓
Postprocessor
   ↓
Final Response
```

Service-level flow:

```
Client Request
   ↓
Service Layer
   ↓
Model Registry
   ↓
Inference Pipeline
   ↓
Execution Engine
   ↓
Response
```

---

## Core Concepts & Terminology

| Term          | Meaning                               |
| ------------- | ------------------------------------- |
| Model         | Pure inference logic                  |
| Preprocessor  | External input → model input          |
| Postprocessor | Model output → response               |
| Pipeline      | Preprocessor + Model + Postprocessor  |
| Registry      | Loads, versions, and caches pipelines |
| Service       | Orchestrates inference use-cases      |
| Executor      | Controls execution resources          |
| Adapter       | Transport layer (HTTP, CLI, gRPC)     |

These definitions are fixed.

---

## Repository Structure (Frozen)

```
inference_engine/
├── README.md
├── pyproject.toml
├── app/
│   ├── core/          # config, logging, lifecycle
│   ├── domain/        # models, pipelines, registry
│   ├── services/      # use-case orchestration
│   ├── adapters/      # FastAPI / CLI / gRPC
│   └── infra/         # cache, queue, storage
└── tests/
```

Folder responsibilities **must not overlap**.

---

## Design Philosophy

* ML models are **plugins**
* The inference engine is **framework-agnostic**
* FastAPI is a **transport detail**
* Correct abstractions come before performance optimizations
* Scaling should be boring once correctness is achieved

---