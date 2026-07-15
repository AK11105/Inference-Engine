# fix

Fix a broken existing pipeline definition.

```bash
inference-engine fix <model-dir> [options]
```

`<model-dir>` is the path to a model version directory containing a `definition.py`,
e.g. `models/sentiment/v1/`.

## What it does

![CLI fix retry loop flowchart](../assets/cli-fix-light.png#only-light)
![CLI fix retry loop flowchart](../assets/cli-fix-dark.png#only-dark)

1. Reads the existing `definition.py`
2. Validates it against a sample input you provide
3. If validation passes — reports success and exits (nothing to fix)
4. If validation fails — sends the error + current code to the LLM for a fix
5. Re-validates the fixed code; retries up to 3 times
6. Shows a unified diff of the proposed changes
7. Writes the fixed file (after confirmation in interactive mode, immediately with `--yes`)

## Options

| Flag | Default | Description |
|---|---|---|
| `--sample-input` | prompted interactively | Sample input for pipeline validation |
| `--yes` / `-y` | off | Skip all confirmation prompts (CI mode) |

## Examples

Interactive:

```bash
inference-engine fix models/sentiment/v1/
```

You will be prompted for a sample input to run the pipeline against.

Non-interactive (CI):

```bash
inference-engine fix models/sentiment/v1/ \
  --sample-input "this movie was great" --yes
```

## Retry behaviour

Up to 3 fix attempts are made. Each failure sends the latest traceback back to
the LLM. If all 3 attempts fail, the command exits with an error and the original
file is left unchanged.

## Notes

- Only `load()` and `predict()` are ever rewritten. The rest of `definition.py`
  (imports, `MODEL_NAME`, `build_pipeline`) is preserved.
- In interactive mode (without `--yes`), you are prompted for sample input and
  asked to confirm before writing.
- With `--yes`, `--sample-input` is required — there is no interactive fallback.
