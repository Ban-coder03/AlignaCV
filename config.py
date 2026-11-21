"""Configuración de la aplicación.

Toda la configuración (incluida la API key) se lee EXCLUSIVAMENTE de variables de
entorno. En desarrollo se cargan desde un archivo `.env` (nunca versionado) con
python-dotenv; las variables ya definidas en el entorno tienen prioridad sobre el `.env`.
"""

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv(override=False)

logger = logging.getLogger("cv_analyzer.config")

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
_TRUE = {"1", "true", "yes", "on", "si", "sí"}
_PLACEHOLDER_MARKERS = ("replace", "your_", "your-", "xxxx", "changeme", "<")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in _TRUE


def _env_number(name: str, default: float, minimum: float, maximum: float, cast=float):
    """Lee un número del entorno; si es inválido usa el valor por defecto (y avisa en el log)."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = cast(raw.strip())
    except ValueError:
        logger.warning("Variable %s inválida; se usa el valor por defecto (%s).", name, default)
        return default
    if not minimum <= value <= maximum:
        logger.warning("Variable %s fuera de rango [%s, %s]; se usa el valor por defecto (%s).", name, minimum, maximum, default)
        return default
    return value


def _clean_api_key(raw: str | None) -> str | None:
    """Devuelve la clave limpia o None si falta o es un valor de plantilla (p. ej. copiado de .env.example)."""
    if not raw:
        return None
    key = raw.strip().strip("'\"")
    if not key or any(marker in key.lower() for marker in _PLACEHOLDER_MARKERS):
        return None
    return key


@dataclass(frozen=True)
class Settings:
    use_mock_ai: bool
    anthropic_api_key: str | None
    anthropic_model: str
    ai_timeout_seconds: float          # timeout de CADA llamada al proveedor
    ai_total_timeout_seconds: float    # tope total de la petición (incluye reintentos)
    ai_sdk_retries: int                # reintentos de red/429/5xx del SDK
    ai_output_retries: int             # reintentos cuando el modelo devuelve una salida mal formada
    ai_max_output_tokens: int
    ai_temperature: float | None       # None = se omite el parámetro
    cors_origins: tuple[str, ...]
    max_upload_bytes: int
    rate_limit_per_minute: int         # 0 = desactivado
    ai_provider: str = "anthropic"     # "anthropic" | "gemini"
    gemini_api_key: str | None = None
    gemini_model: str = DEFAULT_GEMINI_MODEL

    @property
    def active_api_key(self) -> str | None:
        return self.gemini_api_key if self.ai_provider == "gemini" else self.anthropic_api_key

    @property
    def active_model(self) -> str:
        return self.gemini_model if self.ai_provider == "gemini" else self.anthropic_model

    @property
    def ai_configured(self) -> bool:
        return self.use_mock_ai or self.active_api_key is not None


def get_settings() -> Settings:
    """Construye la configuración desde el entorno (barato: se puede llamar en cada petición)."""
    origins_raw = os.getenv("CORS_ORIGINS", "*")
    origins = tuple(o.strip() for o in origins_raw.split(",") if o.strip()) or ("*",)
    temperature_raw = os.getenv("AI_TEMPERATURE", "").strip()
    temperature = None
    if temperature_raw:
        temperature = _env_number("AI_TEMPERATURE", 0.2, 0.0, 1.0)

    provider = (os.getenv("AI_PROVIDER") or "anthropic").strip().lower()
    if provider not in ("anthropic", "gemini"):
        logger.warning("AI_PROVIDER inválido (%r); se usa 'anthropic'.", provider)
        provider = "anthropic"

    return Settings(
        ai_provider=provider,
        gemini_api_key=_clean_api_key(os.getenv("GEMINI_API_KEY")),
        gemini_model=(os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL).strip(),
        use_mock_ai=_env_bool("USE_MOCK_AI", False),
        anthropic_api_key=_clean_api_key(os.getenv("ANTHROPIC_API_KEY")),
        anthropic_model=(os.getenv("ANTHROPIC_MODEL") or DEFAULT_MODEL).strip(),
        ai_timeout_seconds=_env_number("AI_TIMEOUT_SECONDS", 60.0, 5.0, 600.0),
        ai_total_timeout_seconds=_env_number("AI_TOTAL_TIMEOUT_SECONDS", 150.0, 10.0, 900.0),
        ai_sdk_retries=_env_number("AI_SDK_RETRIES", 2, 0, 5, cast=int),
        ai_output_retries=_env_number("AI_OUTPUT_RETRIES", 2, 0, 4, cast=int),
        ai_max_output_tokens=_env_number("AI_MAX_OUTPUT_TOKENS", 4096, 1024, 32000, cast=int),
        ai_temperature=temperature,
        cors_origins=origins,
        max_upload_bytes=int(_env_number("MAX_UPLOAD_MB", 5, 1, 25, cast=int)) * 1024 * 1024,
        rate_limit_per_minute=_env_number("RATE_LIMIT_PER_MINUTE", 20, 0, 10000, cast=int),
    )