'use strict';

// ClinReport launcher window. Everything goes through window.pywebview.api (clinreport_desktop/api.py);
// each call resolves to data or to {error: "..."} for problems the user should see.

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
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

class ApiError extends Error {}

async function call(method, ...args) {
  const result = await window.pywebview.api[method](...args);
  if (result && result.error) throw new ApiError(result.error);
  return result;
}

// --- feedback ---

let toastTimer;
function toast(text) {
  const node = $('toast');
  node.textContent = text;
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, 2600);
}

function notify(kind, text) {
  const close = el('button', { type: 'button', 'aria-label': 'Закрыть' }, '×');
  const node = el('div', { className: `notice ${kind}` }, el('span', {}, text), close);
  close.addEventListener('click', () => node.remove());
  $('notices').append(node);
  if (kind !== 'err') setTimeout(() => node.remove(), 8000);
}

async function busy(button, action) {
  if (button) button.disabled = true;
  try {
    return await action();
  } catch (error) {
    notify('err', error.message || String(error));
    return undefined;
  } finally {
    if (button) button.disabled = false;
  }
}

const pad = (n) => String(n).padStart(2, '0');
const duration = (s) => `${pad(Math.floor(s / 3600))}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}`;
const clock = (epoch) => { const d = new Date(epoch * 1000); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };

function when(epoch) {
  if (!epoch) return '';
  const d = new Date(epoch * 1000);
  const today = new Date();
  const yesterday = new Date(); yesterday.setDate(today.getDate() - 1);
  const time = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  if (d.toDateString() === today.toDateString()) return `сегодня ${time}`;
  if (d.toDateString() === yesterday.toDateString()) return `вчера ${time}`;
  return d.toLocaleDateString('ru-RU');
}

// --- tabs ---

const TABS = ['overview', 'templates', 'environments', 'settings', 'log'];
let currentTab = 'overview';
function show(name) {
  currentTab = name;
  for (const t of TABS) {
    $('tab-' + t).setAttribute('aria-selected', String(t === name));
    $('p-' + t).hidden = t !== name;
  }
  if (name === 'templates') loadTemplates();
  if (name === 'environments') loadEnvironments();
  if (name === 'settings') loadSettings();
  if (name === 'log') loadLog();
  if (name === 'overview') loadRecent();
}

// --- state (polled) ---

const STATE_TEXT = {
  starting: 'Запуск OpenCRAVAT…', running: 'OpenCRAVAT работает', stopping: 'Остановка…',
  stopped: 'OpenCRAVAT остановлен', failed: 'OpenCRAVAT не запустился',
};
let last = null;
let shuttingDown = false;

// Called by the launcher (App._close_after_stopping) while the window closes: cover the page, stop polling.
window.clinreportShutdown = function (text, done) {
  shuttingDown = true;
  $('shutdown').hidden = false;
  $('shutdown-text').textContent = text;
  $('shutdown-bar').className = done ? 'bar' : 'bar busy';
  if (done) $('shutdown-bar').firstElementChild.style.width = '100%';
};
let shownEnvNotice = null;
let serverCall = null;  // 'start' | 'stop' while the window waits for that call

// Открыть: only while running. One server button: Остановить while running or starting (cancels it),
// Запустить otherwise. While a start/stop call is on its way, both wait for it.
function renderControls() {
  const s = last ? last.server.state : 'unknown';
  const running = s === 'running';
  const waiting = Boolean(serverCall);
  $('open-oc').disabled = waiting || !running;
  $('open-result').disabled = s === 'stopping';  // when stopped, opening a result starts OpenCRAVAT
  const stops = running || s === 'starting';
  const toggle = $('toggle-server');
  toggle.textContent = stops ? 'Остановить' : 'Запустить';
  toggle.className = stops ? 'btn stop' : 'btn go';
  toggle.disabled = waiting || !(stops || s === 'stopped' || s === 'failed');
}

async function serverAction(method) {
  serverCall = method;
  renderControls();
  try {
    await call(method);
  } catch (error) {
    notify('err', error.message || String(error));
  } finally {
    serverCall = null;
    await refreshState();
  }
}

async function refreshState() {
  if (shuttingDown) return;
  let state;
  try {
    state = await call('state');
  } catch (error) {
    return;
  }
  last = state;
  window.__clinreportState = { server: state.server.state, port: state.server.port };
  const s = state.server;
  for (const dot of [$('hero-dot'), $('mini-dot')]) dot.className = `dot ${s.state}`;
  $('hero-state').textContent = STATE_TEXT[s.state] || s.state;
  $('mini-state').textContent = s.state === 'running' ? `Работает · порт ${s.port}` : STATE_TEXT[s.state];

  const meta = [];
  if (s.state === 'running') {
    meta.push(el('span', {}, el('button', { type: 'button', className: 'link', onclick: () => busy(null, () => call('open_oc')) }, s.url)));
    meta.push(el('span', {}, 'запущен ', el('b', {}, clock(s.started_at))));
    meta.push(el('span', {}, 'время работы ', el('b', {}, duration(s.uptime))));
    if (s.environment && s.environment !== 'Встроенное') meta.push(el('span', {}, 'окружение ', el('b', {}, s.environment)));
  } else if (s.state === 'stopped') {
    meta.push(el('span', {}, 'Нажмите «Запустить» или откройте результат — OpenCRAVAT запустится.'));
  } else if (s.state === 'starting') {
    meta.push(el('span', {}, 'Первый запуск после установки или обновления занимает до минуты.'));
  }
  $('hero-meta').replaceChildren(...meta);
  $('hero-error').hidden = s.state !== 'failed';
  $('hero-error').textContent = s.error || '';

  renderControls();

  if (state.env_notice && state.env_notice !== shownEnvNotice) { shownEnvNotice = state.env_notice; notify('warn', state.env_notice); }
  const v = state.versions;
  $('brand-version').textContent = `версия ${v.app}`;
  $('foot').textContent = `Данные: ${state.data_dir}`;
  renderComponents(state);
  renderChecks(state);
  const bad = state.checks.templates_bad;
  $('tpl-count').textContent = bad ? `${bad} ⚠` : state.checks.templates_total;
  $('tpl-count').className = bad ? 'count warn' : 'count';
}

function renderComponents(state) {
  const v = state.versions;
  const update = state.update || {};
  const updateChip = update.newer ? updateControl(update) : null;
  const modules = state.modules.map((m) => el('span', { className: m.ok ? 'chip ok' : 'chip err', title: m.version ? `версия ${m.version}` : 'не установлен' }, m.name));
  $('components').replaceChildren(
    el('dt', {}, 'ClinReport'), el('dd', {}, el('span', {}, v.app), updateChip),
    el('dt', {}, 'Расширение'), el('dd', {}, v.extension),
    el('dt', {}, 'OpenCRAVAT'), el('dd', {}, v.opencravat),
    el('dt', {}, 'Python'), el('dd', {}, v.python),
    el('dt', {}, 'Модули'), el('dd', {}, modules),
  );
}

let updateConfirm = false;

function updateControl(update) {
  if (update.state === 'downloading') {
    const pct = update.total ? Math.floor((100 * update.done) / update.total) : 0;
    return el('span', { className: 'chip plain' }, `загрузка ${update.version}: ${pct}%`);
  }
  if (update.state === 'installing') return el('span', { className: 'chip plain' }, `установка ${update.version}…`);
  const label = update.can_install ? `обновить до ${update.version}` : `доступна ${update.version}`;
  const title = update.install_error ? `Не удалось: ${update.install_error}`
    : update.can_install ? 'Скачать и установить; ClinReport перезапустится, настройки и шаблоны сохранятся'
      : 'Открыть страницу выпуска';
  const install = () => busy(null, async () => {
    updateConfirm = false;
    await call('install_update');
    refreshState();
  });
  if (updateConfirm) {
    return el('span', { className: 'confirm neutral' }, `Установить ${update.version}? ClinReport закроется и запустится снова.`,
      el('button', { className: 'btn sm primary', type: 'button', onclick: install }, 'Установить'),
      el('button', { className: 'btn sm ghost', type: 'button', onclick: () => { updateConfirm = false; refreshState(); } }, 'Отмена'));
  }
  return el('button', {
    type: 'button', className: update.install_error ? 'chip warn' : 'chip info', title,
    onclick: update.can_install ? () => { updateConfirm = true; refreshState(); } : install,
  }, label);
}

function ruChip(ru) {
  if (!ru || ru.state === 'pending') return el('span', { className: 'chip plain' }, 'после запуска');
  if (ru.state === 'loading') return el('span', { className: 'chip plain' }, 'загружаются…');
  if (ru.state === 'ok') {
    const time = ru.loaded_at ? ru.loaded_at.slice(11, 16) : '';
    return el('span', { className: 'chip ok', title: Object.entries(ru.counts || {}).map(([k, n]) => `${k}: ${n}`).join(', ') }, `загружены ${time}`);
  }
  return el('span', { className: 'chip warn', title: ru.warning || '' }, 'нет связи — английский OMIM');
}

function storeChip(store) {
  if (!store || store.state === 'pending' || store.state === 'checking') return el('span', { className: 'chip plain' }, 'проверяется…');
  if (store.state === 'ok') return el('span', { className: 'chip ok' }, 'доступен');
  return el('span', { className: 'chip warn', title: `${store.error || ''}
Модули из магазина OpenCRAVAT не установятся. Часто причина — VPN: отключите его на время установки.` },
    'недоступен — VPN?');
}

function renderChecks(state) {
  const c = state.checks;
  $('checks').replaceChildren(
    el('dt', {}, 'Клиницист'), el('dd', {}, c.clinician || el('span', { className: 'chip warn' }, 'не указан'),
      c.clinician ? null : el('button', { type: 'button', className: 'btn sm ghost', onclick: () => show('settings') }, 'Указать')),
    el('dt', {}, 'Аннотации RU'), el('dd', {}, ruChip(state.ru)),
    el('dt', {}, 'Магазин модулей'), el('dd', {}, storeChip(state.store),
      el('button', { type: 'button', className: 'btn sm ghost', onclick: (e) => busy(e.currentTarget, async () => {
        const s = await call('check_store'); toast(s.state === 'ok' ? 'Магазин модулей доступен' : 'Магазин модулей недоступен');
      }) }, 'Проверить')),
    el('dt', {}, 'Шаблоны'), el('dd', {}, c.templates_bad
      ? el('button', { type: 'button', className: 'chip warn', onclick: () => show('templates') }, `${c.templates_bad} с неизвестными полями`)
      : el('span', { className: 'chip ok' }, `${c.templates_total} в порядке`)),
    el('dt', {}, 'Доступ'), el('dd', {}, 'только этот компьютер'),
  );
}

// --- recent results ---

function queuedToast(result) {
  if (result && result.queued) toast('OpenCRAVAT запускается — результат откроется, когда он будет готов');
}

async function openResult(path, target) {
  queuedToast(await call('open_or_start', path, target));
  refreshState();
  loadRecent();
}

async function loadRecent() {
  const box = $('recent');
  let data;
  try { data = await call('recent'); } catch (error) { box.replaceChildren(el('p', { className: 'empty' }, error.message)); return; }
  if (!data.items.length) {
    box.replaceChildren(el('p', { className: 'empty' },
      'Здесь появятся открытые файлы. Нажмите «Открыть результат…» и выберите .sqlite из OpenCRAVAT.'));
    return;
  }
  const stopping = Boolean(last && last.server.state === 'stopping');
  box.replaceChildren(...data.items.map((r) => {
    const acts = r.exists ? [
      el('button', { className: 'btn sm', type: 'button', disabled: stopping, onclick: (e) => busy(e.currentTarget, () => openResult(r.path, 'viewer')) }, 'Просмотр'),
      el('button', { className: 'btn sm primary', type: 'button', disabled: stopping, onclick: (e) => busy(e.currentTarget, () => openResult(r.path, 'report')) }, 'Заключение'),
    ] : [el('button', { className: 'btn sm ghost', type: 'button', onclick: async () => { await call('forget_result', r.path); loadRecent(); } }, 'Убрать')];
    const sub = [];
    if (!r.exists) sub.push(el('span', { className: 'chip warn' }, 'файл не найден'));
    if (r.samples) sub.push(el('span', {}, r.samples.join(', ')));
    if (r.marked !== undefined) {
      sub.push(r.marked ? el('span', { className: 'chip info' }, `отмечено ${r.marked}`) : el('span', { className: 'chip plain' }, 'нет отметок'));
    }
    sub.push(el('span', {}, when(r.opened)));
    sub.push(el('span', { className: 'mono' }, r.dir));
    return el('div', { className: r.exists ? 'item' : 'item missing' },
      el('div', { className: 'name' }, r.name), el('div', { className: 'acts' }, acts), el('div', { className: 'sub' }, sub));
  }));
}

// --- templates ---

const tpl = { listing: null, open: new Set(), confirm: null, adding: null };

async function loadTemplates() {
  await busy(null, async () => {
    tpl.listing = await call('templates');
    $('add-kind').replaceChildren(...Object.entries(tpl.listing.kinds).map(([k, title]) => el('option', { value: k }, title)));
    renderTemplates();
  });
}

function checkDetails(check) {
  if (!check) return null;
  if (check.error) return el('div', { className: 'check warn' }, check.error);
  if (check.ok) return el('div', { className: 'check ok' }, 'Тестовое заключение собрано, все поля найдены.');
  return el('div', { className: 'check warn' },
    el('span', {}, 'Этих полей нет в данных заключения, в документе они останутся пустыми:'),
    check.unknown.map((u) => el('span', {}, el('code', {}, `{{ ${u.field} }}`), u.suggestion ? [' — возможно, ', el('code', {}, u.suggestion)] : null)));
}

function renderTemplates() {
  const { listing } = tpl;
  if (!listing) return;
  $('add-tpl').hidden = !listing.editable;
  $('tpl-list').replaceChildren(...listing.templates.map((t) => {
    const acts = [];
    if (tpl.confirm === t.id) {
      acts.push(el('span', { className: 'confirm' }, 'Удалить шаблон?',
        el('button', { className: 'btn sm danger', type: 'button', onclick: (e) => busy(e.currentTarget, async () => {
          await call('template_delete', t.id); tpl.confirm = null; toast(`Шаблон «${t.title}» удалён`); await loadTemplates(); refreshState();
        }) }, 'Удалить'),
        el('button', { className: 'btn sm ghost', type: 'button', onclick: () => { tpl.confirm = null; renderTemplates(); } }, 'Отмена')));
    } else {
      acts.push(el('button', { className: 'btn sm', type: 'button', onclick: (e) => busy(e.currentTarget, async () => {
        const r = await call('template_save', t.id); if (!r.cancelled) toast(`Сохранено: ${r.path}`);
      }) }, 'Сохранить…'));
      acts.push(el('button', { className: 'btn sm', type: 'button', onclick: (e) => busy(e.currentTarget, async () => {
        t.check = await call('template_check', t.id); tpl.open.add(t.id); renderTemplates();
      }) }, 'Проверить'));
      if (!t.builtin && listing.editable) {
        acts.push(el('button', { className: 'btn sm', type: 'button', onclick: (e) => busy(e.currentTarget, async () => {
          const file = await call('pick_docx'); if (file.cancelled) return;
          const r = await call('template_add', file.path, t.title, t.kind, t.id);
          tpl.open.add(r.template.id); toast(`Шаблон «${t.title}» заменён`); await loadTemplates(); refreshState();
        }) }, 'Заменить…'));
        acts.push(el('button', { className: 'btn sm ghost danger', type: 'button', onclick: () => { tpl.confirm = t.id; renderTemplates(); } }, 'Удалить'));
      }
    }
    const sub = [
      el('span', { className: t.builtin ? 'chip plain' : 'chip info' }, t.builtin ? 'встроенный' : 'свой'),
      el('span', {}, listing.kinds[t.kind] || t.kind),
      t.added ? el('span', {}, `добавлен ${new Date(t.added).toLocaleDateString('ru-RU')}`) : null,
      t.id === listing.default_template ? el('span', { className: 'chip plain' }, 'по умолчанию') : null,
      t.check ? (t.check.ok ? el('span', { className: 'chip ok' }, 'проверен')
        : el('button', { type: 'button', className: 'chip warn', onclick: () => { tpl.open.add(t.id); renderTemplates(); } },
          `неизвестных полей: ${(t.check.unknown || []).length}`)) : null,
    ];
    return el('div', { className: 'item' },
      el('div', { className: 'name' }, t.title), el('div', { className: 'acts' }, acts), el('div', { className: 'sub' }, sub),
      tpl.open.has(t.id) ? checkDetails(t.check) : null);
  }));
}

async function startAdd() {
  const file = await call('pick_docx');
  if (file.cancelled) return;
  tpl.adding = file;
  $('add-file').value = file.path;
  $('add-title').value = file.title;
  $('add-form').hidden = false;
  $('add-title').focus();
  $('add-title').select();
}

async function submitAdd() {
  const r = await call('template_add', tpl.adding.path, $('add-title').value.trim(), $('add-kind').value, '');
  $('add-form').hidden = true;
  tpl.adding = null;
  tpl.open.add(r.template.id);
  if (r.template.check.ok) toast(`Шаблон «${r.template.title}» добавлен и проверен`);
  else notify('warn', `Шаблон «${r.template.title}» добавлен, но в нём есть поля, которых нет в данных заключения.`);
  await loadTemplates();
  refreshState();
}

async function toggleFields() {
  const box = $('fields-box');
  const button = $('fields-tpl');
  if (!box.hidden) { box.hidden = true; button.setAttribute('aria-expanded', 'false'); return; }
  const fields = await call('template_fields');
  const kinds = tpl.listing ? tpl.listing.kinds : {};
  box.replaceChildren(el('h3', {}, 'Поля для шаблонов'),
    el('p', { className: 'hint' }, 'Поле вида p_variants[].gene используется внутри цикла: {%tr for v in p_variants %} … {{ v.gene }} … {%tr endfor %}.'),
    el('div', { className: 'fields-cols' }, Object.entries(fields).map(([kind, list]) => el('div', {},
      el('b', {}, kinds[kind] || kind), el('ul', {}, list.map((f) => el('li', {}, f)))))));
  box.hidden = false;
  button.setAttribute('aria-expanded', 'true');
}

// --- settings ---

let loadedSettings = null;

async function loadSettings() {
  await busy(null, async () => {
    const s = await call('settings');
    loadedSettings = s;
    const r = s.report;
    $('s-clinician').value = r.clinician || '';
    $('s-template').replaceChildren(...s.default_templates.map((t) => el('option', { value: t.id }, t.title)));
    $('s-template').value = s.default_template;
    $('s-browser-at-start').checked = Boolean(s.launcher.open_browser_at_start);
    $('s-start-at-launch').checked = Boolean(s.launcher.start_server_at_launch);
    $('s-autostart').checked = Boolean(s.launcher.autostart);
    $('s-prerelease').checked = Boolean(s.launcher.update_prerelease);
    $(s.launcher.port_mode === 'fixed' ? 's-port-fixed' : 's-port-auto').checked = true;
    $('s-port-value').value = s.launcher.port;
    $('s-data-dir').textContent = s.data_dir;
    renderRu();
  });
}

function renderRu() {
  const ru = last && last.ru;
  const text = !ru || ru.state === 'pending' ? 'загрузятся после запуска сервера'
    : ru.state === 'loading' ? 'загружаются…'
      : ru.state === 'ok' ? `загружены ${(ru.loaded_at || '').replace('T', ' ').slice(0, 16)} (${Object.values(ru.counts || {}).join(' + ')} записей)`
        : `не загружены: ${ru.warning || ''}`;
  $('s-ru').textContent = text;
}

async function saveSettings() {
  const report = { clinician: $('s-clinician').value, template: $('s-template').value };
  const launcher = {
    open_browser_at_start: $('s-browser-at-start').checked, start_server_at_launch: $('s-start-at-launch').checked,
    autostart: $('s-autostart').checked,
    update_prerelease: $('s-prerelease').checked,
    port_mode: $('s-port-fixed').checked ? 'fixed' : 'auto', port: Number($('s-port-value').value) || 8080,
  };
  const result = await call('save_settings', report, launcher);
  toast('Настройки сохранены');
  if (result.restart_needed) notify('warn', 'Новый порт начнёт действовать после перезапуска сервера (кнопки «Остановить» → «Запустить»).');
  refreshState();
}

// --- environments ---

const KIND = {
  builtin: 'встроенное', venv: 'pip · venv', conda: 'conda', pipx: 'pipx', pyenv: 'pyenv',
  system: 'системный Python', installer: 'установщик OpenCRAVAT', data: 'только данные',
};
const KIND_WORDS = {
  builtin: 'Python и OpenCRAVAT поставляются вместе с ClinReport и обновляются вместе с ним.',
  venv: 'OpenCRAVAT установлен через pip в виртуальное окружение Python.',
  conda: 'OpenCRAVAT установлен в окружение conda.',
  pipx: 'OpenCRAVAT установлен через pipx.',
  pyenv: 'OpenCRAVAT установлен в Python, которым управляет pyenv.',
  system: 'OpenCRAVAT установлен в общий Python компьютера.',
  installer: 'OpenCRAVAT установлен его собственным установщиком.',
  data: 'Найдена папка OpenCRAVAT (модули, задания), но Python, в котором он установлен, не найден.',
};
const LEVEL_CHIP = { ok: 'ok', warn: 'warn', bad: 'err' };
const envUi = { data: null, selected: null, details: {}, confirm: null, pro: 'paths', pkgQuery: '', fetching: false };

const envBusy = () => Boolean(envUi.data && (envUi.data.search.running
  || Object.values(envUi.data.jobs).some((j) => j.state === 'running')));

let lastEnvLoad = 0;
async function loadEnvironments(force) {
  if (envUi.fetching) return;
  if (!force && !envBusy() && Date.now() - lastEnvLoad < 5000 && envUi.data) return;
  envUi.fetching = true;
  try {
    const before = envUi.data;
    envUi.data = await call('env_list');
    lastEnvLoad = Date.now();
    if (!envUi.selected || !envUi.data.items.some((e) => e.id === envUi.selected)) {
      envUi.selected = envUi.data.chosen && envUi.data.items.some((e) => e.id === envUi.data.chosen) ? envUi.data.chosen : 'builtin';
    }
    // a job just finished: forget cached details so the packages/modules shown are fresh
    for (const [id, job] of Object.entries(envUi.data.jobs)) {
      const was = before && before.jobs[id];
      if (was && was.state === 'running' && job.state !== 'running') {
        delete envUi.details[id];
        if (job.state === 'done') toast(job.action === 'install' ? `Модули ClinReport ${job.version} установлены` : 'Модули ClinReport удалены');
      }
    }
    if (before && before.search.running && !envUi.data.search.running) envUi.details = {};
    renderEnvironments();
  } catch (error) {
    notify('err', error.message || String(error));
  } finally {
    envUi.fetching = false;
  }
}

async function startSearch(deep) {
  await call('env_search', deep);
  await loadEnvironments(true);
}

function renderEnvironments() {
  const data = envUi.data;
  if (!data) return;
  const running = envBusy();
  $('env-search').disabled = data.search.running;
  $('env-search-deep').disabled = data.search.running;
  renderSearch(data.search);
  $('env-list').replaceChildren(...data.items.map(envRow));
  const env = data.items.find((e) => e.id === envUi.selected);
  $('env-detail').hidden = !env;
  if (env) renderEnvDetail(env);
  void running;
}

function renderSearch(s) {
  const box = $('env-search-box');
  if (!s.running && !s.finished_at) { box.hidden = true; return; }
  box.hidden = false;
  if (s.running) {
    const counts = s.total ? `проверено ${s.checked} из ${s.total}` : 'собираю список Python…';
    const deepLine = s.deep && s.visited ? `просмотрено папок: ${s.visited.toLocaleString('ru-RU')}` : '';
    box.replaceChildren(
      el('div', { className: 'head' }, el('b', {}, s.phase || 'Поиск…'), el('span', { className: 'hint', style: 'margin:0' },
        [counts, deepLine, `найдено: ${s.found}`].filter(Boolean).join(' · ')),
      el('span', { className: 'spacer' }),
      el('button', { className: 'btn sm', type: 'button', onclick: (e) => busy(e.currentTarget, () => call('env_search_cancel')) }, 'Остановить поиск')),
      el('div', { className: s.total ? 'bar' : 'bar busy' }, el('i', { style: s.total ? `width:${Math.round((100 * s.checked) / s.total)}%` : '' })),
      ...(s.current ? [el('div', { className: 'current' }, s.current)] : []));
    return;
  }
  const text = s.cancelled ? 'Поиск остановлен.' : `Поиск завершён${s.deep ? ' (глубокий)' : ''}.`;
  const found = s.found ? `Найдено окружений с OpenCRAVAT: ${s.found}.` : 'Других окружений с OpenCRAVAT не найдено.';
  const problems = s.errors.length
    ? el('details', {}, el('summary', { className: 'hint' }, `Не удалось проверить: ${s.errors.length}`),
      el('pre', { className: 'log', style: 'max-height:140px' }, s.errors.join('\n')))
    : null;
  box.replaceChildren(el('div', { className: 'head' }, el('b', {}, text), el('span', {}, found),
    el('span', { className: 'spacer' }),
    el('button', { className: 'btn sm ghost', type: 'button', onclick: () => { box.hidden = true; envUi.data.search.finished_at = null; } }, 'Скрыть')),
  ...(problems ? [problems] : []));
}

function envRow(env) {
  const data = envUi.data;
  const v = env.verdict || {};
  const facts = env.kind === 'data'
    ? [el('span', {}, 'Python не найден'), el('span', {}, `модулей: ${env.modules.count}`)]
    : [el('span', {}, `Python ${env.python_version}`), el('span', {}, `OpenCRAVAT ${env.opencravat}`), el('span', {}, `модулей: ${env.modules.count}`)];
  const chips = [];
  if (env.running_here) chips.push(el('span', { className: 'chip ok' }, data.server.state === 'running' ? 'работает' : 'запускается'));
  else if (env.id === data.chosen) chips.push(el('span', { className: 'chip ok' }, 'выбрано'));
  const job = data.jobs[env.id];
  if (job && job.state === 'running') chips.push(el('span', { className: 'chip info' }, job.action === 'install' ? 'установка…' : 'удаление…'));
  else if (env.kind !== 'builtin') chips.push(el('span', { className: `chip ${LEVEL_CHIP[v.level] || 'plain'}` },
    v.can_run ? 'готово' : v.can_install ? 'нужны модули ClinReport' : 'не подходит'));
  return el('button', {
    type: 'button', role: 'option', className: env.id === data.chosen ? 'env-row chosen' : 'env-row',
    'aria-selected': String(env.id === envUi.selected),
    onclick: () => { envUi.selected = env.id; envUi.confirm = null; renderEnvironments(); },
  }, el('span', { className: 'radio', 'aria-hidden': 'true' }),
  el('span', { className: 'name' }, env.name, el('span', { className: 'kind' }, KIND[env.kind] || env.kind)),
  el('span', { className: 'sub' }, facts),
  el('span', { className: 'state' }, chips));
}

function renderEnvDetail(env) {
  const data = envUi.data;
  const v = env.verdict || { level: 'ok', reasons: [] };
  const job = data.jobs[env.id];
  const jobRunning = Object.values(data.jobs).some((j) => j.state === 'running');
  const isChosen = env.id === data.chosen;
  const actions = [];
  if (isChosen) actions.push(el('button', { className: 'btn', type: 'button', disabled: true }, 'Выбрано'));
  else if (env.kind !== 'data') actions.push(el('button', {
    className: 'btn primary', type: 'button', disabled: !v.can_run || jobRunning,
    title: v.can_run ? '' : 'Сначала устраните то, что указано ниже',
    onclick: () => { envUi.confirm = 'use'; renderEnvironments(); },
  }, 'Использовать'));
  if (env.kind === 'data') actions.push(el('button', { className: 'btn primary', type: 'button', onclick: (e) => busy(e.currentTarget, async () => {
    const r = await call('env_add'); if (!r.cancelled) { envUi.selected = r.id; await loadEnvironments(true); }
  }) }, 'Указать Python…'));
  if (env.kind !== 'builtin' && env.kind !== 'data') actions.push(el('button', { className: 'btn ghost', type: 'button', onclick: (e) => busy(e.currentTarget, async () => {
    await call('env_refresh', env.id); delete envUi.details[env.id]; await loadEnvironments(true); toast('Сведения обновлены');
  }) }, 'Проверить заново'));
  if (env.kind !== 'builtin' && !isChosen) actions.push(el('button', { className: 'btn ghost', type: 'button', onclick: (e) => busy(e.currentTarget, async () => {
    await call('env_forget', env.id); envUi.selected = 'builtin'; await loadEnvironments(true); toast('Окружение убрано из списка; его файлы не тронуты');
  }) }, 'Убрать из списка'));

  const head = el('div', { className: 'env-head' },
    el('div', {},
      el('div', { className: 'title' }, env.running_here ? el('span', { className: 'dot running' }) : null, env.name,
        el('span', { className: 'kind' }, KIND[env.kind] || env.kind)),
      el('div', { className: 'facts' },
        env.python_version ? el('span', {}, 'Python ', el('b', {}, env.python_version)) : null,
        env.opencravat ? el('span', {}, 'OpenCRAVAT ', el('b', {}, env.opencravat)) : null,
        el('span', {}, 'модулей ', el('b', {}, env.modules.count)),
        env.package_count ? el('span', {}, 'пакетов ', el('b', {}, env.package_count)) : null,
        el('span', {}, 'найдено: ', el('b', {}, env.source || '—'))),
      el('p', { className: 'hint' }, KIND_WORDS[env.kind] || '')),
    el('div', { className: 'actions' }, actions),
    env.kind === 'builtin' ? null : el('div', { className: `verdict ${v.level}` },
      el('b', {}, v.summary),
      v.reasons.length ? el('ul', {}, v.reasons.map((r) => el('li', { className: r.level }, r.text))) : null),
    envUi.confirm === 'use' ? el('div', { className: 'confirm-box' },
      el('span', {}, `OpenCRAVAT остановится и запустится в окружении «${env.name}». Открытые в браузере результаты нужно будет открыть заново.`),
      el('button', { className: 'btn sm primary', type: 'button', onclick: (e) => busy(e.currentTarget, async () => {
        envUi.confirm = null;
        try { await call('env_use', env.id); toast(`OpenCRAVAT запускается в окружении «${env.name}»`); } finally { await loadEnvironments(true); refreshState(); }
      }) }, 'Переключить'),
      el('button', { className: 'btn sm ghost', type: 'button', onclick: () => { envUi.confirm = null; renderEnvironments(); } }, 'Отмена')) : null);

  $('env-detail').replaceChildren(head, modulesSection(env, job, jobRunning), proSection(env));
}

function modulesSection(env, job, jobRunning) {
  const data = envUi.data;
  const ours = env.modules.ours || {};
  const latest = data.bundled_version;
  const state = (version) => {
    if (!version) return el('span', { className: 'chip plain' }, 'не установлен');
    if (latest && version === latest) return el('span', { className: 'chip ok' }, 'актуальна');
    return el('span', { className: 'chip warn' }, `в программе ${latest}`);
  };
  const rows = [['clinreport', 'webapps', 'Окно заключения'], ['wgclinreport', 'webviewerwidgets', 'Кнопка на вкладке Summary']].map(([id, type, title]) =>
    el('tr', {}, el('td', {}, el('div', {}, title), el('div', { className: 'mono hint', style: 'margin:0' }, `${type}/${id}`)),
      el('td', { className: 'mono' }, ours[id] || '—'), el('td', {}, state(ours[id]))));
  const section = el('div', { className: 'env-section' }, el('h3', {}, 'Модули ClinReport в этом окружении'),
    el('table', { className: 'mods' }, el('thead', {}, el('tr', {}, el('th', {}, 'Модуль'), el('th', {}, 'Версия'), el('th', {}, 'Состояние'))), el('tbody', {}, rows)));

  if (env.kind === 'builtin') {
    section.append(el('p', { className: 'hint' }, 'Во встроенное окружение модули ставятся сами при каждом запуске.'));
    return section;
  }
  const v = env.verdict || {};
  const installed = ours.clinreport && ours.wgclinreport;
  const fresh = installed && ours.clinreport === latest;
  if (v.can_install) {
    const install = (source) => busy(null, async () => {
      envUi.confirm = null;
      const r = await call('env_install', env.id, source);
      if (!r.cancelled) await loadEnvironments(true);
    });
    const controls = el('div', { className: 'row', style: 'margin-top:10px' },
      el('button', { className: fresh ? 'btn' : 'btn primary', type: 'button', disabled: jobRunning,
        onclick: () => { envUi.confirm = 'install'; renderEnvironments(); } },
      fresh ? `Переустановить ${latest}` : installed ? `Обновить до ${latest}` : `Установить ${latest}`),
      el('button', { className: 'btn ghost', type: 'button', disabled: jobRunning, onclick: () => install('zip') }, 'Из файла .zip…'),
      installed ? el('button', { className: 'btn ghost danger', type: 'button', disabled: jobRunning || env.running_here,
        title: env.running_here ? 'Сначала переключитесь на другое окружение' : '',
        onclick: () => { envUi.confirm = 'remove'; renderEnvironments(); } }, 'Удалить модули') : null);
    section.append(controls);
    if (envUi.confirm === 'install') {
      const deps = (v.reasons || []).find((r) => r.text.startsWith('При установке'));
      section.append(el('div', { className: 'confirm-box', style: 'margin-top:10px' },
        el('span', {}, `В папку ${env.modules_dir} будут записаны модули ClinReport ${latest} (webapps/clinreport и webviewerwidgets/wgclinreport).`
          + (installed ? ' Прежние сохранятся в резервной копии.' : '') + (deps ? ' ' + deps.text : ' Пакеты Python этого окружения не меняются.')
          + (env.running_here ? ' OpenCRAVAT перезапустится.' : '')),
        el('button', { className: 'btn sm primary', type: 'button', onclick: () => install('bundle') }, 'Установить'),
        el('button', { className: 'btn sm ghost', type: 'button', onclick: () => { envUi.confirm = null; renderEnvironments(); } }, 'Отмена')));
    }
    if (envUi.confirm === 'remove') {
      section.append(el('div', { className: 'confirm-box', style: 'margin-top:10px' },
        el('span', {}, `Папки webapps/clinreport и webviewerwidgets/wgclinreport будут убраны из ${env.modules_dir} (копия сохранится в папке данных ClinReport). Остальные модули и задания не трогаются.`),
        el('button', { className: 'btn sm danger', type: 'button', onclick: (e) => busy(e.currentTarget, async () => {
          envUi.confirm = null; await call('env_remove', env.id); await loadEnvironments(true);
        }) }, 'Удалить'),
        el('button', { className: 'btn sm ghost', type: 'button', onclick: () => { envUi.confirm = null; renderEnvironments(); } }, 'Отмена')));
    }
  } else if (env.kind !== 'data') {
    section.append(el('p', { className: 'hint' }, 'Установить модули ClinReport сюда нельзя — причины указаны выше.'));
  }
  if (job) {
    const title = job.state === 'running' ? (job.action === 'install' ? 'Установка…' : 'Удаление…')
      : job.state === 'done' ? 'Готово' : 'Не получилось — ничего не изменено';
    section.append(el('div', { className: 'job' },
      job.state === 'running' ? el('div', { className: 'bar busy' }, el('i')) : null,
      el('b', {}, title), el('ol', {}, job.steps.map((s) => el('li', {}, s))),
      job.error ? el('div', { className: 'err' }, job.error) : null));
  }
  return section;
}

function proSection(env) {
  const tabs = [['paths', 'Пути и настройки'], ['pkgs', `Пакеты Python${env.package_count ? ` (${env.package_count})` : ''}`], ['mods', 'Модули OpenCRAVAT'], ['run', 'Запуск']];
  const box = el('div', {});
  const pro = el('details', { className: 'pro env-section', open: envUi.proOpen || null,
    ontoggle: (e) => { envUi.proOpen = e.currentTarget.open; if (envUi.proOpen) fillPro(env, box); } },
  el('summary', {}, 'Для специалистов', el('small', {}, 'пути, пакеты, модули OpenCRAVAT, команда запуска')),
  el('div', { className: 'seg', role: 'tablist' }, tabs.map(([id, label]) => el('button', {
    type: 'button', role: 'tab', 'aria-selected': String(envUi.pro === id),
    onclick: () => { envUi.pro = id; renderEnvironments(); },
  }, label))), box);
  if (envUi.proOpen) fillPro(env, box);
  return pro;
}

async function fillPro(env, box) {
  if (envUi.pro === 'paths') {
    const rows = [
      ['Python', 'интерпретатор', env.python], ['Команда oc', 'oc', env.oc_command], ['Пакет OpenCRAVAT', 'package_path', env.package_path],
      ['Настройки OpenCRAVAT', 'cravat-system.yml', env.conf_exists ? env.conf_path : null], ['Папка настроек', 'conf_dir', env.conf_dir],
      ['Модули', 'modules_dir', env.modules_dir], ['Задания', 'jobs_dir', env.jobs_dir], ['Рабочая папка', 'work_dir', env.work_dir],
      ['Журналы', 'log_dir', env.log_dir], ['Пакеты из Store', 'python-packages', env.user_packages],
    ].filter(([, , path]) => path !== undefined);
    box.replaceChildren(el('dl', { className: 'paths' }, rows.flatMap(([label, key, path]) => [
      el('dt', {}, label, el('small', {}, key)),
      el('dd', {}, path ? el('span', { className: 'mono' }, path) : el('span', { className: 'hint', style: 'margin:0' }, 'нет')),
      el('div', { className: 'acts' }, path ? el('button', { className: 'btn sm ghost', type: 'button', onclick: () => busy(null, () => call('open_path', path)) }, 'Показать') : null),
    ])));
    return;
  }
  if (envUi.pro === 'mods') {
    const types = Object.entries(env.modules.types || {});
    box.replaceChildren(types.length
      ? el('div', { className: 'mtypes' }, types.map(([t, n]) => el('div', { className: 'mtype' }, el('b', {}, n), t)))
      : el('p', { className: 'empty' }, 'Модулей нет.'),
    ...(env.kind !== 'builtin' && !env.modules.wgnote ? [el('p', { className: 'hint' }, 'Нет wgnote: колонку Note заполнять нельзя.')] : []));
    return;
  }
  if (envUi.pro === 'run') {
    const command = env.kind === 'builtin'
      ? `"${env.oc_command}" gui --headless --port <порт>\nOPENCRAVAT_SYSTEM_CONF_PATH=${env.conf_path}`
      : env.python ? `"${env.python}" -c "from cravat.oc import main; …" gui --headless --port <порт>\nCLINREPORT_CONF_DIR=<папка данных ClinReport>\\conf  (общие шаблоны и настройки)\nНастройки и модули этого OpenCRAVAT не меняются.` : 'Python не указан.';
    box.replaceChildren(el('pre', { className: 'log', style: 'max-height:none' }, command));
    return;
  }
  if (!envUi.details[env.id]) {
    box.replaceChildren(el('p', { className: 'empty' }, 'Загрузка…'));
    try { envUi.details[env.id] = await call('env_details', env.id); } catch (error) { box.replaceChildren(el('p', { className: 'empty' }, error.message)); return; }
  }
  const packages = envUi.details[env.id].packages || [];
  const draw = () => {
    const q = envUi.pkgQuery.trim().toLowerCase();
    const shown = packages.filter((p) => !q || p.name.includes(q));
    table.replaceChildren(...(shown.length ? shown.map((p) => el('tr', {}, el('td', {}, p.name), el('td', { className: 'v' }, p.version)))
      : [el('tr', {}, el('td', { className: 'hint' }, 'Ничего не найдено'))]));
  };
  const table = el('tbody');
  const search = el('input', { type: 'search', id: 'env-pkg-q', placeholder: 'Найти пакет', value: envUi.pkgQuery, 'aria-label': 'Найти пакет',
    oninput: (e) => { envUi.pkgQuery = e.target.value; draw(); } });
  const copy = el('button', { className: 'btn sm ghost', type: 'button', onclick: async () => {
    const text = packages.map((p) => `${p.name}==${p.version}`).join('\n');
    try { await navigator.clipboard.writeText(text); toast('Скопировано как requirements.txt'); } catch (e) { notify('err', 'Не удалось скопировать'); }
  } }, 'Копировать как requirements.txt');
  box.replaceChildren(el('div', { className: 'row', style: 'margin-bottom:8px' }, search, copy),
    el('div', { className: 'pk-scroll' }, el('table', { className: 'pk' }, table)));
  draw();
}

// --- log ---

async function loadLog() {
  let data;
  try { data = await call('log'); } catch (error) { return; }
  const lines = data.lines.map((line) => {
    const m = line.match(/^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) (\w+) (.*)$/);
    if (!m) return el('span', {}, line + '\n');
    const today = new Date().toISOString().slice(0, 10) === m[1];
    const cls = m[3] === 'WARNING' ? 'w' : (m[3] === 'ERROR' || m[3] === 'CRITICAL') ? 'e' : '';
    const label = cls === 'w' ? 'ВНИМАНИЕ  ' : cls === 'e' ? 'ОШИБКА  ' : '';
    return [el('span', { className: 't' }, (today ? m[2] : `${m[1]} ${m[2]}`) + '  '), el('span', { className: cls }, label + m[4] + '\n')];
  });
  const box = $('log');
  const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 20;
  box.replaceChildren(...lines.flat());
  if (atBottom) box.scrollTop = box.scrollHeight;
  $('server-log').textContent = data.server || '(пусто)';
  const problems = data.lines.filter((l) => / (WARNING|ERROR|CRITICAL) /.test(l)).length;
  $('log-count').textContent = problems ? `${problems} ⚠` : '';
  $('log-count').className = problems ? 'count warn' : 'count';
}

async function copyDiagnostics() {
  const { text } = await call('diagnostics');
  try {
    await navigator.clipboard.writeText(text);
    toast('Диагностика скопирована');
  } catch (e) {
    const area = $('diag-text');
    area.value = text;
    area.select();
    document.execCommand('copy');
    toast('Диагностика скопирована');
  }
}

// --- wiring ---

function init() {
  TABS.forEach((t) => $('tab-' + t).addEventListener('click', () => show(t)));
  $('open-result').addEventListener('click', (e) => busy(e.currentTarget, async () => { queuedToast(await call('choose_result')); refreshState(); loadRecent(); }).then(renderControls));
  $('open-oc').addEventListener('click', (e) => busy(e.currentTarget, () => call('open_oc')).then(renderControls));
  $('toggle-server').addEventListener('click', () => {
    const s = last && last.server.state;
    serverAction(s === 'running' || s === 'starting' ? 'stop' : 'start');
  });
  $('add-tpl').addEventListener('click', (e) => busy(e.currentTarget, startAdd));
  $('add-cancel').addEventListener('click', () => { $('add-form').hidden = true; tpl.adding = null; });
  $('add-form').addEventListener('submit', (e) => { e.preventDefault(); busy($('add-submit'), submitAdd); });
  $('sample-tpl').addEventListener('click', (e) => busy(e.currentTarget, async () => {
    const r = await call('template_save', 'DZM'); if (!r.cancelled) toast(`Образец сохранён: ${r.path}`);
  }));
  $('fields-tpl').addEventListener('click', (e) => busy(e.currentTarget, toggleFields));
  $('tpl-folder').addEventListener('click', () => busy(null, () => call('open_templates_folder')));
  $('settings-form').addEventListener('submit', (e) => { e.preventDefault(); busy($('settings-save'), saveSettings); });
  $('settings-reset').addEventListener('click', () => loadSettings());
  $('ru-refresh').addEventListener('click', (e) => busy(e.currentTarget, async () => {
    const ru = await call('ru_refresh'); await refreshState(); renderRu();
    toast(ru.state === 'ok' ? 'Аннотации обновлены' : 'Не удалось загрузить аннотации');
  }));
  $('open-data').addEventListener('click', () => busy(null, () => call('open_data_folder')));
  $('open-logs').addEventListener('click', () => busy(null, () => call('open_logs_folder')));
  $('copy-diag').addEventListener('click', (e) => busy(e.currentTarget, copyDiagnostics));
  $('env-search').addEventListener('click', (e) => busy(e.currentTarget, () => startSearch(false)));
  $('env-search-deep').addEventListener('click', (e) => busy(e.currentTarget, () => startSearch(true)));
  $('env-add').addEventListener('click', (e) => busy(e.currentTarget, async () => {
    const r = await call('env_add');
    if (!r.cancelled) { envUi.selected = r.id; toast('Окружение добавлено'); await loadEnvironments(true); }
  }));

  refreshState().then(loadRecent);
  setInterval(refreshState, 1000);
  setInterval(() => { if (currentTab === 'log') loadLog(); }, 3000);
  setInterval(() => { if (currentTab === 'environments' || envBusy()) loadEnvironments(); }, 1000);
  setInterval(() => { if (currentTab === 'overview') loadRecent(); }, 15000);
  let wasRunning = false;
  setInterval(() => {  // re-enable the recent buttons as soon as the server is up
    const running = last && last.server.state === 'running';
    if (running !== wasRunning) { wasRunning = running; loadRecent(); }
  }, 1000);
  window.clinreportLog('ready', 'init done');
}

if (window.pywebview && window.pywebview.api) init();
else window.addEventListener('pywebviewready', init, { once: true });
