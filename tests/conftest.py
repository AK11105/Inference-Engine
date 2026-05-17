"""Session-scoped fixture generation for tests that need a real sklearn artifact."""
from __future__ import annotations

import pickle
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "sentiment.pkl"


def _create_sentiment_pkl() -> None:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    texts = [
        "this movie was great", "excellent film loved it", "amazing performance",
        "wonderful story", "best movie ever", "highly recommend",
        "terrible movie hated it", "awful film boring", "worst movie ever",
        "complete waste of time", "very bad film", "do not watch",
    ]
    labels = [1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0]

    pipeline = Pipeline([("tfidf", TfidfVectorizer()), ("clf", LogisticRegression(max_iter=1000))])
    pipeline.fit(texts, labels)

    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    with open(FIXTURE, "wb") as f:
        pickle.dump(pipeline, f)


def pytest_configure(config):
    if not FIXTURE.exists():
        _create_sentiment_pkl()
