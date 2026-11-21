"""API FastAPI del analizador de CV frente a una oferta laboral.

Ejecutar:  uvicorn main:app --reload --port 8000
Docs interactivas: http://localhost:8000/docs
"""

import logging
import time
from collections import defaultdict, deque

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import parsers
from ai_service import run_analysis
from config import get_settings
from errors import AppError, FileTooLargeError, InvalidInputError, RateLimitExceededError
from schemas import (
    AnalysisResponse,
    AnalyzeRequest,
    ErrorResponse,
    ExtractTextResponse,
    HealthResponse,
)

APP_VERSION = "1.0.0"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cv_analyzer.api")

settings = get_settings()

app = FastAPI(
    title="CV Analyzer API",
    version=APP_VERSION,
    description="Compara un CV con una oferta laboral y devuelve un análisis estructurado (JSON).",
)

# CORS: por defecto abierto para desarrollo local. En producción define CORS_ORIGINS con tu dominio.
# (Con "*" no se permiten credenciales; la API no usa cookies.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    max_age=600,
)

# ---- Rate limit simple en memoria (por IP) para proteger el gasto de la API key ----------------
_hits: dict[str, deque[float]] = defaultdict(deque)


def _check_rate_limit(request: Request) -> None:
    limit = get_settings().rate_limit_per_minute
    if limit <= 0:
        return
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _hits[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= limit:
        retry = max(1, int(60 - (now - window[0])))
        raise RateLimitExceededError(headers={"Retry-After": str(retry)})
    window.append(now)


# ---- Manejo de errores: SIEMPRE el mismo formato {"error": {code, message, details}} -----------
def _error_response(status: int, code: str, message: str, details=None, headers=None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details}},
        headers=headers,
    )


@app.exception_handler(AppError)
async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return _error_response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Solo campo + mensaje: nunca se devuelve el valor recibido (podría ser el CV completo).
    details = [
        {"field": ".".join(str(p) for p in err["loc"] if p != "body"), "message": err["msg"], "type": err["type"]}
        for err in exc.errors()
    ]
    return _error_response(422, "invalid_input", "Los datos enviados no son válidos.", details)


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
    return _error_response(exc.status_code, code, str(exc.detail), headers=getattr(exc, "headers", None))


@app.exception_handler(Exception)
async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Error no controlado: %s", type(exc).__name__, exc_info=True)  # traza solo en el log del servidor
    return _error_response(500, "internal_error", "Error interno del servidor.")


# ---- Endpoints ---------------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    s = get_settings()
    return HealthResponse(
        status="ok",
        version=APP_VERSION,
        mode="mock" if s.use_mock_ai else "live",
        ai_configured=s.ai_configured,
        model=None if s.use_mock_ai else s.active_model,
    )


_ERROR_RESPONSES = {
    413: {"model": ErrorResponse}, 415: {"model": ErrorResponse}, 422: {"model": ErrorResponse},
    429: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 503: {"model": ErrorResponse},
    504: {"model": ErrorResponse},
}


@app.post("/api/extract-text", response_model=ExtractTextResponse, responses=_ERROR_RESPONSES, tags=["cv"])
async def extract_text(request: Request, file: UploadFile = File(..., description="CV en .pdf o .docx")) -> ExtractTextResponse:
    """Extrae y normaliza el texto de un CV (.pdf / .docx). Pega el resultado en `cv_text` de /api/analyze."""
    _check_rate_limit(request)
    max_bytes = get_settings().max_upload_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes + 64 * 1024:
        raise FileTooLargeError(f"El archivo supera el máximo de {max_bytes // (1024 * 1024)} MB.")
    data = await file.read(max_bytes + 1)   # lee como máximo un byte de más para detectar el exceso
    if len(data) > max_bytes:
        raise FileTooLargeError(f"El archivo supera el máximo de {max_bytes // (1024 * 1024)} MB.")
    doc = parsers.extract_text(file.filename or "cv", data)
    return ExtractTextResponse(
        filename=doc.filename, file_type=doc.file_type, pages=doc.pages,
        characters=len(doc.text), text=doc.text, warnings=doc.warnings,
    )


@app.post("/api/analyze", response_model=AnalysisResponse, responses=_ERROR_RESPONSES, tags=["cv"])
async def analyze(payload: AnalyzeRequest, request: Request) -> AnalysisResponse:
    """Analiza el CV frente a la oferta y devuelve el JSON estructurado (ver README para el contrato)."""
    _check_rate_limit(request)
    if payload.cv_text.strip() == payload.job_description.strip():
        raise InvalidInputError("El CV y la oferta laboral no pueden ser el mismo texto.")
    return await run_analysis(payload)