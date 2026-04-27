"""
S3ModelLoader — downloads model artifacts from an S3 bucket to a local temp dir.

Expected S3 key prefix:  <prefix>/<model_name>/<version>/

Requires boto3.  Falls back gracefully if not installed.
"""
import tempfile
from pathlib import Path

from app.domain.loading.base import ModelLoader


class S3ModelLoader(ModelLoader):
    """
    Downloads all objects under s3://<bucket>/<prefix>/<model>/<version>/
    into a temporary local directory and returns that path.
    """

    def __init__(self, bucket: str, prefix: str = "models"):
        self._bucket = bucket
        self._prefix = prefix.rstrip("/")

    def load(self, model_name: str, version: str) -> Path:
        try:
            import boto3
        except ImportError as e:
            raise RuntimeError("boto3 is required for S3ModelLoader") from e

        s3 = boto3.client("s3")
        s3_prefix = f"{self._prefix}/{model_name}/{version}/"

        paginator = s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=self._bucket, Prefix=s3_prefix)

        tmp = Path(tempfile.mkdtemp())
        found = False
        for page in pages:
            for obj in page.get("Contents", []):
                key: str = obj["Key"]
                rel = key[len(s3_prefix):]
                if not rel:
                    continue
                dest = tmp / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                s3.download_file(self._bucket, key, str(dest))
                found = True

        if not found:
            raise FileNotFoundError(
                f"No artifacts found at s3://{self._bucket}/{s3_prefix}"
            )
        return tmp
