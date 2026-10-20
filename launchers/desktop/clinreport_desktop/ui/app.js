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

const TABS = ['overview', 'templates', 'settings', 'log'];
let currentTab = 'overview';
function show(name) {
  currentTab = name;
  for (const t of TABS) {
    $('tab-' + t).setAttribute('aria-selected', String(t === name));
    $('p-' + t).hidden = t !== name;
  }
  if (name === 'templates') loadTemplates();
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

async function refreshState() {
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
  } else if (s.state === 'starting') {
    meta.push(el('span', {}, 'Первый запуск после установки или обновления занимает до минуты.'));
  }
  $('hero-meta').replaceChildren(...meta);
  $('hero-error').hidden = s.state !== 'failed';
  $('hero-error').textContent = s.error || '';

  const running = s.state === 'running';
  $('open-result').disabled = !running;
  $('open-oc').disabled = !running;
  const toggle = $('toggle-server');
  toggle.textContent = running || s.state === 'starting' ? 'Остановить' : 'Запустить';
  toggle.className = running || s.state === 'starting' ? 'btn ghost danger' : 'btn primary';
  toggle.disabled = s.state === 'stopping';

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
    el('dt', {}, 'ClinReport'), el('dd', {}, v.app, updateChip),
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

async function loadRecent() {
  const box = $('recent');
  let data;
  try { data = await call('recent'); } catch (error) { box.replaceChildren(el('p', { className: 'empty' }, error.message)); return; }
  if (!data.items.length) {
    box.replaceChildren(el('p', { className: 'empty' },
      'Здесь появятся открытые файлы. Нажмите «Открыть результат…» и выберите .sqlite из OpenCRAVAT.'));
    return;
  }
  const running = last && last.server.state === 'running';
  box.replaceChildren(...data.items.map((r) => {
    const acts = r.exists ? [
      el('button', { className: 'btn sm', type: 'button', disabled: !running, onclick: (e) => busy(e.currentTarget, async () => { await call('open_result', r.path, 'viewer'); loadRecent(); }) }, 'Просмотр'),
      el('button', { className: 'btn sm primary', type: 'button', disabled: !running, onclick: (e) => busy(e.currentTarget, async () => { await call('open_result', r.path, 'report'); loadRecent(); }) }, 'Заключение'),
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
    $('s-browser').checked = Boolean(s.launcher.open_browser);
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
    open_browser: $('s-browser').checked, autostart: $('s-autostart').checked,
    update_prerelease: $('s-prerelease').checked,
    port_mode: $('s-port-fixed').checked ? 'fixed' : 'auto', port: Number($('s-port-value').value) || 8080,
  };
  const result = await call('save_settings', report, launcher);
  toast('Настройки сохранены');
  if (result.restart_needed) notify('warn', 'Новый порт начнёт действовать после перезапуска сервера (кнопки «Остановить» → «Запустить»).');
  refreshState();
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
  $('open-result').addEventListener('click', (e) => busy(e.currentTarget, async () => { await call('choose_result'); loadRecent(); }));
  $('open-oc').addEventListener('click', (e) => busy(e.currentTarget, () => call('open_oc')));
  $('toggle-server').addEventListener('click', (e) => busy(e.currentTarget, async () => {
    const s = last && last.server.state;
    await call(s === 'running' || s === 'starting' ? 'stop' : 'start');
    refreshState();
  }));
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

  refreshState().then(loadRecent);
  setInterval(refreshState, 1000);
  setInterval(() => { if (currentTab === 'log') loadLog(); }, 3000);
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
