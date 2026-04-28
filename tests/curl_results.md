# Curl Test Results
Base: http://localhost:8000
Run: Tue, Apr 28, 2026  7:55:53 PM

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
{"job_id":"4838b7a6-a6c8-4588-9e5e-e62daa17e847"}
```

## GET /predict/async/:id
```
{"job_id":"4838b7a6-a6c8-4588-9e5e-e62daa17e847","status":"succeeded","model":"echo","version":"v1","created_at":"2026-04-28T14:25:57.567316Z","result":"async-test","error_message":null}
```

## GET /predict/async/unknown-id -> 404
```
HTTP 404
{"detail":"Job Not Found"}
```

## X-Request-ID
```
Sent: test-1777386358
Got:  test-1777386358
```

## GET /metrics (admin key)
```
HTTP 200
# HELP inference_requests_total Total inference requests
# TYPE inference_requests_total counter
inference_requests_total{model="echo",tenant="tenant_dev",version="v1"} 3.0
inference_requests_total{model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_requests_total{model="ghost",tenant="tenant_dev",version="v1"} 1.0
# HELP inference_requests_created Total inference requests
# TYPE inference_requests_created gauge
inference_requests_created{model="echo",tenant="tenant_dev",version="v1"} 1.777386355973014e+09
inference_requests_created{model="echo",tenant="tenant_dev",version="v2"} 1.7773863563628726e+09
inference_requests_created{model="ghost",tenant="tenant_dev",version="v1"} 1.7773863567533114e+09
# HELP inference_errors_total Total inference errors
# TYPE inference_errors_total counter
inference_errors_total{error_type="model_not_found",model="ghost",tenant="tenant_dev",version="v1"} 1.0
# HELP inference_errors_created Total inference errors
# TYPE inference_errors_created gauge
inference_errors_created{error_type="model_not_found",model="ghost",tenant="tenant_dev",version="v1"} 1.7773863567533114e+09
# HELP inference_latency_seconds Inference latency
# TYPE inference_latency_seconds histogram
inference_latency_seconds_bucket{le="0.005",model="echo",tenant="tenant_dev",version="v1"} 1.0
inference_latency_seconds_bucket{le="0.01",model="echo",tenant="tenant_dev",version="v1"} 2.0
inference_latency_seconds_bucket{le="0.02",model="echo",tenant="tenant_dev",version="v1"} 2.0
inference_latency_seconds_bucket{le="0.05",model="echo",tenant="tenant_dev",version="v1"} 2.0
inference_latency_seconds_bucket{le="0.1",model="echo",tenant="tenant_dev",version="v1"} 2.0
inference_latency_seconds_bucket{le="0.25",model="echo",tenant="tenant_dev",version="v1"} 2.0
inference_latency_seconds_bucket{le="0.5",model="echo",tenant="tenant_dev",version="v1"} 2.0
inference_latency_seconds_bucket{le="1.0",model="echo",tenant="tenant_dev",version="v1"} 2.0
inference_latency_seconds_bucket{le="2.0",model="echo",tenant="tenant_dev",version="v1"} 2.0
inference_latency_seconds_bucket{le="5.0",model="echo",tenant="tenant_dev",version="v1"} 2.0
inference_latency_seconds_bucket{le="10.0",model="echo",tenant="tenant_dev",version="v1"} 2.0
inference_latency_seconds_bucket{le="+Inf",model="echo",tenant="tenant_dev",version="v1"} 2.0
inference_latency_seconds_count{model="echo",tenant="tenant_dev",version="v1"} 2.0
inference_latency_seconds_sum{model="echo",tenant="tenant_dev",version="v1"} 0.011624574661254883
inference_latency_seconds_bucket{le="0.005",model="echo",tenant="tenant_dev",version="v2"} 0.0
inference_latency_seconds_bucket{le="0.01",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="0.02",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="0.05",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="0.1",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="0.25",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="0.5",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="1.0",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="2.0",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="5.0",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="10.0",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="+Inf",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_count{model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_sum{model="echo",tenant="tenant_dev",version="v2"} 0.007513523101806641
# HELP inference_latency_seconds_created Inference latency
# TYPE inference_latency_seconds_created gauge
inference_latency_seconds_created{model="echo",tenant="tenant_dev",version="v1"} 1.777386355976529e+09
inference_latency_seconds_created{model="echo",tenant="tenant_dev",version="v2"} 1.7773863563703861e+09
# HELP executor_inflight Number of in-flight inference executions
# TYPE executor_inflight gauge
executor_inflight{device="gpu"} 0.0
executor_inflight{device="cpu"} 0.0
# HELP executor_timeouts_total Total executor timeouts
# TYPE executor_timeouts_total counter
```

## GET /metrics (dev key — no admin scope) -> 403
```
HTTP 403
{"detail":"Missing Scope: admin"}
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
Request 10: HTTP 200
Request 11: HTTP 200
Request 12: HTTP 200
Request 13: HTTP 200
Request 14: HTTP 200
Request 15: HTTP 200
```

## POST /predict/async/batch
```
HTTP 200
{"job_id":"2c9ee9d4-01d7-4ab1-a06e-d901ae06fc32"}
```

## GET /predict/async/:id (batch)
```
{"job_id":"2c9ee9d4-01d7-4ab1-a06e-d901ae06fc32","status":"succeeded","model":"echo","version":"v1","created_at":"2026-04-28T14:26:04.391791Z","result":["x","y","z"],"error_message":null}
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

## GET /metrics contains tenant label
```
HTTP 200
# HELP inference_requests_total Total inference requests
# TYPE inference_requests_total counter
inference_requests_total{model="echo",tenant="tenant_dev",version="v1"} 19.0
inference_requests_total{model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_requests_total{model="ghost",tenant="tenant_dev",version="v1"} 1.0
inference_requests_total{model="echo",tenant="tenant_admin",version="v1"} 1.0
# HELP inference_requests_created Total inference requests
# TYPE inference_requests_created gauge
inference_requests_created{model="echo",tenant="tenant_dev",version="v1"} 1.777386355973014e+09
inference_requests_created{model="echo",tenant="tenant_dev",version="v2"} 1.7773863563628726e+09
inference_requests_created{model="ghost",tenant="tenant_dev",version="v1"} 1.7773863567533114e+09
inference_requests_created{model="echo",tenant="tenant_admin",version="v1"} 1.7773863665388997e+09
# HELP inference_errors_total Total inference errors
# TYPE inference_errors_total counter
inference_errors_total{error_type="model_not_found",model="ghost",tenant="tenant_dev",version="v1"} 1.0
# HELP inference_errors_created Total inference errors
# TYPE inference_errors_created gauge
inference_errors_created{error_type="model_not_found",model="ghost",tenant="tenant_dev",version="v1"} 1.7773863567533114e+09
# HELP inference_latency_seconds Inference latency
# TYPE inference_latency_seconds histogram
inference_latency_seconds_bucket{le="0.005",model="echo",tenant="tenant_dev",version="v1"} 5.0
inference_latency_seconds_bucket{le="0.01",model="echo",tenant="tenant_dev",version="v1"} 18.0
inference_latency_seconds_bucket{le="0.02",model="echo",tenant="tenant_dev",version="v1"} 18.0
inference_latency_seconds_bucket{le="0.05",model="echo",tenant="tenant_dev",version="v1"} 18.0
inference_latency_seconds_bucket{le="0.1",model="echo",tenant="tenant_dev",version="v1"} 18.0
inference_latency_seconds_bucket{le="0.25",model="echo",tenant="tenant_dev",version="v1"} 18.0
inference_latency_seconds_bucket{le="0.5",model="echo",tenant="tenant_dev",version="v1"} 18.0
inference_latency_seconds_bucket{le="1.0",model="echo",tenant="tenant_dev",version="v1"} 18.0
inference_latency_seconds_bucket{le="2.0",model="echo",tenant="tenant_dev",version="v1"} 18.0
inference_latency_seconds_bucket{le="5.0",model="echo",tenant="tenant_dev",version="v1"} 18.0
inference_latency_seconds_bucket{le="10.0",model="echo",tenant="tenant_dev",version="v1"} 18.0
inference_latency_seconds_bucket{le="+Inf",model="echo",tenant="tenant_dev",version="v1"} 18.0
inference_latency_seconds_count{model="echo",tenant="tenant_dev",version="v1"} 18.0
inference_latency_seconds_sum{model="echo",tenant="tenant_dev",version="v1"} 0.1010751724243164
inference_latency_seconds_bucket{le="0.005",model="echo",tenant="tenant_dev",version="v2"} 0.0
inference_latency_seconds_bucket{le="0.01",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="0.02",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="0.05",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="0.1",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="0.25",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="0.5",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="1.0",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="2.0",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="5.0",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="10.0",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_bucket{le="+Inf",model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_count{model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_latency_seconds_sum{model="echo",tenant="tenant_dev",version="v2"} 0.007513523101806641
inference_latency_seconds_bucket{le="0.005",model="echo",tenant="tenant_admin",version="v1"} 0.0
inference_latency_seconds_bucket{le="0.01",model="echo",tenant="tenant_admin",version="v1"} 1.0
inference_latency_seconds_bucket{le="0.02",model="echo",tenant="tenant_admin",version="v1"} 1.0
inference_latency_seconds_bucket{le="0.05",model="echo",tenant="tenant_admin",version="v1"} 1.0
inference_latency_seconds_bucket{le="0.1",model="echo",tenant="tenant_admin",version="v1"} 1.0
inference_latency_seconds_bucket{le="0.25",model="echo",tenant="tenant_admin",version="v1"} 1.0
inference_latency_seconds_bucket{le="0.5",model="echo",tenant="tenant_admin",version="v1"} 1.0
inference_latency_seconds_bucket{le="1.0",model="echo",tenant="tenant_admin",version="v1"} 1.0
inference_latency_seconds_bucket{le="2.0",model="echo",tenant="tenant_admin",version="v1"} 1.0
inference_latency_seconds_bucket{le="5.0",model="echo",tenant="tenant_admin",version="v1"} 1.0
inference_latency_seconds_bucket{le="10.0",model="echo",tenant="tenant_admin",version="v1"} 1.0
inference_latency_seconds_bucket{le="+Inf",model="echo",tenant="tenant_admin",version="v1"} 1.0
inference_latency_seconds_count{model="echo",tenant="tenant_admin",version="v1"} 1.0
inference_latency_seconds_sum{model="echo",tenant="tenant_admin",version="v1"} 0.005187034606933594
# HELP inference_latency_seconds_created Inference latency
# TYPE inference_latency_seconds_created gauge
inference_latency_seconds_created{model="echo",tenant="tenant_dev",version="v1"} 1.777386355976529e+09
inference_latency_seconds_created{model="echo",tenant="tenant_dev",version="v2"} 1.7773863563703861e+09
inference_latency_seconds_created{model="echo",tenant="tenant_admin",version="v1"} 1.7773863665440867e+09
# HELP executor_inflight Number of in-flight inference executions
# TYPE executor_inflight gauge
executor_inflight{device="gpu"} 0.0
executor_inflight{device="cpu"} 0.0
# HELP executor_timeouts_total Total executor timeouts
# TYPE executor_timeouts_total counter
```

## Metrics tenant label check
```
inference_requests_total{model="echo",tenant="tenant_dev",version="v1"} 3.0
inference_requests_total{model="echo",tenant="tenant_dev",version="v2"} 1.0
inference_requests_total{model="ghost",tenant="tenant_dev",version="v1"} 1.0
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
{"job_id":"4838b7a6-a6c8-4588-9e5e-e62daa17e847","status":"succeeded","model":"echo","version":"v1","created_at":"2026-04-28T14:25:57.567316+00:00"}
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
Sent: p4-1777386372
Got:  p4-1777386372
```


## Summary
**35 passed, 0 failed**
