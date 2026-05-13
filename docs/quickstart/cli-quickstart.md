# CLI Quickstart

Deploy a trained model artifact in one command using the deployment CLI.

---

## Install CLI extras

```bash
uv sync --extra cli   # or: pip install -e ".[cli]"
```

---

## Set your API key

```bash
export GROQ_API_KEY=<your-groq-api-key>
```

The CLI uses Groq to generate `load()` and `predict()` method bodies for your model.

---

## Deploy a model

```bash
inference-engine deploy ./my_model.pkl
```

The CLI will:
1. Inspect the artifact (framework, input shape, class labels)
2. Prompt for name, version, device, and routing strategy
3. Generate serving code via LLM
4. Validate the pipeline against a sample input
5. Show a preview and write files on confirmation

---

## Non-interactive deploy (CI)

```bash
inference-engine deploy ./my_model.pkl \
  --name my_model --version v1 \
  --device cpu --routing static \
  --sample-input '{"features": [1.0, 2.0, 3.0]}'
```

---

## Fix a broken pipeline

```bash
inference-engine fix models/my_model/v1/
```

Reads the existing `definition.py`, validates it, and sends failures to the LLM for repair.

---

See [CLI Reference](../cli/overview.md) for full documentation.
