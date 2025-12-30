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