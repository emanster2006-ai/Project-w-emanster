# ── Stage 1: Builder ────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps for unstructured + presidio
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmagic1 \
    poppler-utils \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# The PyTorch CPU index offers "+cpu" builds, which pip prefers over the default wheel
# that pulls ~4 GB of CUDA libraries the API never uses.
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt \
    --extra-index-url https://download.pytorch.org/whl/cpu

# Download spacy model for presidio NER
# (pip --prefix installs no interpreter, so /install/bin/python does not exist; install the
# model wheel matching spacy==3.7.5 straight into the same prefix instead.)
# --no-deps: resolving the model's dependencies here would overwrite the pinned versions
# installed above with whatever is newest.
RUN pip install --no-cache-dir --no-deps --prefix=/install \
    https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.7.1/en_core_web_lg-3.7.1-py3-none-any.whl

# ── Stage 2: Runtime ────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    poppler-utils \
    tesseract-ocr \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Non-root user for security; --chown avoids a second copy of the source in another layer.
# UID 1000 matches the user Hugging Face Spaces runs containers as.
RUN useradd -m -u 1000 appuser

# Copy application source (.dockerignore keeps .env, .git, frontend and data out)
COPY --chown=appuser:appuser . .
USER appuser

# Load the reranker, BM25 index and PII models at startup instead of on the first question,
# so a freshly started host answers its first request quickly.
ENV WARM_UP_MODELS=1

EXPOSE 8000

# Each worker loads its own models (2.5 GB measured with 2 workers), so hosted demos should use 1.
# PORT is set by hosts such as Hugging Face Spaces (7860); defaults to 8000.
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${UVICORN_WORKERS:-2}"]
