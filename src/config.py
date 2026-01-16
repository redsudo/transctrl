import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SOCKET_PATH: str = "/var/run/transctrl/transctrl.sock"
    DOCKER_HOST: str = "unix:///var/run/docker.sock"
    ALLOWED_MOUNT_BASE: str = "/mnt"
    RATE_LIMIT_REQUESTS: int = 10
    RATE_LIMIT_WINDOW: int = 60
    DEFAULT_MEM_LIMIT: str = "512m"
    DEFAULT_CPU_QUOTA: int = 50000
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"


settings = Settings()
