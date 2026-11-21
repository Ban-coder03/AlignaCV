"""Modelos Pydantic: contrato de entrada y de salida de la API.

- `AnalyzeRequest`  → validación estricta de lo que envía el frontend.
- `AnalysisResult`  → lo que el modelo de IA debe producir (es también el JSON Schema de la
                      herramienta que fuerza la salida estructurada).
- `AnalysisResponse`→ `AnalysisResult` + `meta` (lo que recibe el frontend).

Los límites de longitud de las listas/textos de la SALIDA son tolerantes (recortan en vez de
fallar) para no desperdiciar reintentos por detalles menores; los tipos y rangos sí son estrictos.
"""

from enum import Enum
from typing import Annotated, Any, Callable, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

# ---- Límites de entrada (única fuente de verdad) ------------------------------------------
CV_MIN_CHARS = 100
CV_MAX_CHARS = 30_000
JD_MIN_CHARS = 50
JD_MAX_CHARS = 15_000


class Tone(str, Enum):
    professional = "professional"   # equilibrado y formal (por defecto)
    executive = "executive"         # directo, orientado a impacto y liderazgo
    technical = "technical"         # preciso, centrado en stack y detalles técnicos
    friendly = "friendly"           # cercano pero profesional


class TargetSection(str, Enum):
    professional_summary = "professional_summary"
    experience = "experience"
    skills = "skills"
    projects = "projects"


class OutputLanguage(str, Enum):
    auto = "auto"   # el mismo idioma de la oferta laboral
    es = "es"
    en = "en"


def _clean_control_chars(value: Any) -> Any:
    """Elimina caracteres de control (salvo saltos de línea y tabulaciones) y bytes nulos."""
    if not isinstance(value, str):
        return value
    return "".join(ch for ch in value if ch in "\n\r\t" or ch.isprintable() or ch.isspace())


def _assert_readable(value: str) -> str:
    letters = sum(ch.isalpha() for ch in value)
    if letters / max(len(value), 1) < 0.3:
        raise ValueError("El texto no parece contener contenido legible (muy pocas letras).")
    return value


# ============================================================================================
# ENTRADA
# ============================================================================================
class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",  # campos desconocidos (p. ej. "jobDescription") → 422, evita typos silenciosos
        json_schema_extra={
            "examples": [
                {
                    "cv_text": "Ana Pérez — Desarrolladora Backend\nResumen: 4 años construyendo APIs en Python...",
                    "job_description": "Buscamos Backend Engineer con Python, FastAPI, Docker y AWS...",
                    "target_section": "professional_summary",
                    "tone": "professional",
                    "output_language": "auto",
                }
            ]
        },
    )

    cv_text: str = Field(
        ...,
        min_length=CV_MIN_CHARS,
        max_length=CV_MAX_CHARS,
        description=f"Texto del CV ({CV_MIN_CHARS}–{CV_MAX_CHARS} caracteres). Puede obtenerse con /api/extract-text.",
    )
    job_description: str = Field(
        ...,
        min_length=JD_MIN_CHARS,
        max_length=JD_MAX_CHARS,
        description=f"Texto de la oferta laboral ({JD_MIN_CHARS}–{JD_MAX_CHARS} caracteres).",
    )
    target_section: TargetSection | None = Field(
        default=None,
        description="Sección del CV a reescribir. Si se omite, la IA elige la de mayor impacto.",
    )
    tone: Tone = Field(default=Tone.professional, description="Tono del texto reescrito.")
    output_language: OutputLanguage = Field(
        default=OutputLanguage.auto,
        description="Idioma de la respuesta. 'auto' usa el idioma de la oferta laboral.",
    )

    @field_validator("cv_text", "job_description", mode="before")
    @classmethod
    def _strip_control_chars(cls, v: Any) -> Any:
        return _clean_control_chars(v)

    @field_validator("cv_text", "job_description", mode="after")
    @classmethod
    def _must_be_readable(cls, v: str) -> str:
        return _assert_readable(v)


# ============================================================================================
# SALIDA (lo que produce el modelo)
# ============================================================================================
def _clip(max_len: int) -> Callable[[Any], Any]:
    """Recorta cadenas demasiado largas en lugar de fallar."""
    def _inner(value: Any) -> Any:
        return value.strip()[:max_len] if isinstance(value, str) else value
    return _inner


def _limit_items(max_items: int) -> Callable[[Any], Any]:
    """Recorta listas demasiado largas en lugar de fallar."""
    def _inner(value: Any) -> Any:
        return value[:max_items] if isinstance(value, list) else value
    return _inner


Score = Annotated[int, Field(ge=0, le=100)]
Keyword = Annotated[str, BeforeValidator(_clip(60)), StringConstraints(strip_whitespace=True, min_length=1)]


class ScoreBreakdown(BaseModel):
    technical_match: Score = Field(description="Cobertura de requisitos técnicos de la oferta (0-100).")
    experience_impact: Score = Field(description="Seniority/experiencia relevante y logros cuantificados (0-100).")
    soft_skills_match: Score = Field(description="Evidencia de habilidades blandas que pide la oferta (0-100).")
    structure_clarity: Score = Field(description="Estructura, claridad y compatibilidad con ATS (0-100).")


class MissingKeywords(BaseModel):
    technical: Annotated[list[Keyword], BeforeValidator(_limit_items(25))] = Field(
        description="Tecnologías/herramientas/conceptos técnicos de la oferta ausentes o débiles en el CV."
    )
    soft: Annotated[list[Keyword], BeforeValidator(_limit_items(12))] = Field(
        description="Habilidades blandas relevantes de la oferta sin evidencia clara en el CV."
    )


class Improvement(BaseModel):
    priority: Literal["high", "medium", "low"] = Field(description="Prioridad de la mejora.")
    section: Annotated[str, BeforeValidator(_clip(80)), StringConstraints(min_length=1)] = Field(
        description="Sección del CV afectada (p. ej. 'Experiencia', 'Resumen', 'Habilidades')."
    )
    what_to_change: Annotated[str, BeforeValidator(_clip(600)), StringConstraints(min_length=1)] = Field(
        description="Qué cambiar, de forma concreta y accionable."
    )
    why: Annotated[str, BeforeValidator(_clip(600)), StringConstraints(min_length=1)] = Field(
        description="Por qué importa para esta oferta (criterio de reclutador)."
    )
    example: Annotated[str, BeforeValidator(_clip(600))] | None = Field(
        default=None,
        description="Ejemplo opcional. Si faltan datos reales, usa marcadores como [X%] en lugar de inventarlos.",
    )


class RewrittenSection(BaseModel):
    section_name: Annotated[str, BeforeValidator(_clip(80)), StringConstraints(min_length=1)] = Field(
        description="Nombre de la sección reescrita."
    )
    original_excerpt: Annotated[str, BeforeValidator(_clip(3000))] = Field(
        description="Fragmento ORIGINAL copiado literalmente del CV. Cadena vacía si la sección no existe."
    )
    improved_text: Annotated[str, BeforeValidator(_clip(5000)), StringConstraints(min_length=1)] = Field(
        description="Texto mejorado y enfocado en la oferta. Solo hechos del CV; sin inventar datos."
    )
    rationale: Annotated[str, BeforeValidator(_clip(1500)), StringConstraints(min_length=1)] = Field(
        description="Por qué el texto nuevo funciona mejor para esta oferta."
    )
    needs_user_input: Annotated[list[Annotated[str, BeforeValidator(_clip(200))]], BeforeValidator(_limit_items(10))] = Field(
        default_factory=list,
        description="Datos que la persona debe completar o verificar (p. ej. métricas marcadas como [X%]).",
    )


class AnalysisResult(BaseModel):
    """Estructura que el modelo de IA está OBLIGADO a producir."""

    compatibility_score: Score = Field(description="Compatibilidad global del CV con la oferta (0-100).")
    score_breakdown: ScoreBreakdown
    summary: Annotated[str, BeforeValidator(_clip(1500)), StringConstraints(min_length=1)] = Field(
        description="Diagnóstico ejecutivo breve y directo (2-4 frases)."
    )
    missing_keywords: MissingKeywords
    improvements: Annotated[list[Improvement], BeforeValidator(_limit_items(12))] = Field(
        min_length=1, description="Mejoras accionables ordenadas por prioridad (de mayor a menor)."
    )
    rewritten_section: RewrittenSection

    @model_validator(mode="after")
    def _sort_improvements(self) -> "AnalysisResult":
        order = {"high": 0, "medium": 1, "low": 2}
        self.improvements = sorted(self.improvements, key=lambda i: order[i.priority])  # estable
        return self


# ============================================================================================
# SALIDA (lo que recibe el frontend)
# ============================================================================================
class AnalysisMeta(BaseModel):
    mode: Literal["live", "mock"] = Field(description="'mock' si el análisis es heurístico (USE_MOCK_AI=true).")
    model: str = Field(description="Modelo de IA utilizado ('mock-heuristic-v1' en modo demo).")
    elapsed_ms: int = Field(ge=0, description="Duración total del análisis en milisegundos.")
    tone: Tone
    target_section: TargetSection | None = None
    warnings: list[str] = Field(default_factory=list, description="Avisos no fatales sobre la calidad del resultado.")


class AnalysisResponse(AnalysisResult):
    meta: AnalysisMeta


class ExtractTextResponse(BaseModel):
    filename: str
    file_type: Literal["pdf", "docx"]
    pages: int | None = Field(default=None, description="Número de páginas leídas (solo PDF).")
    characters: int
    text: str
    warnings: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    mode: Literal["live", "mock"]
    ai_configured: bool
    model: str | None = None


class ErrorBody(BaseModel):
    code: str = Field(description="Código estable legible por máquina (p. ej. 'invalid_input').")
    message: str = Field(description="Mensaje seguro para mostrar al usuario.")
    details: Any = Field(default=None, description="Detalles opcionales (p. ej. errores por campo).")


class ErrorResponse(BaseModel):
    error: ErrorBody
