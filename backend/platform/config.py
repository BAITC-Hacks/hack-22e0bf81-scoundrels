from pathlib import Path
from typing import Literal
from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    app_mode: Literal["scaffold", "live"] = "scaffold"
    openai_api_key: SecretStr | None = None
    openai_router_model: str | None = None
    openai_router_reasoning_effort: str = "low"
    openai_router_compact_output: bool = False
    openai_stt_model: str = "gpt-transcribe"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "marin"
    session_budget_usd: float = 1.0
    run_budget_usd: float = 5.0

    @model_validator(mode="after")
    def validate_live(self):
        if self.app_mode == "live":
            if not self.openai_api_key or not self.openai_api_key.get_secret_value():
                raise ValueError("APP_MODE=live requires OPENAI_API_KEY")
            if self.openai_router_model != "gpt-6-luna":
                raise ValueError("APP_MODE=live currently requires OPENAI_ROUTER_MODEL=gpt-6-luna")
            if self.openai_stt_model not in {"gpt-transcribe", "gpt-4o-mini-transcribe"}:
                raise ValueError("unsupported live STT model")
            if self.openai_tts_model != "gpt-4o-mini-tts":
                raise ValueError("unsupported live TTS model")
            if self.session_budget_usd <= 0 or self.run_budget_usd <= 0:
                raise ValueError("live budgets must be positive")
        return self
