# transctrl

A secure service that manages Transmission Docker containers declaratively via gRPC over Unix sockets.

## Quick Start

```bash
# Install dependencies & generate gRPC code
uv sync
make proto

# Start server (requires Docker socket access)
export SOCKET_PATH=/tmp/transctrl.sock
uv run src/server.py
```

Or using Docker Compose:
```bash
docker-compose up -d
```

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `SOCKET_PATH` | `/var/run/transctrl/transctrl.sock` | Path to Unix socket |
| `DOCKER_HOST` | `unix:///var/run/docker.sock` | Docker daemon address |
| `ALLOWED_MOUNT_BASE` | `/mnt` | Only allow mounts under this path |
| `RATE_LIMIT_REQUESTS` | `10` | Max reconciles per window |
| `RATE_LIMIT_WINDOW` | `60` | Rate limit window in seconds |

## API Example

```python
from client.transctrl_client import TransmissionControllerClient

client = TransmissionControllerClient('/tmp/transctrl.sock')

# Reconcile desired state
result = client.reconcile([
    {
        'id': 'user-1',
        'config_path': '/mnt/configs/user-1',
        'data_path': '/mnt/data/user-1',
        'watch_path': '/mnt/watch/user-1',
        'web_port': 9091,
        'data_port': 51413
    }
])

# Get current status
status = client.get_status()
```

## Development

### Prerequisites

- [uv](https://github.com/astral-sh/uv)
- Docker
- Make

### Local Setup

```bash
# Install dependencies
uv sync

# Generate gRPC code
make proto
```

### Running Tests

```bash
make test
```

### Building Docker Image

```bash
make build-image
```

## Security Design

- **Stateless**: The system relies on Docker labels (`transctrl.managed=true`) as the source of truth.
- **Isolation**: Minimal capabilities (CHOWN, SETGID, SETUID) and `no-new-privileges` for containers.
- **Path Restriction**: Only allows mounting host paths under a pre-configured base directory.
- **Socket Communication**: Uses gRPC over Unix sockets for local, secure inter-process communication.
