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