# fix

Fix a broken existing pipeline definition.

```bash
inference-engine fix <model-dir>
```

`<model-dir>` is the path to a model version directory containing a `definition.py`,
e.g. `models/sentiment/v1/`.

## What it does

1. Reads the existing `definition.py`
2. Validates it against a sample input you provide
3. If validation passes — reports success and exits (nothing to fix)
4. If validation fails — sends the error + current code to the LLM for a fix
5. Re-validates the fixed code; retries up to 3 times
6. Shows a unified diff of the proposed changes
7. Writes the fixed file only after you confirm

## Example

```bash
inference-engine fix models/sentiment/v1/
```

You will be prompted for a sample input to run the pipeline against.

## Retry behaviour

Up to 3 fix attempts are made. Each failure sends the latest traceback back to
the LLM. If all 3 attempts fail, the command exits with an error and the original
file is left unchanged.

## Notes

- Only `load()` and `predict()` are ever rewritten. The rest of `definition.py`
  (imports, `MODEL_NAME`, `build_pipeline`) is preserved.
- The command is interactive-only. It requires a TTY to prompt for sample input
  and confirmation.
