import logging
from typing import List, Dict, Set
from .docker_client import DockerClient
from .config import settings

logger = logging.getLogger(__name__)

class Reconciler:
    def __init__(self, docker_client: DockerClient):
        self.docker_client = docker_client

    def reconcile(self, desired_instances: List) -> Dict:
        """
        Reconcile desired state with actual state.
        
        desired_instances: List of InstanceSpec objects
        """
        results = {
            "instances": [],
            "created_count": 0,
            "destroyed_count": 0,
            "unchanged_count": 0,
            "recreated_count": 0,
            "errors": []
        }
        
        try:
            # 1. Get all currently managed containers
            existing_containers = self.docker_client.list_managed_containers()
            existing_map = {c.labels.get("transctrl.instance-id"): c for c in existing_containers}
            
            desired_ids = {spec.id for spec in desired_instances}
            
            # 2. Identify actions
            to_destroy = [c for id, c in existing_map.items() if id not in desired_ids]
            to_create = []
            to_recreate = []
            to_keep = []
            
            for spec in desired_instances:
                if spec.id not in existing_map:
                    to_create.append(spec)
                else:
                    container = existing_map[spec.id]
                    if self._needs_recreation(container, spec):
                        to_recreate.append(spec)
                        to_destroy.append(container)
                    else:
                        to_keep.append(spec)
            
            # 3. Execute actions (Best effort)
            
            # Destroy
            for container in to_destroy:
                try:
                    instance_id = container.labels.get("transctrl.instance-id")
                    logger.info(f"Destroying container for instance {instance_id}")
                    self.docker_client.remove_container(container)
                    results["destroyed_count"] += 1
                except Exception as e:
                    results["errors"].append(f"Failed to destroy {instance_id}: {e}")
            
            # Create / Recreate
            for spec in to_create + to_recreate:
                try:
                    logger.info(f"Creating container for instance {spec.id}")
                    # Path validation should happen here if not already done in the server layer
                    self._validate_spec(spec)
                    
                    container = self.docker_client.create_container(spec)
                    # Note: In a real implementation, we'd map this back to InstanceStatus
                    results["created_count"] += 1
                    if spec in to_recreate:
                        results["recreated_count"] += 1
                except Exception as e:
                    results["errors"].append(f"Failed to create {spec.id}: {e}")
            
            # Mark unchanged
            results["unchanged_count"] = len(to_keep)
            
            return results
            
        except Exception as e:
            logger.error(f"Reconciliation loop failed: {e}")
            results["errors"].append(f"Global reconciliation error: {e}")
            return results

    def _needs_recreation(self, container, spec) -> bool:
        """Check if container configuration differs from spec."""
        # Check volumes
        mounts = {m["Destination"]: m["Source"] for m in container.attrs.get("Mounts", [])}
        if mounts.get("/config") != spec.config_path: return True
        if mounts.get("/downloads") != spec.data_path: return True
        if mounts.get("/watch") != spec.watch_path: return True
        
        # Check ports
        port_bindings = container.attrs.get("HostConfig", {}).get("PortBindings", {})
        web_binding = port_bindings.get("9091/tcp", [])
        data_binding = port_bindings.get("51413/tcp", [])
        
        if not web_binding or int(web_binding[0].get("HostPort")) != spec.web_port: return True
        if not data_binding or int(data_binding[0].get("HostPort")) != spec.data_port: return True
        
        # Check image tag
        image_name = container.image.tags[0] if container.image.tags else ""
        desired_image = f"linuxserver/transmission:{spec.image_tag or 'latest'}"
        if image_name and image_name != desired_image: return True
        
        # Check resource limits (simplified)
        host_config = container.attrs.get("HostConfig", {})
        if host_config.get("Memory") != self._parse_memory(spec.resource_limits.memory or settings.DEFAULT_MEM_LIMIT): return True
        if host_config.get("CpuQuota") != (spec.resource_limits.cpu_quota or settings.DEFAULT_CPU_QUOTA): return True
        
        return False

    def _validate_spec(self, spec):
        """Validate instance spec against security requirements."""
        # 1. Path validation
        for path_attr in ["config_path", "data_path", "watch_path"]:
            path = getattr(spec, path_attr)
            if not os.path.isabs(path):
                raise ValueError(f"{path_attr} must be an absolute path: {path}")
            if not path.startswith(settings.ALLOWED_MOUNT_BASE):
                raise ValueError(f"{path_attr} must be under {settings.ALLOWED_MOUNT_BASE}: {path}")
            if not os.path.exists(path):
                raise ValueError(f"{path_attr} does not exist: {path}")

        # 2. Port validation
        if not (1024 <= spec.web_port <= 65535):
            raise ValueError(f"web_port out of range: {spec.web_port}")
        if not (1024 <= spec.data_port <= 65535):
            raise ValueError(f"data_port out of range: {spec.data_port}")
        if spec.web_port == spec.data_port:
            raise ValueError("web_port and data_port must be different")

        # 3. ID validation
        import re
        if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", spec.id) or spec.id.startswith("-"):
            raise ValueError(f"Invalid instance ID: {spec.id}")

    def _parse_memory(self, mem_str: str) -> int:
        """Parse memory string (e.g., 512m) to bytes."""
        units = {"k": 1024, "m": 1024**2, "g": 1024**3}
        unit = mem_str[-1].lower()
        if unit in units:
            return int(mem_str[:-1]) * units[unit]
        return int(mem_str)
import os
