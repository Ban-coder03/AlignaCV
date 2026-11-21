/** app.js
 * Aligna CV · Controlador de interfaz.
 * No guarda CV ni ofertas en localStorage: solo preferencias de modo, tema y URL.
 * La entrada del usuario y la respuesta del backend siempre se insertan como texto,
 * nunca como HTML, para evitar inyección de etiquetas o scripts.
 */
(() => {
  'use strict';
  const API = window.AlignaAPI;
  if (!API) {
    document.body.insertAdjacentText('afterbegin', 'Error: no se pudo cargar api.js. Coloca los cuatro archivos en la misma carpeta.');
    return;
  }

  const $ = id => document.getElementById(id);
  const el = {
    themeButton: $('themeButton'), demoToggle: $('demoToggle'), modeIndicator: $('modeIndicator'),
    noticeTitle: $('noticeTitle'), noticeBody: $('noticeBody'), backendConfig: $('backendConfig'),
    backendUrl: $('backendUrl'), analyzeForm: $('analyzeForm'), analyzeButton: $('analyzeButton'),
    cvFile: $('cvFile'), dropzone: $('dropzone'), fileFeedback: $('fileFeedback'),
    cvText: $('cvText'), cvCount: $('cvCount'), jobText: $('jobText'), jobCount: $('jobCount'),
    targetSection: $('targetSection'), formError: $('formError'),
    exampleButton: $('exampleButton'), clearButton: $('clearButton'),
    reportStatus: $('reportStatus'), emptyState: $('emptyState'), loadingState: $('loadingState'),
    report: $('report'), reportDate: $('reportDate'), sourceTag: $('sourceTag'),
    scoreProgress: $('scoreProgress'), scoreValue: $('scoreValue'), scoreLabel: $('scoreLabel'),
    summaryText: $('summaryText'), technicalScore: $('technicalScore'), softScore: $('softScore'),
    relevanceScore: $('relevanceScore'), technicalBar: $('technicalBar'), softBar: $('softBar'),
    relevanceBar: $('relevanceBar'), scoreDisclaimer: $('scoreDisclaimer'),
    technicalCount: $('technicalCount'), softCount: $('softCount'),
    technicalMatched: $('technicalMatched'), technicalMissing: $('technicalMissing'),
    softMatched: $('softMatched'), softMissing: $('softMissing'),
    suggestionList: $('suggestionList'), rewriteSectionLabel: $('rewriteSectionLabel'),
    beforeText: $('beforeText'), afterText: $('afterText'), rewriteNote: $('rewriteNote'),
    copyKeywordsButton: $('copyKeywordsButton'), copyRewriteButton: $('copyRewriteButton'),
    exportMdButton: $('exportMdButton'), printButton: $('printButton'), toastStack: $('toastStack')
  };

  const PREFS_KEY = 'aligna-cv-preferences-v1';
  const SECTION_NAMES = { summary: 'Resumen profesional', experience: 'Experiencia reciente', skills: 'Habilidades y competencias' };
  const EXAMPLE = Object.freeze({
    cv: `María Fernanda Solís\nDesarrolladora Frontend · San José, Costa Rica\n\nRESUMEN PROFESIONAL\nDesarrolladora frontend con 3 años de experiencia creando interfaces web accesibles y responsivas. Experiencia práctica en JavaScript, HTML, CSS y React. Trabajo con Git y metodologías Scrum en equipos interdisciplinarios.\n\nEXPERIENCIA LABORAL\nDesarrolladora Frontend | Lumen Labs | 2023–2026\n- Construí pantallas responsivas con React, HTML, CSS y JavaScript para un portal de autoservicio.\n- Colaboré con diseño para implementar prototipos en Figma y gestioné versiones con Git.\n- Reduje el tiempo de carga de una página un 18 % optimizando recursos e imágenes.\n- Participé en revisiones de código y reuniones Scrum con un equipo de seis personas.\n\nHABILIDADES\nJavaScript, HTML, CSS, React, Git, Figma, Scrum, diseño responsivo.\nTrabajo en equipo, comunicación, resolución de problemas.\n\nEDUCACIÓN\nDiplomado en Desarrollo Web | Instituto de Tecnología Aplicada | 2022`,
    job: `Frontend Developer (React + TypeScript)\nEmpresa de software busca profesional para desarrollar productos web claros, escalables y accesibles.\n\nResponsabilidades:\n- Construir componentes con React, JavaScript, TypeScript, HTML y CSS.\n- Integrar REST APIs y colaborar con diseño usando Figma.\n- Escribir Testing automatizado y documentar cambios.\n- Utilizar Git y procesos de CI/CD.\n\nRequisitos:\n- Experiencia con React y diseño responsivo.\n- Conocimientos de Docker son valorados.\n- Buen trabajo en equipo, comunicación, resolución de problemas y adaptabilidad.\n- Capacidad de organización y autonomía.\n\nOfrecemos colaboración con producto, mentoría y oportunidades de crecimiento.`
  });

  const state = {
    theme: 'light', demo: true, result: null, inputAtAnalysis: null,
    analyzedAt: null, inFlight: null, pendingFileId: 0, fileLoading: false
  };

  function readPrefs() {
    try {
      const prefs = JSON.parse(localStorage.getItem(PREFS_KEY) || '{}');
      return prefs && typeof prefs === 'object' ? prefs : {};
    } catch { return {}; }
  }
  function savePrefs() {
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify({
        theme: state.theme, demo: state.demo, apiBaseUrl: el.backendUrl.value.trim()
      }));
    } catch { /* Preferencias opcionales: la aplicación sigue funcionando sin storage. */ }
  }
  function toast(message, type = 'success') {
    const node = document.createElement('div');
    node.className = `toast${type === 'error' ? ' error' : ''}`;
    node.setAttribute('role', type === 'error' ? 'alert' : 'status');
    node.textContent = `${type === 'error' ? '⚠ ' : '✓ '}${message}`;
    el.toastStack.append(node);
    setTimeout(() => node.remove(), 3800);
  }
  function setTheme(theme) {
    state.theme = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.theme = state.theme;
    el.themeButton.setAttribute('aria-label', state.theme === 'dark' ? 'Activar modo claro' : 'Activar modo oscuro');
    el.themeButton.title = state.theme === 'dark' ? 'Activar modo claro' : 'Activar modo oscuro';
    savePrefs();
  }
  function setDemoMode(value) {
    state.demo = Boolean(value);
    el.demoToggle.checked = state.demo;
    el.backendConfig.hidden = state.demo;
    el.modeIndicator.classList.toggle('server', !state.demo);
    el.noticeTitle.textContent = state.demo ? 'Demo 100 % local.' : 'Modo conectado a FastAPI.';
    el.noticeBody.textContent = state.demo
      ? 'Tus textos no salen del navegador. El puntaje es orientativo y se calcula con reglas transparentes, no con inteligencia artificial.'
      : 'El CV y la oferta se envían a tu servidor al analizar. Verifica la URL y la política de privacidad del backend antes de usar datos sensibles.';
    savePrefs();
  }
  function setFeedback(message, type = '') {
    el.fileFeedback.textContent = message;
    el.fileFeedback.classList.toggle('error', type === 'error');
  }
  function setFormError(message = '') {
    el.formError.textContent = message;
    el.formError.hidden = !message;
  }
  function updateCounts() {
    el.cvCount.textContent = `${el.cvText.value.length.toLocaleString('es-CR')} caracteres`;
    el.jobCount.textContent = `${el.jobText.value.length.toLocaleString('es-CR')} caracteres`;
    el.cvText.removeAttribute('aria-invalid');
    el.jobText.removeAttribute('aria-invalid');
    if (!el.formError.hidden) setFormError();
    if (state.result && state.inputAtAnalysis) {
      const snapshot = state.inputAtAnalysis;
      const stale = snapshot.cv_text !== el.cvText.value.trim() ||
        snapshot.job_description !== el.jobText.value.trim() ||
        snapshot.target_section !== el.targetSection.value;
      el.reportStatus.textContent = stale ? 'Cambios sin analizar' : 'Informe generado';
    }
  }
  function setAnalyzeDisabled(value) {
    el.analyzeButton.disabled = value || state.fileLoading;
    el.analyzeButton.querySelector('span:nth-child(2)').textContent = value ? 'Analizando tu perfil...' : 'Analizar compatibilidad';
    el.exampleButton.disabled = value || state.fileLoading;
  }
  function showView(view) {
    el.emptyState.hidden = view !== 'empty';
    el.loadingState.hidden = view !== 'loading';
    el.report.hidden = view !== 'report';
    el.reportStatus.textContent = view === 'report' ? 'Informe generado' : view === 'loading' ? 'Procesando...' : 'Listo para comenzar';
  }
  function validateInputs() {
    const cv = el.cvText.value.trim();
    const job = el.jobText.value.trim();
    if (cv.length < 100) {
      el.cvText.setAttribute('aria-invalid', 'true');
      el.cvText.focus();
      throw new Error('Escribe al menos 100 caracteres de contenido real de tu CV.');
    }
    if (job.length < 50) {
      el.jobText.setAttribute('aria-invalid', 'true');
      el.jobText.focus();
      throw new Error('La oferta debe contener al menos 50 caracteres para detectar requisitos.');
    }
    return { cv_text: cv, job_description: job, target_section: el.targetSection.value };
  }

  async function runAnalysis() {
    if (state.inFlight || state.fileLoading) return;
    let request;
    try {
      request = validateInputs();
      if (!state.demo) {
        API.setBaseUrl(el.backendUrl.value);
        savePrefs();
      }
    } catch (error) {
      setFormError(error.message);
      toast(error.message, 'error');
      return;
    }
    setFormError();
    state.result = null;
    state.inputAtAnalysis = null;
    const controller = new AbortController();
    state.inFlight = controller;
    setAnalyzeDisabled(true);
    showView('loading');
    try {
      const result = await API.analyze(request, { demo: state.demo, signal: controller.signal });
      if (controller.signal.aborted) return;
      state.result = result;
      state.inputAtAnalysis = request;
      state.analyzedAt = new Date();
      renderReport(result);
      showView('report');
      toast(state.demo ? 'Análisis local completado.' : 'Informe recibido desde FastAPI.');
      if (window.matchMedia('(max-width: 760px)').matches) {
        el.reportStatus.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      showView('empty');
      setFormError(error.message || 'No fue posible completar el análisis.');
      toast(error.message || 'Error al analizar', 'error');
    } finally {
      if (state.inFlight === controller) state.inFlight = null;
      setAnalyzeDisabled(Boolean(state.inFlight));
    }
  }

  function renderMetric(numberId, barId, value) {
    const valid = typeof value === 'number' && Number.isFinite(value);
    el[numberId].textContent = valid ? `${value} %` : 'N/D';
    el[barId].style.width = valid ? `${Math.max(0, Math.min(100, value))}%` : '0%';
    el[barId].parentElement.title = valid ? `${value} por ciento` : 'No evaluable con esta oferta';
  }
  function populateChips(element, words, variant) {
    element.replaceChildren();
    if (!words.length) {
      const item = document.createElement('span');
      item.className = 'chip chip-empty';
      item.textContent = variant === 'present' ? 'Ninguna detectada' : 'Sin faltantes detectadas';
      element.append(item);
      return;
    }
    for (const word of words) {
      const chip = document.createElement('span');
      chip.className = `chip ${variant === 'present' ? 'chip-present' : variant === 'technical' ? 'chip-tech-missing' : 'chip-soft-missing'}`;
      chip.textContent = word;
      element.append(chip);
    }
  }
  function renderSuggestions(items) {
    el.suggestionList.replaceChildren();
    if (!items.length) {
      const li = document.createElement('li');
      li.textContent = 'El backend no devolvió sugerencias específicas para esta solicitud.';
      el.suggestionList.append(li);
      return;
    }
    const impactLabel = { high: 'Alto impacto', medium: 'Impacto medio', low: 'Ajuste útil' };
    items.forEach((item, index) => {
      const li = document.createElement('li');
      const number = document.createElement('span');
      number.className = 'suggestion-number';
      number.textContent = String(index + 1).padStart(2, '0');
      const content = document.createElement('div');
      const header = document.createElement('div');
      header.className = 'suggestion-title-row';
      const title = document.createElement('h4');
      title.textContent = item.title;
      const impact = document.createElement('span');
      impact.className = `impact-tag ${item.impact}`;
      impact.textContent = impactLabel[item.impact] || impactLabel.medium;
      header.append(title, impact);
      const detail = document.createElement('p');
      detail.textContent = item.detail;
      content.append(header, detail);
      li.append(number, content);
      el.suggestionList.append(li);
    });
  }
  function renderReport(result) {
    const score = Math.max(0, Math.min(100, Math.round(result.score)));
    const circumference = 2 * Math.PI * 57;
    el.scoreProgress.style.strokeDasharray = String(circumference);
    el.scoreProgress.style.strokeDashoffset = String(circumference * (1 - score / 100));
    el.scoreProgress.classList.toggle('low', score < 45);
    el.scoreProgress.classList.toggle('mid', score >= 45 && score < 72);
    el.scoreProgress.parentElement.setAttribute('aria-label', `Compatibilidad estimada: ${score} de 100`);
    el.scoreValue.textContent = score;
    el.scoreLabel.textContent = score >= 80 ? 'Buena coincidencia' : score >= 60 ? 'Afinidad moderada' : score >= 40 ? 'Hay margen de mejora' : 'Requiere mayor adaptación';
    el.summaryText.textContent = result.summary;
    el.scoreDisclaimer.textContent = result.disclaimer;
    el.sourceTag.textContent = result.source === 'demo' ? 'Demo local · heurístico' : 'Análisis FastAPI';
    el.reportDate.textContent = new Intl.DateTimeFormat('es-CR', { dateStyle: 'medium', timeStyle: 'short' }).format(state.analyzedAt);
    renderMetric('technicalScore', 'technicalBar', result.breakdown.technical);
    renderMetric('softScore', 'softBar', result.breakdown.soft);
    renderMetric('relevanceScore', 'relevanceBar', result.breakdown.relevance);
    const tech = result.keywords.technical, soft = result.keywords.soft;
    el.technicalCount.textContent = `${tech.matched.length + tech.missing.length} términos`;
    el.softCount.textContent = `${soft.matched.length + soft.missing.length} términos`;
    populateChips(el.technicalMatched, tech.matched, 'present');
    populateChips(el.technicalMissing, tech.missing, 'technical');
    populateChips(el.softMatched, soft.matched, 'present');
    populateChips(el.softMissing, soft.missing, 'soft');
    renderSuggestions(result.suggestions);
    el.rewriteSectionLabel.textContent = result.rewrite.section;
    el.beforeText.textContent = result.rewrite.before || '(No hay texto original disponible.)';
    el.afterText.textContent = result.rewrite.after || '(El backend no devolvió una reescritura para esta sección.)';
    el.rewriteNote.textContent = result.rewrite.note;
    el.copyRewriteButton.disabled = !result.rewrite.after;
  }

  async function copyText(value) {
    if (!value.trim()) throw new Error('No hay contenido disponible para copiar.');
    if (navigator.clipboard?.writeText) {
      try { await navigator.clipboard.writeText(value); return; }
      catch { /* Algunos contextos locales bloquean Clipboard API; probar vía selección. */ }
    }
    const textarea = document.createElement('textarea');
    textarea.value = value;
    textarea.setAttribute('readonly', '');
    textarea.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0;';
    document.body.append(textarea);
    textarea.select();
    try {
      if (!document.execCommand('copy')) throw new Error('El navegador no permitió copiar automáticamente.');
    } finally { textarea.remove(); }
  }
  async function onCopyKeywords() {
    if (!state.result) return;
    const { technical, soft } = state.result.keywords;
    const text = [
      'PALABRAS CLAVE POR REVISAR',
      `Técnicas: ${technical.missing.length ? technical.missing.join(', ') : 'Ninguna'}`,
      `Blandas: ${soft.missing.length ? soft.missing.join(', ') : 'Ninguna'}`,
      'Incluye solo las habilidades que realmente tienes.'
    ].join('\n');
    try { await copyText(text); toast('Palabras clave copiadas.'); }
    catch (error) { toast(error.message, 'error'); }
  }
  async function onCopyRewrite() {
    if (!state.result) return;
    try { await copyText(state.result.rewrite.after); toast('Texto mejorado copiado.'); }
    catch (error) { toast(error.message, 'error'); }
  }

  function codeFence(text) {
    const matches = String(text).match(/`{3,}/g) || [];
    const max = Math.max(2, ...matches.map(group => group.length));
    const fence = '`'.repeat(max + 1);
    return `${fence}text\n${text}\n${fence}`;
  }
  function formatKeywordGroup(title, data) {
    return `### ${title}\n\n- **Presentes:** ${data.matched.join(', ') || 'Ninguna'}\n- **Por revisar:** ${data.missing.join(', ') || 'Ninguna'}`;
  }
  function markdownReport() {
    if (!state.result) throw new Error('Primero genera un informe.');
    const r = state.result;
    const date = new Intl.DateTimeFormat('es-CR', { dateStyle: 'full', timeStyle: 'short' }).format(state.analyzedAt);
    const p = value => typeof value === 'number' ? `${value} %` : 'No evaluable';
    const improvements = r.suggestions.map((item, index) => `${index + 1}. **${item.title}** (${item.impact})\n   ${item.detail}`).join('\n') || 'Sin sugerencias recibidas.';
    return [
      '# Informe de compatibilidad · Aligna CV',
      `**Fecha:** ${date}`,
      `**Origen:** ${r.source === 'demo' ? 'Demostración local heurística' : 'Backend FastAPI'}`,
      `**Sección revisada:** ${r.rewrite.section}`,
      '',
      '## Puntaje y evaluación',
      `**Compatibilidad estimada:** ${r.score} / 100`,
      '', r.summary, '',
      `- Competencias técnicas: ${p(r.breakdown.technical)}`,
      `- Competencias blandas: ${p(r.breakdown.soft)}`,
      `- Coincidencia textual: ${p(r.breakdown.relevance)}`,
      '', r.disclaimer, '',
      '## Palabras clave', '',
      formatKeywordGroup('Competencias técnicas', r.keywords.technical), '',
      formatKeywordGroup('Competencias blandas', r.keywords.soft), '',
      '## Mejoras prioritarias', '', improvements, '',
      '## Comparativa de reescritura', '',
      '### Antes', '', codeFence(r.rewrite.before || '(Sin texto)'), '',
      '### Después', '', codeFence(r.rewrite.after || '(Sin reescritura)'), '',
      `> ${r.rewrite.note}`, '',
      '---',
      '**Nota:** No incorpores habilidades, experiencias, cifras o logros que no puedas acreditar. Este documento es una ayuda de edición, no una garantía de selección.', ''
    ].join('\n');
  }
  function exportMarkdown() {
    if (!state.result) return;
    const blob = new Blob([markdownReport()], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    const date = state.analyzedAt.toISOString().slice(0, 10);
    link.href = url;
    link.download = `aligna-cv-informe-${date}.md`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    toast('Informe Markdown descargado.');
  }

  function cancelOperation() {
    state.inFlight?.abort();
    state.inFlight = null;
    state.pendingFileId += 1; // Descarta resultados de extracciones anteriores.
    state.fileLoading = false;
    setAnalyzeDisabled(false);
  }
  function clearAll() {
    cancelOperation();
    el.cvText.value = '';
    el.jobText.value = '';
    el.targetSection.value = 'summary';
    el.cvFile.value = '';
    setFeedback('');
    setFormError();
    state.result = null;
    state.inputAtAnalysis = null;
    state.analyzedAt = null;
    updateCounts();
    showView('empty');
    toast('Campos e informe limpiados.');
  }
  function loadExample() {
    cancelOperation();
    el.cvText.value = EXAMPLE.cv;
    el.jobText.value = EXAMPLE.job;
    el.targetSection.value = 'summary';
    el.cvFile.value = '';
    setFeedback('Ejemplo ficticio precargado. Los datos no corresponden a una persona real.');
    el.demoToggle.checked = true;
    setDemoMode(true);
    updateCounts();
    toast('Ejemplo cargado. Ejecutando análisis local...');
    void runAnalysis();
  }

  async function loadFile(file) {
    if (!file || state.fileLoading) return;
    const token = ++state.pendingFileId;
    state.fileLoading = true;
    el.analyzeButton.disabled = true;
    el.exampleButton.disabled = true;
    setFormError();
    setFeedback(`Leyendo «${file.name}»...`);
    try {
      const extension = file.name.toLowerCase().split('.').pop();
      if (state.demo && ['pdf', 'docx'].includes(extension)) {
        throw new Error('Para extraer un PDF o DOCX necesitas FastAPI. Desactiva «Modo demo» y enciende el backend, o pega aquí el texto del CV. Los .txt sí funcionan sin servidor.');
      }
      if (!state.demo && extension !== 'txt') API.setBaseUrl(el.backendUrl.value);
      const text = await API.extractText(file);
      if (token !== state.pendingFileId) return;
      if (text.length > el.cvText.maxLength) throw new Error(`El documento supera el máximo de ${el.cvText.maxLength.toLocaleString('es-CR')} caracteres. Reduce su longitud.`);
      el.cvText.value = text;
      updateCounts();
      setFeedback(`✓ ${file.name} · ${text.length.toLocaleString('es-CR')} caracteres extraídos.`);
      toast('El CV ya está listo para analizar.');
    } catch (error) {
      if (token !== state.pendingFileId) return;
      setFeedback(error.message || 'No se pudo leer el archivo.', 'error');
      toast(error.message || 'No se pudo leer el archivo.', 'error');
    } finally {
      if (token === state.pendingFileId) {
        state.fileLoading = false;
        setAnalyzeDisabled(Boolean(state.inFlight));
        el.cvFile.value = '';
      }
    }
  }

  function initDragAndDrop() {
    const zone = el.dropzone;
    zone.addEventListener('click', () => el.cvFile.click());
    zone.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); el.cvFile.click(); }
    });
    const prevent = event => { event.preventDefault(); event.stopPropagation(); };
    zone.addEventListener('dragenter', event => { prevent(event); zone.classList.add('drag-over'); });
    zone.addEventListener('dragover', event => { prevent(event); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', event => { prevent(event); zone.classList.remove('drag-over'); });
    zone.addEventListener('drop', event => {
      prevent(event);
      zone.classList.remove('drag-over');
      void loadFile(event.dataTransfer?.files?.[0]);
    });
    el.cvFile.addEventListener('change', event => void loadFile(event.target.files?.[0]));
  }

  function init() {
    const prefs = readPrefs();
    el.backendUrl.value = typeof prefs.apiBaseUrl === 'string' ? prefs.apiBaseUrl : API.API_BASE_URL;
    setTheme(prefs.theme === 'dark' ? 'dark' : 'light');
    setDemoMode(typeof prefs.demo === 'boolean' ? prefs.demo : location.protocol === 'file:'); // en la web, por defecto usa el backend
    updateCounts();
    showView('empty');
    initDragAndDrop();
    el.themeButton.addEventListener('click', () => setTheme(state.theme === 'light' ? 'dark' : 'light'));
    el.demoToggle.addEventListener('change', () => setDemoMode(el.demoToggle.checked));
    el.backendUrl.addEventListener('change', savePrefs);
    el.cvText.addEventListener('input', updateCounts);
    el.jobText.addEventListener('input', updateCounts);
    el.targetSection.addEventListener('change', updateCounts);
    el.analyzeForm.addEventListener('submit', event => { event.preventDefault(); void runAnalysis(); });
    el.exampleButton.addEventListener('click', loadExample);
    el.clearButton.addEventListener('click', clearAll);
    el.copyKeywordsButton.addEventListener('click', () => void onCopyKeywords());
    el.copyRewriteButton.addEventListener('click', () => void onCopyRewrite());
    el.exportMdButton.addEventListener('click', exportMarkdown);
    el.printButton.addEventListener('click', () => state.result && window.print());
  }

  init();
})();