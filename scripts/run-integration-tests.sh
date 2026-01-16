#!/bin/sh
set -e

echo "=== Starting Docker daemon ==="
dockerd-entrypoint.sh &

# Wait for Docker daemon to be ready
echo "=== Waiting for Docker daemon ==="
timeout=30
while ! docker info >/dev/null 2>&1; do
    timeout=$((timeout - 1))
    if [ $timeout -le 0 ]; then
        echo "ERROR: Docker daemon failed to start"
        exit 1
    fi
    sleep 1
done
echo "Docker daemon is ready"

# Create test mount directories inside DinD
mkdir -p /mnt/test-config /mnt/test-data /mnt/test-watch

# Build transctrl image inside DinD
echo "=== Building transctrl image ==="
docker build -t transctrl:test .

# Create socket directory on DinD host (shared with transctrl container)
mkdir -p /var/run/transctrl

# Run transctrl container inside DinD
# Note: Running as root to access docker socket in DinD test environment
echo "=== Starting transctrl container ==="
docker run -d \
    --name transctrl-server \
    --user root \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v /var/run/transctrl:/var/run/transctrl \
    -v /mnt:/mnt:ro \
    -e ALLOWED_MOUNT_BASE=/mnt \
    -e SOCKET_PATH=/var/run/transctrl/transctrl.sock \
    -e LOG_LEVEL=DEBUG \
    -e RATE_LIMIT_REQUESTS=100 \
    transctrl:test

# Wait for server socket to be created
echo "=== Waiting for transctrl server ==="
timeout=30
while [ ! -S /var/run/transctrl/transctrl.sock ]; do
    timeout=$((timeout - 1))
    if [ $timeout -le 0 ]; then
        echo "ERROR: transctrl server failed to start"
        docker logs transctrl-server
        exit 1
    fi
    sleep 1
done
echo "transctrl server is ready"

# Run integration tests from test runner (uses apk python with py3-grpcio)
echo "=== Running integration tests ==="
cd /app
PYTHONPATH=/app python3 -m pytest tests/integration -v --tb=short
TEST_EXIT_CODE=$?

echo "=== Cleaning up ==="
docker stop transctrl-server || true
docker rm transctrl-server || true

exit $TEST_EXIT_CODE
