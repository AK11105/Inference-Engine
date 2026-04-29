FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

COPY app/ app/

EXPOSE 8000
CMD ["uvicorn", "app.adapters.http.app:app", "--host", "0.0.0.0", "--port", "8000"]
