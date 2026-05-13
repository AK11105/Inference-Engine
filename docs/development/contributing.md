# Contributing

## Setup

```bash
git clone <repo>
cd inference-engine
uv sync
cp .env.example .env
```

---

## Making changes

1. Create a branch from `main`
2. Make your changes
3. Run tests: `pytest`
4. Ensure coverage stays ≥ 70%
5. Open a pull request

---

## Adding a model

See [Adding Custom Models](../guides/adding-custom-models.md).

---

## Adding an execution backend

1. Subclass `BaseExecutor` in `app/execution/`
2. Implement `submit()` and `submit_background()`
3. Register in `app/adapters/http/deps.py`
4. Reference in `EXECUTION_POLICY` in `app/config/execution.py`

---

## Architecture rules

- No upward imports (domain → services → adapters)
- No HTTP imports outside `app/adapters/`
- No storage SDK imports outside `app/infra/`
- Every new inference path must create a `Job` record

See [Architecture](../concepts/architecture.md) for full invariants.

---

## Documentation

Documentation lives in `docs/`. Preview locally:

```bash
pip install mkdocs-material
mkdocs serve
```
