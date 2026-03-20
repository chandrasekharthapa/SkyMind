"""
Application configuration loaded from environment variables.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "SkyMind"
    debug: bool = False
    secret_key: str = "change-me-in-production"

    # Database
    database_url: str = ""
    supabase_url: str = ""
    supabase_service_key: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Flight APIs
    amadeus_client_id: str = ""
    amadeus_client_secret: str = ""
    amadeus_base_url: str = "https://test.api.amadeus.com"
    aviationstack_api_key: str = ""

    # Payment
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""

    # ML
    model_path: str = "./ml/models"

    # Email — Gmail SMTP
    gmail_user: str = ""
    gmail_app_password: str = ""
    email_from_name: str = "SkyMind Flights"
    email_reply_to: str = ""

    # SMS — Fast2SMS
    fast2sms_api_key: str = ""
    sms_sender_id: str = "SKYMND"

    # WhatsApp + Intl SMS — Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    twilio_whatsapp_number: str = "whatsapp:+14155238886"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()