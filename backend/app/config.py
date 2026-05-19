from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "probing"
    jwt_secret: str = "dev-secret"
    jwt_alg: str = "HS256"
    jwt_ttl_minutes: int = 60
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_validator_model: str = "gemini-2.5-flash"
    cors_origins: str = "http://localhost:5173"


settings = Settings()
