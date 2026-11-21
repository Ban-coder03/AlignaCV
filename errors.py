"""Errores controlados de la aplicación.

Cada error tiene un código HTTP, un `code` estable (para que el frontend decida qué mostrar)
y un mensaje seguro: nunca incluye claves, trazas ni el contenido del CV.
"""

from typing import Any


class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"
    default_message: str = "Error interno del servidor."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = details
        self.headers = headers or {}
        super().__init__(self.message)


# ---- Entrada del usuario / archivos -------------------------------------------------------
class InvalidInputError(AppError):
    status_code = 422
    code = "invalid_input"
    default_message = "Los datos enviados no son válidos."


class UnsupportedFileTypeError(AppError):
    status_code = 415
    code = "unsupported_file_type"
    default_message = "Tipo de archivo no soportado. Usa .pdf o .docx."


class FileTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"
    default_message = "El archivo supera el tamaño máximo permitido."


class FileParseError(AppError):
    status_code = 422
    code = "file_parse_error"
    default_message = "No se pudo leer el contenido del archivo."


class RateLimitExceededError(AppError):
    status_code = 429
    code = "rate_limit_exceeded"
    default_message = "Demasiadas peticiones. Inténtalo de nuevo en unos segundos."


# ---- Servicio de IA -------------------------------------------------------------------------
class AIConfigError(AppError):
    status_code = 503
    code = "ai_not_configured"
    default_message = "El servicio de IA no está configurado en el servidor."


class AIAuthError(AppError):
    status_code = 502
    code = "ai_auth_failed"
    default_message = "El proveedor de IA rechazó las credenciales configuradas en el servidor."


class AIRateLimitError(AppError):
    status_code = 429
    code = "ai_rate_limited"
    default_message = "El proveedor de IA está limitando las peticiones. Inténtalo de nuevo en unos segundos."


class AITimeoutError(AppError):
    status_code = 504
    code = "ai_timeout"
    default_message = "El proveedor de IA tardó demasiado en responder. Inténtalo de nuevo."


class AIUpstreamError(AppError):
    status_code = 502
    code = "ai_upstream_error"
    default_message = "El proveedor de IA no está disponible o devolvió un error."


class AIInvalidOutputError(AppError):
    status_code = 502
    code = "ai_invalid_output"
    default_message = "El modelo devolvió una respuesta que no cumple el formato esperado."
