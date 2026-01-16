#!/bin/sh
set -e

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

log "=== Starting Docker daemon ==="
dockerd-entrypoint.sh > /var/log/dockerd.log 2>&1 &

# Wait for Docker daemon to be ready
log "=== Waiting for Docker daemon ==="
timeout=30
while ! docker info >/dev/null 2>&1; do
    timeout=$((timeout - 1))
    if [ $timeout -le 0 ]; then
        log "ERROR: Docker daemon failed to start"
        cat /var/log/dockerd.log
        exit 1
    fi
    sleep 1
done
log "Docker daemon is ready"

# Create test mount directories inside DinD
mkdir -p /mnt/test-config /mnt/test-data /mnt/test-watch

# Build transctrl image inside DinD
log "=== Building transctrl image ==="
docker build -t transctrl:test .

# Create socket directory on DinD host (shared with transctrl container)
mkdir -p /var/run/transctrl

# Run transctrl container inside DinD
# Note: Running as root to access docker socket in DinD test environment
log "=== Starting transctrl container ==="
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
log "=== Waiting for transctrl server ==="
timeout=30
while [ ! -S /var/run/transctrl/transctrl.sock ]; do
    timeout=$((timeout - 1))
    if [ $timeout -le 0 ]; then
        log "ERROR: transctrl server failed to start"
        docker logs transctrl-server
        exit 1
    fi
    sleep 1
done
log "transctrl server is ready"

# Run integration tests from test runner (uses apk python with py3-grpcio)
log "=== Running integration tests ==="
cd /app
PYTHONPATH=/app python3 -m pytest tests/integration -v -s --tb=short
TEST_EXIT_CODE=$?

log "=== Cleaning up ==="
if [ $(docker ps -q -f name=transctrl-server) ]; then
    log "Stopping transctrl-server..."
    docker stop transctrl-server
fi
if [ $(docker ps -aq -f name=transctrl-server) ]; then
    log "Removing transctrl-server..."
    docker rm transctrl-server
fi

# Check for any leftover transmission containers
LEFTOVER=$(docker ps -a --filter "name=transmission-" --format "{{.ID}} {{.Names}}")
if [ ! -z "$LEFTOVER" ]; then
    log "WARNING: Leftover transmission containers found (should have been cleaned by tests):"
    echo "$LEFTOVER"
    log "Force removing leftovers..."
    docker rm -f $(echo "$LEFTOVER" | awk '{print $1}')
else
    log "No leftover transmission containers found."
fi

exit $TEST_EXIT_CODE
