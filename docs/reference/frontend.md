# Frontend

Two independent pieces of browser code, no build step, no external libraries.

## Review page — `modules/webapps/clinreport/{index.html, static/app.js, static/app.css}`

Served statically at `/webapps/clinreport/index.html`; all API calls use **relative URLs** (`fetch('process')` →
`/webapps/clinreport/process`), so the page works under any host/port.

### URL parameters

`?dbpath=<path>&job_id=<id>&username=<u>` (set by the widget). Without `dbpath`/`job_id` the page shows the
«Файл результата» card with a path field (for `oc gui --webapp clinreport`).

### Markup (index.html)

| Element | Purpose |
|---|---|
| `header.topbar` | title, `#file-name` (tooltip = full path), `#settings-btn` |
| `#notices` | stacked banners: `ok` (auto-dismiss 6 s), `warn`/`err` (sticky, e.g. Russian-annotation warning) |
| `#open-card` | path field when opened without a result |
| `#process-card` | `#target` select, `#process-btn`, `#process-lpwgs-btn`, `#clinician-line`, Note-code hint |
| `#reports` → `#tabs`, `#panels` | one tab per report; only the active panel is in the DOM |
| `dialog#settings-dialog` | form with inputs named exactly like the settings keys |
| `dialog#similar-dialog`, `dialog#error-dialog` | «Похожие» table; error message + collapsible traceback |

### State (`app.js`)

```js
state = {
  source,      // {dbpath} | {job_id, username} from the URL or the path field
  dbpath,      // resolved absolute path returned by `open` (later calls use it, unless the page was opened by job_id —
               //   then job_id again, because login mode accepts nothing else: sourceParams())
  settings,    // the user's settings + db_configured/username/multiuser (nothing else about the DB)
  reports,     // from `process`: [{label, kind, is_target, filename, context, template?}]
  layouts,     // from `process`: labels.LAYOUTS
  activeTab,   // index into reports
}
```

**Edits mutate `report.context` in place** (input/textarea listeners). Nothing is sent until save/upload.
`report.template` remembers the template choice per tab. Switching tabs re-renders the panel from `report.context`,
so edits survive tab switches but the yellow "edited" highlight does not (it compares with the value at render time).
Re-processing replaces `state.reports` → **all edits are discarded** without warning ([issue 006](../issues/clinreport/006-reprocess-discards-edits.md)).

### Rendering

`renderReports()` → tabs + `renderPanel(report)`:

1. action row: template `<select>` (only if the layout has >1 template), «Сохранить как…», «Выгрузить в базу»
   (only if `layout.upload`; disabled without a server DB connection), date/kind label;
2. common fields: `layout.common` → labelled `<input>`s bound to `context[section][key]`;
3. one section per `layout.tables`: title + count, or «Нет вариантов», or a table of `<textarea>` cells bound to
   `context[table.key][row][field]`, plus a «Похожие» button per row if `layout.similar`.

Cells get CSS classes `col-<field>` (e.g. `col-gene` is italic, `col-variation` monospace). Textareas auto-grow
(`autosize`) — **must run while the panel is visible**, hence `$('reports').hidden = false` before `renderReports()`
and the `requestAnimationFrame` (a hidden element has `scrollHeight` 0; this bug existed and was fixed).

### Flows

- **Process**: `busy(button, …)` disables the button and shows a spinner; `POST process` → state → render; warnings → sticky banners.
- **Save** (`saveReport`):
  1. `showSaveFilePicker({suggestedName: report.filename, types: .docx})` **first**, while the click still counts as a user
     gesture (the gesture expires after a few seconds, so the picker cannot come after the network call);
     `AbortError` (user cancelled) → stop; picker missing/other error → fallback;
  2. `POST render` → Blob;
  3. write via the file handle, or fallback: `<a download>` with `report.filename`;
  4. if `kind === 'default'` and `settings.auto_upload` and `db_configured` → `uploadReport(report, {quiet: true})`.
  The picker exists in Edge/Chrome on `localhost` (secure context); Firefox always downloads.
- **Upload** (`uploadReport`): `POST upload`; on `{duplicate}` → `confirm("Для образца … Записать ещё?")` → `POST upload {force: true}`.
- **Similar**: `POST similar {variant: row}` → modal table (or "no rows" text).
- **Settings**: `GET settings` fills the form (checkbox for `auto_upload`, select for the default `template`), submit →
  `POST settings` → updates `#clinician-line` and re-renders the panel (enables/disables DB buttons). The clinician name is
  applied at the next «Обработать»; the default template preselects the template picker of new report tabs.
  There are no database fields: the connection is the server's. Without one (`db_configured` false) the auto-upload
  checkbox is hidden and «Выгрузить в базу» / «Похожие» are disabled with the tooltip «База данных не подключена на сервере».
  In login mode the dialog and `#clinician-line` show the logged-in user.
- **Errors**: every server error → `RequestError(message, trace)` → `#error-dialog`. Network failure →
  «Нет связи с сервером OpenCRAVAT. Запущен ли oc gui?».

### Style

`app.css` defines tokens on `:root` (`--accent`, `--border`, …), light theme only (the OpenCRAVAT viewer has no dark mode),
responsive below 700 px. System font stack (Segoe UI on Windows).

Favicon: `static/favicon.svg` (report sheet in `--accent` blue, so the tab is distinguishable from the viewer's), with
OpenCRAVAT's `/submit/logo_transparent.png` as the PNG fallback for browsers without SVG favicons. Do not use
`/result/favicon.ico` — it is a leftover "?" icon that OpenCRAVAT itself no longer uses.

## Viewer widget — `modules/webviewerwidgets/wgclinreport/wgclinreport.js`

```js
widgetGenerators['clinreport'] = { info: { name, width: 380, height: 170, function(div) { … } } };
```

- Key `info` = Summary tab ([opencravat-integration](../reference/opencravat-integration.md#result-viewer-and-widgets)); shown for every result because
  `required_annotator: base`.
- Builds `/webapps/clinreport/index.html?dbpath=&job_id=&username=` from the viewer globals (guarded with `typeof`),
  renders a hint paragraph and a button (`class="butn"`, the viewer's button style) that `window.open`s the URL.
- Sets the card font to the viewer's Roboto (the widget card otherwise inherits a serif font).
- The viewer loads it with `$.getScript`; after editing, **hard-reload** the viewer (the browser caches the script).

## Changing UI text

All user-visible strings are Russian and live in `index.html`, `app.js` (messages, button labels) and — for column
titles/section titles — `clinreport_core/labels.py`. Keep the wording clinicians know from the Tk app (its
windows are in the git history before 3.0, `ui/*.py`).
