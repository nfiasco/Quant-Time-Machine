# The benchmark image for spikes/host_compare: backend/Dockerfile's steps, plus the store
# baked in at /data/store and bench_app.py as the entry point, so every host runs the
# same bytes. build_context.sh assembles its build context. The store holds Tiingo's
# internal-use prices, so only push this image to a private registry.
FROM python:3.14.7-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

COPY app ./app
COPY spikes/hosting.py ./spikes/hosting.py
COPY bench_app.py ./bench_app.py
COPY store /data/store

ENV PATH="/app/.venv/bin:$PATH" \
    DATA_DIR=/data
EXPOSE 8080
# The shell notes when the container started, for the cold-start breakdown.
CMD ["sh", "-c", "export BENCH_CONTAINER_STARTED=$(date +%s.%N); exec fastapi run bench_app.py --port ${PORT:-8080}"]
