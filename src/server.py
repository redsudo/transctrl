import grpc
import logging
import os
import json
from concurrent import futures
from datetime import datetime
from google.protobuf import timestamp_pb2

from . import transctrl_pb2
from . import transctrl_pb2_grpc
from .config import settings
from .docker_client import DockerClient
from .reconciler import Reconciler
from .rate_limiter import RateLimiter

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger(__name__)

def log_event(event: str, instance_id: str = None, details: dict = None):
    """Log audit events as JSON to stdout."""
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "event": event,
    }
    if instance_id:
        log_data["instance_id"] = instance_id
    if details:
        log_data["details"] = details
    print(json.dumps(log_data))

class TransmissionControllerServicer(transctrl_pb2_grpc.TransmissionControllerServicer):
    def __init__(self):
        self.docker_client = DockerClient()
        self.reconciler = Reconciler(self.docker_client)
        self.rate_limiter = RateLimiter()

    def Reconcile(self, request, context):
        if not self.rate_limiter.is_allowed():
            context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "Rate limit exceeded")

        log_event("reconcile", details={"instance_count": len(request.instances)})
        
        reconcile_results = self.reconciler.reconcile(request.instances)
        
        # Convert results to gRPC message
        response = transctrl_pb2.ReconcileResult(
            created_count=reconcile_results["created_count"],
            destroyed_count=reconcile_results["destroyed_count"],
            unchanged_count=reconcile_results["unchanged_count"],
            recreated_count=reconcile_results["recreated_count"],
            errors=reconcile_results["errors"]
        )
        
        # In a full implementation, we'd query status for each instance to return here
        # For now, let's just return what we have
        return response

    def GetStatus(self, request, context):
        containers = self.docker_client.list_managed_containers()
        instances = []
        for c in containers:
            instances.append(self._container_to_status(c))
        return transctrl_pb2.CurrentState(instances=instances)

    def GetInstance(self, request, context):
        container = self.docker_client.get_container_by_id(request.id)
        if not container:
            context.abort(grpc.StatusCode.NOT_FOUND, f"Instance {request.id} not found")
        return self._container_to_status(container)

    def _container_to_status(self, container) -> transctrl_pb2.InstanceStatus:
        instance_id = container.labels.get("transctrl.instance-id")
        created_at_str = container.labels.get("transctrl.created-at")
        
        status_map = {
            "running": transctrl_pb2.RUNNING,
            "exited": transctrl_pb2.STOPPED,
            "created": transctrl_pb2.CREATING,
            "restarting": transctrl_pb2.CREATING,
            "paused": transctrl_pb2.STOPPED,
        }
        
        port_bindings = container.attrs.get("HostConfig", {}).get("PortBindings", {})
        web_port = int(port_bindings.get("9091/tcp", [{"HostPort": "0"}])[0]["HostPort"])
        data_port = int(port_bindings.get("51413/tcp", [{"HostPort": "0"}])[0]["HostPort"])
        
        status = status_map.get(container.status, transctrl_pb2.ERROR)
        
        created_at = timestamp_pb2.Timestamp()
        if created_at_str:
            try:
                dt = datetime.fromisoformat(created_at_str)
                created_at.FromDatetime(dt)
            except ValueError:
                pass

        return transctrl_pb2.InstanceStatus(
            id=instance_id,
            container_id=container.id,
            status=status,
            created_at=created_at,
            actual_web_port=web_port,
            actual_data_port=data_port
        )

def serve():
    socket_path = settings.SOCKET_PATH
    # Ensure directory exists
    os.makedirs(os.path.dirname(socket_path), exist_ok=True)
    # Remove existing socket if it exists
    if os.path.exists(socket_path):
        os.remove(socket_path)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    transctrl_pb2_grpc.add_TransmissionControllerServicer_to_server(
        TransmissionControllerServicer(), server
    )
    
    # Listen on Unix socket
    server.add_insecure_port(f"unix:{socket_path}")
    
    logger.info(f"Server starting on {socket_path}")
    server.start()
    
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == "__main__":
    serve()
