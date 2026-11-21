"""Modo demo (USE_MOCK_AI=true): análisis heurístico y determinista, SIN llamar a ningún modelo.

Sirve para probar el backend y el frontend al instante (p. ej. al clonar el repositorio desde
GitHub) sin API key. Compara el CV con la oferta usando un vocabulario de tecnologías y
habilidades blandas, y devuelve exactamente la misma estructura (`AnalysisResult`) que el
modo real. Es una aproximación: no sustituye el análisis de un modelo de IA.
"""

import re

from schemas import (
    AnalysisResult,
    AnalyzeRequest,
    Improvement,
    MissingKeywords,
    OutputLanguage,
    RewrittenSection,
    ScoreBreakdown,
    TargetSection,
)

# --------------------------------------------------------------------------------------------
# Vocabularios (nombre mostrado → alias que cuentan como evidencia)
# --------------------------------------------------------------------------------------------
TECH_TERMS: dict[str, list[str]] = {
    "Python": ["python"], "FastAPI": ["fastapi"], "Django": ["django"], "Flask": ["flask"],
    "JavaScript": ["javascript", "js"], "TypeScript": ["typescript"], "React": ["react", "reactjs", "react.js"],
    "Node.js": ["node.js", "nodejs", "node"], "Vue": ["vue", "vue.js"], "Angular": ["angular"],
    "Java": ["java"], "Spring": ["spring", "spring boot"], "C#": ["c#"], ".NET": [".net", "dotnet"],
    "Golang": ["golang"], "Rust": ["rust"], "PHP": ["php"], "Laravel": ["laravel"],
    "SQL": ["sql"], "PostgreSQL": ["postgresql", "postgres"], "MySQL": ["mysql"], "MongoDB": ["mongodb"],
    "Redis": ["redis"], "Kafka": ["kafka"], "RabbitMQ": ["rabbitmq"],
    "Docker": ["docker"], "Kubernetes": ["kubernetes", "k8s"], "Terraform": ["terraform"],
    "AWS": ["aws", "amazon web services"], "Azure": ["azure"], "GCP": ["gcp", "google cloud"],
    "CI/CD": ["ci/cd", "cicd", "integración continua", "continuous integration", "github actions", "gitlab ci", "jenkins"],
    "Git": ["git", "github", "gitlab"], "Linux": ["linux"],
    "REST APIs": ["rest", "restful", "api rest", "apis"], "GraphQL": ["graphql"],
    "Microservicios": ["microservicios", "microservices"],
    "Pruebas automatizadas": ["pytest", "unit testing", "pruebas unitarias", "pruebas automatizadas", "jest", "testing"],
    "Pandas": ["pandas"], "Spark": ["spark", "pyspark"], "Airflow": ["airflow"],
    "Machine Learning": ["machine learning", "aprendizaje automático", "ml"],
    "TensorFlow": ["tensorflow"], "PyTorch": ["pytorch"], "LLMs": ["llm", "llms", "large language model"],
    "Power BI": ["power bi", "powerbi"], "Tableau": ["tableau"], "Excel": ["excel"],
    "Scrum/Agile": ["scrum", "agile", "ágil", "agil", "kanban"],
}

SOFT_TERMS: list[dict] = [
    {"es": "Liderazgo", "en": "Leadership", "aliases": ["liderazgo", "leadership", "liderar", "lideré", "led a team", "team lead"]},
    {"es": "Trabajo en equipo", "en": "Teamwork", "aliases": ["trabajo en equipo", "teamwork", "equipos multidisciplinarios", "cross-functional"]},
    {"es": "Comunicación", "en": "Communication", "aliases": ["comunicación", "comunicacion", "communication", "presentaciones", "presentations"]},
    {"es": "Resolución de problemas", "en": "Problem solving", "aliases": ["resolución de problemas", "resolucion de problemas", "problem solving", "problem-solving"]},
    {"es": "Colaboración", "en": "Collaboration", "aliases": ["colaboración", "colaboracion", "collaboration", "collaborative", "colaborativo"]},
    {"es": "Mentoría", "en": "Mentoring", "aliases": ["mentoría", "mentoria", "mentoring", "mentor"]},
    {"es": "Adaptabilidad", "en": "Adaptability", "aliases": ["adaptabilidad", "adaptability", "adaptable", "flexibilidad", "flexibility"]},
    {"es": "Pensamiento analítico", "en": "Analytical thinking", "aliases": ["pensamiento analítico", "analítico", "analytical", "analysis"]},
    {"es": "Orientación a resultados", "en": "Results orientation", "aliases": ["orientación a resultados", "orientado a resultados", "results-oriented", "results driven"]},
    {"es": "Autonomía", "en": "Ownership", "aliases": ["autonomía", "autonomia", "ownership", "autónomo", "self-starter", "proactividad", "proactive", "proactivo"]},
    {"es": "Gestión del tiempo", "en": "Time management", "aliases": ["gestión del tiempo", "time management", "priorización", "prioritization"]},
]

SECTION_PATTERNS: dict[str, str] = {
    "summary": r"resumen(?: profesional)?|perfil(?: profesional)?|summary|professional summary|profile|about me|sobre mí",
    "experience": r"experiencia(?: laboral| profesional)?|work experience|professional experience|experience|employment",
    "education": r"educación|educacion|formación|formacion|estudios|education|academic",
    "skills": r"habilidades|competencias|skills|technical skills|tecnologías|stack",
    "projects": r"proyectos|projects",
    "languages": r"idiomas|languages",
}
_ANY_HEADING = re.compile(r"^\s*(?:" + "|".join(SECTION_PATTERNS.values()) + r")\s*:?\s*$", re.IGNORECASE)

ACTION_VERBS = (
    "desarrollé|implementé|lideré|diseñé|optimicé|automaticé|reduje|aumenté|creé|gestioné|coordiné|migré|construí|dirigí|mejoré|logré|"
    "developed|implemented|led|designed|optimized|automated|reduced|increased|created|managed|coordinated|migrated|built|improved|achieved|delivered|launched"
)
_ACTION_LINE = re.compile(rf"^\s*(?:-\s*)?(?:{ACTION_VERBS})\b", re.IGNORECASE)
_METRIC = re.compile(
    r"\d+\s?%|[$€]\s?\d|\b\d+\s?(?:k|m|x|ms|usuarios|users|clientes|clients|customers|segundos|seconds|horas|hours|millones|million)\b",
    re.IGNORECASE,
)

# Textos por idioma
STR = {
    "es": {
        "sections": {"professional_summary": "Resumen profesional", "experience": "Experiencia", "skills": "Habilidades", "projects": "Proyectos"},
        "role_fallback": "el puesto",
        "summary": "[Modo demo] Compatibilidad estimada para «{role}»: {score}/100. Cubres {hit} de {total} requisitos técnicos detectados en la oferta. {gap} {impact}",
        "gap_some": "Falta evidencia de: {items}.",
        "gap_none": "No se detectaron carencias técnicas claras.",
        "impact_low": "Tu CV casi no muestra logros cuantificados.",
        "impact_ok": "Tu CV incluye algunos logros cuantificados.",
        "imp_tech_what": "Incorpora (solo si es cierto) evidencia de: {items}, en los proyectos o puestos donde los usaste.",
        "imp_tech_why": "La oferta los menciona explícitamente y los sistemas ATS filtran por estas palabras clave.",
        "imp_metrics_what": "Convierte tus viñetas en logros medibles: verbo de acción + qué hiciste + resultado (%, tiempo, usuarios, costos).",
        "imp_metrics_why": "Los reclutadores priorizan impacto demostrable sobre listas de tareas.",
        "imp_metrics_ex": "Optimicé las consultas de la API, reduciendo la latencia en [X%] para [N] usuarios.",
        "imp_summary_what": "Añade un resumen profesional de 3-4 líneas alineado con el puesto y sus tecnologías principales.",
        "imp_summary_why": "Es lo primero que lee un reclutador y donde se decide si sigue leyendo.",
        "imp_soft_what": "Demuestra con ejemplos breves: {items}.",
        "imp_soft_why": "La oferta pide estas habilidades y los CV suelen afirmarlas sin evidencia.",
        "imp_struct_what": "Usa secciones estándar (Resumen, Experiencia, Educación, Habilidades) y mantén el CV en 1-2 páginas.",
        "imp_struct_why": "Una estructura clara mejora la lectura rápida y el parseo automático por ATS.",
        "imp_terms_what": "Usa la misma terminología de la oferta cuando describas tu experiencia real.",
        "imp_terms_why": "Alinea tu CV con el lenguaje del reclutador y mejora el filtrado por palabras clave.",
        "sec_summary": "Resumen profesional",
        "sec_experience": "Experiencia",
        "sec_skills": "Habilidades",
        "sec_projects": "Proyectos",
        "rewrite_summary": "Profesional con experiencia en {skills}, enfocado en {role}. Orientado a resultados medibles: [X%] de mejora en [métrica] y [N] proyectos entregados.",
        "rewrite_exp_line": "- {line}; resultado: [X% de mejora / impacto medible].",
        "rewrite_projects": "- {line}; resultado: [impacto medible].",
        "rationale": "Texto generado por reglas (modo demo, tono «{tone}»): prioriza las palabras clave de la oferta que ya aparecen en tu CV y deja marcadores [X] para métricas reales.",
        "ni_metric": "Sustituye [X%], [N] y [métrica] por datos reales o elimina esa parte.",
        "ni_skill": "Añade «{kw}» solo si realmente lo dominas.",
        "absent": "",
    },
    "en": {
        "sections": {"professional_summary": "Professional summary", "experience": "Experience", "skills": "Skills", "projects": "Projects"},
        "role_fallback": "the role",
        "summary": "[Demo mode] Estimated fit for \"{role}\": {score}/100. You cover {hit} of {total} technical requirements detected in the job post. {gap} {impact}",
        "gap_some": "Missing evidence of: {items}.",
        "gap_none": "No clear technical gaps were detected.",
        "impact_low": "Your CV barely shows quantified achievements.",
        "impact_ok": "Your CV includes some quantified achievements.",
        "imp_tech_what": "Add (only if true) evidence of: {items}, in the projects or roles where you used them.",
        "imp_tech_why": "The job post names them explicitly and ATS systems filter on these keywords.",
        "imp_metrics_what": "Turn bullets into measurable achievements: action verb + what you did + result (%, time, users, cost).",
        "imp_metrics_why": "Recruiters prioritize demonstrable impact over task lists.",
        "imp_metrics_ex": "Optimized API queries, cutting latency by [X%] for [N] users.",
        "imp_summary_what": "Add a 3-4 line professional summary aligned with the role and its core technologies.",
        "imp_summary_why": "It is the first thing a recruiter reads and decides whether they keep reading.",
        "imp_soft_what": "Show with short examples: {items}.",
        "imp_soft_why": "The job post asks for these skills and CVs usually claim them without evidence.",
        "imp_struct_what": "Use standard sections (Summary, Experience, Education, Skills) and keep the CV to 1-2 pages.",
        "imp_struct_why": "A clear structure improves skim-reading and automatic ATS parsing.",
        "imp_terms_what": "Mirror the job post terminology when describing your real experience.",
        "imp_terms_why": "It aligns your CV with the recruiter's language and improves keyword filtering.",
        "sec_summary": "Professional summary",
        "sec_experience": "Experience",
        "sec_skills": "Skills",
        "sec_projects": "Projects",
        "rewrite_summary": "Professional with experience in {skills}, focused on {role}. Results-oriented: [X%] improvement in [metric] and [N] projects delivered.",
        "rewrite_exp_line": "- {line}; result: [X% improvement / measurable impact].",
        "rewrite_projects": "- {line}; result: [measurable impact].",
        "rationale": "Rule-based text (demo mode, tone \"{tone}\"): it prioritizes job-post keywords already present in your CV and leaves [X] placeholders for real metrics.",
        "ni_metric": "Replace [X%], [N] and [metric] with real data or remove that part.",
        "ni_skill": "Add \"{kw}\" only if you genuinely know it.",
        "absent": "",
    },
}

_ES_WORDS = (" de ", " la ", " el ", " y ", " con ", " para ", " en ", " los ", " las ", "experiencia", "buscamos")
_EN_WORDS = (" the ", " and ", " with ", " for ", " of ", " to ", " you ", " our ", "experience", "looking")


def detect_language(text: str) -> str:
    low = f" {text.lower()} "
    es = sum(low.count(w) for w in _ES_WORDS)
    en = sum(low.count(w) for w in _EN_WORDS)
    return "es" if es >= en else "en"


def _has(term: str, text: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, re.IGNORECASE) is not None


def _any(aliases: list[str], text: str) -> bool:
    return any(_has(a, text) for a in aliases)


def _clamp(value: float, low: int = 5, high: int = 98) -> int:
    return max(low, min(high, round(value)))


def _section_block(cv: str, key: str, max_chars: int = 1200) -> str:
    """Texto de una sección del CV (hasta el siguiente encabezado conocido). '' si no existe."""
    pattern = re.compile(rf"^\s*(?:{SECTION_PATTERNS[key]})\s*:?\s*(.*)$", re.IGNORECASE)
    lines = cv.split("\n")
    for i, line in enumerate(lines):
        m = pattern.match(line)
        if not m or len(line) > 400:
            continue
        rest = m.group(1).strip()
        # Un encabezado real es corto ("Experiencia") o tiene dos puntos ("Resumen: ...").
        if rest and ":" not in line[: len(line) - len(rest)] and len(line.split()) > 6:
            continue
        block = [rest] if rest else []
        for nxt in lines[i + 1 : i + 40]:
            if _ANY_HEADING.match(nxt):
                break
            block.append(nxt)
        text = "\n".join(block).strip()
        if text:
            return text[:max_chars]
    return ""


def _role_title(jd: str, fallback: str) -> str:
    m = re.search(r"(?:puesto|cargo|posici[oó]n|position|role|job title|vacante)\s*[:\-–]\s*(.+)", jd, re.IGNORECASE)
    line = m.group(1) if m else next((ln for ln in jd.split("\n") if ln.strip()), "")
    line = re.sub(r"\s+", " ", line).strip(" -–:•*")
    return line[:80] if len(line) >= 3 else fallback


def generate_mock_analysis(req: AnalyzeRequest) -> AnalysisResult:
    cv, jd = req.cv_text, req.job_description
    lang = req.output_language.value if req.output_language != OutputLanguage.auto else detect_language(jd)
    s = STR[lang]

    # ---- coincidencias de palabras clave ----
    jd_tech = [name for name, aliases in TECH_TERMS.items() if _any(aliases, jd)]
    cv_tech = [name for name in jd_tech if _any(TECH_TERMS[name], cv)]
    missing_tech = [name for name in jd_tech if name not in cv_tech]

    jd_soft = [t for t in SOFT_TERMS if _any(t["aliases"], jd)]
    missing_soft = [t[lang] for t in jd_soft if not _any(t["aliases"], cv)]
    soft_hit = len(jd_soft) - len(missing_soft)

    # ---- señales de impacto y estructura ----
    lines = [ln for ln in cv.split("\n") if ln.strip()]
    quantified = sum(1 for ln in lines if _METRIC.search(ln))
    action_lines = sum(1 for ln in lines if _ACTION_LINE.match(ln))
    sections_found = {k for k in SECTION_PATTERNS if _section_block(cv, k) or re.search(rf"^\s*(?:{SECTION_PATTERNS[k]})\s*:?\s*$", cv, re.IGNORECASE | re.MULTILINE)}
    has_contact = bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", cv)) or bool(re.search(r"\+?\d[\d\s().-]{7,}", cv))
    words = len(cv.split())

    technical_match = _clamp(100 * len(cv_tech) / len(jd_tech)) if jd_tech else 60
    soft_skills_match = _clamp(100 * soft_hit / len(jd_soft)) if jd_soft else 60
    experience_impact = _clamp(25 + 14 * min(quantified, 4) + 4 * min(action_lines, 6))
    structure_clarity = _clamp(20 + 12 * len(sections_found & {"summary", "experience", "education", "skills"}) + (10 if has_contact else 0) + (8 if 250 <= words <= 1200 else 0))
    score = _clamp(0.4 * technical_match + 0.3 * experience_impact + 0.1 * soft_skills_match + 0.2 * structure_clarity)

    role = _role_title(jd, s["role_fallback"])
    gap = s["gap_some"].format(items=", ".join(missing_tech[:3])) if missing_tech else s["gap_none"]
    impact = s["impact_low"] if quantified < 2 else s["impact_ok"]
    summary = s["summary"].format(role=role, score=score, hit=len(cv_tech), total=len(jd_tech), gap=gap, impact=impact)

    # ---- mejoras priorizadas ----
    improvements: list[Improvement] = []
    if missing_tech:
        improvements.append(Improvement(priority="high", section=s["sec_skills"], what_to_change=s["imp_tech_what"].format(items=", ".join(missing_tech[:6])), why=s["imp_tech_why"]))
    if quantified < 3:
        improvements.append(Improvement(priority="high", section=s["sec_experience"], what_to_change=s["imp_metrics_what"], why=s["imp_metrics_why"], example=s["imp_metrics_ex"]))
    if "summary" not in sections_found:
        improvements.append(Improvement(priority="medium", section=s["sec_summary"], what_to_change=s["imp_summary_what"], why=s["imp_summary_why"]))
    if missing_soft:
        improvements.append(Improvement(priority="medium", section=s["sec_experience"], what_to_change=s["imp_soft_what"].format(items=", ".join(missing_soft[:4])), why=s["imp_soft_why"]))
    if structure_clarity < 70:
        improvements.append(Improvement(priority="low", section="CV", what_to_change=s["imp_struct_what"], why=s["imp_struct_why"]))
    if len(improvements) < 3:
        improvements.append(Improvement(priority="low", section="CV", what_to_change=s["imp_terms_what"], why=s["imp_terms_why"]))

    # ---- sección reescrita ----
    target = req.target_section or TargetSection.professional_summary
    kw = ", ".join(cv_tech[:4]) or ", ".join(jd_tech[:3]) or "—"
    section_key = {"professional_summary": "summary", "experience": "experience", "skills": "skills", "projects": "projects"}[target.value]
    original = _section_block(cv, section_key, 800)
    needs = [s["ni_metric"]]

    if target == TargetSection.professional_summary:
        improved = s["rewrite_summary"].format(skills=", ".join(cv_tech[:4]) or ", ".join(jd_tech[:3]) or "—", role=role)
    elif target == TargetSection.skills:
        tokens = [t.strip() for t in re.split(r"[,;|\n]", original) if t.strip().strip("-").strip()]
        tokens = [t.lstrip("- ").strip() for t in tokens]
        relevant = [t for t in tokens if any(_has(a, t) for n in jd_tech for a in TECH_TERMS[n])]
        rest = [t for t in tokens if t not in relevant]
        improved = ", ".join(relevant + rest) or ", ".join(cv_tech) or "—"
        needs = [s["ni_skill"].format(kw=m) for m in missing_tech[:5]] or [s["ni_metric"]]
    else:
        src = [ln.strip("- ").strip() for ln in original.split("\n") if ln.strip()][:3] or [role]
        template = s["rewrite_exp_line"] if target == TargetSection.experience else s["rewrite_projects"]
        # Solo se añade el marcador de métrica a las líneas que aún no tienen una; nunca se inventan tecnologías.
        improved = "\n".join(
            f"- {ln.rstrip('.')}" if _METRIC.search(ln) else template.format(line=ln.rstrip("."), kw=kw)
            for ln in src
        )

    rewritten = RewrittenSection(
        section_name=s["sections"][target.value],
        original_excerpt=original,
        improved_text=improved,
        rationale=s["rationale"].format(tone=req.tone.value),
        needs_user_input=needs,
    )

    return AnalysisResult(
        compatibility_score=score,
        score_breakdown=ScoreBreakdown(
            technical_match=technical_match,
            experience_impact=experience_impact,
            soft_skills_match=soft_skills_match,
            structure_clarity=structure_clarity,
        ),
        summary=summary,
        missing_keywords=MissingKeywords(technical=missing_tech, soft=missing_soft),
        improvements=improvements,
        rewritten_section=rewritten,
    )
