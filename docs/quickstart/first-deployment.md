# First Deployment

This guide walks through making your first inference request using the built-in echo model.

---

## 1. Start the server

```bash
uvicorn app.adapters.http.app:app --reload
```

---

## 2. Check available models

```bash
curl -H "X-API-Key: dev-key" http://localhost:8000/models
# -> {"models": [{"name": "echo", "version": "v1"}, {"name": "echo", "version": "v2"}]}
```

---

## 3. Run synchronous inference

```bash
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "echo", "version": "v1", "data": "hello"}'
# -> {"result": "hello"}
```

---

## 4. Run batch inference

```bash
curl -X POST http://localhost:8000/predict/batch \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "echo", "version": "v1", "items": ["a", "b", "c"]}'
# -> {"results": ["a", "b", "c"]}
```

---

## 5. Submit an async job

```bash
# Submit
curl -X POST http://localhost:8000/predict/async \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "echo", "version": "v1", "data": "hello"}'
# -> {"job_id": "550e8400-..."}

# Poll status
curl -H "X-API-Key: dev-key" http://localhost:8000/predict/async/<job_id>
# -> {"job_id": "...", "status": "succeeded", "result": "hello", ...}
```

---

Next: [CLI Quickstart](cli-quickstart.md) — deploy your own model in one command.
