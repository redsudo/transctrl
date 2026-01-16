"""
Integration tests for transctrl container lifecycle management.

These tests run against a real Docker daemon (via DinD) and test:
- Container creation via Reconcile
- Status fetching via GetStatus
- Container destruction
- Recreation on config changes
"""

import pytest
import time
import grpc
import sys
import os

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from src import transctrl_pb2
from src import transctrl_pb2_grpc


SOCKET_PATH = "/var/run/transctrl/transctrl.sock"


@pytest.fixture
def client():
    """Create a gRPC client connected to the transctrl server."""
    channel = grpc.insecure_channel(f"unix:{SOCKET_PATH}")
    stub = transctrl_pb2_grpc.TransmissionControllerStub(channel)
    yield stub
    channel.close()


@pytest.fixture
def clean_state(client):
    """Ensure no managed containers exist before/after test."""
    # Clean before
    client.Reconcile(transctrl_pb2.DesiredState(instances=[]))
    yield
    # Clean after - destroy any containers created during test
    client.Reconcile(transctrl_pb2.DesiredState(instances=[]))


def create_instance_spec(
    instance_id: str,
    web_port: int = 19091,
    data_port: int = 61413,
    image_tag: str = "latest"
) -> transctrl_pb2.InstanceSpec:
    """Helper to create an InstanceSpec with test paths."""
    return transctrl_pb2.InstanceSpec(
        id=instance_id,
        config_path="/mnt/test-config",
        data_path="/mnt/test-data",
        watch_path="/mnt/test-watch",
        web_port=web_port,
        data_port=data_port,
        image_tag=image_tag,
        resource_limits=transctrl_pb2.ResourceLimits(
            memory="256m",
            cpu_quota=25000
        )
    )


class TestContainerCreation:
    """Tests for creating containers via Reconcile."""

    def test_create_single_container(self, client, clean_state):
        """Reconcile with one instance should create one container."""
        spec = create_instance_spec("test-create-1")
        request = transctrl_pb2.DesiredState(instances=[spec])

        result = client.Reconcile(request)

        assert result.created_count == 1
        assert result.destroyed_count == 0
        assert result.unchanged_count == 0
        assert len(result.errors) == 0

    def test_create_multiple_containers(self, client, clean_state):
        """Reconcile with multiple instances should create all containers."""
        specs = [
            create_instance_spec("test-multi-1", web_port=19091, data_port=61413),
            create_instance_spec("test-multi-2", web_port=19092, data_port=61414),
        ]
        request = transctrl_pb2.DesiredState(instances=specs)

        result = client.Reconcile(request)

        assert result.created_count == 2
        assert result.destroyed_count == 0
        assert len(result.errors) == 0


class TestContainerStatus:
    """Tests for GetStatus and GetInstance."""

    def test_get_status_returns_running_container(self, client, clean_state):
        """GetStatus should return info about running containers."""
        spec = create_instance_spec("test-status-1")
        client.Reconcile(transctrl_pb2.DesiredState(instances=[spec]))
        
        # Give container a moment to start
        time.sleep(2)

        status = client.GetStatus(transctrl_pb2.Empty())

        assert len(status.instances) == 1
        instance = status.instances[0]
        assert instance.id == "test-status-1"
        assert instance.status == transctrl_pb2.RUNNING or instance.status == transctrl_pb2.CREATING
        assert instance.actual_web_port == 19091
        assert instance.actual_data_port == 61413

    def test_get_instance_by_id(self, client, clean_state):
        """GetInstance should return specific container info."""
        spec = create_instance_spec("test-get-1")
        client.Reconcile(transctrl_pb2.DesiredState(instances=[spec]))
        time.sleep(1)

        instance = client.GetInstance(transctrl_pb2.InstanceId(id="test-get-1"))

        assert instance.id == "test-get-1"
        assert instance.container_id != ""

    def test_get_instance_not_found(self, client, clean_state):
        """GetInstance for non-existent ID should return NOT_FOUND."""
        with pytest.raises(grpc.RpcError) as exc_info:
            client.GetInstance(transctrl_pb2.InstanceId(id="nonexistent"))
        
        assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND


class TestContainerDestruction:
    """Tests for destroying containers via Reconcile."""

    def test_destroy_container_by_removing_from_desired(self, client, clean_state):
        """Removing an instance from desired state should destroy it."""
        # First create a container
        spec = create_instance_spec("test-destroy-1")
        client.Reconcile(transctrl_pb2.DesiredState(instances=[spec]))
        time.sleep(1)

        # Verify it exists
        status = client.GetStatus(transctrl_pb2.Empty())
        assert len(status.instances) == 1

        # Reconcile with empty list should destroy it
        result = client.Reconcile(transctrl_pb2.DesiredState(instances=[]))

        assert result.destroyed_count == 1
        assert result.created_count == 0

        # Verify it's gone
        status = client.GetStatus(transctrl_pb2.Empty())
        assert len(status.instances) == 0


class TestContainerRecreation:
    """Tests for recreating containers when config changes."""

    def test_recreate_on_port_change(self, client, clean_state):
        """Changing port should trigger recreation."""
        # Create initial container
        spec1 = create_instance_spec("test-recreate-1", web_port=19091)
        client.Reconcile(transctrl_pb2.DesiredState(instances=[spec1]))
        time.sleep(1)

        # Change the port
        spec2 = create_instance_spec("test-recreate-1", web_port=19099)
        result = client.Reconcile(transctrl_pb2.DesiredState(instances=[spec2]))

        # recreated_count is incremented, and since recreation involves destroy+create,
        # those counts are also incremented (this is implementation-specific)
        assert result.recreated_count == 1

        # Verify new port
        status = client.GetStatus(transctrl_pb2.Empty())
        assert len(status.instances) == 1
        assert status.instances[0].actual_web_port == 19099

    def test_unchanged_when_same_config(self, client, clean_state):
        """Same config should not trigger recreation."""
        spec = create_instance_spec("test-unchanged-1")
        
        # First reconcile creates
        client.Reconcile(transctrl_pb2.DesiredState(instances=[spec]))
        time.sleep(1)

        # Second reconcile with same config should be unchanged
        result = client.Reconcile(transctrl_pb2.DesiredState(instances=[spec]))

        assert result.unchanged_count == 1
        assert result.created_count == 0
        assert result.destroyed_count == 0
        assert result.recreated_count == 0
