from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./data/agency.db"
    app_version: str = "0.1.0"
    cors_origins: list[str] = ["http://localhost:3000"]
    opencode_base_port: int = 4096
    opencode_base_url: str = "http://localhost:4096"
    step_timeout_seconds: int = 600
    agents_config_path: str = "config/agents.yaml"
    pipelines_config_path: str = "config/pipelines.yaml"


settings = Settings()
