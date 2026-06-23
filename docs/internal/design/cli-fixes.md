# CLI Known Issues & Fixes

Bugs and fragilities identified in the CLI outside of the inspector. See `docs/inspector-fix.md` for inspector-specific work.

---

## 1. `fix` command unusable in non-interactive / CI mode

**File:** `app/cli/commands/fix.py`, `app/cli/__main__.py`

**The bug:**

`run_fix` always reads `sample_input` from `input()`. If stdin is not a TTY it immediately exits:

```python
# fix.py
if _is_interactive():
    sample_input = input("Sample input for validation: ").strip()
else:
    console.print("[red]Error:[/red] sample input required. Run in an interactive terminal.")
    sys.exit(1)
```

There is also no `--sample-input` flag on the `fix` subcommand in `__main__.py`, so there is no way to pass it non-interactively even if you wanted to.

**Fix:**

Add `--sample-input` to the `fix` subparser in `__main__.py`:

```python
fix_parser.add_argument("--sample-input", dest="sample_input", default=None)
```

Pass it through to `run_fix`. In `run_fix`, prefer the flag value; fall back to `input()` only when interactive and the flag was not provided; exit with a clear message only when neither is available:

```python
def run_fix(model_dir: str, sample_input: str | None = None) -> None:
    ...
    if sample_input is None:
        if _is_interactive():
            sample_input = input("Sample input for validation: ").strip()
        else:
            console.print("[red]Error:[/red] --sample-input required in non-interactive mode.")
            sys.exit(1)
```

---

## 2. `_splice_methods` regex corrupts files with non-trivial class bodies

**File:** `app/cli/commands/fix.py`

**The bug:**

```python
source = re.sub(
    r"(    def load\(self\).*?)(?=\n    def |\ndef |\Z)",
    lambda m: "    " + load_body.strip(),
    source, count=1, flags=re.DOTALL,
)
```

Three problems with this:

1. **Indentation prefix is wrong.** `load_body` from the LLM already includes `def load(self) -> None:` and its indented body. Prepending `"    "` to `load_body.strip()` puts the `def` line at 4-space indent but leaves the body lines at whatever indentation the LLM produced — typically also 4 spaces, resulting in 8-space body indentation inside a 4-space class. The file becomes syntactically broken.

2. **Lookahead `(?=\n    def )` requires a blank line.** If the LLM returns the two methods with no blank line separator, the lookahead `\n    def ` never matches and the regex captures `load` + `predict` together as one block. Both `load_body` and `predict_body` then contain both methods. Validation may still pass (predict body runs correctly) but `load` is silently wrong.

3. **Any helper method breaks the splice.** If the class has a `__init__` or a private helper between `load` and `predict`, the lookahead fires on the helper, not on `predict`, and the splice truncates the method early.

**Fix:**

Use AST to locate the exact line range of each method, then do line-based replacement instead of regex:

```python
import ast

def _splice_methods(source: str, load_body: str, predict_body: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    # Find _GeneratedModel class
    cls = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "_GeneratedModel"
    )

    replacements = {}
    for node in cls.body:
        if isinstance(node, ast.FunctionDef):
            if node.name == "load":
                replacements["load"] = (node.lineno - 1, node.end_lineno, load_body)
            elif node.name == "predict":
                replacements["predict"] = (node.lineno - 1, node.end_lineno, predict_body)

    # Apply in reverse order so line numbers stay valid
    for _, (start, end, body) in sorted(replacements.items(), key=lambda x: -x[1][0]):
        indented = textwrap.indent(body, "    ")
        lines[start:end] = [indented + "\n"]

    result = "".join(lines)
    ast.parse(result)   # verify before returning
    return result
```

This is exact, indentation-safe, and handles any class body structure.

---

## 3. `sample_input` is never parsed — numeric models always fail validation

**File:** `app/cli/core/prompts.py`, `app/cli/commands/deploy.py`

**The bug:**

`sample_input` is collected as a raw string and passed directly to `pipeline.run(sample_input)`. A model expecting a float array receives a string and raises a type error. The validation loop then treats this as a codegen failure and burns all three LLM retries trying to "fix" code that was never wrong.

Example: user enters `[1.2, 0.4, 3.1]` at the prompt. `pipeline.run("[1.2, 0.4, 3.1]")` passes a string to an sklearn model expecting a numpy array. Every attempt fails. The scaffold is written. The codegen was correct the whole time.

**Fix:**

Parse `sample_input` with `json.loads` before validation. Fall back to the raw string if parsing fails (legitimate for text models):

```python
import json

def _parse_sample_input(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw  # treat as plain string input
```

Apply this in `deploy.py` and `fix.py` before passing `sample_input` to `validate_pipeline`. Do not apply it to the string stored in `DeployAnswers` — the raw string is still needed for the curl example in the writer.

---

## 4. `_parse_methods` regex conflates both methods when no blank line separates them

**File:** `app/cli/core/agent.py`

**The bug:**

```python
load_match = re.search(r"(def load\(self\).*?)(?=\ndef |\Z)", raw, re.DOTALL)
predict_match = re.search(r"(def predict\(self,.*?)(?=\ndef |\Z)", raw, re.DOTALL)
```

The lookahead `(?=\ndef )` requires a newline followed immediately by `def`. When the LLM outputs:

```python
def load(self) -> None:
    ...
def predict(self, x):
    ...
```

(no blank line between them), the lookahead `\ndef ` matches `\ndef predict` correctly. But when the LLM adds a trailing comment or blank line after `predict`, `\Z` is the only terminator and `predict_match` captures everything to end-of-string including any trailing text.

More critically: if the LLM wraps output in a class body (despite the system prompt saying not to), both regexes match the same outer block and both bodies contain both methods. Validation passes if `predict` happens to work, but `load` is silently broken — `self._model` is never set, and the error only surfaces at runtime when the server loads the model.

**Fix:**

Split on `def ` boundaries explicitly rather than using a lookahead:

```python
def _parse_methods(raw: str) -> tuple[str, str]:
    raw = re.sub(r"```(?:python)?", "", raw).replace("```", "").strip()

    # Split into top-level method blocks
    blocks = re.split(r"(?=^def )", raw, flags=re.MULTILINE)
    methods = {}
    for block in blocks:
        block = block.strip()
        if block.startswith("def load(self)"):
            methods["load"] = block
        elif block.startswith("def predict(self,"):
            methods["predict"] = block

    if "load" not in methods or "predict" not in methods:
        raise ValueError(f"Could not parse load() and predict() from LLM output:\n{raw}")

    return methods["load"], methods["predict"]
```

This is split-based rather than lookahead-based, handles any spacing between methods, and is explicit about what constitutes a match.

---

## 5. `write_scaffold` will crash when inspector fields are `None`

**File:** `app/cli/core/writer.py`

**The bug:**

After the inspector overhaul (`docs/inspector-fix.md`), `ArtifactMetadata` fields like `framework`, `class_name`, `input_hint`, and `output_hint` can be `None` when inspection partially failed. The scaffold template formats them directly:

```python
source = _SCAFFOLD_TEMPLATE.format(
    framework=meta.framework,       # None → writes "framework=None"
    class_name=meta.class_name,     # None → writes "# Class: None"
    input_hint=meta.input_hint,     # None → AttributeError if field removed
    output_hint=meta.output_hint,
    ...
)
```

`None` in comments is harmless but misleading. If any field is removed from `ArtifactMetadata` during the overhaul, this raises `KeyError` at the format call.

**Fix:**

Coerce `None` fields to a placeholder string before formatting:

```python
def write_scaffold(meta, answers, artifact_path, ...):
    unknown = "unknown"
    source = _SCAFFOLD_TEMPLATE.format(
        framework=meta.framework or unknown,
        class_name=meta.class_name or unknown,
        input_hint=meta.input_hint or unknown,
        output_hint=meta.output_hint or unknown,
        ...
    )
```

---

## 6. Validation temp dir reused across retry attempts

**File:** `app/cli/commands/deploy.py`

**The bug:**

```python
with tempfile.TemporaryDirectory() as tmp_dir:
    for attempt in range(1, _MAX_RETRIES + 1):
        result = validate_pipeline(source, answers.sample_input, Path(tmp_dir))
```

`validate_pipeline` pops `sys.modules["definition"]` after each run, but the `.py` file written to `tmp_dir` persists between attempts. If a retry writes a new `definition.py` while a previous import is still being cleaned up (e.g. a background thread holds a reference), the module loader can pick up the stale file. This produces a confusing pattern where attempt 2 passes but attempt 3 fails with the same error as attempt 1.

**Fix:**

Use a fresh subdirectory per attempt:

```python
import uuid

with tempfile.TemporaryDirectory() as tmp_root:
    for attempt in range(1, _MAX_RETRIES + 1):
        tmp_dir = Path(tmp_root) / str(attempt)
        tmp_dir.mkdir()
        result = validate_pipeline(source, answers.sample_input, tmp_dir)
```

Cost is negligible (three small directories). Eliminates the stale-module class of failures entirely.

---

## Priority Order

| # | Issue | Severity | File |
|---|---|---|---|
| 3 | `sample_input` never parsed — numeric models always fail | High | `prompts.py`, `deploy.py`, `fix.py` |
| 1 | `fix` command broken in CI / non-interactive | High | `fix.py`, `__main__.py` |
| 2 | `_splice_methods` corrupts files with non-trivial class bodies | High | `fix.py` |
| 4 | `_parse_methods` conflates methods when no blank line | Medium | `agent.py` |
| 5 | `write_scaffold` crashes on `None` fields post-inspector overhaul | Medium | `writer.py` |
| 6 | Stale module from reused temp dir across retries | Low | `deploy.py` |
