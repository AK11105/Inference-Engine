ROUTES = {
    "echo": {
        "strategy": "canary",
        "primary": "v1",
        "canary": "v2",
        "canary_percent": 50,
    },

    # example A/B
    "classifier": {
        "strategy": "ab",
        "variants": {
            "v1": 50,
            "v2": 50,
        },
    },

    # example static
    "stable_model": {
        "strategy": "static",
        "version": "v3",
    },
}
