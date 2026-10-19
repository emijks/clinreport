'use strict';

// Review page of the ClinReport webapp. The server builds one context per
// sample (process), the page edits those contexts in place, and render/upload
// send the edited context back — the web version of the Tk confirmation windows.

const DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

const state = {
  source: {},        // {dbpath} or {job_id, username} as passed by the viewer widget
  dbpath: null,
  settings: {},
  reports: [],       // [{label, kind, is_target, filename, context}]
  layouts: {},
  activeTab: 0,
};

const $ = (id) => document.getElementById(id);

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'className') node.className = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

// --- server calls ---

class RequestError extends Error {
  constructor(message, trace) { super(message); this.trace = trace; }
}

async function request(method, action, payload) {
  let url = action;
  const options = { method };
  if (method === 'GET' && payload) {
    url += '?' + new URLSearchParams(payload).toString();
  } else if (payload !== undefined) {
    options.headers = { 'Content-Type': 'application/json' };
    options.body = JSON.stringify(payload);
  }
  let response;
  try {
    response = await fetch(url, options);
  } catch (e) {
    throw new RequestError('Нет связи с сервером OpenCRAVAT. Запущен ли oc gui?');
  }
  if (!response.ok) {
    let body = {};
    try { body = await response.json(); } catch (e) { /* not JSON */ }
    throw new RequestError(body.error || `HTTP ${response.status}`, body.traceback);
  }
  return response;
}

const getJSON = async (action, params) => (await request('GET', action, params)).json();
const postJSON = async (action, payload) => (await request('POST', action, payload)).json();
const postBlob = async (action, payload) => (await request('POST', action, payload)).blob();

// A job is addressed by job_id again (login mode accepts nothing else); a file by its resolved path.
function sourceParams() {
  return state.source.job_id || !state.dbpath ? state.source : { dbpath: state.dbpath };
}

// --- feedback ---

function notify(kind, text, { sticky = false } = {}) {
  const close = el('button', { type: 'button', 'aria-label': 'Закрыть', title: 'Закрыть' }, '×');
  const node = el('div', { className: `notice ${kind}` }, el('span', {}, text), close);
  close.addEventListener('click', () => node.remove());
  $('notices').append(node);
  if (!sticky) setTimeout(() => node.remove(), 6000);
}

function showError(error) {
  $('error-message').textContent = error.message || String(error);
  $('error-trace').textContent = error.trace || '';
  $('error-details').hidden = !error.trace;
  $('error-dialog').showModal();
}

async function busy(button, action) {
  button.disabled = true;
  button.classList.add('busy');
  try {
    return await action();
  } catch (error) {
    showError(error);
  } finally {
    button.disabled = false;
    button.classList.remove('busy');
  }
}

// --- open ---

async function openResult(params) {
  const data = await getJSON('open', params);
  state.dbpath = data.dbpath;
  state.settings = data.settings;
  $('file-name').textContent = data.filename;
  $('file-name').title = data.dbpath;
  document.title = `ClinReport · ${data.filename}`;

  const select = $('target');
  select.replaceChildren(...data.samples.map((s) => el('option', { value: s.index }, s.label)));
  $('open-card').hidden = true;
  $('process-card').hidden = false;
  updateClinicianLine();
}

function updateClinicianLine() {
  const parts = [];
  if (state.settings.multiuser) parts.push(`Пользователь: ${state.settings.username}`);
  parts.push(state.settings.clinician ? `Клиницист: ${state.settings.clinician}` : 'Клиницист не указан');
  $('clinician-line').textContent = parts.join(' · ');
}

// --- process ---

async function processResult(mode) {
  const data = await postJSON('process', { ...sourceParams(), target: $('target').value, mode });
  state.reports = data.reports;
  state.layouts = data.layouts;
  state.activeTab = 0;
  for (const warning of data.warnings) notify('warn', warning, { sticky: true });
  $('reports').hidden = false;  // visible first: autosize needs real layout
  renderReports();
  $('reports').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderReports() {
  const tabs = state.reports.map((report, i) => el('button', {
    type: 'button',
    className: 'tab',
    role: 'tab',
    'aria-selected': i === state.activeTab ? 'true' : 'false',
    onclick: () => { state.activeTab = i; renderReports(); },
  }, report.label, report.kind === '10x' ? el('span', { className: 'badge' }, 'LPWGS 10x')
    : (report.is_target && state.reports.length > 1 ? el('span', { className: 'badge' }, 'целевой') : null)));
  $('tabs').replaceChildren(...tabs);
  $('panels').replaceChildren(renderPanel(state.reports[state.activeTab]));
  requestAnimationFrame(() => {
    for (const area of $('panels').querySelectorAll('textarea')) autosize(area);
  });
}

function autosize(area) {
  if (!area.offsetParent) return;  // hidden: scrollHeight would be 0
  area.style.height = 'auto';
  area.style.height = area.scrollHeight + 2 + 'px';
}

function editableArea(value, onChange, className) {
  const original = value === null || value === undefined ? '' : String(value);
  const area = el('textarea', { rows: 1, className, spellcheck: 'false' });
  area.value = original;
  area.addEventListener('input', () => {
    onChange(area.value);
    area.classList.toggle('edited', area.value !== original);
    autosize(area);
  });
  return area;
}

function renderPanel(report) {
  const layout = state.layouts[report.kind];
  const context = report.context;

  // actions row
  // layout.templates: [{id, title}] (built-in + the lab's own); template_default: the user's choice
  const templateSelect = layout.templates.length > 1
    ? el('select', { 'aria-label': 'Шаблон' }, layout.templates.map((t) => el('option', { value: t.id }, t.title)))
    : null;
  if (templateSelect) {
    const ids = layout.templates.map((t) => t.id);
    templateSelect.value = ids.includes(report.template) ? report.template : layout.template_default;
  }
  if (templateSelect) templateSelect.addEventListener('change', () => { report.template = templateSelect.value; });

  const saveBtn = el('button', { type: 'button', className: 'btn primary' }, 'Сохранить как…');
  saveBtn.addEventListener('click', () => busy(saveBtn, () => saveReport(report, templateSelect)));
  const uploadBtn = layout.upload
    ? el('button', { type: 'button', className: 'btn', disabled: !state.settings.db_configured,
      title: state.settings.db_configured ? null : 'База данных не подключена на сервере' }, 'Выгрузить в базу')
    : null;
  if (uploadBtn) uploadBtn.addEventListener('click', () => busy(uploadBtn, () => uploadReport(report)));
  const clinbioBtn = state.settings.clinbio_enabled && report.kind === 'default'
    ? el('button', { type: 'button', className: 'btn', title: 'Заключение уйдёт в CLINBIO (office) и оттуда в лабораторию' },
      'Отправить в CLINBIO')
    : null;
  if (clinbioBtn) clinbioBtn.addEventListener('click', () => busy(clinbioBtn, () => sendClinbio(report, templateSelect)));

  const actions = el('div', { className: 'row panel-actions' },
    templateSelect ? el('label', { className: 'field-inline' }, 'Шаблон', templateSelect) : null,
    saveBtn, uploadBtn, clinbioBtn,
    el('span', { className: 'spacer' }),
    el('span', { className: 'muted' }, report.kind === '10x' ? 'Технический документ LPWGS (10x)' : `Дата заключения: ${context.report_date || ''}`),
  );

  // patient / tech fields
  const common = el('div', { className: 'common-grid' }, layout.common.map((f) => {
    const input = el('input', { type: 'text' });
    input.value = context[f.section][f.key] ?? '';
    input.addEventListener('input', () => { context[f.section][f.key] = input.value; });
    return el('label', { className: 'field' }, f.label, input);
  }));

  // variant tables
  const sections = layout.tables.map((table) => {
    const rows = context[table.key] || [];
    const head = el('div', { className: 'section-head' }, el('h3', {}, table.title),
      el('span', { className: 'count' }, rows.length ? `${rows.length}` : ''));
    if (!rows.length) return el('div', { className: 'section' }, head, el('p', { className: 'empty' }, 'Нет вариантов'));

    const header = el('tr', {}, table.columns.map((c) => el('th', {}, c.label)), layout.similar ? el('th', {}) : null);
    const body = rows.map((row) => el('tr', {},
      table.columns.map((c) => el('td', { className: `col-${c.field}` },
        editableArea(row[c.field], (v) => { row[c.field] = v; }))),
      layout.similar ? el('td', { className: 'actions' }, similarButton(row)) : null,
    ));
    return el('div', { className: 'section' }, head,
      el('div', { className: 'table-wrap' }, el('table', { className: 'variants' }, el('thead', {}, header), el('tbody', {}, body))));
  });

  return el('div', { className: 'panel', role: 'tabpanel' }, actions, common, sections);
}

// --- save / upload / similar ---

async function pickSaveTarget(filename) {
  if (!window.showSaveFilePicker) return null;
  try {
    return await window.showSaveFilePicker({
      suggestedName: filename,
      types: [{ description: 'Документ Word', accept: { [DOCX_MIME]: ['.docx'] } }],
    });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    return null;  // picker unavailable (e.g. not a secure context): fall back to a download
  }
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = el('a', { href: url, download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function saveReport(report, templateSelect) {
  let handle;
  try {
    handle = await pickSaveTarget(report.filename);  // ask first, while the click still counts as a user gesture
  } catch (e) {
    return;  // user cancelled
  }
  const blob = await postBlob('render', {
    context: report.context,
    kind: report.kind,
    template: templateSelect ? templateSelect.value : null,
    filename: handle ? handle.name : report.filename,
  });
  if (handle) {
    const writable = await handle.createWritable();
    await writable.write(blob);
    await writable.close();
  } else {
    downloadBlob(blob, report.filename);
  }
  const name = handle ? handle.name : report.filename;
  if (report.kind === 'default' && state.settings.auto_upload && state.settings.db_configured) {
    const inserted = await uploadReport(report, { quiet: true });
    notify('ok', inserted === null ? `Документ сохранён: ${name}` : `Документ сохранён (${name}) и данные выгружены в БД`);
  } else {
    notify('ok', `Документ сохранён: ${name}`);
  }
}

async function uploadReport(report, { quiet = false } = {}) {
  let result = await postJSON('upload', { context: report.context });
  if (result.duplicate) {
    if (!confirm(`Для образца "${result.sample}" уже есть записи в БД. Записать ещё?`)) return null;
    result = await postJSON('upload', { context: report.context, force: true });
  }
  if (!quiet) notify('ok', `${result.inserted} вариант(ов) успешно выгружены`);
  return result.inserted;
}

// CLINBIO: office checks the sample is assigned to the logged-in clinician and emails the conclusion on.
async function sendClinbio(report, templateSelect) {
  if (!confirm(`Отправить заключение по образцу ${report.label} в CLINBIO?\nОно будет передано в лабораторию.`)) return;
  const payload = {
    context: report.context,
    kind: report.kind,
    template: templateSelect ? templateSelect.value : null,
    filename: report.filename,
    sample: report.label,
  };
  let result = await postJSON('send_clinbio', payload);
  if (result.already_sent) {
    if (!confirm(result.message)) return;
    result = await postJSON('send_clinbio', { ...payload, replace: true });
  }
  notify('ok', `Заключение по образцу ${result.sample} отправлено в CLINBIO (задача ${result.issue}). ` +
    'Статус отправки — в office, раздел CLINBIO.', { sticky: true });
}

function similarButton(row) {
  const button = el('button', {
    type: 'button', className: 'btn small',
    disabled: !state.settings.db_configured,
    title: state.settings.db_configured ? 'Ранее выгруженные варианты с тем же изменением ДНК' : 'База данных не подключена на сервере',
  }, 'Похожие');
  button.addEventListener('click', () => busy(button, () => showSimilar(row)));
  return button;
}

async function showSimilar(row) {
  const { rows } = await postJSON('similar', { variant: row });
  const columns = ['Номер образца', 'Патогенность', 'Клиницист', 'Дата заключения'];
  $('similar-title').textContent = `Похожие варианты для ${row.gene || ''}`;
  $('similar-body').replaceChildren(rows.length
    ? el('table', {}, el('thead', {}, el('tr', {}, columns.map((c) => el('th', {}, c)))),
      el('tbody', {}, rows.map((r) => el('tr', {}, columns.map((c) => el('td', {}, r[c] ?? ''))))))
    : el('p', { className: 'muted' }, 'В базе нет ранее выгруженных вариантов с этим изменением.'));
  $('similar-dialog').showModal();
}

// --- settings ---

// Clinician, template and auto-upload are the logged-in user's own. The database connection is the server's
// (CLINREPORT_DB_*): the page only knows whether it is there (db_configured).
async function openSettings() {
  const [settings, listing] = await Promise.all([getJSON('settings'), getJSON('templates')]);
  $('default-template').replaceChildren(...listing.templates.filter((t) => t.kind === 'default')
    .map((t) => el('option', { value: t.id }, t.title)));
  const form = $('settings-form');
  form.reset();
  for (const [key, value] of Object.entries(settings)) {
    const input = form.elements.namedItem(key);
    if (!input) continue;
    if (input.type === 'checkbox') input.checked = Boolean(value);
    else input.value = value ?? '';
  }

  $('settings-user').hidden = !settings.multiuser;
  $('settings-user').textContent = `Настройки пользователя ${settings.username}`;
  $('auto-upload-row').hidden = !settings.db_configured;
  $('settings-dialog').showModal();
}

async function saveSettings() {
  const form = $('settings-form');
  const payload = {};
  for (const input of form.querySelectorAll('input[name], select[name]')) {
    if (input.matches(':disabled')) continue;
    payload[input.name] = input.type === 'checkbox' ? input.checked : input.value;
  }
  state.settings = await postJSON('settings', payload);
  updateClinicianLine();
  if (state.reports.length) renderReports();  // enable/disable DB buttons
  notify('ok', 'Настройки сохранены');
}

// --- templates ---

const tplState = { listing: null, open: new Set(), confirmDelete: null };

async function openTemplates() {
  await loadTemplates();
  $('templates-dialog').showModal();
}

async function loadTemplates() {
  const listing = await getJSON('templates');
  tplState.listing = listing;
  $('tpl-kind').replaceChildren(...Object.entries(listing.kinds).map(([k, title]) => el('option', { value: k }, title)));
  $('template-add-form').hidden = !listing.editable;
  $('templates-readonly').hidden = listing.editable;
  renderTemplates();
  refreshTemplateChoices(listing.templates);
}

function checkSummary(check) {
  if (!check) return null;
  return check.ok ? el('span', { className: 'chip ok' }, 'поля проверены')
    : el('span', { className: 'chip warn' }, `неизвестных полей: ${check.unknown.length}`);
}

function checkDetails(check) {
  if (!check) return null;
  if (check.ok) return el('div', { className: 'tpl-check ok' }, 'Шаблон собран на примере заключения, все поля найдены.');
  return el('div', { className: 'tpl-check warn' },
    el('div', {}, 'Этих полей нет в данных заключения, в документе они останутся пустыми:'),
    check.unknown.map((u) => el('div', {}, el('code', {}, `{{ ${u.field} }}`),
      u.suggestion ? [' — возможно, ', el('code', {}, u.suggestion)] : null)));
}

function renderTemplates() {
  const { listing } = tplState;
  $('templates-list').replaceChildren(...listing.templates.map((t) => {
    const download = el('button', { type: 'button', className: 'btn small' }, 'Скачать');
    download.addEventListener('click', () => busy(download, () => downloadTemplate(t)));
    const check = el('button', { type: 'button', className: 'btn small' }, 'Проверить');
    check.addEventListener('click', () => busy(check, async () => {
      t.check = await postJSON('template_check', { id: t.id });
      tplState.open.add(t.id);
      renderTemplates();
    }));
    const actions = [download, check];
    if (!t.builtin && listing.editable) {
      if (tplState.confirmDelete === t.id) {
        const yes = el('button', { type: 'button', className: 'btn small' }, 'Удалить');
        yes.addEventListener('click', () => busy(yes, async () => {
          await postJSON('template_delete', { id: t.id });
          tplState.confirmDelete = null;
          notify('ok', `Шаблон «${t.title}» удалён`);
          await loadTemplates();
        }));
        const no = el('button', { type: 'button', className: 'btn small ghost' }, 'Отмена');
        no.addEventListener('click', () => { tplState.confirmDelete = null; renderTemplates(); });
        actions.push(el('span', { className: 'muted' }, 'Удалить шаблон?'), yes, no);
      } else {
        const replace = el('button', { type: 'button', className: 'btn small' }, 'Заменить…');
        replace.addEventListener('click', () => pickFile((file) => busy(replace, () => uploadTemplate(file, t.title, t.kind, t.id))));
        const remove = el('button', { type: 'button', className: 'btn small ghost' }, 'Удалить');
        remove.addEventListener('click', () => { tplState.confirmDelete = t.id; renderTemplates(); });
        actions.push(replace, remove);
      }
    }
    return el('div', { className: 'tpl-row' },
      el('div', { className: 'tpl-name' }, t.title),
      el('div', { className: 'tpl-actions' }, actions),
      el('div', { className: 'tpl-meta' },
        el('span', { className: t.builtin ? 'chip plain' : 'chip info' }, t.builtin ? 'встроенный' : 'свой'),
        el('span', {}, listing.kinds[t.kind] || t.kind),
        t.added ? el('span', {}, `добавлен ${new Date(t.added).toLocaleDateString('ru-RU')}`) : null,
        checkSummary(t.check)),
      tplState.open.has(t.id) ? checkDetails(t.check) : null);
  }));
}

// New templates show up in the open reports' template choice without re-processing.
function refreshTemplateChoices(templates) {
  for (const [kind, lay] of Object.entries(state.layouts)) {
    lay.templates = templates.filter((t) => t.kind === kind).map((t) => ({ id: t.id, title: t.title }));
  }
  if (state.reports.length) renderReports();
}

function pickFile(onFile) {
  const input = el('input', { type: 'file', accept: '.docx' });
  input.addEventListener('change', () => { if (input.files[0]) onFile(input.files[0]); });
  input.click();
}

async function fileToBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

async function uploadTemplate(file, title, kind, replace) {
  if (tplState.listing && file.size > tplState.listing.max_bytes) {
    throw new RequestError(`Файл больше ${Math.round(tplState.listing.max_bytes / 1048576)} МБ — уменьшите картинки в шаблоне.`);
  }
  const { template } = await postJSON('template_add', { title, kind, data: await fileToBase64(file), replace: replace || '' });
  tplState.open.add(template.id);
  notify(template.check.ok ? 'ok' : 'warn', template.check.ok
    ? `Шаблон «${template.title}» добавлен и проверен`
    : `Шаблон «${template.title}» добавлен, но в нём есть неизвестные поля`);
  await loadTemplates();
}

async function downloadTemplate(t) {
  const response = await request('GET', 'template_file', { id: t.id });
  downloadBlob(await response.blob(), `${t.title}.docx`);
}

async function toggleFields(button) {
  const box = $('tpl-fields');
  if (!box.hidden) { box.hidden = true; button.setAttribute('aria-expanded', 'false'); return; }
  const fields = await getJSON('template_fields');
  box.replaceChildren(...Object.entries(fields).map(([kind, paths]) => el('div', {},
    el('h3', {}, tplState.listing ? tplState.listing.kinds[kind] : kind),
    el('ul', {}, paths.map((p) => el('li', {}, el('code', {}, p)))))));
  box.hidden = false;
  button.setAttribute('aria-expanded', 'true');
}

// --- wiring ---

function init() {
  const params = new URLSearchParams(location.search);
  for (const key of ['dbpath', 'job_id', 'username']) {
    if (params.get(key)) state.source[key] = params.get(key);
  }

  $('process-btn').addEventListener('click', (e) => busy(e.currentTarget, () => processResult('default')));
  $('process-lpwgs-btn').addEventListener('click', (e) => busy(e.currentTarget, () => processResult('lpwgs')));
  $('settings-btn').addEventListener('click', () => openSettings().catch(showError));
  $('templates-btn').addEventListener('click', () => openTemplates().catch(showError));
  $('templates-close').addEventListener('click', () => $('templates-dialog').close());
  $('tpl-file').addEventListener('change', () => {
    const file = $('tpl-file').files[0];
    if (file && !$('tpl-title').value) $('tpl-title').value = file.name.replace(/\.docx$/i, '');
  });
  $('template-add-form').addEventListener('submit', (e) => {
    e.preventDefault();
    busy($('tpl-add-btn'), async () => {
      await uploadTemplate($('tpl-file').files[0], $('tpl-title').value.trim(), $('tpl-kind').value);
      $('template-add-form').reset();
    });
  });
  $('tpl-sample-btn').addEventListener('click', (e) => busy(e.currentTarget, () => downloadTemplate({ id: 'DZM', title: 'Образец DZM' })));
  $('tpl-fields-btn').addEventListener('click', (e) => busy(e.currentTarget, () => toggleFields(e.currentTarget)));
  $('settings-cancel').addEventListener('click', () => $('settings-dialog').close());
  $('settings-form').addEventListener('submit', (e) => {
    e.preventDefault();
    saveSettings().then(() => $('settings-dialog').close()).catch(showError);
  });
  $('similar-close').addEventListener('click', () => $('similar-dialog').close());
  $('error-close').addEventListener('click', () => $('error-dialog').close());
  $('open-form').addEventListener('submit', (e) => {
    e.preventDefault();
    state.source = { dbpath: $('open-path').value.trim().replace(/^"|"$/g, '') };
    openResult(state.source).catch(showError);
  });

  if (state.source.dbpath || state.source.job_id) {
    openResult(state.source).catch((error) => { $('open-card').hidden = false; showError(error); });
  } else {
    $('open-card').hidden = false;
    getJSON('settings').then((s) => { state.settings = s; }).catch(() => {});
  }
}

init();
