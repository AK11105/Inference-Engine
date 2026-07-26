# Inference Playground

The Inference Playground is a built-in web UI for testing model predictions directly in the browser. After deploying a model, open `/playground` to submit predictions, view responses, benchmark latency, and generate code snippets — no curl or Postman needed.

## Accessing the Playground

After starting the server:

```bash
uvicorn app.adapters.http.app:app --reload
```

Open [http://localhost:8000/playground](http://localhost:8000/playground) in your browser.

After a CLI deploy, the URL is printed automatically:

```
✓ Model deployed: sentiment v1
✓ Endpoint:    http://localhost:8000/predict
✓ Playground:  http://localhost:8000/playground
✓ OpenAPI:     http://localhost:8000/docs
```

## Features

### Model Selector

The playground fetches available models from the `/models` API. If multiple models are deployed, select which one to test from the dropdown. Click the refresh button (&#8635;) to reload the list.

### Input Modes

Three input modes are available:

| Mode | Use Case |
|------|----------|
| **JSON** | Structured data — objects, arrays, numbers |
| **Text** | Plain text input — NLP models, sentiment analysis |
| **CSV** | Tabular data — upload a file or paste CSV content |

For CSV mode, you can either drag-and-drop a `.csv` file onto the upload zone, browse for a file, or paste CSV content directly into the text area. The CSV is parsed into JSON objects using the header row as keys.

### Response Display

Each prediction shows:

- **Status** — HTTP status code (200 OK or error)
- **Latency** — Round-trip time in milliseconds
- **Output** — Formatted JSON response

### Latency Benchmarking

Click **Benchmark** to run N sequential requests (configurable, default 10) and see percentile latencies:

- **p50** — Median latency
- **p95** — 95th percentile
- **p99** — 99th percentile

This helps establish baseline performance and detect regressions.

### Code Snippets

Auto-generated code for the current model and input in three languages:

- **curl** — Copy-paste into terminal
- **Python** — Uses the `requests` library
- **JavaScript** — Uses the `fetch` API

Snippets update automatically as you change the model, input, or API key.

### Request History

The last 50 requests are stored in `localStorage` and persist across page reloads. Each entry shows:

- Model name and version
- Timestamp and latency
- Abbreviated input → output

Click **Clear** to remove all history.

## Authentication

The playground UI itself loads without an API key (no auth required for static assets). However, the **API calls** to `/predict` and `/models` still require a valid key.

The API Key field is pre-populated with `dev-key` (the built-in development key). In production, enter your actual API key.

## Technical Details

- **Zero dependencies** — Pure HTML + vanilla JavaScript + CSS
- **No build step** — Static files served directly via FastAPI's `StaticFiles`
- **No CDN** — Works fully offline, no external network requests
- **Bundled in Docker** — Automatically included in the container image
- **Location** — `app/static/playground/`

## Customization

The playground is three files you can modify directly:

| File | Purpose |
|------|---------|
| `app/static/playground/index.html` | Page structure and layout |
| `app/static/playground/playground.css` | Styling (dark theme by default) |
| `app/static/playground/playground.js` | All client logic |

No build tools or transpilation needed — edit and reload.
