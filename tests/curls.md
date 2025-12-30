## 1️⃣ Health (Public – No Auth)

```bash
curl http://localhost:8000/health
```

✅ Expected:

```json
{"status":"ok"}
```

---

## 2️⃣ Predict (Authenticated, `predict` scope)

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key" \
  -d '{
    "model": "echo",
    "version": "v1",
    "data": {"x": 42}
  }'
```

✅ Expected:

```json
{"result":{"echo":{"x":42}}}
```

---

## 3️⃣ Predict Without API Key (Auth Failure)

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "model": "echo",
    "version": "v1",
    "data": {"x": 42}
  }'
```

❌ Expected:

```json
{"detail":"Missing API key"}
```

---

## 4️⃣ Predict With Invalid API Key

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -H "X-API-Key: bad-key" \
  -d '{
    "model": "echo",
    "version": "v1",
    "data": {"x": 42}
  }'
```

❌ Expected:

```json
{"detail":"Invalid API key"}
```

---

## 5️⃣ Models List (`read_models` scope)

```bash
curl http://localhost:8000/models \
  -H "X-API-Key: dev-key"
```

✅ Expected:

```json
{
  "models": [
    {"name":"echo","version":"v1"}
  ]
}
```

---

## 6️⃣ Models Without Scope (Using Predict-Only Key)

If you remove `read_models` from a key, this should fail:

```bash
curl http://localhost:8000/models \
  -H "X-API-Key: dev-key"
```

❌ Expected:

```json
{"detail":"Missing scope: read_models"}
```

---

## 7️⃣ Metrics (Admin Only)

```bash
curl http://localhost:8000/metrics \
  -H "X-API-Key: admin-key"
```

✅ Expected: Prometheus metrics output

---

### Metrics With Non-Admin Key

```bash
curl http://localhost:8000/metrics \
  -H "X-API-Key: dev-key"
```

❌ Expected:

```json
{"detail":"Missing scope: admin"}
```

---

## 8️⃣ Debug Loaded Models (Admin Only)

```bash
curl http://localhost:8000/debug/models/loaded \
  -H "X-API-Key: admin-key"
```

✅ Expected:

```json
{
  "loaded_models": [
    {"name":"echo","version":"v1"}
  ]
}
```

---

## 9️⃣ Rate Limit Test (Predict)

Fire multiple requests quickly:

```bash
for i in {1..15}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "X-API-Key: dev-key" \
    -H "Content-Type: application/json" \
    -d '{"model":"echo","version":"v1","data":{"x":1}}' \
    http://localhost:8000/predict
done
```

❌ After limit:

```text
429
```

---

## 🔟 Payload Size Guard (413)

```bash
python - <<EOF | curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  --data-binary @-
print('{"model":"echo","version":"v1","data":"' + "A"*2000000 + '"}')
EOF
```

❌ Expected:

```json
{"detail":"Payload too large"}
```

---


## Test Batch Inference

```bash
curl -X POST http://localhost:8000/predict/batch \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key" \
  -d '{
    "model": "echo",
    "version": "v1",
    "items": [
      {"x": 1},
      {"x": 2},
      {"x": 3}
    ]
  }'
```

✅ Expected:

```json
{
  "results": [
    {"echo":{"x":1}},
    {"echo":{"x":2}},
    {"echo":{"x":3}}
  ]
}
```
---

## Test Async Inference

```bash
curl -X POST http://localhost:8000/predict/async \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "echo",
    "version": "v1",
    "data": {"x": 99}
  }'
```

✅ Expected:

```json
{"job_id":"<uuid>"}
```

```bash
curl http://localhost:8000/predict/async/<uuid> \
  -H "X-API-Key: dev-key"
```

✅ Expected:

```json
{
  "status": "succeeded",
  "result": {"echo":{"x":99}},
  "error": null
}

```
---

## Test Async Batch Inference

```bash
curl -X POST http://localhost:8000/predict/async/batch \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "echo",
    "version": "v1",
    "items": [
      {"x": 1},
      {"x": 2},
      {"x": 3}
    ]
  }'
```

✅ Expected:

```json
{"job_id":"<uuid>"}
```

```bash
curl http://localhost:8000/predict/async/<uuid> \
  -H "X-API-Key: dev-key"
```

✅ Expected:

```json
{
  "status": "succeeded",
  "result": [
    {"echo":{"x":1}},
    {"echo":{"x":2}},
    {"echo":{"x":3}}
  ],
  "error": null
}

```

# Routing Tests

---

## 0️⃣ Preconditions (verify first)

### Routing config (`app/config/routing.py`)

Make sure you have something like this **exactly**:

```python
ROUTES = {
    "echo": {
        "strategy": "canary",
        "primary": "v1",
        "canary": "v2",
        "canary_percent": 100,  # IMPORTANT for deterministic test
    }
}
```

And ensure **both versions exist** in your registry:

* `echo:v1`
* `echo:v2`

Restart the server after any routing change.

---

## 1️⃣ Baseline sanity check (no routing logic yet)

Call predict **with explicit version**
→ routing must be bypassed.

```bash
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "echo",
    "version": "v1",
    "data": {"x": 1}
  }'
```

✅ Expected:

```json
{"echo":{"x":1}}
```

This confirms:

* registry works
* executor works
* routing does **not** override explicit version (correct)

---

## 2️⃣ Canary routing (implicit version)

Now **remove the version** so routing is forced:

```bash
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "echo",
    "version": null,
    "data": {"x": 2}
  }'
```

Because `canary_percent = 100`:

✅ Expected:

```json
{"echo":{"x":2}}
```

But **internally**:

* model resolved to `echo:v2`
* metrics/logs should show `version="v2"`

👉 Check `/metrics` to confirm:

```bash
curl http://localhost:8000/metrics -H "X-API-Key: admin-key"
```

You should see:

```
inference_requests_total{model="echo",version="v2"} 1
```

This confirms routing is applied **inside PredictionService**.

---

## 3️⃣ Batch + routing

```bash
curl -X POST http://localhost:8000/predict/batch \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "echo",
    "version": null,
    "items": [
      {"x": 10},
      {"x": 20}
    ]
  }'
```

✅ Expected:

```json
{
  "results": [
    {"echo":{"x":10}},
    {"echo":{"x":20}}
  ]
}
```

Metrics should now show:

```
inference_requests_total{model="echo",version="v2"} 3
```

This proves:

* routing applies to batch
* routing is not duplicated
* executor unchanged

---

## 4️⃣ Async + routing

### Submit async job

```bash
curl -X POST http://localhost:8000/predict/async \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "echo",
    "version": null,
    "data": {"x": 99}
  }'
```

```json
{"job_id":"<uuid>"}
```

### Poll job

```bash
curl http://localhost:8000/predict/async/<uuid> \
  -H "X-API-Key: dev-key"
```

✅ Expected:

```json
{
  "status": "succeeded",
  "result": {"echo":{"x":99}},
  "error": null
}
```

Metrics again should increment **v2**, not v1.

This confirms:

* async is a wrapper (correct)
* routing happens once
* no double resolution

---

## 5️⃣ Canary probability test (optional)

Change:

```python
"canary_percent": 50
```

Restart, then run:

```bash
for i in {1..20}; do
  curl -s -X POST http://localhost:8000/predict \
    -H "X-API-Key: dev-key" \
    -H "Content-Type: application/json" \
    -d '{"model":"echo","version":null,"data":{"x":1}}' \
    | jq .
done
```

Check `/metrics`:

You should see **both**:

```
version="v1"
version="v2"
```

That proves probabilistic routing works.

---

# Execution Policy Tests

---

## 1️⃣ Metrics sanity (device awareness exists)

```bash
curl http://localhost:8000/metrics -H "X-API-Key: admin-key"
```

✅ You must see **both labels**, even on a CPU-only machine:

```
executor_inflight{device="cpu"} 0
executor_inflight{device="gpu"} 0
executor_timeouts_total{device="cpu"} 0
executor_timeouts_total{device="gpu"} 0
```

👉 This proves:

* multiple executors exist
* metrics are device-scoped

---

## 2️⃣ CPU execution path (default)

Ensure config maps to CPU:

```python
EXECUTION_POLICY = {
    "echo:v1": "cpu",
}
```

Run inference:

```bash
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"echo","version":"v1","data":{"x":1}}'
```

Then re-check metrics:

```bash
curl http://localhost:8000/metrics -H "X-API-Key: admin-key"
```

✅ Expected:

```
executor_inflight{device="cpu"} 0
executor_inflight{device="gpu"} 0
```

(no GPU activity)

---

## 3️⃣ GPU policy path (logical, even without GPU)

Change config:

```python
EXECUTION_POLICY = {
    "echo:v1": "gpu",
}
```

Restart server, then:

```bash
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"echo","version":"v1","data":{"x":2}}'
```

Check metrics:

```bash
curl http://localhost:8000/metrics -H "X-API-Key: admin-key"
```

✅ Expected:

```
executor_inflight{device="gpu"} 0
executor_inflight{device="cpu"} 0
```

👉 This proves:

* execution policy switched executors
* hardware presence is irrelevant to routing

---

## 4️⃣ Batch respects executor selection

```bash
curl -X POST http://localhost:8000/predict/batch \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"echo","version":"v1","items":[{"x":1},{"x":2}]}'
```

✅ Metrics increment **only for the mapped device** (cpu or gpu).

---

## 5️⃣ Async respects executor selection

```bash
JOB_ID=$(curl -s -X POST http://localhost:8000/predict/async \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"echo","version":"v1","data":{"x":3}}' | jq -r .job_id)

curl http://localhost:8000/predict/async/$JOB_ID -H "X-API-Key: dev-key"
```

✅ Metrics again increment **only for the mapped executor**.

---

## 6️⃣ Failure test (invalid executor mapping)

Set:

```python
EXECUTION_POLICY = {
    "echo:v1": "tpu",
}
```

Restart and call predict.

❌ Expected:

```
500 Internal Server Error
"Unknown executor 'tpu'"
```

👉 Confirms:

* policy enforcement is strict
* no silent fallback (correct for Phase 8C)

---

