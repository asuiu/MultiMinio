from abc import ABC
from os import getenv
from pathlib import Path

ROOT = Path(__file__).parent.absolute()


class BaseConfig(ABC):
    MINIO_PUBLIC_SERVER1 = getenv(
        "MINIO_PUBLIC_SERVER",
    )
    MINIO_REGION1 = getenv("MINIO_REGION", "custom")
    MINIO_ACCESS_KEY1 = getenv("MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY1 = getenv("MINIO_SECRET_KEY")

    MINIO_PUBLIC_SERVER2 = getenv(
        "MINIO_PUBLIC_SERVER",
    )
    MINIO_REGION2 = getenv("MINIO_REGION", "custom")
    MINIO_ACCESS_KEY2 = getenv("MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY2 = getenv("MINIO_SECRET_KEY")
