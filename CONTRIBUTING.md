# Contributing to Inference Engine

Thanks for taking the time to contribute.

## Getting Started

```bash
git clone https://github.com/AK11105/Inference-Engine
cd inference-engine
uv sync
cp .env.example .env
```

## Workflow

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Run the test suite: `pytest`
4. Ensure coverage stays ≥ 70%: `pytest --cov=app`
5. Open a pull request against `main`

## What to Work On

Check the [issue tracker](https://github.com/AK11105/Inference-Engine/issues) for open issues. Issues labeled `good first issue` are a good starting point.

## Architecture Rules

These invariants must be preserved:

- No upward imports — dependency direction is `domain → services → adapters`
- No HTTP imports outside `app/adapters/`
- No storage SDK imports outside `app/infra/`
- Every new inference path must create a `Job` record

See [Architecture](docs/concepts/architecture.md) for full details.

## Adding a Model

See [Adding Custom Models](docs/guides/adding-custom-models.md).

## Adding an Execution Backend

1. Subclass `BaseExecutor` in `app/execution/`
2. Implement `submit()` and `submit_background()`
3. Register in `app/adapters/http/deps.py`
4. Add the policy value to `app/config/execution.py`

## Documentation

Docs live in `docs/`. Preview locally:

```bash
pip install mkdocs-material mkdocs-git-revision-date-localized-plugin mkdocs-glightbox mkdocs-redirects
mkdocs serve
```

## Commit Style

Use conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`.

## Code of Conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). Please read it before contributing.
