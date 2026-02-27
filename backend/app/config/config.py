from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./data/agency.db"
    app_version: str = "0.1.0"
    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
