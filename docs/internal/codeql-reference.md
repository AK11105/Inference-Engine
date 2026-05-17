# CodeQL — Internal Reference

## What is CodeQL

CodeQL is GitHub's static analysis engine. It reads source code, builds a model of how data moves through the program (data-flow analysis), and flags patterns that are known to be dangerous.

The key difference from simpler tools (grep, Bandit): CodeQL traces data across function boundaries. It can detect that user input entered at function A, passed through functions B and C, and reached a dangerous sink at function D — even if no single line looks suspicious in isolation.

It is free for public repositories and runs entirely within GitHub Actions via `github/codeql-action`. No external service, no account required.

---

## How it works

1. CodeQL compiles the source into a database (a queryable model of the code)
2. It runs a set of queries against that database — each query describes a vulnerability pattern
3. Findings are posted as inline annotations on the PR or commit

The query suite used matters:
- `security-and-quality` — security vulnerabilities + code quality rules. Noisy for CI.
- `security-extended` — security vulnerabilities only, broader coverage than the default. **This is what we use.**

---

## Vulnerability classes relevant to this project

### 1. Path Traversal

**What it is:** User-controlled input reaches a file system operation (read, write, delete) without being sanitized. An attacker crafts the input to escape the intended directory.

**Where it exists in this project:**

The CLI `deploy` command takes `--name` and `--version` from the user and constructs a write path:

```python
# app/cli/core/writer.py
dest = Path("models") / answers.name / answers.version / "definition.py"
```

If a user passes `--name ../../etc --version passwd`, this resolves outside the project directory. The file write lands wherever the resolved path points.

**What CodeQL does:** Flags the data flow: CLI argument → `Path()` construction → file write, with no sanitization (e.g. no `path.resolve().is_relative_to(base)` check) in between.

**The fix when implementing:** Resolve the final path and assert it stays within the intended base directory before writing.

---

### 2. Unsafe Deserialization (pickle)

**What it is:** `pickle.load()` executes whatever is encoded in the file. A maliciously crafted `.pkl` runs arbitrary Python code on the machine that loads it — at the moment of loading, before any model logic runs.

**Where it exists in this project:**

The CLI inspector loads the artifact to introspect it:

```python
# app/cli/core/inspector.py
# runs a subprocess that imports and pickle-loads the artifact
```

The deploy command also passes the artifact path to the LLM-generated `load()` function which typically calls `pickle.load()`.

The project already shows a warning (`_PICKLE_WARNING` in `deploy.py`) but the actual `pickle.load()` call is still present and unguarded.

**What CodeQL does:** Flags `pickle.load()` calls where the file path originates from user input or an external source.

**Important:** These calls are intentional — the CLI is designed to load user-provided artifacts. The right response when CodeQL flags them is not to remove `pickle.load()` but to:
1. Add `# codeql-suppress` with a justification comment
2. Ensure the warning to the user is prominent and cannot be bypassed silently

---

### 3. Sensitive Data in Logs

**What it is:** A secret (API key, password, token) flows into a log call and gets written to stdout/a log file where it can be captured.

**Where it could appear in this project:**

The auth middleware (`app/adapters/http/middleware/auth.py`) handles raw API keys from request headers. The logging setup (`app/core/logging.py`) logs request context. If a future contributor adds a debug log line that includes `request.headers` or the raw key, it ships silently.

**What CodeQL does:** Traces the flow from "secret source" (HTTP header named `X-API-Key`, env var named `*KEY*`, `*PASSWORD*`, `*SECRET*`) to log sinks.

---

### 4. Code Injection via subprocess (inspector)

**What it is:** User-controlled input reaches a `subprocess` call without sanitization, allowing arbitrary command execution.

**Where it exists in this project:**

The CLI inspector runs a subprocess to introspect the artifact:

```python
# app/cli/core/inspector.py
subprocess.run([python, "-c", inspect_script, artifact_path], ...)
```

`artifact_path` comes from the user (`inference-engine deploy ./path`). If the path contains shell metacharacters and the subprocess call uses `shell=True`, it becomes a command injection vector.

**What CodeQL does:** Flags user input → `subprocess` with `shell=True`. If `shell=False` (which is the safer default), CodeQL still flags it as a lower-severity finding for review.

**Note:** The current code uses `shell=False` (passing a list, not a string) which is the correct approach. CodeQL will still flag it for review — this is one of the expected false-positive-adjacent findings that should be suppressed with a comment after confirming `shell=False` is used.

---

## Expected false positives and how to handle them

When CodeQL is first run on this codebase, it will flag some intentional patterns. These are not bugs — they need a suppression comment, not a code change.

| Finding | Location | Action |
|---|---|---|
| Unsafe deserialization | `inspector.py`, generated `load()` bodies | Add `# codeql-suppress[py/unsafe-deserialization]` with justification |
| subprocess with user input | `inspector.py`, `validator.py` | Confirm `shell=False`, add suppression comment |

Do not suppress path traversal findings without actually fixing them — those are real.

---

## What CodeQL does NOT cover (handled by other tools)

| Concern | Tool |
|---|---|
| Vulnerable dependencies (CVEs) | `pip-audit` (ci.yml) + Trivy (docker.yml) |
| Secrets committed to git | GitHub secret scanning (enabled by default on public repos) |
| Runtime vulnerabilities | Out of scope for static analysis |

---

## Workflow schedule

Two triggers:
- **Every PR** — catches new vulnerabilities before merge
- **Weekly cron** — catches newly published CodeQL queries against existing code that was previously clean

---

## References

- [CodeQL documentation](https://codeql.github.com/docs/)
- [github/codeql-action](https://github.com/github/codeql-action)
- [security-extended query suite](https://docs.github.com/en/code-security/code-scanning/managing-your-code-scanning-configuration/built-in-codeql-query-suites)
