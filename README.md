# CV Analyzer API (FastAPI + Pydantic + Structured Outputs)

Compara un CV con una oferta laboral y devuelve un análisis **JSON estructurado y validado**.

## Arquitectura
| Archivo | Responsabilidad |
|---|---|
| `main.py` | Endpoints, CORS, errores HTTP uniformes, `/health`, rate limit por IP |
| `schemas.py` | Contrato Pydantic (entrada, salida, errores) |
| `parsers.py` | Extracción de texto `.pdf` (pypdf) y `.docx` (python-docx) + normalización |
| `ai_service.py` | Prompt de reclutadora, salida estructurada (tool use forzado), validación + reintentos |
| `mock_ai.py` | Modo demo heurístico (`USE_MOCK_AI=true`) |
| `config.py` / `errors.py` | Variables de entorno / errores controlados |

## Instalación y arranque
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                    # USE_MOCK_AI=true funciona sin API key
uvicorn main:app --reload --port 8000
```
Docs interactivas: http://localhost:8000/docs · Salud: http://localhost:8000/health

Modo real: en `.env` pon `USE_MOCK_AI=false` y `ANTHROPIC_API_KEY=<tu clave>` (nunca se versiona: `.gitignore` excluye `.env`).

Tests: `pip install -r requirements-dev.txt && pytest`

## Contrato de la API

### `POST /api/analyze` (JSON)
**Request**
```json
{
  "cv_text": "string, 100–30000 caracteres",
  "job_description": "string, 50–15000 caracteres",
  "target_section": "professional_summary | experience | skills | projects  (opcional)",
  "tone": "professional | executive | technical | friendly  (opcional, default professional)",
  "output_language": "auto | es | en  (opcional, default auto = idioma de la oferta)"
}
```
Campos desconocidos → 422. Textos sin contenido legible → 422.

**Response 200**
```json
{
  "compatibility_score": 62,
  "score_breakdown": {
    "technical_match": 55, "experience_impact": 70,
    "soft_skills_match": 60, "structure_clarity": 75
  },
  "summary": "Diagnóstico ejecutivo breve.",
  "missing_keywords": { "technical": ["FastAPI", "AWS"], "soft": ["Comunicación"] },
  "improvements": [
    {
      "priority": "high | medium | low",
      "section": "Habilidades",
      "what_to_change": "Qué cambiar, concreto.",
      "why": "Por qué importa para esta oferta.",
      "example": "string | null"
    }
  ],
  "rewritten_section": {
    "section_name": "Resumen profesional",
    "original_excerpt": "Texto original del CV ('' si la sección no existe)",
    "improved_text": "Texto mejorado; métricas desconocidas como [X%]",
    "rationale": "Por qué funciona mejor",
    "needs_user_input": ["Datos que la persona debe completar/verificar"]
  },
  "meta": {
    "mode": "live | mock", "model": "claude-sonnet-5-5", "elapsed_ms": 4210,
    "tone": "professional", "target_section": "experience | null",
    "warnings": ["avisos no fatales"]
  }
}
```
Garantías: todas las puntuaciones son enteros 0–100; `improvements` viene ordenado por prioridad (1–12 ítems); `missing_keywords.technical` ≤ 25 y `soft` ≤ 12.

### `POST /api/extract-text` (multipart/form-data, campo `file`)
`.pdf` o `.docx` (máx. `MAX_UPLOAD_MB`, 5 por defecto). Respuesta:
```json
{ "filename": "cv.pdf", "file_type": "pdf", "pages": 2, "characters": 3120, "text": "...", "warnings": [] }
```
Flujo típico del frontend: subir archivo → `text` → mostrarlo/editarlo → enviarlo como `cv_text` a `/api/analyze`.

### `GET /health`
```json
{ "status": "ok", "version": "1.0.0", "mode": "live | mock", "ai_configured": true, "model": "claude-sonnet-5-5" }
```

### Errores (formato único)
```json
{ "error": { "code": "ai_not_configured", "message": "mensaje seguro", "details": null } }
```
En 422 de validación, `details` = `[{ "field": "cv_text", "message": "...", "type": "..." }]` (nunca se devuelve el texto enviado).

| HTTP | `code` | Cuándo |
|---|---|---|
| 413 | `file_too_large` | Archivo sobre el límite |
| 415 | `unsupported_file_type` | Extensión/firma no válida (.doc, .exe, PDF falso…) |
| 422 | `invalid_input` / `file_parse_error` | Validación, PDF escaneado/dañado/protegido |
| 429 | `rate_limit_exceeded` / `ai_rate_limited` | Límite local (cabecera `Retry-After`) o del proveedor |
| 502 | `ai_auth_failed` / `ai_upstream_error` / `ai_invalid_output` | Clave rechazada, proveedor caído, salida del modelo inválida tras reintentos |
| 503 | `ai_not_configured` | Sin API key (y sin `USE_MOCK_AI=true`) |
| 504 | `ai_timeout` | Timeout del proveedor |
| 500 | `internal_error` | Error inesperado (la traza solo queda en el log del servidor) |

## Seguridad
- API key solo por entorno / `.env`; nunca en respuestas ni logs. Se ignoran valores de plantilla.
- Prompt-injection: CV y oferta van entre etiquetas como datos no confiables.
- Salida forzada vía herramienta + validación Pydantic + reintentos con feedback del error.
- Límites de tamaño, validación de firma de archivos, defensa contra zip-bombs, rate limit por IP.
- CORS: `*` por defecto para desarrollo; en producción define `CORS_ORIGINS`.
