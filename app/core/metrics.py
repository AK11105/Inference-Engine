from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry

REGISTRY = CollectorRegistry()

#Request-Level

INFERENCE_REQUESTS = Counter(
    "inference_requests_total",
    "Total inference requests",
    ["model", "version"],
    registry=REGISTRY,
)

INFERENCE_ERRORS = Counter(
    "inference_errors_total",
    "Total inference errors",
    ["model", "version", "error_type"],
    registry=REGISTRY,
)

INFERENCE_LATENCY = Histogram(
    "inference_latency_seconds",
    "Inference latency",
    ["model", "version"],
    buckets=(0.005, 0.01, 0.02, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
    registry=REGISTRY,
)

INFERENCE_RETRIES = Counter(
    "inference_retries_total",
    "Total inference retry attempts",
    ["model", "version", "reason"],  # e.g. ExecutionTimeoutError
    registry=REGISTRY,
)

INFERENCE_RETRY_EXHAUSTED = Counter(
    "inference_retry_exhausted_total",
    "Total jobs where retry budget was exhausted",
    ["model", "version", "reason"],
    registry=REGISTRY,
)

#Executor Level

EXECUTOR_INFLIGHT = Gauge(
    "executor_inflight",
    "Number of in-flight inference executions",
    ["device"],
    registry=REGISTRY,
)

EXECUTOR_TIMEOUTS = Counter(
    "executor_timeouts_total",
    "Total executor timeouts",
    ["device"],
    registry=REGISTRY,
)