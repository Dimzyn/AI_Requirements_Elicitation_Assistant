import secrets

from ..config import settings


def new_token() -> str:
    return secrets.token_urlsafe(32)


def accept_url_for(token: str, base: str | None = None) -> str:
    origin = base or settings.cors_origins.split(",")[0].strip()
    return f"{origin}/invite/{token}"
