# Build stage
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies separately to leverage Docker cache
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

COPY proto/ ./proto/
COPY src/ ./src/
COPY pyproject.toml uv.lock ./

# Generate gRPC code and fix imports for module execution
RUN uv run python -m grpc_tools.protoc -I./proto --python_out=./src --grpc_python_out=./src ./proto/transctrl.proto && \
    sed -i 's/^import transctrl_pb2/from . import transctrl_pb2/' ./src/transctrl_pb2_grpc.py

# Final stage
FROM python:3.14-slim-bookworm

WORKDIR /app

# Copy the virtual environment and source code
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH"
ENV SOCKET_PATH=/var/run/transctrl/transctrl.sock
ENV DOCKER_HOST=unix:///var/run/docker.sock
ENV ALLOWED_MOUNT_BASE=/mnt
ENV PYTHONPATH=/app

RUN mkdir -p /var/run/transctrl && chown 1000:1000 /var/run/transctrl

USER 1000:1000

CMD ["python", "-m", "src.server"]
