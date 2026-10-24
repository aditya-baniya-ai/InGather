from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    model_api_key: str = ""
    meta_model: str = "muse-spark-1.3"
    meta_image_model: str = "muse-image-1.0"
    meta_voice_model: str = "muse-voice-transcribe-1.0"
    meta_model_base_url: str = "https://api.meta.ai/v1"
    meta_model_timeout_seconds: int = 60
    agent_max_tool_rounds: int = 6
    agent_max_candidates: int = 12
    agent_reasoning_effort: str = "low"  # minimal|low|medium|high; low keeps live demos snappy

    app_env: str = "development"
    demo_mode: bool = True
    allow_real_world_meetups: bool = False
    enable_stranger_discovery: bool = False
    enable_real_identity_verification: bool = False
    stripe_secret_key: str = ""  # sk_test_... enables Stripe Identity
    stripe_webhook_secret: str = ""  # whsec_... verifies Stripe webhooks
    public_base_url: str = "http://localhost:8000"  # where Stripe returns the user after verification
    jwt_secret: str = "dev-only-secret-change-me"
    jwt_ttl_minutes: int = 60 * 24
    cors_origins: str = "http://localhost:5173,http://localhost:8000"
    database_url: str = "sqlite:///./ingather.db"
    media_dir: str = "./media"
    static_dir: str = "../frontend/dist"

    @property
    def ai_live(self) -> bool:
        return bool(self.model_api_key)

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
