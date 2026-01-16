import docker
import logging
from typing import List, Dict, Optional
from datetime import datetime
from .config import settings

logger = logging.getLogger(__name__)

class DockerClient:
    def __init__(self):
        self.client = docker.DockerClient(base_url=settings.DOCKER_HOST)

    def list_managed_containers(self) -> List[docker.models.containers.Container]:
        """List all containers managed by transctrl."""
        return self.client.containers.list(
            all=True,
            filters={"label": "transctrl.managed=true"}
        )

    def get_container_by_id(self, instance_id: str) -> Optional[docker.models.containers.Container]:
        """Get a managed container by its instance-id label."""
        containers = self.client.containers.list(
            all=True,
            filters={
                "label": [
                    "transctrl.managed=true",
                    f"transctrl.instance-id={instance_id}"
                ]
            }
        )
        return containers[0] if containers else None

    def create_container(self, spec) -> docker.models.containers.Container:
        """Create a new Transmission container based on spec."""
        instance_id = spec.id
        name = f"transctrl-{instance_id}"
        
        # Validation should have happened before this call
        volumes = {
            spec.config_path: {"bind": "/config", "mode": "rw"},
            spec.data_path: {"bind": "/downloads", "mode": "rw"},
            spec.watch_path: {"bind": "/watch", "mode": "rw"},
        }
        
        ports = {
            "9091/tcp": spec.web_port,
            "51413/tcp": spec.data_port,
        }
        
        labels = {
            "transctrl.managed": "true",
            "transctrl.instance-id": instance_id,
            "transctrl.created-at": datetime.now().isoformat(),
        }
        
        mem_limit = spec.resource_limits.memory if spec.resource_limits.memory else settings.DEFAULT_MEM_LIMIT
        cpu_quota = spec.resource_limits.cpu_quota if spec.resource_limits.cpu_quota > 0 else settings.DEFAULT_CPU_QUOTA
        
        image_tag = spec.image_tag or "latest"
        image = f"linuxserver/transmission:{image_tag}"
        
        try:
            # Drop ALL capabilities, add only those needed
            # "cap_drop": ["ALL"],
            # "cap_add": ["CHOWN", "SETGID", "SETUID"],
            # security_opt=["no-new-privileges=true"]
            
            container = self.client.containers.run(
                image,
                name=name,
                detach=True,
                volumes=volumes,
                ports=ports,
                labels=labels,
                environment={
                    "PUID": "1000",
                    "PGID": "1000",
                    "TZ": "UTC",
                },
                restart_policy={"Name": "unless-stopped"},
                mem_limit=mem_limit,
                cpu_quota=cpu_quota,
                cap_drop=["ALL"],
                cap_add=["CHOWN", "SETGID", "SETUID"],
                security_opt=["no-new-privileges=true"],
                network_mode="bridge"
            )
            return container
        except Exception as e:
            logger.error(f"Failed to create container {name}: {e}")
            raise

    def remove_container(self, container: docker.models.containers.Container):
        """Remove a managed container."""
        if container.labels.get("transctrl.managed") != "true":
            raise ValueError(f"Container {container.id} is not managed by transctrl")
        
        try:
            container.stop(timeout=10)
            container.remove(force=True)
        except Exception as e:
            logger.error(f"Failed to remove container {container.name}: {e}")
            raise
