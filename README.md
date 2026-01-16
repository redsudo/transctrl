# transctrl

A secure service that manages Transmission Docker containers declaratively via gRPC over Unix sockets.

## Quick Start

Pull the pre-built image and run:

```bash
docker run -d \
  --name transctrl \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v transctrl-socket:/var/run/transctrl \
  -v /mnt:/mnt:ro \
  -e ALLOWED_MOUNT_BASE=/mnt \
  ghcr.io/redsudo/transctrl:latest
```

Your core service can then connect via the Unix socket at `/var/run/transctrl/transctrl.sock`.

For a complete setup, see [examples/docker-compose.yml](examples/docker-compose.yml).

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

client = TransmissionControllerClient('/var/run/transctrl/transctrl.sock')

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

## Deployment

### With Docker Socket Proxy (Recommended)

> **Security Note**: Mounting the Docker socket directly gives transctrl full control over the Docker daemon. For production deployments, use a [Docker socket proxy](https://github.com/Tecnativa/docker-socket-proxy) to restrict API access to only the operations transctrl needs (container create/delete). This limits the blast radius if transctrl is compromised.

See [examples/docker-compose.proxy.yml](examples/docker-compose.proxy.yml) for a complete example.

```yaml
services:
  docker-socket-proxy:
    image: tecnativa/docker-socket-proxy:latest
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    environment:
      CONTAINERS: 1
      POST: 1
      DELETE: 1

  transctrl:
    image: ghcr.io/redsudo/transctrl:latest
    environment:
      DOCKER_HOST: tcp://docker-socket-proxy:2375
      ALLOWED_MOUNT_BASE: /mnt
    volumes:
      - transctrl-socket:/var/run/transctrl
      - /mnt:/mnt:ro
    # No docker.sock mount needed

volumes:
  transctrl-socket:
```

### Docker Compose (without Docker Socket Proxy)

```yaml
services:
  transctrl:
    image: ghcr.io/redsudo/transctrl:latest
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - transctrl-socket:/var/run/transctrl
      - /mnt:/mnt:ro
    environment:
      ALLOWED_MOUNT_BASE: /mnt

  core:
    image: your-core-service
    volumes:
      - transctrl-socket:/var/run/transctrl:ro
    environment:
      TRANSCTRL_SOCKET: /var/run/transctrl/transctrl.sock

volumes:
  transctrl-socket:
```

## Development

### Prerequisites

- [uv](https://github.com/astral-sh/uv)
- Docker
- Make

### Setup

```bash
# Install dependencies
uv sync

# Generate gRPC code
make proto
```

### Running Tests

```bash
# Unit tests
make test

# Integration tests (runs in Docker-in-Docker)
make test-integration
```

### Building Docker Image

```bash
make build-image
```

## Security Design

- **Stateless**: The system relies on Docker labels (`transctrl.managed=true`) as the source of truth.
- **Isolation**: Minimal capabilities (CHOWN, SETGID, SETUID) and `no-new-privileges` for containers.
- **Socket Communication**: Uses gRPC over Unix sockets for local, secure inter-process communication.

### Path Restriction (`ALLOWED_MOUNT_BASE`)

transctrl validates that all paths (`config_path`, `data_path`, `watch_path`) in reconcile requests start with `ALLOWED_MOUNT_BASE`. This prevents a compromised core service from creating Transmission containers with arbitrary host mounts like `/etc` or `/root/.ssh`.

**Why mount `/mnt:/mnt:ro`?**

transctrl needs to verify that requested paths actually exist before creating containers (`os.path.exists()`). Without this mount, transctrl can't see host paths from inside its container. The `:ro` (read-only) mount is sufficient—transctrl only needs to check existence, not write to these paths. The actual read-write mounts are configured via the Docker API when transctrl creates Transmission containers.

**Example**: If `ALLOWED_MOUNT_BASE=/mnt`, a request for `config_path: /etc/passwd` will be rejected, but `config_path: /mnt/user1/config` will be allowed (if the path exists).

