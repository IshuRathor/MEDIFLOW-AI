import os

from dotenv import load_dotenv


load_dotenv()


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./hospital.db"
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()
REDIS_URL = os.getenv("REDIS_URL", "").strip() or None

_configured_jwt_secret = os.getenv("JWT_SECRET_KEY")
JWT_SECRET_KEY = (
    _configured_jwt_secret
    if _configured_jwt_secret
    else (
        None
        if ENVIRONMENT == "production"
        else "change-this-development-secret"
    )
)

ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
)

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    if origin.strip()
]


def validate_startup_config() -> None:
    if ENVIRONMENT == "production":
        if not JWT_SECRET_KEY or JWT_SECRET_KEY == "change-this-development-secret":
            raise RuntimeError("JWT_SECRET_KEY must be configured in production")
        if len(JWT_SECRET_KEY) < 32:
            raise RuntimeError("JWT_SECRET_KEY must contain at least 32 characters")
        if not CORS_ORIGINS:
            raise RuntimeError("CORS_ORIGINS must be explicitly configured in production")