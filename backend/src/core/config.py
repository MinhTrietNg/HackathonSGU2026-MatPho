"""
Application Configuration Settings for Mắt Phố Backend
"""

import os
import json
from pathlib import Path
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Resolve project paths
BACKEND_DIR = Path(__file__).resolve().parents[2]
env_path = BACKEND_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()


class Settings(BaseSettings):
    PROJECT_NAME: str = "Mắt Phố - AI Surveillance & Fire Emergency API"
    VERSION: str = "1.2.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    API_V1_STR: str = "/api/v1"

    # Security & Keys
    INTERNAL_API_SECRET_KEY: str = os.getenv(
        "INTERNAL_API_SECRET_KEY", "secure_internal_key_for_ai_and_worker_communication"
    )
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "matpho_jwt_secret_for_emergency_tokens_12345")

    # Firebase & Storage
    FIREBASE_STORAGE_BUCKET: str = os.getenv(
        "FIREBASE_STORAGE_BUCKET", "matpho-c7e77.firebasestorage.app"
    )
    FIREBASE_CREDENTIALS_PATH: str = os.getenv(
        "FIREBASE_CREDENTIALS_PATH", "credentials/firebase-service-account.json"
    )

    # Redis & State Cache (Upstash Cloud Redis with TLS by default)
    REDIS_URL: str = os.getenv(
        "REDIS_URL",
        "rediss://default:gQAAAAAAAvH2AAIgcDI3Mzg5YjhlYzNhODc0MTJhOWIyNDg2NmIwNmJmMWI0YQ@integral-osprey-193014.upstash.io:6379",
    )

    # MediaMTX
    MEDIAMTX_API_URL: str = os.getenv("MEDIAMTX_API_URL", "http://localhost:9997")
    MEDIAMTX_HLS_BASE_URL: str = os.getenv("MEDIAMTX_HLS_BASE_URL", "http://localhost:8888")

    # CORS
    CORS_ORIGINS: List[str] = ["*"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return ["*"]

    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")


settings = Settings()
