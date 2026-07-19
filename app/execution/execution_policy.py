from app.core.logging import get_logger

_logger = get_logger(__name__)
_COMPONENT = "ExecutionPolicy"


class ExecutionPolicy:
    def __init__(self, executors: dict, policy: dict, default: str):
        self._executors = executors
        self._policy = policy
        self._default = default

    def resolve(self, model: str, version: str):
        key = f"{model}:{version}"
        target = self._policy.get(key, self._default)
        try:
            executor = self._executors[target]
        except KeyError:
            raise RuntimeError(f"Unknown executor '{target}'")
        _logger.info(
            event="ExecutorSelected", component=_COMPONENT,
            model=model, version=version, executor=target,
        )
        return executor
