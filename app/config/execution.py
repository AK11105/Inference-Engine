EXECUTION_POLICY = {
    # model:version → executor
    "echo:v1": "gpu",
    "echo:v2": "cpu",        # later: gpu
    # "classifier:v2": "gpu",
}

DEFAULT_EXECUTOR = "cpu"
