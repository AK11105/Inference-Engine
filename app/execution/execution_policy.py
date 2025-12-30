class ExecutionPolicy:
    def __init__(self, executors: dict, policy: dict, default: str):
        self._executors = executors
        self._policy = policy
        self._default = default
    def resolve(self, model: str, version: str):
        key=f"{model}:{version}"
        target = self._policy.get(key, self._default)
        
        try:
            return self._executors[target]
        except:
            raise RuntimeError(f"Unknown executor '{target}'")