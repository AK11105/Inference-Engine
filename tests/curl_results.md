# Curl Test Results
Base: http://localhost:8000
Run: Sun, Apr 26, 2026 12:16:18 PM

## GET /health
```
HTTP 200
{"status":"ok"}
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

## POST /predict unknown -> 400
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
{"job_id":"3b65ee6e-c770-4615-9ef0-f0188b6c8516"}
```

## GET /predict/async/:id
```
{"job_id":"3b65ee6e-c770-4615-9ef0-f0188b6c8516","status":"succeeded","model":"echo","version":"v1","created_at":"2026-04-26T06:46:22.402805Z","result":"async-test","error_message":null}
```

## GET /predict/async/bad-id -> 404
```
HTTP 404
{"detail":"Job Not Found"}
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

## GET /metrics
```
HTTP 200
# HELP inference_requests_total Total inference requests
# TYPE inference_requests_total counter
inference_requests_total{model="echo",version="v1"} 2.0
inference_requests_total{model="echo",version="v2"} 1.0
inference_requests_total{model="ghost",version="v1"} 1.0
# HELP inference_requests_created Total inference requests
# TYPE inference_requests_created gauge
inference_requests_created{model="echo",version="v1"} 1.777185980224687e+09
inference_requests_created{model="echo",version="v2"} 1.7771859807491615e+09
inference_requests_created{model="ghost",version="v1"} 1.777185981340859e+09
# HELP inference_errors_total Total inference errors
# TYPE inference_errors_total counter
inference_errors_total{error_type="model_not_found",model="ghost",version="v1"} 1.0
# HELP inference_errors_created Total inference errors
# TYPE inference_errors_created gauge
inference_errors_created{error_type="model_not_found",model="ghost",version="v1"} 1.777185981340859e+09
# HELP inference_latency_seconds Inference latency
# TYPE inference_latency_seconds histogram
inference_latency_seconds_bucket{le="0.005",model="echo",version="v1"} 0.0
inference_latency_seconds_bucket{le="0.01",model="echo",version="v1"} 0.0
inference_latency_seconds_bucket{le="0.02",model="echo",version="v1"} 1.0
inference_latency_seconds_bucket{le="0.05",model="echo",version="v1"} 1.0
inference_latency_seconds_bucket{le="0.1",model="echo",version="v1"} 1.0
inference_latency_seconds_bucket{le="0.25",model="echo",version="v1"} 1.0
inference_latency_seconds_bucket{le="0.5",model="echo",version="v1"} 1.0
inference_latency_seconds_bucket{le="1.0",model="echo",version="v1"} 1.0
inference_latency_seconds_bucket{le="2.0",model="echo",version="v1"} 1.0
inference_latency_seconds_bucket{le="5.0",model="echo",version="v1"} 1.0
inference_latency_seconds_bucket{le="10.0",model="echo",version="v1"} 1.0
inference_latency_seconds_bucket{le="+Inf",model="echo",version="v1"} 1.0
inference_latency_seconds_count{model="echo",version="v1"} 1.0
inference_latency_seconds_sum{model="echo",version="v1"} 0.013489961624145508
inference_latency_seconds_bucket{le="0.005",model="echo",version="v2"} 0.0
inference_latency_seconds_bucket{le="0.01",model="echo",version="v2"} 0.0
inference_latency_seconds_bucket{le="0.02",model="echo",version="v2"} 1.0
inference_latency_seconds_bucket{le="0.05",model="echo",version="v2"} 1.0
inference_latency_seconds_bucket{le="0.1",model="echo",version="v2"} 1.0
inference_latency_seconds_bucket{le="0.25",model="echo",version="v2"} 1.0
inference_latency_seconds_bucket{le="0.5",model="echo",version="v2"} 1.0
inference_latency_seconds_bucket{le="1.0",model="echo",version="v2"} 1.0
inference_latency_seconds_bucket{le="2.0",model="echo",version="v2"} 1.0
inference_latency_seconds_bucket{le="5.0",model="echo",version="v2"} 1.0
inference_latency_seconds_bucket{le="10.0",model="echo",version="v2"} 1.0
inference_latency_seconds_bucket{le="+Inf",model="echo",version="v2"} 1.0
inference_latency_seconds_count{model="echo",version="v2"} 1.0
inference_latency_seconds_sum{model="echo",version="v2"} 0.011805057525634766
# HELP inference_latency_seconds_created Inference latency
# TYPE inference_latency_seconds_created gauge
inference_latency_seconds_created{model="echo",version="v1"} 1.777185980238177e+09
inference_latency_seconds_created{model="echo",version="v2"} 1.7771859807619827e+09
# HELP executor_inflight Number of in-flight inference executions
# TYPE executor_inflight gauge
executor_inflight{device="gpu"} 0.0
executor_inflight{device="cpu"} 0.0
# HELP executor_timeouts_total Total executor timeouts
# TYPE executor_timeouts_total counter
```

## X-Request-ID
```
Sent: test-1777185985
Got:  test-1777185985
```

## Rate limit
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
```


## Summary
**15 passed, 0 failed**
