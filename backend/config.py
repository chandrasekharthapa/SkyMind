"""
SkyMind — Application Configuration
All settings loaded from environment variables (Pydantic V2 BaseSettings).
"""

from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────────────
    app_name: str = "SkyMind"
    debug: bool = False
    secret_key: str = "change-me-in-production"

    # ── Database ──────────────────────────────────────────────────────
    database_url: str = ""
    supabase_url: str = ""
    supabase_service_key: str = ""

    # ── Redis ─────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379"

    # ── Flight APIs ───────────────────────────────────────────────────
    # Amadeus (both naming conventions accepted)
    amadeus_client_id: str = ""
    amadeus_client_secret: str = ""
    amadeus_api_key: str = ""           # alias
    amadeus_api_secret: str = ""        # alias
    amadeus_base_url: str = "https://test.api.amadeus.com"

    aviationstack_api_key: str = ""

    # ── Payment ───────────────────────────────────────────────────────
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""

    # ── ML ────────────────────────────────────────────────────────────
    model_path: str = "./ml/models"

    # ── Email (Gmail SMTP) ────────────────────────────────────────────
    gmail_user: str = ""
    gmail_app_password: str = ""
    email_from_name: str = "SkyMind Flights"
    email_reply_to: str = ""

    # ── SMS / Notifications ───────────────────────────────────────────
    fast2sms_api_key: str = ""
    sms_sender_id: str = "SKYMND"

    # ── Twilio ────────────────────────────────────────────────────────
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    twilio_whatsapp_number: str = "whatsapp:+14155238886"

    # ── CORS ──────────────────────────────────────────────────────────
    # Comma-separated extra origins injected at deploy time
    cors_origins: str = ""

    @field_validator("amadeus_api_key")
    @classmethod
    def coalesce_amadeus_key(cls, v: str, info) -> str:  # noqa: ANN001
        """If amadeus_api_key not set but amadeus_client_id is, use that."""
        if not v:
            client_id = info.data.get("amadeus_client_id", "")
            return client_id or v
        return v

    @field_validator("amadeus_api_secret")
    @classmethod
    def coalesce_amadeus_secret(cls, v: str, info) -> str:
        if not v:
            client_secret = info.data.get("amadeus_client_secret", "")
            return client_secret or v
        return v

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
