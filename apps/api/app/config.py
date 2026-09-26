from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../../.env"), extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    gemini_api_key: SecretStr
    groq_api_key: SecretStr

settings = Settings()

