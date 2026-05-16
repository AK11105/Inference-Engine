# Curl Test Results
Base: http://localhost:8000
Run: Sat May 16 22:28:39 IST 2026

## GET /health (no auth)
```
HTTP 200
{"status":"ok"}
```

## GET /ready
```
HTTP 200
{"status":"ready"}
```

## GET /models
```
HTTP 200
{"models":[{"name":"echo","version":"v1"},{"name":"echo","version":"v2"}]}
```

## POST /predict no key -> 401
```
HTTP 401
{"detail":"Missing API Key"}
```

## POST /predict bad key -> 401
```
HTTP 401
{"detail":"Invalid API Key"}
```

## POST /predict echo v1
```
HTTP 200
{"result":"hello"}
```

## POST /predict echo v2
```
HTTP 200
{"result":42}
```

## POST /predict unknown model -> 400
```
HTTP 400
{"detail":"Model 'ghost' with version 'v1' not found."}
```

## POST /predict/batch
```
HTTP 200
{"results":["a","b","c"]}
```

## POST /predict/async
```
HTTP 200
{"job_id":"87e44fc1-d138-43bd-af2c-faa8f74a3c2e"}
```

## GET /predict/async/:id
```
{"job_id":"87e44fc1-d138-43bd-af2c-faa8f74a3c2e","status":"succeeded","model":"echo","version":"v1","created_at":"2026-05-16T16:58:39.692070Z","result":"async-test","error_message":null}
```

## GET /predict/async/unknown-id -> 404
```
HTTP 404
{"detail":"Job Not Found"}
```

## X-Request-ID
```
Sent: test-1778950720
Got:  test-1778950720
```

## GET /metrics (no auth — public)
```
HTTP 200
# HELP inference_requests_total Total inference requests
# TYPE inference_requests_total counter
inference_requests_total{model="echo",tenant="tenant_dev",version="v1"} 31.0
inference_requests_total{model="echo",tenant="tenant_dev",version="v2"} 3.0
inference_requests_total{model="ghost",tenant="tenant_dev",version="v1"} 3.0
inference_requests_total{model="echo",tenant="tenant_admin",version="v1"} 2.0
# HELP inference_requests_created Total inference requests
# TYPE inference_requests_created gauge
inference_requests_created{model="echo",tenant="tenant_dev",version="v1"} 1.7789495350827734e+09
inference_requests_created{model="echo",tenant="tenant_dev",version="v2"} 1.778949535109862e+09
inference_requests_created{model="ghost",tenant="tenant_dev",version="v1"} 1.7789495351387594e+09
inference_requests_created{model="echo",tenant="tenant_admin",version="v1"} 1.7789495369200494e+09
# HELP inference_errors_total Total inference errors
# TYPE inference_errors_total counter
inference_errors_total{error_type="model_not_found",model="ghost",tenant="tenant_dev",version="v1"} 3.0
# HELP inference_errors_created Total inference errors
# TYPE inference_errors_created gauge
inference_errors_created{error_type="model_not_found",model="ghost",tenant="tenant_dev",version="v1"} 1.778949535138786e+09
# HELP inference_latency_seconds Inference latency
# TYPE inference_latency_seconds histogram
inference_latency_seconds_bucket{le="0.005",model="echo",tenant="tenant_dev",version="v1"} 25.0
inference_latency_seconds_bucket{le="0.01",model="echo",tenant="tenant_dev",version="v1"} 28.0
inference_latency_seconds_bucket{le="0.02",model="echo",tenant="tenant_dev",version="v1"} 28.0
inference_latency_seconds_bucket{le="0.05",model="echo",tenant="tenant_dev",version="v1"} 28.0
inference_latency_seconds_bucket{le="0.1",model="echo",tenant="tenant_dev",version="v1"} 28.0
inference_latency_seconds_bucket{le="0.25",model="echo",tenant="tenant_dev",version="v1"} 28.0
inference_latency_seconds_bucket{le="0.5",model="echo",tenant="tenant_dev",version="v1"} 28.0
inference_latency_seconds_bucket{le="1.0",model="echo",tenant="tenant_dev",version="v1"} 28.0
inference_latency_seconds_bucket{le="2.0",model="echo",tenant="tenant_dev",version="v1"} 28.0
inference_latency_seconds_bucket{le="5.0",model="echo",tenant="tenant_dev",version="v1"} 28.0
inference_latency_seconds_bucket{le="10.0",model="echo",tenant="tenant_dev",version="v1"} 28.0
inference_latency_seconds_bucket{le="+Inf",model="echo",tenant="tenant_dev",version="v1"} 28.0
inference_latency_seconds_count{model="echo",tenant="tenant_dev",version="v1"} 28.0
inference_latency_seconds_sum{model="echo",tenant="tenant_dev",version="v1"} 0.08963632583618164
inference_latency_seconds_bucket{le="0.005",model="echo",tenant="tenant_dev",version="v2"} 3.0
inference_latency_seconds_bucket{le="0.01",model="echo",tenant="tenant_dev",version="v2"} 3.0
inference_latency_seconds_bucket{le="0.02",model="echo",tenant="tenant_dev",version="v2"} 3.0
inference_latency_seconds_bucket{le="0.05",model="echo",tenant="tenant_dev",version="v2"} 3.0
inference_latency_seconds_bucket{le="0.1",model="echo",tenant="tenant_dev",version="v2"} 3.0
inference_latency_seconds_bucket{le="0.25",model="echo",tenant="tenant_dev",version="v2"} 3.0
inference_latency_seconds_bucket{le="0.5",model="echo",tenant="tenant_dev",version="v2"} 3.0
inference_latency_seconds_bucket{le="1.0",model="echo",tenant="tenant_dev",version="v2"} 3.0
inference_latency_seconds_bucket{le="2.0",model="echo",tenant="tenant_dev",version="v2"} 3.0
inference_latency_seconds_bucket{le="5.0",model="echo",tenant="tenant_dev",version="v2"} 3.0
inference_latency_seconds_bucket{le="10.0",model="echo",tenant="tenant_dev",version="v2"} 3.0
inference_latency_seconds_bucket{le="+Inf",model="echo",tenant="tenant_dev",version="v2"} 3.0
inference_latency_seconds_count{model="echo",tenant="tenant_dev",version="v2"} 3.0
inference_latency_seconds_sum{model="echo",tenant="tenant_dev",version="v2"} 0.00959324836730957
inference_latency_seconds_bucket{le="0.005",model="echo",tenant="tenant_admin",version="v1"} 1.0
inference_latency_seconds_bucket{le="0.01",model="echo",tenant="tenant_admin",version="v1"} 2.0
inference_latency_seconds_bucket{le="0.02",model="echo",tenant="tenant_admin",version="v1"} 2.0
inference_latency_seconds_bucket{le="0.05",model="echo",tenant="tenant_admin",version="v1"} 2.0
inference_latency_seconds_bucket{le="0.1",model="echo",tenant="tenant_admin",version="v1"} 2.0
inference_latency_seconds_bucket{le="0.25",model="echo",tenant="tenant_admin",version="v1"} 2.0
inference_latency_seconds_bucket{le="0.5",model="echo",tenant="tenant_admin",version="v1"} 2.0
inference_latency_seconds_bucket{le="1.0",model="echo",tenant="tenant_admin",version="v1"} 2.0
inference_latency_seconds_bucket{le="2.0",model="echo",tenant="tenant_admin",version="v1"} 2.0
inference_latency_seconds_bucket{le="5.0",model="echo",tenant="tenant_admin",version="v1"} 2.0
inference_latency_seconds_bucket{le="10.0",model="echo",tenant="tenant_admin",version="v1"} 2.0
inference_latency_seconds_bucket{le="+Inf",model="echo",tenant="tenant_admin",version="v1"} 2.0
inference_latency_seconds_count{model="echo",tenant="tenant_admin",version="v1"} 2.0
inference_latency_seconds_sum{model="echo",tenant="tenant_admin",version="v1"} 0.011166810989379883
# HELP inference_latency_seconds_created Inference latency
# TYPE inference_latency_seconds_created gauge
inference_latency_seconds_created{model="echo",tenant="tenant_dev",version="v1"} 1.7789495350864043e+09
inference_latency_seconds_created{model="echo",tenant="tenant_dev",version="v2"} 1.7789495351122854e+09
inference_latency_seconds_created{model="echo",tenant="tenant_admin",version="v1"} 1.7789495369269269e+09
# HELP executor_inflight Number of in-flight inference executions
# TYPE executor_inflight gauge
executor_inflight{device="gpu"} 0.0
executor_inflight{device="cpu"} 0.0
# HELP executor_timeouts_total Total executor timeouts
# TYPE executor_timeouts_total counter
# HELP job_queue_depth Number of jobs currently in PENDING state
# TYPE job_queue_depth gauge
job_queue_depth{model="echo",version="v1"} 5.0
job_queue_depth{model="echo",version="v2"} 0.0
job_queue_depth{model="ghost",version="v1"} 3.0
```

## Rate limit burst
```
Request 1: HTTP 200
Request 2: HTTP 200
Request 3: HTTP 200
Request 4: HTTP 200
Request 5: HTTP 200
Request 6: HTTP 200
Request 7: HTTP 200
Request 8: HTTP 200
Request 9: HTTP 200
Request 10: HTTP 429
Request 11: HTTP 429
Request 12: HTTP 429
Request 13: HTTP 429
Request 14: HTTP 429
Request 15: HTTP 429
```

## POST /predict/async/batch
```
HTTP 200
{"job_id":"42c57a72-8ab6-441c-b3b1-afea40f69b1c"}
```

## GET /predict/async/:id (batch)
```
{"job_id":"42c57a72-8ab6-441c-b3b1-afea40f69b1c","status":"succeeded","model":"echo","version":"v1","created_at":"2026-05-16T16:58:40.790241Z","result":["x","y","z"],"error_message":null}
```

## POST /predict (tenant_dev)
```
HTTP 200
{"result":"tenant-dev-input"}
```

## POST /predict (tenant_admin)
```
HTTP 200
{"result":"tenant-admin-input"}
```

## Metrics tenant label check
```
inference_requests_total{model="echo",tenant="tenant_dev",version="v1"} 41.0
inference_requests_total{model="echo",tenant="tenant_dev",version="v2"} 3.0
inference_requests_total{model="ghost",tenant="tenant_dev",version="v1"} 3.0
```

## Models list
```
{"models":[{"name":"echo","version":"v1"},{"name":"echo","version":"v2"}]}
```

## POST /predict oversized payload -> 413
```
HTTP 413
{"detail":"Payload too large"}
```

## GET /debug/models/loaded (admin)
```
HTTP 200
{"loaded_models":[{"name":"echo","version":"v2"},{"name":"echo","version":"v1"}]}
```

## GET /debug/models/loaded (dev key — no admin scope) -> 403
```
HTTP 403
{"detail":"Missing Scope: admin"}
```

## GET /jobs/:id
```
HTTP 200
{"job_id":"87e44fc1-d138-43bd-af2c-faa8f74a3c2e","status":"succeeded","model":"echo","version":"v1","created_at":"2026-05-16T16:58:39.692070+00:00"}
```

## POST /admin/models/echo/v1/reload (admin)
```
HTTP 200
{"reloaded":true,"model":"echo","version":"v1"}
```

## POST /admin/models/echo/v1/reload (dev key) -> 403
```
HTTP 403
{"detail":"Missing Scope: admin"}
```

## POST /admin/models/ghost/v99/reload -> 404
```
HTTP 404
{"detail":"Model 'ghost' with version 'v99' not found."}
```

## POST /predict after reload
```
HTTP 200
{"result":"post-reload"}
```

## GET /admin/models/memory (admin)
```
HTTP 200
{"loaded":2,"max_loaded":null,"models":[{"name":"echo","version":"v2"},{"name":"echo","version":"v1"}]}
```

## GET /admin/models/memory (dev key) -> 403
```
HTTP 403
{"detail":"Missing Scope: admin"}
```

## Memory status body
```
{"loaded":2,"max_loaded":null,"models":[{"name":"echo","version":"v2"},{"name":"echo","version":"v1"}]}
```

## X-Request-ID (phase 4)
```
Sent: p4-1778950725
Got:  p4-1778950725
```


## Summary
**33 passed, 0 failed**
