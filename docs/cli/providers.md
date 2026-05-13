# Supported Frameworks

The CLI inspector detects the artifact framework and selects a prompt template for code generation. All detections use lazy imports — none are required dependencies.

| Framework | Support | Metadata extracted |
|---|---|---|
| sklearn | Full | pipeline steps, feature count, class labels |
| PyTorch (`nn.Module`) | Full | layer count, first/last layer names |
| Transformers (`PreTrainedModel`) | Full | model type, num_labels, tokenizer class |
| XGBoost | Full | n_estimators, objective |
| LightGBM | Full | n_estimators, objective |
| CatBoost | Full | feature count, loss function |
| ONNX (`.onnx` file) | Full | input/output names and shapes |
| sentence-transformers | Full | embedding dimension |
| Generic | Fallback | class name only — LLM fills the gaps |

The inspector runs in an isolated subprocess, so missing frameworks degrade gracefully without affecting the CLI.

---

## LLM provider

The CLI uses [Groq](https://groq.com) by default (`llama-3.3-70b-versatile`). Override with:

```bash
INFERENCE_ENGINE_LLM_MODEL=llama-3.1-8b-instant
```
