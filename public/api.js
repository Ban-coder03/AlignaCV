/** api.js
 * Aligna CV · Capa de datos y motor de demostración.
 * Cambia API_BASE_URL o define window.API_BASE_URL antes de cargar este script.
 * Contrato HTTP:
 * POST /api/analyze      JSON {cv_text, job_description, target_section}
 * POST /api/extract-text multipart/form-data, campo "file" => {text: "..."}
 *
 * Respuesta de análisis recomendada:
 * {score: 0..100, summary: string,
 *  breakdown: {technical: 0..100|null, soft: 0..100|null, relevance: 0..100},
 *  keywords: {technical:{matched:[],missing:[]}, soft:{matched:[],missing:[]}},
 *  suggestions:[{title,detail,impact:"high"|"medium"|"low"}],
 *  rewrite:{section:string,before:string,after:string,note:string}}
 *
 * Sin import/export para permitir ejecución directa bajo file:// (scripts con defer).
 * Única exposición global: window.AlignaAPI.
 */
(() => {
  'use strict';

  // En la web (http/https) se usa el mismo dominio; abierto como archivo local, el backend de desarrollo.
  const API_BASE_URL = window.API_BASE_URL || (/^https?:$/.test(location.protocol) ? location.origin : 'http://127.0.0.1:8000');
  let baseUrl = API_BASE_URL.replace(/\/+$/, '');
  const TIMEOUT_MS = 95000; // el backend puede tardar hasta ~90 s
  const MAX_FILE_BYTES = 4 * 1024 * 1024; // límite del backend en Vercel

  class ApiError extends Error {
    constructor(message, status = null) {
      super(message);
      this.name = 'ApiError';
      this.status = status;
    }
  }

  function setBaseUrl(value) {
    const candidate = String(value || '').trim().replace(/\/+$/, '');
    let url;
    try { url = new URL(candidate); }
    catch { throw new ApiError('Introduce una URL válida para FastAPI, por ejemplo http://127.0.0.1:8000.'); }
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
      throw new ApiError('La URL del backend debe usar http:// o https:// y no incluir credenciales.');
    }
    if (url.search || url.hash) throw new ApiError('Usa únicamente la URL base del backend, sin parámetros ni fragmentos.');
    baseUrl = candidate;
    return baseUrl;
  }

  function normalizeText(value) {
    return String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }

  function escapeRegExp(text) { return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  function termPresent(text, aliases) {
    return aliases.some(alias => {
      const normalized = normalizeText(alias);
      const expression = new RegExp(`(?:^|[^a-z0-9])${escapeRegExp(normalized)}(?=$|[^a-z0-9])`, 'i');
      return expression.test(text);
    });
  }

  // Catálogo explícito de términos evaluables: se evita "detectar" habilidades no escritas.
  const TECHNICAL = [
    ['HTML', 'html5'], ['CSS', 'css3'], ['JavaScript', 'javascript', 'js', 'es6'],
    ['TypeScript', 'typescript'], ['React', 'react.js', 'reactjs'], ['Angular', 'angular'],
    ['Vue', 'vue.js', 'vuejs'], ['Node.js', 'node.js', 'nodejs'], ['Python', 'python'],
    ['FastAPI', 'fastapi'], ['Django', 'django'], ['Java', 'java'], ['Kotlin', 'kotlin'],
    ['SQL', 'sql'], ['PostgreSQL', 'postgresql', 'postgres'], ['MySQL', 'mysql'],
    ['MongoDB', 'mongodb'], ['Firebase', 'firebase'], ['REST APIs', 'api rest', 'apis rest', 'restful', 'rest api'],
    ['Git', 'git'], ['GitHub', 'github'], ['Docker', 'docker'], ['Kubernetes', 'kubernetes'],
    ['AWS', 'aws', 'amazon web services'], ['Azure', 'azure'], ['Linux', 'linux'],
    ['CI/CD', 'ci/cd', 'integracion continua', 'despliegue continuo'],
    ['Testing', 'testing', 'pruebas automatizadas', 'unit tests'], ['Jest', 'jest'],
    ['Playwright', 'playwright'], ['Figma', 'figma'], ['UX/UI', 'ux/ui', 'ui/ux', 'experiencia de usuario'],
    ['Accesibilidad web', 'accesibilidad web', 'wcag'], ['Diseño responsivo', 'responsive', 'diseno responsivo'],
    ['Excel', 'excel'], ['Power BI', 'power bi'], ['Tableau', 'tableau'],
    ['Análisis de datos', 'analisis de datos', 'data analysis'],
    ['Machine learning', 'machine learning', 'aprendizaje automatico'],
    ['Scrum', 'scrum'], ['Agile', 'agile', 'agil', 'metodologias agiles'],
    ['Ciberseguridad', 'ciberseguridad', 'cybersecurity'],
    ['Redes', 'redes de computadoras', 'networking'], ['Soporte técnico', 'soporte tecnico', 'it support']
  ];
  const SOFT = [
    ['Comunicación', 'comunicacion', 'communication'],
    ['Trabajo en equipo', 'trabajo en equipo', 'teamwork', 'colaboracion'],
    ['Liderazgo', 'liderazgo', 'leadership'],
    ['Resolución de problemas', 'resolucion de problemas', 'problem solving'],
    ['Pensamiento crítico', 'pensamiento critico', 'critical thinking'],
    ['Adaptabilidad', 'adaptabilidad', 'adaptation'],
    ['Gestión del tiempo', 'gestion del tiempo', 'time management'],
    ['Organización', 'organizacion', 'organized'],
    ['Proactividad', 'proactividad', 'proactivo', 'initiative'],
    ['Atención al detalle', 'atencion al detalle', 'attention to detail'],
    ['Autonomía', 'autonomia', 'autonomous'],
    ['Empatía', 'empatia', 'empathy'],
    ['Orientación al cliente', 'orientacion al cliente', 'servicio al cliente', 'customer service'],
    ['Gestión de proyectos', 'gestion de proyectos', 'project management']
  ];
  const STOP_WORDS = new Set(('para como este esta estas estos unos unas desde donde sobre entre desde ante bajo hasta hacia segun durante mediante cada debe deber mas muy que con sin por las los una uno del al el la su sus un y o e a en de lo se ser tener es son ha han fue y el nuestro nuestra nuestro nuestros las los experiencia conocimientos conocimiento capacidad deseable requerido requeridos requisitos buscamos sera trabajo empresa oportunidad puesto funciones responsabilidades profesional excelentes equipo nivel experiencia persona personas').split(' '));

  const SECTION_LABELS = Object.freeze({ summary: 'Resumen profesional', experience: 'Experiencia reciente', skills: 'Habilidades y competencias' });
  const HEADING_RE = /^(?:resumen profesional|perfil profesional|perfil|sobre mi|acerca de mi|objetivo profesional|experiencia reciente|experiencia profesional|experiencia laboral|experiencia|historial laboral|habilidades|habilidades tecnicas|habilidades y competencias|competencias|conocimientos|skills|formacion|educacion|estudios|proyectos|certificaciones|idiomas|referencias)\s*:?$/i;
  const SECTION_HEADINGS = {
    summary: /^(?:resumen profesional|perfil profesional|perfil|sobre mi|acerca de mi|objetivo profesional)\s*:?$/i,
    experience: /^(?:experiencia reciente|experiencia profesional|experiencia laboral|experiencia|historial laboral)\s*:?$/i,
    skills: /^(?:habilidades|habilidades tecnicas|habilidades y competencias|competencias|conocimientos|skills)\s*:?$/i
  };

  function keywordMatches(cv, job, dictionary) {
    const cvNorm = normalizeText(cv);
    const jobNorm = normalizeText(job);
    const matched = [], missing = [];
    for (const [label, ...aliases] of dictionary) {
      const terms = [label, ...aliases];
      if (!termPresent(jobNorm, terms)) continue;
      (termPresent(cvNorm, terms) ? matched : missing).push(label);
    }
    return { matched, missing };
  }

  function tokenize(text) {
    return new Set(normalizeText(text)
      .match(/[a-z0-9]{4,}/g)?.filter(token => !STOP_WORDS.has(token) && !/^\d+$/.test(token)) || []);
  }

  function getSectionText(cv, section) {
    const lines = String(cv).replace(/\r/g, '').split('\n');
    let start = -1;
    for (let i = 0; i < lines.length; i++) {
      if (SECTION_HEADINGS[section].test(normalizeText(lines[i].trim()))) { start = i + 1; break; }
    }
    if (start !== -1) {
      const body = [];
      for (let i = start; i < lines.length; i++) {
        if (HEADING_RE.test(normalizeText(lines[i].trim()))) break;
        body.push(lines[i]);
      }
      const extracted = body.join('\n').trim();
      if (extracted) return extracted.slice(0, 1800);
    }
    // Si el CV no tiene encabezados reconocibles, usar un extracto explícito.
    const meaningful = lines.map(line => line.trim()).filter(line => line.length > 15);
    return meaningful.slice(0, section === 'experience' ? 5 : 3).join('\n').slice(0, 1400) || cv.trim().slice(0, 1400);
  }

  function buildRewrite(cv, section, keywords) {
    const before = getSectionText(cv, section);
    const knownTech = keywords.technical.matched.slice(0, 6);
    const knownSoft = keywords.soft.matched.slice(0, 4);
    const confirmed = [...knownTech, ...knownSoft];
    let after;
    if (section === 'skills') {
      const parts = [];
      if (knownTech.length) parts.push(`Competencias técnicas mencionadas en el CV: ${knownTech.join(' · ')}.`);
      if (knownSoft.length) parts.push(`Competencias transversales mencionadas en el CV: ${knownSoft.join(' · ')}.`);
      if (!parts.length) parts.push('Reorganiza tus habilidades existentes por categorías y destaca primero las que puedas demostrar y que sean pertinentes para la vacante.');
      after = `${parts.join('\n')}\n\nInformación de base:\n${before}`;
    } else if (section === 'experience') {
      after = `${before}\n\n${knownTech.length ? `Herramientas y enfoques mencionados en tu CV y relevantes para esta oferta: ${knownTech.join(', ')}.` : 'Revisa qué responsabilidades reales de esta experiencia están vinculadas con los requisitos de la oferta.'}`;
    } else {
      const intro = confirmed.length
        ? `Perfil con experiencia y competencias descritas en el CV, relevantes para la vacante: ${confirmed.join(', ')}.`
        : 'Perfil profesional con experiencia descrita en el CV y orientación al puesto solicitado.';
      after = `${intro}\n\n${before}`;
    }
    return {
      section: SECTION_LABELS[section] || SECTION_LABELS.summary,
      before,
      after,
      note: 'Borrador local construido solo con información presente en el CV; verifica que cada afirmación sea cierta. Añade cifras o logros únicamente si puedes respaldarlos.'
    };
  }

  function buildSuggestions(keywords, relevance) {
    const suggestions = [];
    if (keywords.technical.missing.length) {
      suggestions.push({ title: 'Revisa las competencias técnicas solicitadas',
        detail: `La oferta menciona ${keywords.technical.missing.slice(0, 4).join(', ')}. Si tienes experiencia demostrable, explícitala en la sección pertinente; no añadas herramientas que no conozcas.`, impact: 'high' });
    }
    if (keywords.soft.missing.length) {
      suggestions.push({ title: 'Haz visibles tus competencias de colaboración',
        detail: `La vacante valora ${keywords.soft.missing.slice(0, 3).join(', ')}. Si las has ejercido, ilústralas con un ejemplo real de proyecto o resultado.`, impact: 'medium' });
    }
    if (relevance < 70) {
      suggestions.push({ title: 'Adapta la redacción al lenguaje de la oferta',
        detail: 'Prioriza responsabilidades y proyectos de tu CV relacionados con la vacante, usando términos equivalentes cuando describan fielmente tu trabajo.', impact: 'high' });
    }
    suggestions.push({ title: 'Da contexto e impacto a tus aportes',
      detail: 'Convierte tareas genéricas en acciones concretas. Incorpora resultados medibles solo si conoces las cifras y puedes justificarlas.', impact: 'medium' });
    suggestions.push({ title: 'Mejora la lectura rápida de tu CV',
      detail: 'Usa encabezados claros, fechas consistentes, listas breves y una sección de habilidades verificables. Evita palabras clave repetidas sin contexto.', impact: 'low' });
    return suggestions.slice(0, 5);
  }

  function demoAnalyze({ cv_text, job_description, target_section = 'summary' }) {
    const cv = String(cv_text || '').trim();
    const job = String(job_description || '').trim();
    if (cv.length < 60 || job.length < 50) throw new ApiError('Se necesitan al menos 60 caracteres de CV y 50 de oferta para analizar.');
    const section = SECTION_LABELS[target_section] ? target_section : 'summary';
    const keywords = {
      technical: keywordMatches(cv, job, TECHNICAL),
      soft: keywordMatches(cv, job, SOFT)
    };
    const techTotal = keywords.technical.matched.length + keywords.technical.missing.length;
    const softTotal = keywords.soft.matched.length + keywords.soft.missing.length;
    const technical = techTotal ? Math.round(100 * keywords.technical.matched.length / techTotal) : null;
    const soft = softTotal ? Math.round(100 * keywords.soft.matched.length / softTotal) : null;
    const jobWords = tokenize(job), cvWords = tokenize(cv);
    const overlap = [...jobWords].filter(word => cvWords.has(word)).length;
    const relevance = jobWords.size ? Math.round(100 * overlap / jobWords.size) : 0;
    const measures = [[relevance, .30]];
    if (technical !== null) measures.push([technical, .55]);
    if (soft !== null) measures.push([soft, .15]);
    const divisor = measures.reduce((acc, [, weight]) => acc + weight, 0);
    const score = Math.round(measures.reduce((acc, [value, weight]) => acc + value * weight, 0) / divisor);
    const recognizedCount = techTotal + softTotal;
    const recognizedMatched = keywords.technical.matched.length + keywords.soft.matched.length;
    const summary = recognizedCount
      ? `Tu CV refleja ${recognizedMatched} de ${recognizedCount} competencias explícitas reconocidas en esta oferta. La similitud de vocabulario relevante es del ${relevance} %. Revisa los requisitos ausentes solo cuando realmente los domines.`
      : `No se detectaron competencias del catálogo local en la oferta. El ${score} % corresponde exclusivamente a coincidencia de vocabulario y no mide tu nivel profesional.`;
    return {
      score,
      summary,
      breakdown: { technical, soft, relevance },
      keywords,
      suggestions: buildSuggestions(keywords, relevance),
      rewrite: buildRewrite(cv, section, keywords),
      source: 'demo',
      disclaimer: 'Análisis heurístico local: usa coincidencia de términos y una lista explícita de competencias. No es una puntuación ATS real ni una predicción de contratación.'
    };
  }

  function uniqueStrings(value) {
    return Array.isArray(value)
      ? [...new Set(value.map(item => String(item ?? '').trim()).filter(Boolean))].slice(0, 100)
      : [];
  }

  function normalizedKeywordGroup(data, kind) {
    const branch = data.keywords?.[kind];
    const genericMissing = data.missing_keywords?.[kind];
    const genericMatched = data.matched_keywords?.[kind];
    return {
      matched: uniqueStrings(Array.isArray(branch) ? genericMatched : branch?.matched ?? genericMatched),
      missing: uniqueStrings(Array.isArray(branch) ? branch : branch?.missing ?? genericMissing)
    };
  }

  function percent(value) {
    if (value === null || value === undefined || value === '') return null;
    const n = Number(value);
    return Number.isFinite(n) ? Math.min(100, Math.max(0, Math.round(n))) : null;
  }

  function normalizeResponse(raw, request) {
    const data = raw && typeof raw === 'object' ? (raw.result || raw.analysis || raw) : null;
    if (!data || typeof data !== 'object') throw new ApiError('El backend devolvió una respuesta de análisis que no es un objeto JSON válido.');
    const score = percent(data.score ?? data.compatibility_score ?? data.match_score);
    if (score === null) throw new ApiError('El backend no devolvió un campo numérico "score" entre 0 y 100.');
    const rewriteRaw = data.rewrite || {};
    const rs = data.rewritten_section && typeof data.rewritten_section === 'object' ? data.rewritten_section : null;
    const needs = Array.isArray(rs?.needs_user_input) ? rs.needs_user_input.map(String).filter(Boolean) : [];
    const warnings = Array.isArray(data.meta?.warnings) ? data.meta.warnings.map(String).filter(Boolean) : [];
    const selected = SECTION_LABELS[request.target_section] ? request.target_section : 'summary';
    const rawSuggestions = data.suggestions ?? data.improvements;
    const suggestions = Array.isArray(rawSuggestions) ? rawSuggestions.slice(0, 30).map(item => {
      if (typeof item === 'string') return { title: item, detail: '', impact: 'medium' };
      const level = item?.impact ?? item?.priority;
      if (item?.what_to_change) { // formato del backend: section / what_to_change / why / example
        const extra = [item.why ? `Por qué: ${item.why}` : '', item.example ? `Ejemplo: ${item.example}` : ''].filter(Boolean);
        return { title: String(item.section || 'Mejora sugerida'),
          detail: [String(item.what_to_change), ...extra].join('\n'),
          impact: ['high', 'medium', 'low'].includes(level) ? level : 'medium' };
      }
      return { title: String(item?.title || item?.suggestion || 'Mejora sugerida'),
        detail: String(item?.detail || item?.reason || item?.description || ''),
        impact: ['high', 'medium', 'low'].includes(level) ? level : 'medium' };
    }) : [];
    return {
      score,
      summary: String(data.summary ?? data.executive_summary ?? 'Análisis completado. Revisa el detalle de las competencias y las recomendaciones.'),
      breakdown: {
        technical: percent(data.breakdown?.technical ?? data.scores?.technical ?? data.score_breakdown?.technical_match),
        soft: percent(data.breakdown?.soft ?? data.scores?.soft ?? data.score_breakdown?.soft_skills_match),
        relevance: percent(data.breakdown?.relevance ?? data.scores?.relevance ?? data.score_breakdown?.experience_impact)
      },
      keywords: { technical: normalizedKeywordGroup(data, 'technical'), soft: normalizedKeywordGroup(data, 'soft') },
      suggestions,
      rewrite: {
        section: String(rewriteRaw.section || rs?.section_name || SECTION_LABELS[selected]),
        before: String(rewriteRaw.before || rs?.original_excerpt || getSectionText(request.cv_text, selected)),
        after: String(rewriteRaw.after ?? rs?.improved_text ?? (typeof data.rewritten_section === 'string' ? data.rewritten_section : '')),
        note: String(rewriteRaw.note || [rs?.rationale, needs.length ? `Completa o verifica: ${needs.join(' · ')}` : '']
          .filter(Boolean).join('\n\n') || 'Revisa la exactitud de la redacción propuesta antes de incorporarla a tu CV.')
      },
      source: 'backend',
      disclaimer: [String(data.disclaimer || 'Puntaje orientativo. No garantiza una entrevista ni contratación.'), ...warnings].join(' ')
    };
  }

  /** Convierte el error del backend en un texto legible (nunca "[object Object]"). */
  function describeError(payload, status) {
    const err = payload?.error;
    if (err && typeof err === 'object') {
      const fields = Array.isArray(err.details)
        ? err.details.map(d => (d?.field ? `${d.field}: ${d.message}` : d?.message)).filter(Boolean).join('; ')
        : '';
      return [err.message, fields].filter(Boolean).join(' — ') || `Error HTTP ${status}.`;
    }
    if (typeof payload?.detail === 'string') return payload.detail;
    if (Array.isArray(payload?.detail)) return payload.detail.map(d => d?.msg).filter(Boolean).join('; ') || 'Verifica los campos enviados.';
    return typeof payload?.message === 'string' ? payload.message : `Error HTTP ${status}.`;
  }

  async function send(path, { body, headers, signal } = {}) {
    const controller = new AbortController();
    const abortExternal = () => controller.abort();
    if (signal?.aborted) controller.abort();
    signal?.addEventListener('abort', abortExternal, { once: true });
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, TIMEOUT_MS);
    try {
      const response = await fetch(`${baseUrl}${path}`, { method: 'POST', body, headers, signal: controller.signal });
      const rawText = await response.text();
      let payload;
      try { payload = rawText ? JSON.parse(rawText) : {}; }
      catch { throw new ApiError('El servidor devolvió texto en lugar de JSON. Revisa la respuesta de FastAPI.', response.status); }
      if (!response.ok) {
        throw new ApiError(describeError(payload, response.status), response.status);
      }
      return payload;
    } catch (error) {
      if (timedOut) throw new ApiError('El backend tardó demasiado en responder (95 s). Verifica que FastAPI esté activo.');
      if (controller.signal.aborted || error?.name === 'AbortError') throw new ApiError('Operación cancelada.');
      if (error instanceof ApiError) throw error;
      throw new ApiError('No se pudo conectar con FastAPI. Comprueba la URL, que el servidor esté encendido y su configuración CORS. Activa «Modo demo» para analizar sin servidor.');
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', abortExternal);
    }
  }

  async function analyze(request, { demo = false, signal } = {}) {
    if (demo) {
      // Dejar un paso asíncrono real para que la UI pueda pintar su estado de carga.
      await new Promise(resolve => setTimeout(resolve, 320));
      if (signal?.aborted) throw new ApiError('Operación cancelada.');
      return demoAnalyze(request);
    }
    return normalizeResponse(await send('/api/analyze', {
      body: JSON.stringify(request), headers: { 'Content-Type': 'application/json' }, signal
    }), request);
  }

  async function extractText(file, { signal } = {}) {
    if (!(file instanceof File)) throw new ApiError('Selecciona un archivo válido.');
    const extension = file.name.toLowerCase().split('.').pop();
    if (!['txt', 'pdf', 'docx'].includes(extension)) throw new ApiError('Formato no compatible. Usa .txt, .pdf o .docx.');
    if (file.size === 0) throw new ApiError('El archivo está vacío.');
    if (file.size > MAX_FILE_BYTES) throw new ApiError('El archivo supera el límite de 4 MB.');
    if (extension === 'txt') {
      const result = await file.text();
      if (!result.trim()) throw new ApiError('El archivo TXT no contiene texto legible.');
      return result;
    }
    const data = new FormData();
    data.append('file', file, file.name);
    const response = await send('/api/extract-text', { body: data, signal });
    const text = response?.text ?? response?.extracted_text ?? response?.content;
    if (typeof text !== 'string' || !text.trim()) {
      throw new ApiError('El backend no devolvió texto extraído. Se espera {"text": "..."}.');
    }
    return text;
  }

  window.AlignaAPI = Object.freeze({ API_BASE_URL, getBaseUrl: () => baseUrl, setBaseUrl, analyze, extractText, ApiError, MAX_FILE_BYTES });
})();