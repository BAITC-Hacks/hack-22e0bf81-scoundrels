from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    # Live mode intentionally fails until provider and budget enforcement are implemented.
    app_mode: Literal["scaffold"] = "scaffold"
