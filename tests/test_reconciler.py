import pytest
from unittest.mock import MagicMock, patch
from src.reconciler import Reconciler
from src.docker_client import DockerClient

@pytest.fixture
def mock_docker_client():
    return MagicMock(spec=DockerClient)

@pytest.fixture
def reconciler(mock_docker_client):
    return Reconciler(mock_docker_client)

def test_reconcile_create_new(reconciler, mock_docker_client):
    # Setup
    mock_docker_client.list_managed_containers.return_value = []
    
    spec = MagicMock()
    spec.id = "test-1"
    spec.config_path = "/mnt/configs/test-1"
    spec.data_path = "/mnt/data/test-1"
    spec.watch_path = "/mnt/watch/test-1"
    spec.web_port = 9091
    spec.data_port = 51413
    spec.image_tag = "latest"
    spec.resource_limits.memory = "512m"
    spec.resource_limits.cpu_quota = 50000
    
    # Mocking os.path.exists to pass validation
    with patch("os.path.exists", return_value=True), \
         patch("os.path.isabs", return_value=True):
        
        result = reconciler.reconcile([spec])
    
    # Assertions
    assert result["created_count"] == 1
    assert result["errors"] == []
    mock_docker_client.create_container.assert_called_once_with(spec)

def test_reconcile_destroy_unwanted(reconciler, mock_docker_client):
    # Setup
    unwanted_container = MagicMock()
    unwanted_container.labels = {"transctrl.instance-id": "old-1", "transctrl.managed": "true"}
    mock_docker_client.list_managed_containers.return_value = [unwanted_container]
    
    result = reconciler.reconcile([])
    
    # Assertions
    assert result["destroyed_count"] == 1
    mock_docker_client.remove_container.assert_called_once_with(unwanted_container)
