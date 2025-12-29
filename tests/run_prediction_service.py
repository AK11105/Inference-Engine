from app.domain.registry import ModelRegistry
from app.services import PredictionService, PredictionError, InferenceExecutionError

def main():
    registry = ModelRegistry()
    service = PredictionService(registry)
    
    result = service.predict(
        model_name="echo",
        version="v1",
        payload={"x":42}
    )
    
    print(result)
    
    ##Invalid
    try:
        inv_result = service.predict(
            model_name="echo",
            version="v2",
            payload={"x":42}
        )
        print(inv_result)
    except PredictionError:
        print("Invalid Model Caught")
    
if __name__ == "__main__":
    main()