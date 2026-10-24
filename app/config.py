"""Application configuration settings.
"""

from functools import lru_cache
import os
from pathlib import Path
from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Application runtime configuration."""
    
    project_name: str = "AffineSurge CT-200 Medical Device QA System"
    version: str = "0.1.0"
    api_v1_str: str = "/api/v1"
    
    # Base directory
    base_dir: Path = Path(__file__).resolve().parent.parent
    
    # Database
    database_url: str = Field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./affinesurge.db")
    )
    
    # File Storage
    storage_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("STORAGE_DIR", "./data/storage"))
    )
    
    # JSON store for LLM outputs
    json_store_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("JSON_STORE_DIR", "./data/json_store"))
    )
    
    # LLM Settings (OpenAI / Gemini / Mock provider)
    llm_provider: str = Field(
        default_factory=lambda: os.getenv("LLM_PROVIDER", "mock")
    )
    llm_model: str = Field(
        default_factory=lambda: os.getenv("LLM_MODEL", "gemini-1.5-pro")
    )
    llm_api_key: str = Field(
        default_factory=lambda: os.getenv("LLM_API_KEY", "")
    )


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    settings = Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.json_store_dir.mkdir(parents=True, exist_ok=True)
    return settings
