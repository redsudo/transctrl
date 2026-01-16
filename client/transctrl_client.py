import grpc
from typing import List, Dict, Optional
import sys
import os

# Add parent directory to path to allow importing from generated code if needed
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/../src")

import transctrl_pb2
import transctrl_pb2_grpc

class TransmissionControllerClient:
    def __init__(self, socket_path: str = "/var/run/transctrl/transctrl.sock"):
        self.channel = grpc.insecure_channel(f"unix:{socket_path}")
        self.stub = transctrl_pb2_grpc.TransmissionControllerStub(self.channel)

    def reconcile(self, desired_instances: List[Dict]) -> transctrl_pb2.ReconcileResult:
        instances = []
        for item in desired_instances:
            limits = None
            if "resource_limits" in item:
                limits = transctrl_pb2.ResourceLimits(
                    memory=item["resource_limits"].get("memory"),
                    cpu_quota=item["resource_limits"].get("cpu_quota")
                )
            
            spec = transctrl_pb2.InstanceSpec(
                id=item["id"],
                config_path=item["config_path"],
                data_path=item["data_path"],
                watch_path=item["watch_path"],
                web_port=item["web_port"],
                data_port=item["data_port"],
                image_tag=item.get("image_tag"),
                resource_limits=limits
            )
            instances.append(spec)
            
        request = transctrl_pb2.DesiredState(instances=instances)
        return self.stub.Reconcile(request)

    def get_status(self) -> List[transctrl_pb2.InstanceStatus]:
        response = self.stub.GetStatus(transctrl_pb2.Empty())
        return list(response.instances)

    def get_instance(self, instance_id: str) -> Optional[transctrl_pb2.InstanceStatus]:
        try:
            return self.stub.GetInstance(transctrl_pb2.InstanceId(id=instance_id))
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return None
            raise
