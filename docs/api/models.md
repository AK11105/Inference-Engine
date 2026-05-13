# Models API

## List models

```
GET /models
X-API-Key: <read_models scope>
```

Response:

```json
{
  "models": [
    {"name": "echo", "version": "v1"},
    {"name": "echo", "version": "v2"}
  ]
}
```

Returns all registered `(name, version)` pairs from the model registry.
