"""Cliente mínimo de Google Gemini (REST) con salida JSON estructurada.

Solo habla con la API: construye la petición, reintenta errores transitorios (429/5xx/red) y
traduce los fallos a errores controlados. La validación Pydantic y los reintentos por salida
mal formada viven en ai_service.py (compartidos con el proveedor Anthropic).

La clave viaja en la cabecera `x-goog-api-key` (nunca en la URL, para que no aparezca en logs).
"""

import asyncio
import copy
import json
import logging
import time
from typing import Any

from config import Settings
from errors import AIAuthError, AIRateLimitError, AITimeoutError, AIUpstreamError

logger = logging.getLogger("cv_analyzer.gemini")

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_UNSUPPORTED_KEYS = {"title", "default", "$defs", "examples", "minLength", "maxLength", "pattern"}
_format_style = {"value": "response_format"}   # se recuerda cuál formato aceptó la API


def prepare_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Convierte el JSON Schema de Pydantic a un subconjunto que Gemini acepta.

    - Resuelve los `$ref` (inline) porque Gemini no documenta `$defs`/`$ref`.
    - `anyOf: [X, null]` → `type: [X, "null"]`.
    - Elimina claves no soportadas (las longitudes se validan después con Pydantic).
    """
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            target = copy.deepcopy(defs[node["$ref"].rsplit("/", 1)[-1]])
            extra = {k: v for k, v in node.items() if k != "$ref"}
            return walk({**target, **extra})
        if "anyOf" in node:
            options = node["anyOf"]
            non_null = [o for o in options if o.get("type") != "null"]
            if len(non_null) == 1 and len(options) == 2:
                merged = walk(non_null[0])
                merged["type"] = [merged["type"], "null"] if isinstance(merged.get("type"), str) else merged.get("type")
                rest = {k: walk(v) for k, v in node.items() if k != "anyOf" and k not in _UNSUPPORTED_KEYS}
                return {**merged, **rest}
        return {k: walk(v) for k, v in node.items() if k not in _UNSUPPORTED_KEYS}

    return walk(schema)


def _build_body(system: str, contents: list[dict[str, Any]], schema: dict[str, Any], settings: Settings, style: str) -> dict[str, Any]:
    config: dict[str, Any] = {"maxOutputTokens": max(settings.ai_max_output_tokens, 8192)}
    if settings.ai_temperature is not None:
        config["temperature"] = settings.ai_temperature
    if style == "response_format":
        config["responseFormat"] = {"text": {"mimeType": "application/json", "schema": schema}}
    else:  # formato clásico
        config["responseMimeType"] = "application/json"
        config["responseJsonSchema"] = schema
    return {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents, "generationConfig": config}


def _status_error(status: int, text: str) -> Exception:
    low = text.lower()
    if status in (401, 403) or "api_key_invalid" in low or "api key not valid" in low:
        return AIAuthError()
    if status == 429:
        return AIRateLimitError("Se alcanzó el límite del plan gratuito de Gemini. Espera un momento e inténtalo de nuevo.")
    if status == 400:
        return AIUpstreamError("Gemini rechazó la solicitud (revisa GEMINI_MODEL y el tamaño de la entrada).")
    return AIUpstreamError()


def _default_client(settings: Settings) -> Any:
    try:
        import httpx
    except ImportError as exc:
        from errors import AIConfigError
        raise AIConfigError("Falta instalar 'httpx' en el servidor (pip install -r requirements.txt).") from exc
    return httpx.AsyncClient(timeout=settings.ai_timeout_seconds)


async def generate(
    settings: Settings,
    system: str,
    contents: list[dict[str, Any]],
    schema: dict[str, Any],
    deadline: float,
    client: Any = None,
) -> tuple[str, str | None]:
    """Devuelve (texto_json, finish_reason). Lanza errores controlados."""
    own_client = client is None
    client = client or _default_client(settings)
    url = f"{BASE_URL}/{settings.gemini_model}:generateContent"
    headers = {"x-goog-api-key": settings.gemini_api_key or "", "Content-Type": "application/json"}
    try:
        attempt = 0
        style = _format_style["value"]
        while True:
            attempt += 1
            if time.monotonic() >= deadline:
                raise AITimeoutError()
            body = _build_body(system, contents, schema, settings, style)
            try:
                resp = await client.post(url, headers=headers, json=body)
            except Exception as exc:  # noqa: BLE001
                names = {c.__name__ for c in type(exc).__mro__}
                if "TimeoutException" in names:
                    error: Exception = AITimeoutError()
                else:
                    error = AIUpstreamError()
                logger.warning("Fallo de red con Gemini (%s)", type(exc).__name__)
                if attempt > settings.ai_sdk_retries:
                    raise error from None
                await asyncio.sleep(min(2 ** (attempt - 1), 4))
                continue

            status = resp.status_code
            if status == 200:
                return _extract_text(resp)
            text = (getattr(resp, "text", "") or "")[:2000]
            if status == 400 and style == "response_format" and any(k in text for k in ("responseFormat", "Unknown name", "Invalid JSON payload")):
                logger.info("Gemini no acepta 'responseFormat'; se usa el formato clásico.")
                style = _format_style["value"] = "classic"
                attempt -= 1
                continue
            logger.warning("Gemini respondió HTTP %s", status)
            if status in (429, 500, 502, 503, 504) and attempt <= settings.ai_sdk_retries:
                await asyncio.sleep(min(2 ** attempt, 6))
                continue
            raise _status_error(status, text)
    finally:
        if own_client:
            await client.aclose()


def _extract_text(resp: Any) -> tuple[str, str | None]:
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        return "", "INVALID_RESPONSE"
    candidates = data.get("candidates") or []
    if not candidates:
        reason = (data.get("promptFeedback") or {}).get("blockReason") or "NO_CANDIDATES"
        return "", str(reason)
    first = candidates[0]
    parts = (first.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought"))
    return text, first.get("finishReason")


def parse_json_text(text: str) -> Any:
    """Parsea la salida del modelo tolerando bloques ```json ... ```."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned[4:] if cleaned.lower().startswith("json") else cleaned
    return json.loads(cleaned.strip())
