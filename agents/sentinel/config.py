from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    gemini_api_key: SecretStr
    groq_api_key: SecretStr
    gemini_model: str = "gemini-3.8-flash"
    groq_model: str = "GROQ_MODEL=openai/gpt-oss-120b"