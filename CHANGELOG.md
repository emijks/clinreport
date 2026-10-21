# Changelog

All notable changes to ClinReport. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/). The section of a version is used as its GitHub release notes.

## [Unreleased]

### Added

- **A log file for every launch** of the desktop app (`logs/sessions`, the last 20): system and WebKit/WebView2 versions,
  errors of the window page and of background tasks, crashes, and output that was lost when the app was started from
  Finder. On macOS the logs moved to `~/Library/Logs/ClinReport` (visible in Console).

### Changed

- **The browser no longer opens by itself** when ClinReport starts (or is started again while running). «Открыть»
  opens OpenCRAVAT when you need it; the old setting is reset to off on update.
- **Clearer server buttons** on «Обзор»: blue «Открыть» (available while OpenCRAVAT runs) and one server button —
  red «Остановить» while it runs or starts, green «Запустить» when it is stopped. «Открыть результат…» moved to the «Недавние результаты» card.

### Fixed

- «Остановить» while OpenCRAVAT was still starting could leave it running in the background.
- **Empty ClinReport window on macOS older than 11.3** (e.g. 10.15 Catalina): the window library asked WebKit for a
  feature these systems lack, and the page was never loaded.
- The window could show another program's page on Windows (or stay empty on macOS) when that program used port 42001.
  The window no longer needs a port at all.
- The window works on macOS 10.15 with the Safari it shipped with (13).

## [3.0.0] - unreleased

ClinReport becomes an OpenCRAVAT extension with a desktop app around it. Reports are made in OpenCRAVAT itself: mark
variants in the Note column, open the review window from the Summary tab, edit, save the `.docx`.

### Added

- **Desktop app for Windows and macOS** with OpenCRAVAT 3.2.3 and Python 3.13 inside: nothing else to install, no
  administrator rights. A control window shows whether OpenCRAVAT is running, opens results, manages templates and
  settings and keeps a log.
- **Review window in OpenCRAVAT** (webapp `clinreport` + Summary-tab widget `wgclinreport`): process standard or LPWGS,
  edit every section, pick the template, save.
- **The lab's own report templates** («Шаблоны»): add a `.docx`, checked against an example report.
- **Updates from inside the app**: «обновить до X» downloads and installs the new version on Windows (settings, templates
  and jobs are kept); macOS opens the release page. Pre-releases only when enabled in Настройки.
- **Extension installer** (`install_extension.py`) for an existing OpenCRAVAT, and a release zip with it.
- **Command line**: modes `default`, `lpwgs`, `10x`, any template, `--list-templates`.
- Builds for macOS 10.15+ (Intel) and 11+ (Apple Silicon); CI on Linux, Windows and macOS for every push.

### Changed

- The installer closes a running ClinReport itself instead of listing its "Python" processes, and says whether it
  installs or updates (from which version).
- Settings and templates are stored in the OpenCRAVAT conf dir / the user's data folder instead of next to the program.
- One version number for the app and its OpenCRAVAT modules.

### Removed

- The Tk desktop app (`app.py`, `ui/`) and its PyInstaller build; `config.json` next to the executable.

## [2.2] - 2026-07-26

Last release of the Tk desktop app. Earlier versions: 2.1 (2026-04-07), 2.0 (2025-06-03), 1.1 (2025-04-28),
1.0 (2025-04-27); see the git history.
