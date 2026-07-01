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
    gemini_fallback_model: str = "gemini-2.5-flash-lite"
    gemini_validator_model: str = "gemini-2.5-flash"
    # Probing questions run on the lighter model to keep per-turn latency low; the
    # heavier gemini_model stays their fallback. Override via GEMINI_QUESTION_MODEL.
    gemini_question_model: str = "gemini-2.5-flash-lite"
    cors_origins: str = "http://localhost:5173"


settings = Settings()
