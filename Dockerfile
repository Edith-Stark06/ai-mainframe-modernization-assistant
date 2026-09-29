# AI-Powered Mainframe Modernization Assistant
#
# One image, two services (see docker-compose.yml): the FastAPI backend
# (uvicorn) and the Streamlit frontend, both installed from the same
# pinned dependency set in pyproject.toml so there is no drift between
# what runs in each container.

FROM python:3.12-slim AS base

# libgomp1: required by onnxruntime/torch at runtime on slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only the dependency manifest first so this layer is cached across
# source-code-only changes.
COPY pyproject.toml README.md ./
COPY app ./app

# torch's default (CUDA) wheel bundles the full NVIDIA CUDA/cuDNN
# runtime -- over 1GB of libraries this CPU-only container will never
# use (sentence-transformers, a runtime dependency, pulls torch in
# transitively). Installing the CPU-only wheel first, pinned to the
# exact version this project is validated against, satisfies that
# dependency before `pip install .` ever gets a chance to resolve the
# much larger default one. --timeout/--retries: this dependency set is
# large enough (torch alone is ~200MB) that a single slow/flaky read on
# an otherwise-healthy connection would otherwise fail the whole build.
RUN pip install --no-cache-dir --timeout=120 --retries=5 \
        torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --timeout=120 --retries=5 .

# Bake the embedding model into the image. Without this the first
# /chat/index or /chat request in every fresh container downloads it
# from HuggingFace (measured: ~3.5 minutes on a slow link, and repeated
# on every container recreation since the cache lives in the container's
# throwaway filesystem) and needs outbound internet at runtime, which
# locked-down mainframe environments often do not allow. HF_HUB_OFFLINE
# then makes a missing/changed model fail fast instead of hanging on
# network retries.
ENV HF_HOME=/opt/hf-cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
ENV HF_HUB_OFFLINE=1

COPY . .

# Non-root runtime user.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/workspace \
    && chown -R appuser:appuser /app /opt/hf-cache
USER appuser

ENV WORKSPACE_DIR=/app/workspace \
    HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000
EXPOSE 8501

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
