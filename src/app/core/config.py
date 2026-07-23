## single resolution point for env-derived config. secrets read here only (Identity Firewall).
import os
from functools import cache
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    db_url: str
    demo_password: str
    session_secret: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool


@cache
def get_settings() -> Settings:
    return Settings(
        db_url=os.environ.get("DATABASE_URL", "sqlite:///./sales.db"),
        demo_password=os.environ.get("DEMO_PASSWORD", "demo123"),
        session_secret=os.environ.get("SESSION_SECRET", "dev-only-insecure-secret"),
        minio_endpoint=os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
        minio_access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
        minio_secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
        minio_bucket=os.environ.get("MINIO_BUCKET", "sales-reports"),
        minio_secure=os.environ.get("MINIO_SECURE", "false").lower() == "true",
    )
