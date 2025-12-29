from app.domain.models import EchoModel
from app.domain.processing import IdentityPreprocessor, IdentityPostprocessor
from app.domain.pipelines import InferencePipeline

def main():
    pre = IdentityPreprocessor()
    model = EchoModel()
    post = IdentityPostprocessor()

    model.load()

    pipeline = InferencePipeline(
        preprocessor=pre,
        model=model,
        postprocessor=post,
    )

    output = pipeline.run({"x": 42})
    print(output)


if __name__ == "__main__":
    main()