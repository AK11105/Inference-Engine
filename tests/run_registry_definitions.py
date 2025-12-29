from app.domain.registry import ModelRegistry, ModelNotFoundError

def main():
    registry = ModelRegistry()
    
    pipeline = registry.get("echo", "v1")
    
    output = pipeline.run({"x": 42})
    print(output)
    
    p1 = registry.get("echo", "v1")
    p2 = registry.get("echo", "v1")
    if (p1 is p2):
        print("In Memory Caching Successful")
    
    try:
        p3 = registry.get("echo", "v3")
        ## Should Raise Model Not Found Error
    except ModelNotFoundError:
        print("Invalid Models Caught Successfully")


if __name__ == "__main__":
    main()